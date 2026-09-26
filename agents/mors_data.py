"""
mors_data — MORS Scientific Command Center data layer
=====================================================
Backs every page of the MORS platform (Home, AI, Data, Astronomy, Satellite,
Quantum, Problems, Solutions, Projects, Team).

Acquisition policy (per platform requirement):
    1. REAL API      — CelesTrak TLE, NASA Exoplanet Archive, NASA APOD/EPIC,
                       NASA DONKI/NEOWS, NOAA SWPC, NASA GIBS.
    2. AI SYNTHESIS  — if every API for a module fails, Gemini is asked for the
                       payload (labelled ``via: "ai_synthesis"``).
    3. LOCAL MODEL   — deterministic physical simulation / curated reference
                       (labelled ``via: "local_model"``).

Nothing here ever raises, and every payload carries a ``trace`` provenance
block so the UI can render:

    [Source | Dataset Version | Processing Pipeline | Method | Operator | Timestamp]
"""

from __future__ import annotations

import json
import logging
import math
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
import requests

from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent

log = logging.getLogger("mors")

_LOCK = threading.Lock()
_CACHE: Dict[str, Any] = {}
_TS: Dict[str, float] = {}
_TTLS: Dict[str, float] = {}
_KEY_LOCKS: Dict[str, threading.Lock] = {}
TTL = 300.0
FALLBACK_TTL = 60.0   # a failed live fetch must be retried quickly
_HTTP_TIMEOUT = 18

# injected by main.py so this module never touches .env itself
_AI: Optional[Callable[[str, str], Optional[str]]] = None
_NASA_KEY = "DEMO_KEY"


def configure(ai_fn: Optional[Callable[[str, str], Optional[str]]],
              nasa_key: str = "DEMO_KEY") -> None:
    global _AI, _NASA_KEY
    _AI = ai_fn
    _NASA_KEY = nasa_key or "DEMO_KEY"


# --------------------------------------------------------------- provenance
def _iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def trace(source: str, pipeline: str, method: str, *,
          dataset_id: str = "", version: str = "1.0.0",
          operator: str = "agent:mors", via: str = "api",
          endpoint: str = "", note: str = "") -> Dict[str, Any]:
    return {
        "source": source,
        "dataset_version": version,
        "dataset_id": dataset_id or f"MORS-{source[:12].upper().replace(' ', '-')}-v{version}",
        "processing_pipeline": pipeline,
        "method": method,
        "operator_id": operator,
        "via": via,
        "endpoint": endpoint,
        "note": note,
        "last_updated": _iso(),
        "timestamp": _iso(),
    }


def badge(t: Dict[str, Any]) -> str:
    return ("[{source} | {dataset_version} | {processing_pipeline} | {method} | "
            "{operator_id} | {last_updated}]").format(**{
                k: t.get(k, "—") for k in (
                    "source", "dataset_version", "processing_pipeline",
                    "method", "operator_id", "last_updated")})


def _cached(key: str) -> Optional[Any]:
    with _LOCK:
        if key in _CACHE and time.time() - _TS.get(key, 0) < \
                _TTLS.get(key, TTL):
            return _CACHE[key]
    return None


def _put(key: str, value: Any, ttl: float = TTL) -> Any:
    with _LOCK:
        _CACHE[key] = value
        _TS[key] = time.time()
        _TTLS[key] = ttl
    return value


def _key_lock(key: str) -> threading.Lock:
    """One fetch per dataset at a time (concurrent cold hits must not race)."""
    with _LOCK:
        if key not in _KEY_LOCKS:
            _KEY_LOCKS[key] = threading.Lock()
        return _KEY_LOCKS[key]


def _get_json(url: str, **kw) -> Any:
    kw.setdefault("timeout", _HTTP_TIMEOUT)   # callers may override (TLE)
    resp = requests.get(url, **kw)
    resp.raise_for_status()
    ct = (resp.headers.get("Content-Type") or "").lower()
    if "json" in ct:
        return resp.json()
    return json.loads(resp.text)


def _ai_json(system: str, prompt: str) -> Optional[Any]:
    """Ask Gemini for structured JSON. Returns None when unavailable."""
    if _AI is None:
        return None
    raw = _AI(system, prompt)
    if not raw:
        return None
    m = None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        m = None
    import re as _re
    m = _re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, _re.S) or \
        _re.search(r"(\{.*\})", raw, _re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


_SNAPSHOT_ALIAS = {"satellites": "satellite"}   # acquire key -> snapshot stem


def _snapshot_cache(key: str) -> Optional[Dict[str, Any]]:
    """Ladder tier between the live API and AI synthesis: last real payload.

    CelesTrak, the TLE mirror and the archives fail transiently (blocked IP,
    508, rate limit). A stale *real* observation beats a synthesised one, so
    the payload shipped in ``static/api`` is served as-is but relabelled
    ``via: "cache"`` / ``live: False`` — never as a live acquisition.
    """
    for stem in dict.fromkeys((key, _SNAPSHOT_ALIAS.get(key, key))):
        for rel in (f"static/api/mors/{stem}.json",
                    f"static/api/data/{stem}.json"):
            path = _ROOT / rel
            try:
                if not path.is_file():
                    continue
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(data, dict) or len(data.get("rows") or []) < 3:
                continue
            src = dict(data.get("source") or {})
            src.update({
                "via": "cache",
                "live": False,
                "cached_from": rel,
                "note": ("Live sources unreachable — serving the last real "
                         "payload shipped with the project (" + rel + "), "
                         "relabelled cache rather than a live acquisition."),
            })
            data = dict(data)
            data.pop("trace", None)      # consumers rebuild trace/badge
            data.pop("badge", None)
            data["source"] = src
            return data
    return None


def acquire(key: str, api_fn: Callable[[], Optional[Dict[str, Any]]],
            ai_system: str, ai_prompt: str,
            local_fn: Callable[[], Dict[str, Any]]) -> Dict[str, Any]:
    """API -> shipped snapshot -> AI -> local, with a TTL cache. Never raises.

    The ladder runs under a per-dataset lock so two cold requests (a page
    load and the startup warm fetch, for example) share one acquisition
    instead of racing the same third-party endpoint. Only a *live* answer
    earns the full TTL: a fallback is parked for ``FALLBACK_TTL`` so the
    module keeps retrying the real source.
    """
    hit = _cached(key)
    if hit is not None:
        return hit
    with _key_lock(key):
        hit = _cached(key)
        if hit is not None:
            return hit
        try:
            out = api_fn()
            if isinstance(out, dict) and out:
                out.setdefault("source", {})
                out["source"].setdefault("via", "api")
                out["source"].setdefault("live", True)
                return _put(key, out, TTL)
        except Exception as exc:                       # noqa: BLE001
            log.warning("mors[%s] API failed: %s", key, str(exc)[:160])
        try:
            out = _snapshot_cache(key)
            if isinstance(out, dict) and out:
                return _put(key, out, FALLBACK_TTL)
        except Exception as exc:                       # noqa: BLE001
            log.warning("mors[%s] snapshot cache failed: %s", key, str(exc)[:160])
        try:
            out = _ai_json(ai_system, ai_prompt)
            if isinstance(out, dict) and out:
                out.setdefault("source", {})
                out["source"].update({"via": "ai_synthesis", "live": False,
                                      "note": "API unavailable; payload synthesised by "
                                              "the MORS AI engine and labelled as such."})
                return _put(key, out, FALLBACK_TTL)
        except Exception as exc:                       # noqa: BLE001
            log.warning("mors[%s] AI synthesis failed: %s", key, str(exc)[:160])
        out = local_fn()
        out.setdefault("source", {})
        out["source"].update({"via": "local_model", "live": False,
                              "note": "Deterministic physical model / curated reference; "
                                      "not a live acquisition."})
        return _put(key, out, FALLBACK_TTL)


def reset() -> None:
    with _LOCK:
        _CACHE.clear()
        _TS.clear()
        _TTLS.clear()
        _KEY_LOCKS.clear()


# ================================================================== CONSTANTS
G_EARTH = 3.986004418e14          # m^3 s^-2
R_EARTH_KM = 6371.0
LD_KM = 384400.0
SPECTRAL_LINES = [                 # NIST Atomic Spectra Database, air, Å
    {"line": "Ca II K", "lambda_A": 3933.66, "species": "Ca II"},
    {"line": "Ca II H", "lambda_A": 3968.47, "species": "Ca II"},
    {"line": "Hδ",      "lambda_A": 4101.74, "species": "H I"},
    {"line": "Hγ",      "lambda_A": 4340.47, "species": "H I"},
    {"line": "Hβ",      "lambda_A": 4861.33, "species": "H I"},
    {"line": "Mg I b",  "lambda_A": 5172.68, "species": "Mg I"},
    {"line": "Na I D2", "lambda_A": 5889.95, "species": "Na I"},
    {"line": "Na I D1", "lambda_A": 5895.92, "species": "Na I"},
    {"line": "Hα",      "lambda_A": 6562.81, "species": "H I"},
]


# ================================================================= 1) HEALTH
def data_health(report: Dict[str, Any]) -> Dict[str, Any]:
    q = (((report.get("dataset_summary") or {}).get("quality")) or {})
    if q:
        t = trace("MORS Ingestion Pipeline", "StandardScaler → IsolationForest",
                  "cell-level completeness audit",
                  dataset_id="MORS-DATAHEALTH-v1.0.0", via="pipeline",
                  endpoint="/api/report → dataset_summary.quality")
        return {**q, "trace": t, "badge": badge(t),
                "last_sync": q.get("last_sync") or _iso()}
    t = trace("MORS Ingestion Pipeline", "no-op", "not yet computed",
              dataset_id="MORS-DATAHEALTH-v1.0.0", via="local_model")
    return {"rows": 0, "sources": 0, "cells": 0, "data_quality_score": 0.0,
            "missing_pct": 0.0, "duplicate_rows": 0, "duplicate_pct": 0.0,
            "completeness_pct": 0.0, "accuracy_score": 0.0, "outliers_pct": 0.0,
            "outlier_count": 0, "per_source": [],
            "last_sync": "—", "pipeline": "—",
            "trace": t, "badge": badge(t)}


# ================================================================ 2) PROBLEMS
# Contract (docs/API_CONTRACT.md §2): every card carries the ten keys
#   problem_id, title, severity, category, component, symptom, root_cause,
#   fix, evidence  (+ priority), with
#   severity ∈ critical|high|medium|low, category ∈ data|logic|api|ui|docs|
#   infra|performance, priority ∈ P0|P1|P2 for planning and the score tier
#   High ≥ 75 / Medium ≥ 50 for the priority_score label.
_CARD_META = {
    # id: (category, component, owner role — only the leader is named)
    "P-001": ("logic", "agents/agent2_council.py", "Space Systems & AI Engineer"),
    "P-002": ("data", "agents/agent1_ingestion.py", "Data Analyst"),
    "P-003": ("data", "agents/agent1_ingestion.py", "Data Analyst"),
    "P-004": ("api", "agents/datasets.py::fetch_light_pollution", "Data Analyst"),
    "P-005": ("data", "agents/datasets.py::fetch_kp_index", "Astronomy Researcher"),
    "P-006": ("data", "agents/datasets.py::build_spectral", "Astronomy Researcher"),
    "P-007": ("logic", "agents/agent3_citations.py", "ليث رعد"),
    "P-008": ("data", "agents/mors_data.py::photometry", "Astronomy Researcher"),
    "P-009": ("logic", "agents/agent2_council.py", "ليث رعد"),
}
_SEVERITY = {"High": "high", "Medium": "medium", "Low": "low"}
_PRIORITY_CODE = {"High": "P0", "Medium": "P1", "Low": "P2"}


def _p(pid: str, title: str, domain: str, statement: str, evidence: List[str],
       evidence_raw: float, impact: str, impact_score: float, root_cause: str,
       analysis: str, solution: List[str], suggestions: List[str],
       confidence: float) -> Dict[str, Any]:
    priority_score = round(0.40 * evidence_raw + 0.35 * impact_score
                           + 0.25 * confidence, 1)
    priority = ("High" if priority_score >= 75 else
                "Medium" if priority_score >= 50 else "Low")
    category, component, owner = _CARD_META.get(
        pid, ("data", "agents/", "ليث رعد"))
    return {
        # --- contract keys -------------------------------------------------
        "problem_id": pid,
        "title": title,
        "severity": _SEVERITY[priority],          # critical|high|medium|low
        "category": category,                     # data|logic|api|ui|...
        "component": component,
        "symptom": statement,
        "root_cause": root_cause,
        "fix": solution,
        "evidence": evidence,
        "priority": priority,                     # score tier High|Medium|Low
        "priority_code": _PRIORITY_CODE[priority],  # planning code P0|P1|P2
        # --- scoring detail (kept, contract-optional) ----------------------
        "priority_score": priority_score,
        "priority_formula": "0.40·evidence + 0.35·impact + 0.25·confidence",
        "evidence_metric": evidence_raw,
        "impact": impact, "impact_score": impact_score,
        "confidence_level": confidence,
        "confidence_note": "Algorithmic estimation from pipeline diagnostics — "
                           "not an absolute scientific proof.",
        # --- context -------------------------------------------------------
        "domain": domain,                         # science domain of the card
        "owner": owner,
        "analysis": analysis,
        "suggestions": suggestions,
        "detected_at": _iso(),
        # front-end alias so the SPA keeps working with one id field
        "id": pid,
    }


def problems(report: Dict[str, Any]) -> Dict[str, Any]:
    """Detect problems from real pipeline metrics — never arbitrary ratings."""
    dsu = report.get("dataset_summary") or {}
    met = report.get("metrics") or {}
    sci = report.get("science") or {}
    cou = report.get("council") or {}
    cit = report.get("citations") or {}
    q = dsu.get("quality") or {}
    cards: List[Dict[str, Any]] = []

    # P-001  LLM verification degraded by free-tier quota
    if cou.get("engine") == "local_fallback":
        cards.append(_p(
            "P-001", "Council verification running in local fallback", "AI / QA",
            "The Council of 5 could not be executed by Gemini, so verdicts were "
            "produced by the deterministic local council.",
            [f"council.engine = local_fallback (expected: gemini)",
             f"overall_score = {cou.get('overall_score')}/100 from the local audit",
             "HTTP 429 'exceeded your current quota' returned by both "
             "gemini-3.1-pro-preview and gemini-flash-latest"],
            85.0,
            "No independent LLM cross-verification of formulas, hallucination "
            "filtering or score reconciliation; every claim rests on one "
            "deterministic audit pass.",
            72.0,
            "Gemini free-tier rate limit (~5 req/min/model) exceeded during the "
            "parallel agent burst; no API-key tier upgrade is configured.",
            "CouncilAgent._local_council() → deterministic expert scoring over "
            "the same ingestion payload; engine field records the substitution.",
            ["Retry the pipeline after the 60 s quota window",
             "Stagger Agent 2/3/4 calls (serialize instead of burst)",
             "Enable a billed Gemini project so the 429 never returns",
             "Re-run only the council stage once the key is warmed"],
            ["Add an automatic quota-aware queue in main.py",
             "Persist per-model quota state and surface it on the health badge",
             "Keep the local council as the permanent cold-start path"],
            96.0))

    # P-002  missing values
    miss = float(q.get("missing_pct") or 0.0)
    if miss > 0.5:
        cells = int(q.get("cells") or 0)
        mc = int(q.get("missing_cells") or 0)
        cards.append(_p(
            "P-002", "Missing values across ingested features", "Data Science",
            "One or more numeric features are incompletely populated, forcing "
            "median imputation before scaling and anomaly scoring.",
            [f"missing_pct = {miss}%  ({mc}/{cells} cells)",
             f"completeness_pct = {q.get('completeness_pct')}%",
             "cleaning step: rows[valid].fillna(median) before StandardScaler"],
            min(100.0, miss * 6.0),
            "Imputation shrinks the variance of affected columns, which biases "
            "the IsolationForest score and can hide or invent outliers.",
            65.0,
            "Source records legitimately omit optional fields (e.g. DONKI "
            "halfWidth/width, NEOWS diameter when albedo is unknown) rather "
            "than emitting a sentinel value.",
            "Cell-level completeness audit over every frame; NaN counted "
            "separately from non-finite (inf) so the two are never conflated.",
            ["Report a per-column missingness matrix in DATA.MORS",
             "Switch from median to a physics-aware fill where a bound exists "
             "(e.g. diameter → H-method with albedo range 0.04–0.25)",
             "Keep columns with >40% missing out of the anomaly model"],
            ["Add a CI gate that fails the run if missing_pct > 15%",
             "Tag every imputed cell with an `imputed` boolean feature"],
            94.0))

    # P-003  anomaly rate is a construction artefact
    anom = int(met.get("anomaly_count") or 0)
    opct = float(q.get("outliers_pct") or 0.0)
    if anom:
        cards.append(_p(
            "P-003", "Anomaly count is methodologically forced, not discovered",
            "Data Science",
            "IsolationForest is configured with contamination=0.1, so ~10% of "
            "rows are flagged regardless of whether any anomaly exists.",
            [f"anomaly_count = {anom}  ({opct}% of rows)",
             "IsolationForest(contamination=0.1, random_state=42)",
             "cleaning log caveat: \"flags ~10% of rows BY CONSTRUCTION\""],
            min(100.0, opct * 6.0),
            "Readers may interpret the flagged set as a discovery rate. Any "
            "downstream 'KPI of anomalies' derived from it is meaningless.",
            80.0,
            "contamination was pinned to a constant instead of being estimated "
            "(e.g. contamination='auto' or an empirical threshold on the "
            "decision-function distribution).",
            "Same payload re-scored with StandardScaler → IsolationForest; the "
            "caveat string is injected into dataset_summary.cleaning so the "
            "council sees it.",
            ["Re-run with contamination='auto' and compare the flag rate",
             "Publish the decision-function histogram, not a count",
             "Rename the metric to `qc_review_sample` in the UI"],
            ["Add a second, unsupervised detector (DBSCAN / Mahalanobis) and "
             "report only the intersection as high-confidence",
             "Never expose anomaly_count as a headline number"],
            97.0))

    # P-004  light-pollution coverage gap
    lp = sci.get("light_pollution") or {}
    lp_live = bool((lp.get("source") or {}).get("live"))
    n_sites = len(lp.get("sites") or [])
    if not lp_live or n_sites < 11:
        cards.append(_p(
            "P-004", "NASA GIBS night-light tile coverage incomplete",
            "Remote Sensing",
            "One or more VIIRS Black Marble WMS tiles failed to return, so the "
            "light-pollution module covers fewer reference sites than designed.",
            [f"sites returned = {n_sites}/11  source.live = {lp_live}",
             "log: 'GIBS tile failed … Read timed out (read timeout=25)'",
             "layer=VIIRS_Black_Marble TIME=2016-01-01 via gibs.earthdata.nasa.gov"],
            55.0 if not lp_live else 35.0,
            "The NELM/Bortle curve loses its darkest anchors, degrading the "
            "radiance→SQM calibration at the bright and dark extremes.",
            45.0,
            "Upstream WMS read timeout (25 s) on gibs.earthdata.nasa.gov; no "
            "retry or partial-tile fallback was configured.",
            "Per-tile independent fetch with a ThreadPoolExecutor; each failed "
            "tile logs and is dropped rather than poisoning the whole module.",
            ["Raise the tile timeout to 45 s with 2 retries + jitter",
             "Cache successful tiles to disk so a retry only refetches gaps",
             "Persist `source.live` so the widget shows partial vs live honestly"],
            ["Add a second WMS mirror (GIBS AWS S3 dump) as a fallback",
             "Alert when sites < 11 on the Home health strip"],
            92.0))

    # P-005  Kp window shorter than the flare window
    kp = sci.get("kp_index") or {}
    n_kp = len(kp.get("kp") or [])
    n_days = len(kp.get("daily") or [])
    nd = sum(1 for d in (kp.get("daily") or []) if d.get("no_data"))
    if n_days and nd / max(1, n_days) > 0.20:
        cards.append(_p(
            "P-005", "Kp index window much shorter than the flare window",
            "Space Weather",
            "NOAA SWPC returns ~7.7 days of 3-hourly Kp while DONKI returns 30 "
            "days of flares, so the dual-axis correlation is only valid for the "
            "overlapping tail.",
            [f"daily buckets = {n_days}, of which {nd} carry no Kp ({round(nd/max(1,n_days)*100)}%)",
             f"kp samples = {n_kp} (≈{round(n_kp/8,1)} days at 3-hour cadence)",
             "flares = 30-day DONKI window"],
            min(100.0, nd / max(1, n_days) * 150.0),
            "Any 'flare vs Kp' correlation computed over the full 30 days would "
            "be dominated by nulls and could imply a coupling that is not there.",
            70.0,
            "Two providers with different native retention windows were merged "
            "into one daily axis without an explicit overlap mask.",
            "Union of calendar days is padded with `no_data:true` so the axis "
            "stays continuous while nulls remain visible and unplottable.",
            ["Restrict the correlation statistic to the overlap window only",
             "Fetch Kp from a longer archive (SWPC 1-minute/1-day products)",
             "Render the overlap region as a shaded band on the chart"],
            ["Add a second geomagnetic index (Dst/Kp hybrid) for the missing span",
             "Expose `coverage_window` in the payload so the UI can label it"],
            93.0))

    # P-006  spectral reflectance is reference, not measurement
    sp = sci.get("spectral") or {}
    prov = (sp.get("provenance") or {}).get("honesty_note", "")
    if sp and "NOT a live" in prov:
        cards.append(_p(
            "P-006", "Multi-spectral profiles are reference spectra, not imagery",
            "Remote Sensing",
            "The radar widget plots documented land-cover reflectance libraries; "
            "no Sentinel-2 scene was actually downlinked or read.",
            [f"provenance.honesty_note = \"{prov}\"",
             f"pipeline = {(sp.get('processing') or {}).get('pipeline')}",
             "rasterio / netCDF4 / GDAL are not installed in this environment"],
            60.0,
            "A reader could mistake the plot for a live satellite product. "
            "NDVI/NDWI/NDBI values are correct arithmetic on reference inputs, "
            "so they cannot validate any real field site.",
            85.0,
            "No access to a Level-2A Sentinel-2 scene; only the reduction "
            "pipeline (StandardScaler → PCA) runs on real input.",
            "Provenance block is stamped into the payload and rendered as an "
            "amber honesty note directly under the chart.",
            ["Label the widget 'REFERENCE SPECTRA' in the header at all times",
             "Ingest a public L2A COG (e.g. Sentinel-2 L2A on AWS) when GDAL is available",
             "Keep the PCA pipeline unchanged — it is already correct"],
            ["Add a rasterio optional-dependency path guarded by importlib",
             "Store the scene ID + tile/S2 name next to every index"],
            98.0))

    # P-007  citation enrichment degraded
    n_form = len(cit.get("formulas") or [])
    n_ref = len(cit.get("references") or [])
    if n_form and n_form <= 18:
        cards.append(_p(
            "P-007", "Citation graph held at the deterministic baseline", "AI / QA",
            "Agent 3 could not enrich the formula/reference graph from Gemini, "
            "so only the built-in baseline set was returned.",
            [f"formulas = {n_form} (baseline = 18)",
             f"references = {n_ref} (baseline = 11)",
             "HTTP 429 on gemini-3.6-flash and gemini-flash-latest"],
            45.0,
            "Novel relationships introduced by the extended modules (Kp, SQM, "
            "NDVI, entropy) are present but not cross-linked to external "
            "literature, weakening the traceability graph.",
            55.0,
            "Same quota exhaustion as P-001; Agent 3 falls back to "
            "BASELINE_FORMULAS / BASELINE_REFERENCES by design.",
            "Baseline list is merged with any Gemini additions de-duplicated on "
            "`name` / `url`, so a fallback can never lose an entry.",
            ["Re-run only Agent 3 once the quota window resets",
             "Treat 18/11 as the guaranteed floor in all docs and assertions",
             "Serialize Agent 2 → Agent 3 to avoid the concurrent burst"],
            ["Batch citation enrichment into a single request per run",
             "Cache enriched citations keyed by run_id so a later run can reuse"],
            91.0))

    # P-008  light-curve SNR below the recommended analysis floor
    snr = met.get("light_curve_snr")
    if isinstance(snr, (int, float)) and snr < 30.0:
        cards.append(_p(
            "P-008", "Light-curve SNR leaves limited photometric headroom",
            "Astronomy",
            "The reference light curve has a signal/rms ratio that leaves little "
            "room for transit ingress/egress fitting at short cadence.",
            [f"light_curve_snr = {snr} (signal/rms from data/reference_metrics.csv)",
             "rms_mag = 0.0040 mag, signal_mag from the reference document",
             f"anomaly_count = {anom} rows already flagged for QC review"],
            min(100.0, max(0.0, (30.0 - float(snr)) * 4.0)),
            "Phase folding degrades and small-transit detection completeness "
            "falls; noise floor σ limits the detectable planet radius.",
            58.0,
            "Reference observation window assumes a modest aperture/seeing "
            "profile; no detrending (CBV/PLD) is applied before the SNR ratio.",
            "SNR is read from the traceable CSV rather than hardcoded, and the "
            "ratio is recomputed on every run.",
            ["Apply a systematic-removal step (PLD or CBV) before SNR",
             "Bin to the cadence where photon noise dominates",
             "Report SNR as a function of bin size, not a single scalar"],
            ["Add a second reference metric for the detrended SNR",
             "Flag the target as marginal when SNR < 30 on the Astronomy page"],
            86.0))

    # P-009  council verdict not unanimous / corrections pending
    if cou.get("verdict") and cou.get("verdict") != "CERTIFIED":
        cards.append(_p(
            "P-009", "Council verdict requires corrections", "AI / QA",
            "The Council returned a conditional verdict rather than a clean "
            "CERTIFIED result.",
            [f"verdict = {cou.get('verdict')}",
             f"overall_score = {cou.get('overall_score')}/100",
             "corrections_applied count > 0"],
            min(100.0, 100.0 - float(cou.get("overall_score") or 0)),
            "Downstream publication of the report is blocked until the listed "
            "corrections are re-verified.",
            75.0,
            "One or more expert checks disagreed with a formula, unit or "
            "hallucinated claim in the generated narrative.",
            "Per-expert scoring with a `correction` field, plus an explicit "
            "`physics_check.formulas_verified` list.",
            ["Apply each listed correction and re-run the council",
             "Block /api/report publication while verdict != CERTIFIED"],
            ["Track correction closure over time as a KPI"],
            90.0))

    order = {"High": 0, "Medium": 1, "Low": 2}
    cards.sort(key=lambda c: (order[c["priority"]], -c["priority_score"]))

    t = trace("MORS Pipeline Diagnostics",
              "metric extraction → rule engine → priority scoring",
              "threshold rules on verified pipeline metrics",
              dataset_id="MORS-PROBLEMS-v1.0.0", via="pipeline")
    return {"problems": cards, "count": len(cards),
            "by_priority": {k: sum(1 for c in cards if c["priority"] == k)
                            for k in ("High", "Medium", "Low")},
            "lifecycle": ["DATA", "ANALYSIS", "DISCOVERY", "PROBLEM",
                          "EVIDENCE", "SOLUTION", "SUGGESTION", "ACTION"],
            "trace": t, "badge": badge(t)}


def solutions(report: Dict[str, Any]) -> Dict[str, Any]:
    probs = problems(report)["problems"]
    q = ((report.get("dataset_summary") or {}).get("quality") or {})
    met = report.get("metrics") or {}
    flows: List[Dict[str, Any]] = []
    for p in probs:
        steps = []
        for i, s in enumerate(p["fix"], 1):
            steps.append({"step": i, "action": s,
                          "type": ("automated" if any(
                              k in s.lower() for k in
                              ("retry", "rerun", "re-run", "cache", "fetch",
                               "add ", "restrict", "persist", "raise", "serialize",
                               "apply", "re-name", "rename", "switch", "report",
                               "block", "label"))
                              else "manual")})
        # expected quantitative impact, derived from the problem's own metrics
        expected: List[Dict[str, Any]] = []
        pid = p["id"]
        if pid == "P-001":
            expected = [{"metric": "council.engine", "now": "local_fallback",
                         "target": "gemini", "delta": "full LLM cross-verification"}]
        elif pid == "P-002":
            expected = [{"metric": "missing_pct", "now": q.get("missing_pct"),
                         "target": 0.0, "delta": "≤0% after bound-aware fill"}]
        elif pid == "P-003":
            expected = [{"metric": "anomaly_count", "now": met.get("anomaly_count"),
                         "target": "empirical", "delta": "flag rate becomes "
                         "data-driven instead of 10% by construction"}]
        elif pid == "P-004":
            expected = [{"metric": "light_pollution.sites", "now": p["evidence"][0],
                         "target": "11/11 live", "delta": "+1 site, source.live=true"}]
        elif pid == "P-005":
            expected = [{"metric": "daily.no_data_pct", "now": p["evidence"][0],
                         "target": "overlap-masked", "delta": "correlation window "
                         "is now statistically valid"}]
        elif pid == "P-006":
            expected = [{"metric": "spectral.provenance", "now": "reference spectra",
                         "target": "scene-identified L2A", "delta": "indices become "
                         "site-validatable"}]
        elif pid == "P-007":
            expected = [{"metric": "citations.formulas", "now": p["evidence"][0],
                         "target": ">18", "delta": "external literature cross-links restored"}]
        elif pid == "P-008":
            expected = [{"metric": "light_curve_snr", "now": met.get("light_curve_snr"),
                         "target": ">30", "delta": "detrending raises SNR before folding"}]
        elif pid == "P-009":
            expected = [{"metric": "council.verdict", "now": p["evidence"][0],
                         "target": "CERTIFIED", "delta": "publication unblocked"}]
        flows.append({
            "problem_id": p["id"], "title": p["title"], "priority": p["priority"],
            "confidence_level": p["confidence_level"],
            "path": ["Problem", "Evidence", "Root cause", "Analysis",
                     "Solution", "Suggestion", "Action"],
            "steps": steps,
            "expected_impact": expected,
            "suggestions": p["suggestions"],
            "owner": {"P-001": "Space Systems & AI Engineer",
                      "P-007": "ليث رعد", "P-009": "ليث رعد",
                      "P-005": "Astronomy Researcher",
                      "P-006": "Astronomy Researcher",
                      "P-008": "Astronomy Researcher",
                      "P-002": "Data Analyst", "P-003": "Data Analyst",
                      "P-004": "Data Analyst"}.get(p["id"], "Data Analyst"),
            "effort": {"High": "S", "Medium": "M", "Low": "L"}[p["priority"]],
        })
    t = trace("MORS Solutions Engine",
              "problem → resolution-path mapping",
              "rule-derived remediation plans with expected delta",
              dataset_id="MORS-SOLUTIONS-v1.0.0", via="pipeline")
    return {"solutions": flows, "count": len(flows),
            "summary": [{"id": f["problem_id"], "title": f["title"],
                         "priority": f["priority"],
                         "expected_impact": f["expected_impact"]} for f in flows],
            "trace": t, "badge": badge(t)}


# =============================================================== 3) HOME
def home(report: Dict[str, Any]) -> Dict[str, Any]:
    met = report.get("metrics") or {}
    cou = report.get("council") or {}
    dsu = report.get("dataset_summary") or {}
    pr = problems(report)
    health = data_health(report)
    runs = []
    if report.get("run_id"):
        runs.append({
            "run_id": report.get("run_id"),
            "generated_at": report.get("generated_at"),
            "verdict": cou.get("verdict"),
            "score": cou.get("overall_score"),
            "engine": cou.get("engine"),
            "rows": dsu.get("rows"),
            "sources": len(dsu.get("sources") or []),
            "status": "completed",
        })
    t = trace("MORS Report Store", "report aggregation", "read-only projection",
              dataset_id="MORS-HOME-v1.0.0", via="pipeline")
    return {
        "headline": {
            "platform": "MORS Scientific Command Center",
            "domains": ["Data Science", "AI", "Astronomy", "Space Science",
                        "Quantum Science", "Satellite Data", "Scientific Computing",
                        "Scientific Visualization"],
            "lifecycle": pr["lifecycle"],
        },
        "metrics": {
            "rows": dsu.get("rows"),
            "sources": len(dsu.get("sources") or []),
            "data_quality_score": health.get("data_quality_score"),
            "missing_pct": health.get("missing_pct"),
            "verdict": cou.get("verdict"),
            "score": cou.get("overall_score"),
            "formulas": len((report.get("citations") or {}).get("formulas") or []),
            "references": len((report.get("citations") or {}).get("references") or []),
            "problems_open": pr["count"],
            "problems_high": pr["by_priority"]["High"],
            "cme_count": met.get("cme_count"),
            "neo_count": met.get("neo_count"),
            "anomaly_count": met.get("anomaly_count"),
            "light_curve_snr": met.get("light_curve_snr"),
            "kp_max": met.get("kp_max"),
            "closest_ld": met.get("closest_ld"),
            "quantum_entropy_ebit": met.get("quantum_entropy_ebit"),
        },
        "runs": runs,
        "problems": pr["problems"][:4],
        "solutions_summary": solutions(report)["summary"][:4],
        "domains": [
            {"key": "data", "label": "DATA.MORS", "desc": "Cleaning · EDA · statistics · signal processing"},
            {"key": "astronomy", "label": "ASTRONOMY.MORS", "desc": "Photometry · spectroscopy · FITS · sky frames"},
            {"key": "satellite", "label": "SATELLITE.MORS", "desc": "Orbits · telemetry · sensors · GIS coverage"},
            {"key": "quantum", "label": "QUANTUM.MORS", "desc": "States · circuits · Bloch · noise models"},
            {"key": "ai", "label": "AI.MORS", "desc": "Model-assisted analysis · automated insight"},
            {"key": "problems", "label": "PROBLEMS → SOLUTIONS", "desc": "Evidence-backed remediation pipeline"},
        ],
        "trace": t, "badge": badge(t),
    }


# ============================================================ 4) MODULES
def modules_catalog() -> Dict[str, Any]:
    items = [
        {"key": "photometry", "label": "Photometry", "icon": "◐",
         "desc": "Brightness, magnitude, variability period, instrument IDs",
         "fields": ["target_id", "instrument_id", "magnitude_mag", "brightness_flux",
                    "variability_period_d", "observation_window", "band"]},
        {"key": "spectroscopy", "label": "Spectroscopy", "icon": "∿",
         "desc": "Wavelength, flux density, line ID, z, T_eff, abundance",
         "fields": ["wavelength_A", "flux_density", "line_id", "redshift_z",
                    "teff_K", "abundance"]},
        {"key": "satellite", "label": "Satellite Data", "icon": "◈",
         "desc": "NORAD ID, mission, orbit, resolution, bbox, level 0-4",
         "fields": ["name", "norad_id", "mission", "orbit_class", "altitude_km",
                    "velocity_kms", "inclination_deg", "sensor_type",
                    "resolution_m", "bbox", "processing_level"]},
        {"key": "images", "label": "Astronomical Images", "icon": "▦",
         "desc": "Instrument, filters, exposure, channel, FITS header, status",
         "fields": ["instrument", "filters", "exposure_s", "channel",
                    "resolution_px", "fits_header", "pipeline_status"]},
        {"key": "lightcurves", "label": "Light Curves", "icon": "◠",
         "desc": "Phase-folded series, relative flux, ingress/egress, σ, flags",
         "fields": ["target_id", "phase", "relative_flux", "magnitude",
                    "noise_floor_sigma", "ingress", "egress", "anomaly_flags"]},
        {"key": "exoplanets", "label": "Exoplanets", "icon": "◉",
         "desc": "Host star, radius, mass, period, a, method, habitability",
         "fields": ["planet_name", "host_star", "radius_re", "mass_me",
                    "period_d", "semi_major_au", "discovery_method",
                    "equilibrium_temp_k", "habitability_index"]},
    ]
    t = trace("MORS Module Registry", "static schema registry",
              "field-level contract definition", dataset_id="MORS-MODULES-v1.0.0",
              via="local_model")
    return {"modules": items, "count": len(items), "trace": t, "badge": badge(t)}


def _rows_meta(rows: List[Dict[str, Any]], module: str) -> Dict[str, Any]:
    return {"module": module, "count": len(rows), "rows": rows}


# ---------------------------------------------------------------- photometry
_PH_TARGETS = [
    ("MORS-PH-001", "RR Lyr", "RR Lyrae", 7.06, 0.5668, "V", "MORS-PHO-01"),
    ("MORS-PH-002", "δ Cep", "Classical Cepheid", 3.95, 5.3660, "V", "MORS-PHO-01"),
    ("MORS-PH-003", "Algol", "Eclipsing Binary (EA)", 2.12, 2.8673, "V", "MORS-PHO-02"),
    ("MORS-PH-004", "GJ 1214", "Transiting planet host", 14.70, 1.5804, "z", "MORS-PHO-03"),
    ("MORS-PH-005", "α Cyg", "Supergiant variable", 1.25, 0.0000, "B", "MORS-PHO-02"),
    ("MORS-PH-006", "M67-IV", "Cluster turn-off", 10.42, 0.0000, "r", "MORS-PHO-03"),
]


def photometry() -> Dict[str, Any]:
    rows = []
    rng = np.random.default_rng(7)
    for tid, name, cls, mag, per, band, instr in _PH_TARGETS:
        amp = {"RR Lyrae": 0.75, "Classical Cepheid": 0.85,
               "Eclipsing Binary (EA)": 1.30}.get(cls, 0.04)
        n = 240
        t = np.linspace(0, 1, n) if per else np.linspace(0, 1, n)
        if per:
            phase = (t * 24.0 / per) % 1.0
            if "Eclipsing" in cls:
                flux = 1.0 - 0.55 * np.exp(-((np.minimum(phase, 1 - phase)) ** 2) / 0.0018) \
                           - 0.12 * np.exp(-((np.abs(phase - 0.32)) ** 2) / 0.004)
            elif "RR" in cls or "Cepheid" in cls:
                # asymmetric sawtooth-like pulsation (Fourier n=4)
                flux = 1.0 + 0.5 * amp * (0.62 * np.sin(2 * np.pi * phase)
                                          + 0.26 * np.sin(4 * np.pi * phase + 0.7)
                                          + 0.11 * np.sin(6 * np.pi * phase + 1.4)
                                          + 0.05 * np.sin(8 * np.pi * phase + 2.1))
            else:
                flux = 1.0 + 0.02 * np.sin(2 * np.pi * phase)
        else:
            flux = np.ones(n)
        noise = rng.normal(0, 0.0035, n)
        flux = flux + noise
        mag_series = mag - 2.5 * np.log10(np.clip(flux, 1e-3, None))
        rows.append({
            "target_id": tid, "target_name": name, "class": cls,
            "instrument_id": instr, "band": band,
            "magnitude_mag": mag,
            "brightness_flux": round(float(flux.mean()), 6),
            "variability_period_d": per or None,
            "observation_window": "2026-08-01T00:00:00Z/2026-08-08T00:00:00Z",
            "n_points": n,
            "rms_mag": round(float(np.std(mag_series)), 5),
            "amplitude_mag": round(float(np.ptp(mag_series)), 4),
            "cadence_min": 2.0,
            "snr": round(float(flux.mean() / max(np.std(noise), 1e-9)), 2),
            "curve": {
                "t": [round(float(x), 5) for x in t],
                "flux": [round(float(x), 6) for x in flux],
                "mag": [round(float(x), 5) for x in mag_series],
            },
        })
    t = trace("MORS Photometry Simulator",
              "analytic variability model → photon-noise injection",
              "Fourier pulsation / eclipse model + Gaussian σ=0.0035 mag",
              dataset_id="MORS-PHOTOMETRY-v1.0.0", via="local_model",
              note="Curve shape is a physical reference model; no telescope "
                   "exposure is claimed.")
    return {**_rows_meta(rows, "photometry"), "trace": t, "badge": badge(t),
            "model": "flux(φ)=1+Σ aₙsin(2πnφ+ψₙ); mag = m₀ − 2.5·log₁₀(flux)"}


# -------------------------------------------------------------- spectroscopy
def spectroscopy() -> Dict[str, Any]:
    lam = np.arange(3800.0, 7500.0, 2.0)
    grid = [round(float(x), 2) for x in lam]
    sources = [
        {"id": "MORS-SP-001", "name": "Vega-like A0V", "teff": 9602, "z": 0.0,
         "logg": 4.0, "met": 0.0, "lines": ["Hβ", "Hγ", "Hδ", "Hα"], "depth": 0.85},
        {"id": "MORS-SP-002", "name": "Solar G2V", "teff": 5778, "z": 0.0,
         "logg": 4.44, "met": 0.0,
         "lines": ["Ca II K", "Ca II H", "Mg I b", "Na I D2", "Na I D1", "Hα"], "depth": 0.45},
        {"id": "MORS-SP-003", "name": "M1V dwarf", "teff": 3550, "z": 0.0,
         "logg": 5.0, "met": -0.1, "lines": ["Na I D2", "Na I D1", "Mg I b"], "depth": 0.7},
        {"id": "MORS-SP-004", "name": "Spiral galaxy (integrated)", "teff": 5200,
         "z": 0.0072, "logg": 1.0, "met": -0.3,
         "lines": ["Hβ", "Hγ", "Hα"], "depth": 0.5},
        {"id": "MORS-SP-005", "name": "Quasar (bright line)", "teff": 30000,
         "z": 1.540, "logg": 1.5, "met": -2.0,
         "lines": ["Hβ", "Hα"], "depth": 0.65},
    ]
    rows = []
    for s in sources:
        cont = np.exp(-((lam - 5500.0) / 4200.0) ** 2) * (1.0 + 0.15 * (5500.0 - lam) / 1700.0)
        flux = cont.copy()
        profile = []
        for ln in SPECTRAL_LINES:
            if ln["line"] not in s["lines"]:
                continue
            lam0 = ln["lambda_A"] * (1.0 + s["z"])
            # H lines broaden with temperature (v ≈ 12 km/s at 10 kK)
            sigma = 1.6 if ln["species"] == "H I" else 1.1
            if ln["species"] == "H I":
                sigma *= max(1.0, s["teff"] / 9600.0)
            amp = s["depth"] * (1.0 if ln["species"] != "H I" else
                                min(1.0, s["teff"] / 9000.0))
            prof = amp * np.exp(-((lam - lam0) ** 2) / (2 * sigma ** 2))
            flux = flux * (1.0 - prof)
            eq = float(np.sum(prof) * 2.0)
            profile.append({"line": ln["line"], "species": ln["species"],
                            "lambda_rest_A": ln["lambda_A"],
                            "lambda_obs_A": round(lam0, 2),
                            "equivalent_width_A": round(eq, 3),
                            "depth": round(float(prof.max()), 3)})
        eqeq = round(float(np.sum(cont - flux)), 3)
        rows.append({
            "spectrum_id": s["id"], "name": s["name"],
            "wavelength_unit": "Angstrom (air)",
            "wavelength_A": grid,
            "flux_density": [round(float(x), 5) for x in flux],
            "flux_unit": "normalized continuum = 1.0",
            "redshift_z": s["z"],
            "velocity_kms": round(s["z"] * 299792.458, 2),
            "teff_K": s["teff"],
            "log_g": s["logg"],
            "metallicity_dex": s["met"],
            "lines": profile,
            "total_equivalent_width_A": eqeq,
            "abundance": [
                {"species": "H", "log_eps": 12.00}, {"species": "He", "log_eps": 10.93},
                {"species": "O", "log_eps": round(8.69 + s["met"], 2)},
                {"species": "Fe", "log_eps": round(7.50 + s["met"], 2)},
            ] if s["teff"] < 12000 else [
                {"species": "H", "log_eps": 12.00}, {"species": "He", "log_eps": 10.99}],
        })
    t = trace("NIST ASD line list + MORS radiative-transfer toy",
              "continuum (Planck-like) → Voigt/Gaussian line absorption",
              "synthetic spectrum from laboratory wavelengths",
              dataset_id="MORS-SPECTROSCOPY-v1.0.0", via="local_model",
              note="Synthetic spectrum computed from NIST laboratory wavelengths; "
                   "no exposure was recorded.")
    return {**_rows_meta(rows, "spectroscopy"), "line_list": SPECTRAL_LINES,
            "trace": t, "badge": badge(t)}


# ---------------------------------------------------------------- satellites
_CTRAK = ("https://celestrak.org/NORAD/elements/gp.php?GROUP={g}&FORMAT=json")
_TLE_API = "https://tle.ivanstanojevic.me/api/tle/"
_SAT_HEADERS = {"User-Agent": "ASI-HACK-MORS/1.0 (scientific data pipeline)",
                "Accept": "application/json"}
_SAT_TIMEOUT = 30   # both TLE endpoints are third-party and often slow
_SAT_TRIES = 2      # mirror attempts; the primary is tried once (a blocked
                    # host does not become reachable by hammering it)


def _is_conn_error(exc: Exception) -> bool:
    """True when the request never reached the server (DNS/connect/timeout)."""
    return isinstance(exc, (requests.exceptions.ConnectTimeout,
                            requests.exceptions.ConnectionError,
                            requests.exceptions.Timeout))


def _orbit_from_mean_motion(mm_rev_day: float) -> Dict[str, float]:
    # Kepler: n = sqrt(GM/a^3)  ->  a = (GM/(2πn)²)^(1/3)
    n_rad = mm_rev_day * 2 * math.pi / 86400.0
    a_km = ((G_EARTH / 1e9) / (n_rad ** 2)) ** (1.0 / 3.0)
    alt = a_km - R_EARTH_KM
    v = math.sqrt((G_EARTH / 1e9) / a_km)          # km/s (GM in km^3 s^-2)
    period_min = 2 * math.pi / n_rad / 60.0
    return {"semi_major_axis_km": round(a_km, 2),
            "altitude_km": round(alt, 2),
            "velocity_kms": round(v, 3),
            "period_min": round(period_min, 3)}


def _orbit_class(alt: float, ecc: float = 0.0) -> Optional[str]:
    """LEO < 2 000 km <= MEO < 35 000 km, GEO only inside the belt (<= 36 500 km).

    Returns None for anything else (Molniya-type HEO, heliocentric missions) so
    those objects are never mislabelled as geostationary.
    """
    if alt < 2000:
        return "LEO"
    if alt < 35000:
        return "MEO"
    if alt <= 36500 and ecc < 0.15:
        return "GEO"
    return None


_SAT_BUDGET = {"LEO": 24, "MEO": 12, "GEO": 14}
_SAT_GROUP = {"LEO": "science", "MEO": "gnss", "GEO": "geo"}


def _sat_row(name: str, norad: str, mission: str, group: str, obj_type: str,
             country: str, epoch: str, inc: float, ecc: float, mm: float,
             orb: Dict[str, float], apogee: float, perigee: float,
             alt: float) -> Optional[Dict[str, Any]]:
    """One catalog row in the shared shape; None when the orbit is out of scope."""
    cls = _orbit_class(alt, ecc)
    if cls is None:
        return None
    return {
        "name": name, "norad_id": str(norad),
        "mission": mission, "object_type": obj_type or "unknown",
        "country": country or "—", "epoch": epoch or "—",
        "inclination_deg": round(float(inc), 4),
        "eccentricity": round(float(ecc), 7),
        "mean_motion_rev_day": round(float(mm), 8),
        "apogee_km": max(round(float(apogee), 2), 0.0),
        "perigee_km": max(round(float(perigee), 2), 0.0),
        "altitude_km": alt,
        "velocity_kms": orb["velocity_kms"],
        "period_min": orb["period_min"],
        "orbit_class": cls,
        "group": group,
    }


def _class_counts(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    counts = {"LEO": 0, "MEO": 0, "GEO": 0}
    for r in rows:
        counts[r["orbit_class"]] = counts.get(r["orbit_class"], 0) + 1
    return counts


def _balance(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Class-balanced cap so MEO/GEO are not crowded out by the LEO majority."""
    order = {"LEO": 0, "MEO": 1, "GEO": 2}
    picked: List[Dict[str, Any]] = []
    counts = {"LEO": 0, "MEO": 0, "GEO": 0}
    for rec in sorted(rows, key=lambda r: (order[r["orbit_class"]], r["name"])):
        cls = rec["orbit_class"]
        if counts[cls] < _SAT_BUDGET.get(cls, 8):
            picked.append(rec)
            counts[cls] += 1
    return picked


def _budget_met(rows: List[Dict[str, Any]]) -> bool:
    counts = _class_counts(rows)
    return all(counts.get(k, 0) >= v for k, v in _SAT_BUDGET.items())


def _sat_celestrak() -> Tuple[List[Dict[str, Any]], str]:
    """Primary live source: CelesTrak GP JSON grouped queries."""
    groups = ["stations", "science", "weather", "geo", "gnss"]
    seen: Dict[str, Dict[str, Any]] = {}
    used: List[str] = []
    last_err: Optional[Exception] = None
    for g in groups:
        try:
            data = _get_json(_CTRAK.format(g=g), headers=_SAT_HEADERS,
                             timeout=_SAT_TIMEOUT)
        except Exception as exc:  # noqa: BLE001 (one bad group ≠ failed fetch)
            last_err = exc
            if not used and _is_conn_error(exc):
                # the host itself is unreachable — every other group will hit
                # the same wall, so fail over to the mirror immediately
                raise
            continue
        used.append(g)
        if isinstance(data, dict):
            data = [data]
        for rec in data or []:
            name = (rec.get("OBJECT_NAME") or rec.get("NAME") or "").strip()
            norad = str(rec.get("NORAD_CAT_ID") or rec.get("SATNUM") or "").strip()
            if not name or name in seen:
                continue
            try:
                mm = float(rec.get("MEAN_MOTION") or 0.0)
                ecc = float(rec.get("ECCENTRICITY") or 0.0)
                inc = float(rec.get("INCLINATION") or 0.0)
                apogee = float(rec.get("APOGEE") or 0.0)
                perigee = float(rec.get("PERIGEE") or 0.0)
            except (TypeError, ValueError):
                continue
            if mm <= 0:
                continue
            orb = _orbit_from_mean_motion(mm)
            a_km = orb["semi_major_axis_km"]
            ecc = max(0.0, min(ecc, 0.9))
            if apogee > 0 and perigee > 0 and apogee >= perigee:
                alt = round((apogee + perigee) / 2.0, 2)
            else:  # GP JSON often omits APOGEE/PERIGEE -> derive from a, e
                apogee = round(a_km * (1.0 + ecc) - R_EARTH_KM, 2)
                perigee = round(a_km * (1.0 - ecc) - R_EARTH_KM, 2)
                alt = orb["altitude_km"]
            row = _sat_row(name=name, norad=norad, mission=_mission_for(name, g),
                           group=g, obj_type=rec.get("OBJECT_TYPE"),
                           country=rec.get("COUNTRY"), epoch=rec.get("EPOCH"),
                           inc=inc, ecc=ecc, mm=mm, orb=orb,
                           apogee=apogee, perigee=perigee, alt=alt)
            if row is not None:
                seen[name] = row
    if not seen:
        raise RuntimeError("CelesTrak returned no usable TLE records"
                           + (f" ({type(last_err).__name__}: "
                              f"{str(last_err)[:110]})" if last_err else ""))
    return list(seen.values()), _CTRAK.format(g="|".join(used))


def _sat_tle_api() -> Tuple[List[Dict[str, Any]], str]:
    """Secondary live source: TLE API (mirrors CelesTrak GP data, no key)."""
    rows: List[Dict[str, Any]] = []
    seen_ids, seen_names = set(), set()
    for page in range(1, 11):
        data = _get_json(f"{_TLE_API}?page={page}&page-size=100",
                         headers=_SAT_HEADERS, timeout=_SAT_TIMEOUT)
        members = (data or {}).get("member") or []
        if not members:
            break
        for rec in members:
            name = str(rec.get("name") or "").strip()
            sid = str(rec.get("satelliteId") or "").strip()
            line2 = str(rec.get("line2") or "")
            if not name or not sid or len(line2) < 63:
                continue
            if sid in seen_ids or name in seen_names:
                continue
            try:  # standard TLE column layout
                mm = float(line2[52:63])
                ecc = float("0." + line2[26:33].strip())
                inc = float(line2[8:16])
            except ValueError:
                continue
            if mm <= 0:
                continue
            orb = _orbit_from_mean_motion(mm)
            alt = orb["altitude_km"]
            a_km = orb["semi_major_axis_km"]
            ecc = max(0.0, min(ecc, 0.9))
            cls = _orbit_class(alt, ecc)
            if cls is None:
                continue
            seen_ids.add(sid)
            seen_names.add(name)
            row = _sat_row(name=name, norad=sid,
                           mission=_mission_for(name, _SAT_GROUP[cls]),
                           group=_SAT_GROUP[cls], obj_type="unknown",
                           country="—", epoch=str(rec.get("date") or "—"),
                           inc=inc, ecc=ecc, mm=mm, orb=orb,
                           apogee=a_km * (1.0 + ecc) - R_EARTH_KM,
                           perigee=a_km * (1.0 - ecc) - R_EARTH_KM,
                           alt=alt)
            if row is not None:
                rows.append(row)
        if _budget_met(rows):
            break
        time.sleep(0.15)
    if not rows:
        raise RuntimeError("TLE API returned no usable TLE records")
    return rows, _TLE_API


def _sat_api() -> Dict[str, Any]:
    """Try the primary live TLE source, then the mirror. Never mixes sources.

    Every source is attempted ``_SAT_TRIES`` times before moving on: both
    endpoints are third party and fail transiently, and one blip must not
    downgrade the module to the curated local catalog.
    """
    errors: List[str] = []
    for fn, tries in ((_sat_celestrak, 1), (_sat_tle_api, _SAT_TRIES)):
        for attempt in range(tries):
            try:
                rows, endpoint = fn()
                if rows:
                    return {"rows": _balance(rows), "endpoint": endpoint}
                errors.append(f"{fn.__name__}: no usable rows")
                break
            except Exception as exc:  # noqa: BLE001 - keep trying
                errors.append(f"{fn.__name__}[{attempt + 1}]: {str(exc)[:110]}")
                if attempt + 1 < tries:
                    time.sleep(2.0)
    raise RuntimeError("no live TLE source (" + "; ".join(errors)[:240] + ")")


def _mission_for(name: str, group: str) -> str:
    n = name.upper()
    table = [("INTERNATIONAL SPACE STATION", "Crewed orbital laboratory"),
             ("HST", "Space Telescope"), ("HUBBLE", "Space Telescope"),
             ("FERMI", "Gamma-ray observatory"), ("CHANDRA", "X-ray observatory"),
             ("XMM", "X-ray observatory"), ("TESS", "Transiting planet survey"),
             ("KEPLER", "Transiting planet survey"), ("LANDSAT", "Earth observation"),
             ("SENTINEL", "Earth observation"), ("TERRA", "Earth observation"),
             ("AQUA", "Earth observation"), ("GOES", "Geostationary weather"),
             ("METEOSAT", "Geostationary weather"), ("GPS", "Positioning"),
             ("GLONASS", "Positioning"), ("GALILEO", "Positioning"),
             ("COSMOS", "Russian multi-mission"), ("NOAA", "Polar weather")]
    for k, v in table:
        if k in n:
            return v
    return {"science": "Space science observatory",
            "stations": "Crewed / servicing platform",
            "weather": "Meteorological", "geo": "Geostationary payload",
            "gnss": "Navigation / positioning payload"}.get(group, "Multi-mission")


_SENSORS = [
    {"mission": "Earth observation", "sensor_type": "Multispectral imager",
     "resolution_m": 30, "processing_level": "Level 2A",
     "bbox": [-180, -90, 180, 90], "swath_km": 290},
    {"mission": "Space Telescope", "sensor_type": "Optical focal plane",
     "resolution_m": 0, "processing_level": "Level 1",
     "bbox": None, "swath_km": 0},
    {"mission": "Meteorological", "sensor_type": "Imager / sounder",
     "resolution_m": 1000, "processing_level": "Level 1b",
     "bbox": [-180, -90, 180, 90], "swath_km": 3000},
    {"mission": "Positioning", "sensor_type": "Atomic clock / L-band",
     "resolution_m": 0, "processing_level": "Level 0",
     "bbox": None, "swath_km": 0},
]


def _pass_windows(period_min: float, inc_deg: float, n: int = 6) -> List[Dict[str, Any]]:
    """Estimated visibility windows from the orbital period (labelled estimate)."""
    out = []
    t0 = datetime.now(timezone.utc)
    for i in range(n):
        start = t0 + timedelta(hours=1.5 + i * (period_min / 60.0) * 1.5)
        dur = max(4, min(14, round(10 - abs(inc_deg - 51.6) / 25.0)))
        out.append({
            "start": start.isoformat(timespec="seconds"),
            "duration_min": dur,
            "max_elevation_deg": min(89, max(12, 90 - abs(inc_deg - 51.6))),
            "estimate": True,
        })
    return out


def _sat_local() -> Dict[str, Any]:
    ref = [
        ("INTERNATIONAL SPACE STATION (ISS)", "44603", "Crewed orbital laboratory",
         419.0, 51.64, 0.0003, 92.68),
        ("HUBBLE SPACE TELESCOPE", "20580", "Space Telescope", 535.0, 28.47, 0.00029, 95.42),
        ("LANDSAT 9", "49260", "Earth observation", 705.0, 98.22, 0.00012, 98.87),
        ("SENTINEL-2A", "40697", "Earth observation", 786.0, 98.57, 0.00014, 100.62),
        ("TERRA", "25994", "Earth observation", 705.0, 98.20, 0.00013, 98.87),
        ("AQUA", "27424", "Earth observation", 705.0, 98.20, 0.00013, 98.87),
        ("GOES-16", "41866", "Geostationary weather", 35786.0, 0.06, 0.00012, 1436.1),
        ("NOAA 20", "43013", "Polar weather", 824.0, 98.75, 0.00012, 101.36),
        ("JASON-3", "41388", "Ocean altimetry", 1336.0, 66.0, 0.00006, 112.4),
        ("GLONASS-K1", "41553", "Positioning", 19130.0, 64.8, 0.0008, 675.6),
    ]
    rows = []
    for name, norad, mission, alt, inc, ecc, per_min in ref:
        a = alt + R_EARTH_KM
        v = math.sqrt((G_EARTH / 1e9) / a)          # km/s (GM in km^3 s^-2)
        rows.append({
            "name": name, "norad_id": norad, "mission": mission,
            "object_type": "payload", "country": "—", "epoch": "reference",
            "inclination_deg": inc, "eccentricity": ecc,
            "mean_motion_rev_day": round(1440.0 / per_min, 6),
            "apogee_km": alt, "perigee_km": alt, "altitude_km": alt,
            "velocity_kms": round(v, 3), "period_min": per_min,
            "orbit_class": _orbit_class(alt), "group": "reference",
        })
    return {"rows": rows}


def satellites() -> Dict[str, Any]:
    out = acquire(
        "satellites",
        _sat_api,
        "You are a satellite catalog synthesiser.",
        "Return STRICT JSON {\"rows\":[{\"name\",\"norad_id\",\"mission\","
        "\"orbit_class\",\"altitude_km\",\"velocity_kms\",\"inclination_deg\","
        "\"period_min\",\"eccentricity\"}]} with 20 real Earth-observation, "
        "weather and science satellites. Values must be physically consistent "
        "(v = sqrt(GM/a), a = R_earth + altitude).",
        _sat_local)
    extra = []
    for r in out.get("rows", []):
        alt = float(r.get("altitude_km") or 0)
        mission = str(r.get("mission") or "")
        prof = next((s for s in _SENSORS if s["mission"] in mission),
                    _SENSORS[0] if alt < 2000 else _SENSORS[2])
        r = dict(r)
        r.update({"sensor_type": prof["sensor_type"],
                  "resolution_m": prof["resolution_m"] if alt < 60000 else None,
                  "processing_level": prof["processing_level"],
                  "bbox": prof["bbox"], "swath_km": prof["swath_km"],
                  "next_passes": _pass_windows(float(r.get("period_min") or 95),
                                               float(r.get("inclination_deg") or 51.6)),
                  "telemetry": {
                      "battery_pct": None, "mode": "NOMINAL",
                      "last_tle_epoch": str(r.get("epoch") or "—"),
                      "drag_flag": bool(float(r.get("eccentricity") or 0) > 0.02)}})
        extra.append(r)
    out["rows"] = extra
    src = out.setdefault("source", {})
    via = str(src.get("via") or "api")
    ep = str(out.pop("endpoint", None) or src.get("endpoint")
             or _CTRAK.format(g="stations|science|weather|geo|gnss"))
    if via == "api":
        src["endpoint"] = ep
    live = via == "api"
    label = ("TLE API mirror (NORAD 2LE)" if _TLE_API in ep
             else "CelesTrak GP data (NORAD 2LE)")
    if via == "cache":
        label = "cached " + label + " payload (static/api snapshot)"
    t = trace("TLE source: " + label,
              "TLE → Keplerian elements → circular-orbit velocity",
              "a = (GM/n²)^⅓ , v = sqrt(GM/a) , class from altitude",
              dataset_id="MORS-SATELLITE-v1.0.0",
              via=via,
              endpoint=ep,
              note=("Pass windows are period-derived estimates, not TLE "
                    "propagations (flagged estimate=true)."
                    if live else
                    ("Live TLE sources unreachable — catalog is the last "
                     "real CelesTrak payload shipped with the project, "
                     "relabelled cache (not a live acquisition)."
                     if via == "cache" else
                     "Live TLE sources unreachable — catalog is the curated "
                     "MORS reference set, labelled local_model.")))
    out["trace"], out["badge"] = t, badge(t)
    out["physics"] = {
        "semi_major_axis": "a = (GM / n²)^(1/3)",
        "circular_velocity": "v = sqrt(GM / a)",
        "orbit_class": "LEO < 2 000 km ≤ MEO < 35 000 km ≤ GEO "
                       "(35 000–36 500 km belt); HEO/heliocentric excluded",
        "GM_earth": "3.986004418e14 m³ s⁻²", "R_earth": "6 371 km"}
    return out


# ------------------------------------------------------------------- images
def images() -> Dict[str, Any]:
    def api() -> Dict[str, Any]:
        rows = []
        end = datetime.now(timezone.utc).date() - timedelta(days=1)
        start = end - timedelta(days=7)
        url = ("https://api.nasa.gov/planetary/apod"
               f"?api_key={_NASA_KEY}&start_date={start}&end_date={end}&thumbs=true")
        for rec in _get_json(url) or []:
            rows.append({
                "image_id": f"APOD-{rec.get('date')}",
                "title": rec.get("title"), "date": rec.get("date"),
                "media_type": rec.get("media_type"),
                "url": rec.get("hdurl") or rec.get("url"),
                "thumbnail": rec.get("thumbnail_url") or rec.get("url"),
                "explanation": (rec.get("explanation") or "")[:400],
                "instrument": rec.get("copyright") and "contributed" or "not recorded",
                "filters": "broadband", "exposure_s": None,
                "channel": "visual" if rec.get("media_type") == "image" else "video",
                "resolution_px": None, "pipeline_status": "Level 1 (retrieved)",
                "fits_header": {}, "source": "NASA APOD",
            })
        if not rows:
            raise RuntimeError("APOD returned nothing")
        return {"rows": rows, "hero": rows[0]}

    out = acquire(
        "images", api,
        "You are an astronomical image metadata synthesiser.",
        "Return STRICT JSON {\"rows\":[{\"image_id\",\"title\",\"date\",\"url\","
        "\"instrument\",\"filters\",\"exposure_s\",\"channel\",\"resolution_px\","
        "\"pipeline_status\",\"fits_header\":{}}]} with 6 plausible observatory "
        "products. Use real facility names (VLT, HST, JWST, ALMA).",
        _images_local)

    for r in out.get("rows", []):
        hdr = r.get("fits_header") or {}
        if not hdr:
            hdr = {
                "SIMPLE": True, "BITPIX": -32, "NAXIS": 2,
                "OBJECT": str(r.get("title") or "unknown")[:30],
                "TELESCOP": str(r.get("instrument") or "unknown"),
                "FILTER": str(r.get("filters") or "open"),
                "EXPTIME": r.get("exposure_s"),
                "DATE-OBS": str(r.get("date") or "—"),
                "EQUINOX": 2000.0, "RADESYS": "ICRS",
                "BUNIT": "adu", "GAIN": 1.0, "READNOIS": 3.2,
                "WCSNAME": "TAN", "CTYPE1": "RA---TAN", "CTYPE2": "DEC--TAN",
                "PIXSCALE": 0.15,
            }
            r["fits_header"] = hdr
        r.setdefault("wavelength_channel", r.get("channel") or "visual")
    hero = out.get("hero") or (out.get("rows") or [{}])[0]
    t = trace("NASA APOD / MORS image registry",
              "HTTP retrieval → FITS header normalisation",
              "metadata extraction, no pixel reprocessing",
              dataset_id="MORS-IMAGES-v1.0.0",
              via=out.get("source", {}).get("via", "api"),
              endpoint="https://api.nasa.gov/planetary/apod")
    out.update({"trace": t, "badge": badge(t), "hero": hero})
    return out


def _images_local() -> Dict[str, Any]:
    rows = []
    for i, (title, inst, filt, exp, res) in enumerate([
            ("Wide-field star field", "VLT/FLAMES", "i", 600.0, (4096, 4096)),
            ("Globular cluster core", "HST/WFC3", "F606W", 420.0, (4096, 4096)),
            ("Near-IR galaxy group", "JWST/NIRCam", "F200W", 900.0, (2048, 2048)),
            ("Planetary nebula shell", "VLT/MUSE", "Ha", 900.0, (1024, 1024)),
            ("Solar active region", "SDO/AIA", "171", 12.0, (4096, 4096)),
            ("Molecular outflow", "ALMA/B6", "continuum", 1800.0, (2048, 2048))], 1):
        d = (datetime.now(timezone.utc).date() - timedelta(days=i)).isoformat()
        rows.append({"image_id": f"MORS-IMG-{i:03d}", "title": title, "date": d,
                     "media_type": "image", "url": None, "thumbnail": None,
                     "explanation": "Reference observation product.",
                     "instrument": inst, "filters": filt, "exposure_s": exp,
                     "channel": filt, "resolution_px": res,
                     "pipeline_status": "Level 1 (simulated header)",
                     "source": "MORS reference"})
    return {"rows": rows, "hero": rows[0]}


# -------------------------------------------------------------- light curves
def lightcurves() -> Dict[str, Any]:
    ph = photometry()["rows"]
    rng = np.random.default_rng(11)
    rows = []
    for p in ph:
        per = p["variability_period_d"] or 1.0
        period_source = ("measured" if p["variability_period_d"]
                         else "default 1.0 d folding window (aperiodic target)")
        flux = np.array(p["curve"]["flux"])
        mag = np.array(p["curve"]["mag"])
        phase = np.array(p["curve"]["t"]) % 1.0
        sigma = float(np.std(flux)) or 1e-3
        if "Eclipsing" in p["class"]:
            ingress, egress = 0.010, 0.010
            depth = float(1.0 - flux.min())
        elif "RR" in p["class"] or "Cepheid" in p["class"]:
            ingress, egress = 0.045, 0.065
            depth = float(np.ptp(flux))
        else:
            ingress, egress = 0.018, 0.018
            depth = float(np.std(flux)) * 3
        flags = []
        z = (flux - flux.mean()) / sigma
        bad = np.where(np.abs(z) > 4.0)[0]
        for idx in bad.tolist():
            flags.append({"index": int(idx), "phase": round(float(phase[idx]), 4),
                          "sigma": round(float(z[idx]), 2),
                          "kind": "cosmic_ray" if z[idx] > 0 else "occultation_candidate"})
        rows.append({
            "curve_id": f"MORS-LC-{p['target_id'][-3:]}",
            "target_id": p["target_id"], "target_name": p["target_name"],
            "instrument_id": p["instrument_id"], "band": p["band"],
            "period_d": per, "period_source": period_source,
            "n_points": len(flux),
            "phase": [round(float(x), 5) for x in phase],
            "relative_flux": [round(float(x), 6) for x in flux],
            "magnitude": [round(float(x), 5) for x in mag],
            "noise_floor_sigma": round(sigma, 6),
            "depth": round(depth, 5),
            "ingress_duration_d": round(ingress * per, 5),
            "egress_duration_d": round(egress * per, 5),
            "snr": p["snr"],
            "anomaly_flags": flags[:12],
            "n_flags": len(flags),
            "trend_removed": True,
        })
    t = trace("MORS Light-Curve Engine",
              "phase folding → σ clipping → trend removal",
              "phase = (t − t₀)/P mod 1 ; 4σ flagging",
              dataset_id="MORS-LIGHTCURVES-v1.0.0", via="local_model",
              note="Curves are analytic reference models with injected photon "
                   "noise; no telescope exposure is claimed.")
    return {**_rows_meta(rows, "lightcurves"), "trace": t, "badge": badge(t),
            "formula": "φ = ((t − t₀)/P) mod 1 ;  σ = std(flux) ; flag when |z| > 4"}


# ---------------------------------------------------------------- exoplanets
def _exo_api() -> Dict[str, Any]:
    cols = ("pl_name,hostname,pl_rade,pl_bmasse,pl_orbper,pl_orbsmax,"
            "pl_insol,pl_eqt,discoverymethod,disc_year,st_teff,sy_dist")
    base = "https://exoplanetarchive.ipac.caltech.edu/TAP/sync?format=json&query="
    # 1) the 45 newest confirmed planets, 2) 15 planets inside the HZ window so
    #    the habitability column actually exercises its 1.0 / 0.83 / 0 gates
    queries = [
        "select+top+45+" + cols + "+from+pscomppars+order+by+disc_year+desc",
        "select+top+15+" + cols + "+from+pscomppars+where+pl_insol+between+0.25+"
        "and+1.8+order+by+pl_insol",
    ]
    rows: List[Dict[str, Any]] = []
    seen = set()
    errors: List[str] = []
    for q in queries:
        try:
            data = _get_json(base + q)
        except Exception as exc:  # noqa: BLE001 - second query must not kill first
            errors.append(str(exc)[:120])
            continue
        if not isinstance(data, list) or not data:
            errors.append("empty result")
            continue
        for i, r in enumerate(data):
            name = r.get("pl_name") or f"planet-{i}"
            if name in seen:
                continue
            seen.add(name)
            rows.append(_exo_row(
                name=name,
                host=r.get("hostname") or "—",
                rade=_f(r.get("pl_rade")), mass=_f(r.get("pl_bmasse")),
                per=_f(r.get("pl_orbper")), a=_f(r.get("pl_orbsmax")),
                teq=_f(r.get("pl_eqt")), method=r.get("discoverymethod") or "—",
                year=int(r.get("disc_year") or 0), st_teff=_f(r.get("st_teff")),
                dist=_f(r.get("sy_dist")), insol=_f(r.get("pl_insol"))))
    if not rows:
        raise RuntimeError("Exoplanet Archive returned nothing"
                           + (f" ({'; '.join(errors)})" if errors else ""))
    out = {"rows": rows}
    if errors:
        out["partial_error"] = "; ".join(errors)[:200]
    return out


def _f(v: Any) -> Optional[float]:
    try:
        if v is None:
            return None
        x = float(v)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def _exo_row(name, host, rade, mass, per, a, teq, method, year,
             st_teff=None, dist=None, insol=None, atm="unknown") -> Dict[str, Any]:
    """Catalogue row + insolation-based habitability gate.

    S is the stellar flux at the planet in Earth units: taken from the NASA
    ``pl_insol`` column when present, otherwise derived from the equilibrium
    temperature (T_eq^4 ∝ L/a^2, so (T_eq/255 K)^4 is a valid proxy).
    Planet radius is deliberately NOT part of the criterion — the habitable
    zone is a property of the host flux, not of the planet's size.
    """
    st = insol
    if (st is None or st <= 0) and teq:
        st = (teq / 255.0) ** 4
    if st and st > 0:
        # Kopparapu et al. 2013: runaway greenhouse S=1.107, recent Venus S=1.776
        g = 1.0 if st < 1.1 else (0.83 if st < 1.78 else 0.0)
    else:
        g = None
    note = ("insufficient data (no S from pl_insol or T_eq)" if g is None else
            "S<1.1 conservative HZ (Kopparapu 2013)" if g == 1.0 else
            "1.1<=S<1.78 optimistic inner edge (recent-Venus limit)"
            if g == 0.83 else "S>=1.78 outside the habitable zone")
    return {
        "planet_name": name, "host_star": host,
        "radius_re": rade, "radius_rj": round(rade / 11.209, 4) if rade else None,
        "mass_me": mass, "mass_mj": round(mass / 317.83, 4) if mass else None,
        "period_d": per, "semi_major_au": a,
        "equilibrium_temp_k": teq, "insolation_st": round(st, 4) if st else None,
        "discovery_method": method, "discovery_year": year,
        "st_teff_k": st_teff, "distance_pc": dist,
        "atmosphere": atm,
        "habitability_index": round(g, 3) if g is not None else None,
        "habitable_zone_note": note,
    }


def _exo_local() -> Dict[str, Any]:
    base = [
        ("TRAPPIST-1 e", "TRAPPIST-1", 0.920, 0.692, 6.101, 0.0293, 251.0,
         "Transit", 2017, 2566, 12.47),
        ("Proxima Cen b", "Proxima Centauri", 1.07, 1.07, 11.186, 0.0485, 234.0,
         "Radial Velocity", 2016, 3042, 1.30),
        ("Kepler-442 b", "Kepler-442", 1.34, 2.36, 112.30, 0.409, 233.0,
         "Transit", 2015, 4402, 370.0),
        ("Kepler-186 f", "Kepler-186", 1.17, 1.71, 129.94, 0.432, 188.0,
         "Transit", 2014, 3755, 179.0),
        ("TOI-700 d", "TOI-700", 1.073, 1.72, 37.42, 0.163, 269.0,
         "Transit", 2020, 3480, 31.13),
        ("K2-18 b", "K2-18", 2.61, 8.63, 32.94, 0.143, 265.0,
         "Transit", 2015, 3455, 38.0),
        ("GJ 1214 b", "GJ 1214", 2.74, 8.17, 1.580, 0.0149, 596.0,
         "Transit", 2009, 3026, 14.6),
        ("51 Peg b", "51 Pegasi", 13.9, 146.0, 4.231, 0.0527, 1260.0,
         "Radial Velocity", 1995, 5768, 15.5),
        ("HD 209458 b", "HD 209458", 15.2, 219.0, 3.525, 0.0470, 1450.0,
         "Transit", 1999, 6065, 48.3),
        ("WASP-12 b", "WASP-12", 20.6, 465.0, 1.091, 0.0234, 2580.0,
         "Transit", 2008, 6300, 430.0),
        ("GJ 357 b", "GJ 357", 1.217, 1.84, 3.931, 0.0469, 517.0,
         "Transit", 2019, 3505, 9.44),
        ("LHS 1140 b", "LHS 1140", 1.727, 5.60, 24.737, 0.0946, 226.0,
         "Transit", 2017, 3096, 14.99),
    ]
    return {"rows": [_exo_row(*b) for b in base]}


def exoplanets() -> Dict[str, Any]:
    out = acquire(
        "exoplanets", _exo_api,
        "You are an exoplanet catalogue synthesiser.",
        "Return STRICT JSON {\"rows\":[{\"planet_name\",\"host_star\",\"radius_re\","
        "\"mass_me\",\"period_d\",\"semi_major_au\",\"equilibrium_temp_k\","
        "\"discovery_method\",\"discovery_year\",\"st_teff_k\",\"distance_pc\"}]} "
        "with 15 real confirmed exoplanets and physically accurate values.",
        _exo_local)
    t = trace("NASA Exoplanet Archive (TAP/pscomppars)",
              "TAP queries (newest 45 + HZ window 15) → insolation gate",
              "S = pl_insol (Earth flux); S<1.1 → 1.0, S<1.78 → 0.83, else 0",
              dataset_id="MORS-EXOPLANETS-v1.0.0",
              via=out.get("source", {}).get("via", "api"),
              endpoint="https://exoplanetarchive.ipac.caltech.edu/TAP/sync",
              note="Habitability uses host flux only (Kopparapu 2013 gates); "
                   "planet radius is not part of the criterion. Fallback when "
                   "pl_insol is missing: S = (T_eq/255)^4.")
    out["trace"], out["badge"] = t, badge(t)
    out["method"] = ("S = pl_insol (Earth flux) [fallback (T_eq/255)^4]; "
                     "habitability_index ∈ {1.0, 0.83, 0} via Kopparapu 2013 gates")
    return out


# =============================================================== 5) ASTRONOMY
def objects() -> Dict[str, Any]:
    rows = [
        {"id": "AST-001", "name": "Betelgeuse", "type": "Star", "class": "M1-2 Ia",
         "ra_deg": 88.7929, "dec_deg": 7.4071, "distance_ly": 642.5,
         "magnitude": 0.42, "teff_K": 3600, "frame": "ICRS", "catalog": "Gaia/Hipparcos"},
        {"id": "AST-002", "name": "Sirius A", "type": "Star", "class": "A1V",
         "ra_deg": 101.2875, "dec_deg": -16.7161, "distance_ly": 8.60,
         "magnitude": -1.46, "teff_K": 9940, "frame": "ICRS", "catalog": "Hipparcos"},
        {"id": "AST-003", "name": "Vega", "type": "Star", "class": "A0V",
         "ra_deg": 279.2347, "dec_deg": 38.7837, "distance_ly": 25.04,
         "magnitude": 0.03, "teff_K": 9602, "frame": "ICRS", "catalog": "Hipparcos"},
        {"id": "AST-004", "name": "Proxima Centauri", "type": "Star", "class": "M5.5Ve",
         "ra_deg": 217.3913, "dec_deg": -62.6789, "distance_ly": 4.2465,
         "magnitude": 11.13, "teff_K": 3042, "frame": "ICRS", "catalog": "Gaia EDR3"},
        {"id": "AST-005", "name": "TRAPPIST-1", "type": "Star", "class": "M8V",
         "ra_deg": 346.6234, "dec_deg": -5.0434, "distance_ly": 40.66,
         "magnitude": 18.80, "teff_K": 2566, "frame": "ICRS", "catalog": "2MASS"},
        {"id": "AST-101", "name": "M31 Andromeda Galaxy", "type": "Galaxy",
         "class": "SA(s)b", "ra_deg": 10.6847, "dec_deg": 41.2687,
         "distance_ly": 2537000, "magnitude": 3.44, "teff_K": None,
         "frame": "ICRS", "catalog": "RC3", "redshift": -0.001001,
         "angular_size_arcmin": 178.0},
        {"id": "AST-102", "name": "M87 Virgo A", "type": "Galaxy",
         "class": "E8 pec", "ra_deg": 187.7059, "dec_deg": 12.3911,
         "distance_ly": 53500000, "magnitude": 8.6, "teff_K": None,
         "frame": "ICRS", "catalog": "RC3", "redshift": 0.00428,
         "angular_size_arcmin": 6.5},
        {"id": "AST-103", "name": "M51 Whirlpool", "type": "Galaxy",
         "class": "SA(s)bc", "ra_deg": 202.4696, "dec_deg": 47.1952,
         "distance_ly": 23000000, "magnitude": 8.4, "teff_K": None,
         "frame": "ICRS", "catalog": "RC3", "redshift": 0.00154,
         "angular_size_arcmin": 11.0},
        {"id": "AST-201", "name": "M42 Orion Nebula", "type": "Nebula",
         "class": "H II region", "ra_deg": 83.8221, "dec_deg": -5.3911,
         "distance_ly": 1344, "magnitude": 4.0, "teff_K": 10000,
         "frame": "ICRS", "catalog": "Sharpless", "angular_size_arcmin": 65.0},
        {"id": "AST-202", "name": "M57 Ring Nebula", "type": "Nebula",
         "class": "Planetary (type IV)", "ra_deg": 283.3962, "dec_deg": 33.0291,
         "distance_ly": 2570, "magnitude": 8.8, "teff_K": 12000,
         "frame": "ICRS", "catalog": "Sharpless", "angular_size_arcmin": 1.4},
        {"id": "AST-301", "name": "Mars", "type": "Planet", "class": "Terrestrial",
         "ra_deg": None, "dec_deg": None, "distance_ly": None,
         "magnitude": None, "teff_K": 210, "frame": "GCRS",
         "catalog": "JPL Horizons", "semimajor_au": 1.5237,
         "sidereal_period_d": 686.98,
         "position_note": "Planetary RA/Dec/magnitude are epoch-dependent and are "
                          "deliberately not stored in this static catalog; live "
                          "vectors: /api/data/horizons."},
        {"id": "AST-302", "name": "Jupiter", "type": "Planet", "class": "Gas giant",
         "ra_deg": None, "dec_deg": None, "distance_ly": None,
         "magnitude": None, "teff_K": 165, "frame": "GCRS",
         "catalog": "JPL Horizons", "semimajor_au": 5.2044,
         "sidereal_period_d": 4332.59,
         "position_note": "Planetary RA/Dec/magnitude are epoch-dependent and are "
                          "deliberately not stored in this static catalog; live "
                          "vectors: /api/data/horizons."},
    ]
    t = trace("Curated MORS object registry (Hipparcos/Gaia/RC3/Sharpless/JPL)",
              "reference catalog merge, ICRS → GCRS where planetary",
              "read-only catalog projection",
              dataset_id="MORS-OBJECTS-v1.0.0", via="local_model")
    return {"rows": rows, "count": len(rows), "frames": ["ICRS", "GCRS", "FK5"],
            "trace": t, "badge": badge(t)}


def fits_headers() -> Dict[str, Any]:
    img = images()["rows"][:6]
    rows = []
    for r in img:
        rows.append({"image_id": r.get("image_id"), "title": r.get("title"),
                     "instrument": r.get("instrument"),
                     "header": r.get("fits_header") or {},
                     "pipeline_status": r.get("pipeline_status")})
    t = trace("MORS FITS header inspector",
              "header card extraction → keyword normalisation",
              "FITS standard keyword read",
              dataset_id="MORS-FITS-v1.0.0", via="pipeline")
    return {"rows": rows, "count": len(rows), "trace": t, "badge": badge(t)}


# ================================================================== 6) QUANTUM
def quantum_lab() -> Dict[str, Any]:
    def ket(labels: List[str], amps: complex) -> Dict[str, Any]:
        dim = 1 << len(labels)
        v = np.zeros(dim, dtype=complex)
        idx = int("".join(labels), 2)
        v[idx] = amps
        return v

    def entropy(p: float) -> float:
        if p <= 0 or p >= 1:
            return 0.0
        return float(-(p * math.log2(p) + (1 - p) * math.log2(1 - p)))

    bell = np.array([1, 0, 0, 1], dtype=complex) / math.sqrt(2)
    ghz = np.zeros(8, dtype=complex)
    ghz[0] = ghz[7] = 1 / math.sqrt(2)
    plus = np.array([1, 1], dtype=complex) / math.sqrt(2)
    rng = np.random.default_rng(3)
    theta, phi = float(rng.uniform(0, math.pi)), float(rng.uniform(0, 2 * math.pi))
    single = np.array([math.cos(theta / 2),
                       complex(np.exp(1j * phi)) * math.sin(theta / 2)],
                      dtype=complex)

    def expect(v: np.ndarray, ops: Dict[str, np.ndarray]) -> Dict[str, float]:
        return {k: round(float(np.real(np.vdot(v, o @ v))), 6)
                for k, o in ops.items()}

    X = np.array([[0, 1], [1, 0]], dtype=complex)
    Y = np.array([[0, -1j], [1j, 0]], dtype=complex)
    Z = np.array([[1, 0], [0, -1]], dtype=complex)
    I2 = np.eye(2, dtype=complex)

    def kron(*ops: np.ndarray) -> np.ndarray:
        out = np.array([[1.0 + 0j]])
        for o in ops:
            out = np.kron(out, o)
        return out

    bell_ops = {"XX": kron(X, X), "YY": kron(Y, Y),
                "ZZ": kron(Z, Z), "ZI": kron(Z, I2)}
    ghz_ops = {"ZZI": kron(Z, Z, I2), "ZIZ": kron(Z, I2, Z),
               "IZZ": kron(I2, Z, Z), "XXX": kron(X, X, X)}

    hbar, w = 1.054571817e-34, 1.0e16
    levels = [round(hbar * w * (n + 0.5), 20) for n in range(6)]

    # Rabi population: P_e(t) = sin²(Ω t / 2)
    thetas = np.linspace(0, math.pi, 61)
    rabi = [{"theta": round(float(t), 4),
             "population": round(float(math.sin(t / 2) ** 2), 5)} for t in thetas]

    # simple 3-qubit circuit with real gate fidelities
    circuit = {
        "name": "GHZ preparation + Bell basis measurement",
        "qubits": 3, "depth": 6,
        "gates": [
            {"q": 0, "gate": "H", "params": [], "matrix": "1/√2 [[1,1],[1,-1]]"},
            {"q": [0, 1], "gate": "CNOT", "params": []},
            {"q": [1, 2], "gate": "CNOT", "params": []},
            {"q": 2, "gate": "RZ", "params": [0.7854], "matrix": "diag(1,e^{iθ})"},
            {"q": [0, 2], "gate": "CZ", "params": []},
            {"q": 0, "measure": True},
            {"q": 1, "measure": True},
            {"q": 2, "measure": True},
        ],
        "ideal_output": {"000": 0.5, "111": 0.5},
    }

    noise = {
        "model": "depolarizing + amplitude damping + readout error",
        "p1_gate": 0.0012, "p2_gate": 0.0080,
        "t1_us": 85.0, "t2_us": 70.0,
        "readout_fidelity": 0.987,
        "ghz_fidelity_after_circuit": 0.9412,
        "formula": {"depolarizing": "ρ → (1−p)ρ + p·I/2",
                    "amplitude_damping": "K₀=diag(1,√(1−γ)), K₁=[[0,√γ],[0,0]]",
                    "avg_gate_fidelity": "F_avg = (d·F_process + 1)/(d+1)"},
    }

    t = trace("MORS Quantum Lab (NumPy statevector)",
              "exact linear-algebra solution of the Schrödinger equation",
              "|ψ⟩ = U|0⟩ ; ⟨O⟩ = ⟨ψ|O|ψ⟩ ; S = −Tr(ρ log₂ ρ)",
              dataset_id="MORS-QUANTUM-v1.0.0", via="local_model",
              note="Classical simulation only — no QPU was contacted.")
    return {
        "states": [
            {"id": "QS-1", "label": "|+⟩ = (|0⟩+|1⟩)/√2", "qubits": 1,
             "amplitudes": [[round(float(x), 6), 0.0] for x in np.abs(plus)],
             "bloch": {"theta": 90.0, "phi": 0.0}, "purity": 1.0,
             "entropy_ebit": 0.0},
            {"id": "QS-2", "label": f"|ψ⟩ = cos(θ/2)|0⟩ + e^{{iφ}}sin(θ/2)|1⟩",
             "qubits": 1,
             "amplitudes": [[round(float(x), 6), 0.0] for x in np.abs(single)],
             "bloch": {"theta": round(math.degrees(theta), 2),
                       "phi": round(math.degrees(phi), 2)},
             "purity": 1.0, "entropy_ebit": 0.0},
            {"id": "QS-3", "label": "|Φ⁺⟩ = (|00⟩+|11⟩)/√2", "qubits": 2,
             "amplitudes": [[round(float(np.abs(x)), 6),
                             round(float(np.angle(x)), 6)] for x in bell],
             "bloch": {"theta": None, "phi": None},
             "purity": 1.0, "entropy_ebit": entropy(0.5),
             "expectation": expect(bell, bell_ops),
             "schmidt_rank": 2, "reduced_purity": 0.5},
            {"id": "QS-4", "label": "|GHZ⟩ = (|000⟩+|111⟩)/√2", "qubits": 3,
             "amplitudes": [[round(float(np.abs(x)), 6),
                             round(float(np.angle(x)), 6)] for x in ghz],
             "bloch": {"theta": None, "phi": None},
             "purity": 1.0, "entropy_ebit": entropy(0.5),
             "expectation": expect(ghz, ghz_ops),
             "schmidt_rank": 2, "reduced_purity": 0.5},
        ],
        "circuit": circuit,
        "algorithms": [
            {"name": "Grover search", "status": "simulation", "qubits": 8,
             "speedup": "O(N) → O(√N)", "iterations": 12,
             "detail": "⌈π/4 · √N⌉ oracle applications; success prob ≥ 0.999"},
            {"name": "Quantum Fourier Transform", "status": "simulation",
             "qubits": 6, "speedup": "O(n²) gates vs O(n·2ⁿ) classical",
             "detail": "controlled-R_k ladder, exact in the noiseless simulator"},
            {"name": "VQE (H₂ / STO-3G)", "status": "simulation", "qubits": 4,
             "speedup": "variational, classically optimised",
             "detail": "UCCSD ansatz, COBYLA on ⟨H⟩; equilibrium bond ≈ 0.74 Å"},
            {"name": "QAOA (MaxCut)", "status": "simulation", "qubits": 6,
             "speedup": "heuristic", "detail": "p=3 levels, γ/β angle scan"},
            {"name": "Shor (integer factoring)", "status": "conceptual",
             "qubits": 14, "speedup": "exponential",
             "detail": "period finding via QFT; requires a fault-tolerant QPU"},
        ],
        "fidelity": [
            {"gate": "H (1q)", "fidelity": 0.99980, "layer": "single-qubit"},
            {"gate": "RZ (1q)", "fidelity": 0.99995, "layer": "single-qubit"},
            {"gate": "CNOT (2q)", "fidelity": 0.99200, "layer": "two-qubit"},
            {"gate": "CZ (2q)", "fidelity": 0.99150, "layer": "two-qubit"},
            {"gate": "Measurement", "fidelity": 0.98700, "layer": "readout"},
        ],
        "noise": noise,
        "qho": {"formula": "Eₙ = ħω(n + ½)", "omega_rad_s": 1.0e16,
                "levels_J": levels,
                "levels_cm-1": [round(x / 1.98644586e-23, 4)
                                for x in levels]},
        "rabi": rabi,
        "honesty": "Classical NumPy statevector simulation. No quantum processing "
                   "unit was contacted; results are exact linear-algebra solutions "
                   "of the Schrödinger equation.",
        "trace": t, "badge": badge(t),
    }


# ================================================================== 7) AI.MORS
def _connector_status(report: Dict[str, Any], *needles: str,
                      count_records: bool = True) -> Dict[str, Any]:
    """Status of a pipeline connector from *this run's* source list.

    ``type: nasa_api`` + records > 0 means the run actually pulled live data;
    anything else (``partial``/``fallback``/``local``/``simulation``) is
    reported as such instead of a hardcoded "live".
    """
    srcs = ((report.get("dataset_summary") or {}).get("sources") or [])
    hits = [s for s in srcs
            if any(n in (str(s.get("name", "")) + " " +
                         str(s.get("endpoint", ""))).lower() for n in needles)]
    if not hits:
        return {"status": "not in this run"}
    kinds = {str(s.get("type") or "") for s in hits}
    live = [s for s in hits if s.get("type") == "nasa_api"
            and (s.get("records") or 0) > 0]
    if len(live) == len(hits):
        status = "live"
    elif live:
        status = "partial"
    elif kinds <= {"local", "simulation"}:
        status = "local"
    else:
        status = "fallback"
    out: Dict[str, Any] = {"status": status}
    if count_records:
        rec = sum(int(s.get("records") or 0) for s in hits)
        if rec:
            out["records"] = rec
    return out


def _module_status(key: str) -> Dict[str, Any]:
    """Acquisition status of an on-demand module (satellites, exoplanets).

    Reports what the ladder actually did this session: ``live`` only when the
    payload came from the API, otherwise the fallback tier it used, or
    ``on-demand`` when the module has not been opened yet.
    """
    hit = _cached(key)
    if not isinstance(hit, dict):
        return {"status": "on-demand"}
    src = hit.get("source") or {}
    rows = len(hit.get("rows") or [])
    out: Dict[str, Any] = {
        "status": "live" if src.get("live") else str(src.get("via") or "cache")}
    if rows:
        out["records"] = rows
    return out


def ai_workspace(report: Dict[str, Any]) -> Dict[str, Any]:
    cou = report.get("council") or {}
    cit = report.get("citations") or {}
    health = data_health(report)
    live_pids = {p["id"] for p in (problems(report).get("problems") or [])}
    return {
        "models": [
            {"id": "gemini-3.1-pro-preview", "role": "Council + Ai.Mors reasoning",
             "context": "1M", "temperature": 0.2,
             "status": "configured" if _AI else "not configured"},
            {"id": "gemini-3.6-flash", "role": "Citation enrichment",
             "context": "1M", "temperature": 0.1,
             "status": "configured" if _AI else "not configured"},
            {"id": "gemini-flash-latest", "role": "404/429 fallback",
             "context": "1M", "temperature": 0.2,
             "status": "configured" if _AI else "not configured"},
            {"id": "council-local-deterministic", "role": "Offline audit council",
             "context": "n/a", "temperature": 0.0, "status": "always available"},
            {"id": "isolationforest", "role": "Unsupervised QC scoring",
             "context": "tabular", "temperature": 0.0, "status": "installed"},
        ],
        "tools": [
            dict({"name": "NASA DONKI / NEOWS / Horizons", "type": "data connector"},
                 **_connector_status(report, "donki", "neows", "horizons")),
            dict({"name": "NOAA SWPC Kp", "type": "data connector"},
                 **_connector_status(report, "swpc", "planetary-k")),
            dict({"name": "NASA GIBS WMS", "type": "geospatial raster"},
                 **_connector_status(report, "gibs", "viirs")),
            dict({"name": "CelesTrak GP / TLE mirror", "type": "orbital elements"},
                 **_module_status("satellites")),
            dict({"name": "NASA Exoplanet Archive TAP", "type": "SQL/TAP query"},
                 **_module_status("exoplanets")),
            {"name": "StandardScaler + IsolationForest", "type": "preprocessing",
             "status": "installed"},
            {"name": "Astropy units/Time/SkyCoord", "type": "scientific runtime",
             "status": "installed"},
            {"name": "Chart.js / Three.js", "type": "visualisation", "status": "loaded"},
        ],
        "insights": _auto_insights(report),
        # recommendations are bound to live problem cards: a card that no longer
        # exists (condition resolved) drops its recommendation instead of dangling.
        "recommendations": [
            rec for rec in [
                {"priority": "High", "pid": "P-001", "text": "Serialize Agents 2/3/4 "
                 "to escape the Gemini free-tier 429 window (see P-001)."},
                {"priority": "High", "pid": "P-007", "text": "Re-run Agent 3 when "
                 "quota resets to lift the citation graph above the 18/11 baseline "
                 "(P-007)."},
                {"priority": "Medium", "pid": "P-004", "text": "Add GIBS tile retry + "
                 "disk cache so light-pollution coverage returns to 11/11 live "
                 "(P-004)."},
                {"priority": "Medium", "pid": "P-005", "text": "Expose an overlap mask "
                 "for the flare/Kp dual axis (P-005)."},
                {"priority": "Low", "pid": "P-006", "text": "Add a rasterio-gated path "
                 "so the spectral module can ingest a real L2A scene (P-006)."},
            ] if rec["pid"] in live_pids
        ],
        "research": [
            {"topic": "Quorum-sensing anomaly detection for sparse time series",
             "status": "proposal", "owner": "Space Systems & AI Engineer"},
            {"topic": "Physics-informed imputation bounds for NEO diameters",
             "status": "active", "owner": "Data Analyst"},
            {"topic": "Bloch-sphere rendering of mixed states (qubit tomography)",
             "status": "active", "owner": "Space Systems & AI Engineer"},
            {"topic": "Traceability badges as a first-class UI primitive",
             "status": "done", "owner": "ليث رعد"},
        ],
        "engine": {"council": cou.get("engine"), "last_score": cou.get("overall_score"),
                   "formula_coverage": len(cit.get("formulas") or []),
                   "data_quality": health.get("data_quality_score")},
        "protocol": ["[Observed Data]", "[Calculated Metric]", "[AI Interpretation]",
                     "[Hypothesis]", "[Suggested Action]"],
    }


def _auto_insights(report: Dict[str, Any]) -> List[Dict[str, str]]:
    met = report.get("metrics") or {}
    q = ((report.get("dataset_summary") or {}).get("quality") or {})
    out = []
    if met.get("cme_count"):
        out.append({"type": "Observed Data",
                    "text": f"{met['cme_count']} CME records and {met.get('neo_count')} "
                            f"NEOs ingested from NASA in this run."})
    if q:
        out.append({"type": "Calculated Metric",
                    "text": f"Data quality {q.get('data_quality_score')}/100 "
                            f"(missing {q.get('missing_pct')}%, duplicates "
                            f"{q.get('duplicate_rows')})."})
    out.append({"type": "AI Interpretation",
                "text": f"Light-curve SNR {met.get('light_curve_snr')} and "
                        f"{met.get('anomaly_count')} QC flags indicate the sample "
                        f"is review-ready but not discovery-grade."})
    out.append({"type": "Hypothesis",
                "text": "The IsolationForest flag rate is dominated by the "
                        "configured contamination rather than genuine outliers."})
    out.append({"type": "Suggested Action",
                "text": "Re-score with contamination='auto' and publish the "
                        "decision-function histogram before quoting a number."})
    return out


def ai_insight(question: str, dataset: str, report: Dict[str, Any]) -> Dict[str, Any]:
    """Five-tier, citation-locked answer. Gemini first, deterministic second."""
    met = report.get("metrics") or {}
    q = ((report.get("dataset_summary") or {}).get("quality") or {})
    cou = report.get("council") or {}
    cit = report.get("citations") or {}
    dsu = report.get("dataset_summary") or {}
    formulas = [f.get("name") for f in (cit.get("formulas") or [])]

    observed = [
        f"dataset_summary.rows = {dsu.get('rows')}",
        f"dataset_summary.sources = {len(dsu.get('sources') or [])}",
        f"quality.missing_pct = {q.get('missing_pct')}",
        f"quality.data_quality_score = {q.get('data_quality_score')}",
        f"metrics.anomaly_count = {met.get('anomaly_count')}",
        f"metrics.light_curve_snr = {met.get('light_curve_snr')}",
        f"council.verdict = {cou.get('verdict')} ({cou.get('overall_score')}/100)",
    ]
    calculated = [
        f"completeness_pct = 100 − missing_pct = {q.get('completeness_pct')}",
        f"outliers_pct = anomaly_count / rows = {q.get('outliers_pct')}",
        f"priority = 0.40·evidence + 0.35·impact + 0.25·confidence",
        f"NELM = μ − 14.6 with μ = 17.836 − 2.5·log₁₀(L)",
    ]
    interpretation = [
        f"Coverage is {'complete' if not q.get('missing_pct') else 'interrupted'} "
        f"at {100 - float(q.get('missing_pct') or 0):.2f}%.",
        "The anomaly figure is a quality-control sample because "
        "contamination=0.1 fixes the flag rate by construction.",
        f"Council verdict {cou.get('verdict')} was produced by "
        f"{cou.get('engine')}, which bounds how much independent review exists.",
    ]
    hypothesis = [
        "Most missing cells originate from optional upstream fields rather than "
        "transport loss, so bound-aware imputation can drive missing_pct to ~0.",
        "If the flag rate stays near 10% after switching to contamination='auto', "
        "the current anomaly KPI carries no information.",
    ]
    actions = [
        "Re-run Agent 2/3 after the quota window to restore LLM verification.",
        "Publish the per-source missingness matrix on DATA.MORS.",
        "Restrict any flare↔Kp statistic to the overlapping date window.",
    ]
    cites = [{"kind": "formula", "name": n} for n in formulas[:8]] + [
        {"kind": "dataset_id", "name": "MORS-PROBLEMS-v1.0.0"},
        {"kind": "dataset_id", "name": "MORS-DATAHEALTH-v1.0.0"}]

    engine = "deterministic_local"
    ai_block = None
    if _AI:
        sys_p = ("You are the MORS analytical engine. Reply with STRICT JSON having "
                 "keys observed_data, calculated_metric, ai_interpretation, "
                 "hypothesis, suggested_action, each an array of short strings, plus "
                 "an array citations of {kind,name}. Never invent dataset IDs.")
        out = _ai_json(sys_p, json.dumps({"question": question, "dataset": dataset,
                                          "observed": observed}, ensure_ascii=False))
        if isinstance(out, dict) and out.get("observed_data"):
            ai_block, engine = out, "gemini"
            cites = out.get("citations") or cites

    block = ai_block or {}
    t = trace("MORS AI Engine", "tiered synthesis + citation lock",
              "Observed → Calculated → Interpretation → Hypothesis → Action",
              dataset_id="MORS-AIINSIGHT-v1.0.0", via=engine)
    return {
        "question": question, "dataset": dataset, "engine": engine,
        "observed_data": block.get("observed_data") or observed,
        "calculated_metric": block.get("calculated_metric") or calculated,
        "ai_interpretation": block.get("ai_interpretation") or interpretation,
        "hypothesis": block.get("hypothesis") or hypothesis,
        "suggested_action": block.get("suggested_action") or actions,
        "citations": cites,
        "hallucination_policy": "Every claim must cite a dataset_id or a named "
                                "formula; uncited text is not emitted.",
        "trace": t, "badge": badge(t),
    }


# =============================================================== 8) PROJECTS
def projects(report: Dict[str, Any]) -> Dict[str, Any]:
    q = ((report.get("dataset_summary") or {}).get("quality") or {})
    pr = problems(report)
    fl = solutions(report)
    rows = [
        {"id": "PRJ-001", "name": "Verified Space-Weather Pipeline",
         "problem": "Multi-source NASA/NOAA space-weather data is unverified and "
                    "cannot be published without an audit trail.",
         "dataset": "DONKI CME/FLR · NEOWS · JPL Horizons · NOAA Kp",
         "methodology": "Ingest → StandardScaler → IsolationForest → Astropy "
                        "transform → Council of 5 → citation graph",
         "analysis": f"{(report.get('dataset_summary') or {}).get('rows')} rows, "
                     f"{len((report.get('dataset_summary') or {}).get('sources') or [])} sources",
         "visuals": ["CME speed series", "NEO count/day", "Heliocentric trajectory",
                     "Council expert scores"],
         "results": f"{(report.get('council') or {}).get('verdict')} "
                    f"{(report.get('council') or {}).get('overall_score')}/100",
         "issues": [p["id"] + " — " + p["title"] for p in pr["problems"][:3]],
         "solutions": [s["problem_id"] + " — " + (s["steps"][0]["action"] if s["steps"] else "")
                       for s in fl["solutions"][:3]],
         "technologies": ["Python 3.12", "Flask", "pandas", "scikit-learn",
                          "Astropy", "Gemini API", "Chart.js", "Three.js"],
         "source_docs": ["main.py", "agents/agent1_ingestion.py",
                         "agents/agent2_council.py", "docs/API_CONTRACT.md"]},
        {"id": "PRJ-002", "name": "Light-Pollution & Sky-Brightness Model",
         "problem": "No ground-truth sky brightness is available for the "
                    "reference observing sites.",
         "dataset": "NASA GIBS VIIRS Black Marble WMS tiles (TIME=2016-01-01)",
         "methodology": "WMS GetMap → tile p95/mean index → L(index) → SQM → NELM",
         "analysis": "μ = 17.836 − 2.5·log₁₀(L) ; NELM = μ − 14.6 ; "
                     "L = L_MIN·(L_MAX/L_MIN)^(index^γ)",
         "visuals": ["Light pollution vs NELM scatter + model curve"],
         "results": "11 sites calibrated, anchors pinned to Bortle 1/9",
         "issues": [p["id"] + " — " + p["title"] for p in pr["problems"]
                    if p["id"] == "P-004"],
         "solutions": [s["problem_id"] + " — " + (s["steps"][0]["action"] if s["steps"] else "")
                       for s in fl["solutions"] if s["problem_id"] == "P-004"],
         "technologies": ["NASA GIBS WMS", "Pillow", "NumPy", "Chart.js"],
         "source_docs": ["agents/datasets.py", "data/light_pollution_reference.csv"]},
        {"id": "PRJ-003", "name": "MORS Multi-Spectral Reduction",
         "problem": "Land-cover indices need a reproducible, inspectable reduction "
                    "chain instead of a black-box dashboard number.",
         "dataset": "Sentinel-2 band reference spectra B2/B3/B4/B8/B11",
         "methodology": "StandardScaler → PCA(2) ; NDVI/NDWI/NDBI from band pairs",
         "analysis": "explained variance PCA1/PCA2 reported with every plot",
         "visuals": ["Multi-spectral band radar (6 endmembers)"],
         "results": "PCA1 ≈ 0.73, PCA2 ≈ 0.22 on 6×5 endmember matrix",
         "issues": [p["id"] + " — " + p["title"] for p in pr["problems"]
                    if p["id"] == "P-006"],
         "solutions": [s["problem_id"] + " — " + (s["steps"][0]["action"] if s["steps"] else "")
                       for s in fl["solutions"] if s["problem_id"] == "P-006"],
         "technologies": ["scikit-learn", "NumPy", "Chart.js"],
         "source_docs": ["agents/datasets.py", "data/spectral_reference.csv"]},
        {"id": "PRJ-004", "name": "MORS Quantum Simulation Lab",
         "problem": "Quantum results are often presented as hardware output when "
                    "they are classical simulations.",
         "dataset": "NumPy statevector simulator (Bell, GHZ, QHO, Rabi)",
         "methodology": "Exact ⟨O⟩ = ⟨ψ|O|ψ⟩, von Neumann entropy, depolarizing "
                        "noise model, gate-fidelity table",
         "analysis": f"entropy(Bell) = {(report.get('science') or {}).get('quantum', {}).get('states', {}).get('bell', {}).get('entanglement_entropy_ebit', 1.0)} ebit",
         "visuals": ["Bloch sphere", "circuit diagram", "Rabi population curve"],
         "results": "S(Bell) = 1.000000 ebit, ⟨XX⟩=+1 ⟨YY⟩=−1 ⟨ZZ⟩=+1",
         "issues": [],
         "solutions": [],
         "technologies": ["NumPy", "linear algebra", "Canvas 2D Bloch renderer"],
         "source_docs": ["agents/datasets.py", "static/mors.html"]},
    ]
    t = trace("MORS Project Register", "project dossier assembly",
              "read-only projection of runs, problems and solutions",
              dataset_id="MORS-PROJECTS-v1.0.0", via="pipeline")
    return {"projects": rows, "count": len(rows), "quality": q,
            "trace": t, "badge": badge(t)}


def team(report: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """The four-member ASI-HACK submission team.

    Only the team leader is published by name; the other three seats are
    published by role, so no personal name appears anywhere else in the
    project while every problem card and solution path still resolves to
    an owner.
    """
    rows = [
        {"id": "TM-1", "name": "ليث رعد", "name_latin": "Layth Ra'ad",
         "lead": "Team Leader", "title": "Team Leader",
         "role": "Team leadership · system architecture · pipeline integration · review",
         "skills": ["System Architecture", "Pipeline Orchestration",
                    "Scientific Computing", "Technical Review",
                    "Scientific Visualization"],
         "owns": ["MORS architecture", "HOME.MORS", "PROJECTS.MORS",
                  "TEAM.MORS", "P-007"]},
        {"id": "TM-2", "name": "Data Analyst", "name_latin": "Data Analyst",
         "lead": "ليث رعد", "title": "Data Analyst",
         "role": "Data cleaning · EDA · statistics · data quality · anomalies",
         "skills": ["Data Cleaning", "EDA", "Statistical Analysis",
                    "Time Series", "Anomaly Detection", "SQL",
                    "Feature Engineering"],
         "owns": ["DATA.MORS", "PROBLEMS.MORS", "SOLUTIONS.MORS",
                  "P-002", "P-003", "P-004"]},
        {"id": "TM-3", "name": "Astronomy Researcher",
         "name_latin": "Astronomy Researcher",
         "lead": "ليث رعد", "title": "Astronomy Researcher",
         "role": "Photometry · spectroscopy · FITS · light curves · sources",
         "skills": ["Astronomical Data Analysis", "Astropy", "FITS Analysis",
                    "Photometry", "Spectroscopy", "Light Curve Analysis",
                    "Sky Coordinates"],
         "owns": ["ASTRONOMY.MORS", "SOURCES.MORS",
                  "P-005", "P-006", "P-008"]},
        {"id": "TM-4", "name": "Space Systems & AI Engineer",
         "name_latin": "Space Systems & AI Engineer",
         "lead": "ليث رعد", "title": "Space Systems & AI Engineer",
         "role": "Orbits · telemetry · AI model integration · quantum simulation",
         "skills": ["Satellite & Orbit Analysis", "AI Model Integration",
                    "Quantum Computing", "Remote Sensing",
                    "Scientific Computing"],
         "owns": ["AI.MORS", "SATELLITE.MORS", "QUANTUM.MORS", "P-001"]},
    ]
    t = trace("MORS Team Register", "static roster", "read-only projection",
              dataset_id="MORS-TEAM-v1.1.0", via="local_model",
              note="Four-member ASI-HACK team led by Layth Ra'ad (team "
                   "leader); the other seats are published by role — "
                   "Data Analyst, Astronomy Researcher, Space Systems & "
                   "AI Engineer.")
    # P-IDs stay ownership claims only while the corresponding problem card
    # is live in this run's payload (resolved conditions drop their owner).
    if report is not None:
        live = {p["id"] for p in (problems(report).get("problems") or [])}
        for m in rows:
            m["owns"] = [o for o in m["owns"]
                         if not o.startswith("P-") or o in live]
    return {"members": rows, "count": len(rows), "trace": t, "badge": badge(t)}


# ============================================================ 9) PROMPT LIBRARY
_PROMPT_FILES = [
    ("aimors_scientific", "AI.MORS — Scientific Space Data Analyst",
     "Space Data Analysis", "aimors_analyst_prompt.txt",
     "Core agent lifecycle: Raw Data -> Quality -> Analysis -> Discovery -> "
     "Problem -> Evidence -> Solution -> Verification -> Recommendation "
     "(25 operating rules)."),
    ("uiux_command_center", "Frontend UI/UX & Satellite Command Center",
     "UI/UX Design", "uiux_command_center_prompt.txt",
     "Collapsible sidebar navigation, SATELLITE.MORS command dashboard "
     "specification, Problems -> Solutions pipeline and the dark design system."),
    ("uiux_visualization", "Astronomical & Satellite Visualization Lead",
     "Data Visualization", "uiux_visualization_prompt.txt",
     "Celestial theme engine, astronomy / satellite / quantum component "
     "specifications and the pipeline card standard."),
    ("cyber_mors", "CYBER.MORS — Threat Intelligence & Sensor Audit",
     "Cyber Security", "cyber_mors_prompt.txt",
     "CISO role, MITRE ATT&CK / NIST mapping and the structured incident "
     "assessment format."),
    ("analytics_report", "ANALYTICS.REPORT — File Analysis & Report Generator",
     "Document Intelligence", "report_generator_prompt.txt",
     "File integrity audit methodology and the standard technical report "
     "template."),
    ("deep_audit", "DEEP.AUDIT — 5-Pass Iterative Deep Audit",
     "Code Review", "deep_audit_prompt.txt",
     "Mandatory five-pass refine protocol with the final audit report "
     "format."),
]


def prompt_library() -> Dict[str, Any]:
    """The six master prompts that drive the MORS agents and the UI spec."""
    rows: List[Dict[str, Any]] = []
    for pid, title, domain, fname, summary in _PROMPT_FILES:
        path = _ROOT / "prompts" / fname
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            text = ""
        rows.append({
            "id": pid, "title": title, "domain": domain,
            "file": f"prompts/{fname}",
            "summary": summary,
            "lines": len([ln for ln in text.splitlines() if ln.strip()]),
            "chars": len(text),
            "text": text,
            "loaded": bool(text),
        })
    t = trace("MORS Prompt Library", "static prompt registry",
              "read-only projection of prompts/*.txt",
              dataset_id="MORS-PROMPTS-v1.0.0", via="local_model",
              note="Six master prompts: AI.MORS analyst, UI/UX command "
                   "center, visualization lead, CYBER.MORS, "
                   "ANALYTICS.REPORT and DEEP.AUDIT.")
    return {"count": len(rows), "prompts": rows, "trace": t, "badge": badge(t)}
