#!/usr/bin/env python3
"""
================================================================================
 ASI-HACK SPACE ANALYTICS ENGINE — Multi-Agent Pipeline Orchestrator
================================================================================
 Hackathon Track : ASI Hack - AI for Space Challenges
 Stack           : Pure Python + Flask + Google Gemini API + NASA Open APIs
 Libraries       : astropy, scikit-learn, pandas, numpy, requests, flask

 PIPELINE
   Agent 1  Ingestion / Document Parser / Astropy Cleaner  (NASA DONKI, NEOWS,
            JPL Horizons + local ./data docs -> sklearn scaling + IsolationForest)
   Agent 2  Council of 5 Astronomy Experts                  (Gemini 1.5 Pro)
   Agent 3  Proofs, Equations & Research Citations Engine   (Gemini 1.5 Flash)
   Agent 4  "Ai.Mors" conversational agent restricted to certified data

 RUN
   python main.py               -> Flask server (default http://127.0.0.1:5000)
   python main.py --selftest    -> run pipeline synchronously, print summary, exit
================================================================================
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import secrets
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------- environment
ROOT = Path(__file__).resolve().parent
if (ROOT / ".env").exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env", override=False)
    except ImportError:  # pragma: no cover
        pass

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
NASA_API_KEY = os.getenv("NASA_API_KEY", "DEMO_KEY")
GEMINI_MODEL_PRO = os.getenv("GEMINI_MODEL_PRO", "gemini-3.1-pro-preview")
GEMINI_MODEL_FLASH = os.getenv("GEMINI_MODEL_FLASH", "gemini-3.6-flash")
GEMINI_MODEL_FALLBACK = os.getenv("GEMINI_MODEL_FALLBACK", "gemini-flash-latest")
FLASK_HOST = os.getenv("FLASK_HOST", "127.0.0.1")
FLASK_PORT = int(os.getenv("FLASK_PORT", "5000"))
# SECURITY: debug defaults OFF. The Werkzeug debugger exposes a code-execution
# console, so it is only ever allowed when binding to loopback.
FLASK_DEBUG = os.getenv("FLASK_DEBUG", "0") == "1"
_IS_LOCAL = FLASK_HOST in {"127.0.0.1", "localhost", "::1"}
if FLASK_DEBUG and not _IS_LOCAL:
    print("[SECURITY] FLASK_DEBUG ignored: refusing debug mode on a non-loopback "
          "host (Werkzeug console = remote code execution risk).")
    FLASK_DEBUG = False

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
# Windows consoles (cp1252/cp1256) cannot encode Arabic/emoji — force UTF-8
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):  # pragma: no cover
        pass
log = logging.getLogger("orchestrator")

# Optional early configuration of the Gemini SDK (agents also configure lazily)
if GEMINI_API_KEY:
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        log.info("Gemini configured (key %s***, pro=%s, flash=%s)",
                 GEMINI_API_KEY[:6], GEMINI_MODEL_PRO, GEMINI_MODEL_FLASH)
    except Exception as exc:  # noqa: BLE001
        log.warning("Gemini configure failed: %s (fallbacks active)", exc)
else:
    log.warning("GEMINI_API_KEY missing -> Agents 2/3/4 use local fallbacks")

if NASA_API_KEY == "DEMO_KEY":
    log.warning("NASA_API_KEY missing -> using DEMO_KEY (rate limited)")

from agents import AiMorsAgent, CitationAgent, CouncilAgent, IngestionAgent  # noqa: E402
from agents import mors_data  # noqa: E402
from agents import sources_data  # noqa: E402

LAST_REPORT_PATH = ROOT / "last_report.json"
DATA_TTL = 300  # seconds for on-demand NASA caches


def _mors_ai(system: str, prompt: str) -> Optional[str]:
    """Gemini adapter for the MORS data layer (API -> AI -> local model)."""
    if not GEMINI_API_KEY:
        return None
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel(model_name=GEMINI_MODEL_FLASH,
                                      system_instruction=system)
        resp = model.generate_content(prompt, request_options={"timeout": 40})
        return (resp.text or "") or None
    except Exception as exc:  # noqa: BLE001 - AI is the *second* choice only
        log.info("mors AI synthesis unavailable -> local model: %s",
                 str(exc)[:160])
        return None


mors_data.configure(_mors_ai, NASA_API_KEY)


# ==================================================================== STATE
def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


class State:
    """Thread-safe pipeline state shared by the background runner & API."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.run_id: Optional[str] = None
        self.status: str = "idle"          # idle | running | completed | failed
        self.progress: int = 0
        self.current_stage: str = "idle"   # ingestion | council | citations | idle
        self.stages: List[Dict[str, Any]] = []
        self.report: Dict[str, Any] = {}
        self.updated_at: str = _utc()
        self._data_cache: Dict[str, Dict[str, Any]] = {}
        self._data_ts: Dict[str, float] = {}

    # -- helpers -----------------------------------------------------------
    def update(self, **kw: Any) -> None:
        with self.lock:
            for k, v in kw.items():
                setattr(self, k, v)
            self.updated_at = _utc()

    def snapshot(self) -> Dict[str, Any]:
        with self.lock:
            return {
                "run_id": self.run_id,
                "status": self.status,
                "progress": self.progress,
                "current_stage": self.current_stage,
                "updated_at": self.updated_at,
            }

    def get_report(self) -> Dict[str, Any]:
        with self.lock:
            return dict(self.report)

    def set_report(self, report: Dict[str, Any]) -> None:
        with self.lock:
            self.report = report

    def cached(self, key: str) -> Optional[Dict[str, Any]]:
        with self.lock:
            if time.time() - self._data_ts.get(key, 0) < DATA_TTL:
                return self._data_cache.get(key)
            return None

    def put_cache(self, key: str, value: Dict[str, Any]) -> None:
        with self.lock:
            self._data_cache[key] = value
            self._data_ts[key] = time.time()


STATE = State()


# =============================================================== PIPELINE
def _stage(name: str, label: str, status: str, detail: str = "") -> Dict[str, Any]:
    return {"stage": name, "label": label, "status": status, "detail": detail}


def run_pipeline(quick: bool = False) -> Dict[str, Any]:
    """Agent 1 -> Agent 2 -> Agent 3. Never raises."""
    run_id = f"run-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"
    STATE.update(run_id=run_id, status="running", progress=0,
                 current_stage="ingestion", stages=[], report={})
    stages: List[Dict[str, Any]] = []
    log.info("=== %s pipeline started (quick=%s) ===", run_id, quick)

    # ---------------------------------------------------------- AGENT 1
    try:
        ingestion = IngestionAgent(nasa_key=NASA_API_KEY).run()
        stages.append(_stage("ingestion", "Agent 1 — Ingest & Clean", "completed",
                             f"{ingestion['rows']} rows, {len(ingestion['sources'])} sources"))
        STATE.update(progress=33, stages=list(stages), current_stage="council")
    except Exception as exc:  # noqa: BLE001
        log.exception("Agent 1 failed")
        stages.append(_stage("ingestion", "Agent 1 — Ingest & Clean", "failed", str(exc)[:200]))
        STATE.update(stages=list(stages), status="failed", current_stage="idle")
        return {"run_id": run_id, "status": "failed", "stages": stages, "report": {}}

    # ---------------------------------------------------------- AGENT 2
    try:
        council = CouncilAgent(GEMINI_API_KEY, GEMINI_MODEL_PRO, GEMINI_MODEL_FALLBACK).verify(ingestion)
        stages.append(_stage(
            "council", "Agent 2 — Council of 5", "completed",
            f"{council.get('verdict')} {council.get('overall_score')}/100 "
            f"[{council.get('engine', '?')}]"))
        STATE.update(progress=66, stages=list(stages), current_stage="citations")
    except Exception as exc:  # noqa: BLE001
        log.exception("Agent 2 failed")
        council = {"verdict": "REJECTED", "overall_score": 0, "experts": [],
                   "log": [f"{_utc()} | COUNCIL | fatal error: {exc}"], "engine": "error"}
        stages.append(_stage("council", "Agent 2 — Council of 5", "failed", str(exc)[:200]))
        STATE.update(stages=list(stages))

    # ---------------------------------------------------------- AGENT 3
    try:
        citations = CitationAgent(GEMINI_API_KEY, GEMINI_MODEL_FLASH, GEMINI_MODEL_FALLBACK).enrich(
            council, ingestion)
        stages.append(_stage(
            "citations", "Agent 3 — Citations", "completed",
            f"{len(citations['formulas'])} formulas, {len(citations['references'])} refs"))
    except Exception as exc:  # noqa: BLE001
        log.exception("Agent 3 failed")
        citations = {"formulas": [], "traceability": ingestion.get("traceability", []),
                     "references": [], "engine": "error"}
        stages.append(_stage("citations", "Agent 3 — Citations", "failed", str(exc)[:200]))

    report = {
        "run_id": run_id,
        "generated_at": _utc(),
        "dataset_summary": {
            "sources": ingestion["sources"],
            "rows": ingestion["rows"],
            "features": ingestion["features"][:40],
            "cleaning": ingestion["cleaning"],
            "metrics": ingestion["metrics"],
            "quality": ingestion.get("quality", {}),
            "reference_facts": ingestion.get("reference_facts", [])[:10],
        },
        "cleaned_preview": ingestion["preview"],
        "metrics": ingestion["metrics"],
        "science": ingestion.get("science", {}),
        "council": council,
        "citations": citations,
    }
    STATE.set_report(report)
    STATE.update(progress=100, stages=list(stages), status="completed",
                 current_stage="idle")
    try:
        LAST_REPORT_PATH.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8")
    except OSError as exc:
        log.warning("Could not persist report: %s", exc)
    log.info("=== %s done: %s %s/100 ===",
             run_id, council.get("verdict"), council.get("overall_score"))
    return {"run_id": run_id, "status": "completed", "stages": stages, "report": report}


def _pipeline_worker(quick: bool = False) -> None:
    try:
        run_pipeline(quick=quick)
    except Exception as exc:  # noqa: BLE001 - last-resort guard
        log.exception("Pipeline crashed")
        STATE.update(status="failed", current_stage="idle")
        STATE.stages = STATE.stages + [_stage("fatal", "Pipeline", "failed", str(exc)[:200])]


# ============================================================= NASA FETCHERS
def _donki_series() -> Dict[str, Any]:
    cached = STATE.cached("space-weather")
    if cached:
        return cached
    agent = IngestionAgent(nasa_key=NASA_API_KEY)
    records = agent.fetch_donki()
    # DONKI returns CME AND FLR rows in one list; this panel is CME-only so the
    # table always matches report.metrics.cme_count (flares live in kp-index).
    cmes = [r for r in records if r.get("event") == "CME"]
    flrs = [r for r in records if r.get("event") == "FLR"]
    series = [{"t": r.get("t", ""), "value": r.get("speed"),
               "label": f"{r.get('event')} speed km/s"}
              for r in records if r.get("speed")]
    times = sorted(str(r.get("t") or "") for r in cmes if r.get("t"))
    out = {"series": series, "items": cmes[:60],
           "count": len(cmes),
           "flare_count": len(flrs),
           "window": {"returned": len(cmes[:60]), "total": len(cmes),
                      "start": times[0] if times else None,
                      "end": times[-1] if times else None},
           "source": {"endpoint": "https://api.nasa.gov/DONKI/CME",
                      "fetched_at": _utc()}}
    STATE.put_cache("space-weather", out)
    return out


def _neo_series() -> Dict[str, Any]:
    cached = STATE.cached("neo")
    if cached:
        return cached
    agent = IngestionAgent(nasa_key=NASA_API_KEY)
    items = agent.fetch_neows()
    counts: Dict[str, int] = {}
    for r in items:
        day = str(r.get("t", ""))[:10]
        counts[day] = counts.get(day, 0) + 1
    series = [{"t": d, "value": c} for d, c in sorted(counts.items())]
    out = {"series": series, "items": items[:60],
           "source": {"endpoint": "https://api.nasa.gov/neo/rest/v1/feed",
                      "fetched_at": _utc()}}
    STATE.put_cache("neo", out)
    return out


def _horizons_series() -> Dict[str, Any]:
    cached = STATE.cached("horizons")
    if cached:
        return cached
    agent = IngestionAgent(nasa_key=NASA_API_KEY)
    items = agent.fetch_horizons()
    # Horizons returns Earth AND Mars vectors — keep them in separate orbits so
    # the chart never draws a line across two planets (body label stays honest).
    orbits: Dict[str, list] = {}
    for r in items:
        b = str(r.get("body") or "Earth")
        orbits.setdefault(b, []).append({
            "t": r.get("jd"), "x_au": r.get("x_au"),
            "y_au": r.get("y_au"), "z_au": r.get("z_au")})
    primary = "Earth" if "Earth" in orbits else (
        sorted(orbits)[0] if orbits else "Earth")
    out = {"series": orbits.get(primary, []), "orbits": orbits,
           "bodies": sorted(orbits), "body": primary,
           "frame": "ICRS heliocentric",
           "source": {"endpoint": "https://ssd.jpl.nasa.gov/api/horizons.api",
                      "fetched_at": _utc()}}
    STATE.put_cache("horizons", out)
    return out


def _neo_matrix() -> Dict[str, Any]:
    """Bubble-matrix payload: miss distance (LD) vs velocity vs size."""
    cached = STATE.cached("neo-matrix")
    if cached:
        return cached
    agent = IngestionAgent(nasa_key=NASA_API_KEY)
    items = agent.fetch_neows()
    points = []
    for r in items:
        if not r.get("velocity_kms") or not r.get("miss_distance_ld"):
            continue
        points.append({
            "name": r.get("name"),
            "t": r.get("t"),
            "x_ld": r.get("miss_distance_ld"),
            "y_kms": r.get("velocity_kms"),
            "diameter_m": r.get("diameter_m") or 0.0,
            "hazardous": bool(r.get("hazardous")),
            "h": r.get("absolute_magnitude_h"),
        })
    out = {
        "points": points,
        "axes": {"x": "miss_distance_ld", "y": "velocity_kms",
                 "size": "diameter_m", "color": "hazardous"},
        "conversions": {"ld_km": 384400.0, "ld_au": 384400.0 / 149597870.7,
                        "formula": "d[LD] = d[au] / 0.0025696"},
        "source": {"endpoint": "https://api.nasa.gov/neo/rest/v1/feed",
                   "fetched_at": _utc()},
    }
    STATE.put_cache("neo-matrix", out)
    return out


# ================================================== extended scientific data
def _science(key: str, fn, *args) -> Dict[str, Any]:
    """Fetch one extended dataset, serving the cached pipeline copy if fresh."""
    rep = STATE.get_report()
    sci = (rep.get("science") or {}) if rep else {}
    hit = sci.get(key)
    if isinstance(hit, dict) and hit:
        return hit
    cached = STATE.cached("sci:" + key)
    if cached:
        return cached
    out = fn(*args)
    STATE.put_cache("sci:" + key, out)
    return out


# ================================================================== FLASK APP
def create_app():
    from flask import Flask, jsonify, request, send_from_directory

    app = Flask(__name__, static_folder=None)

    # -- security headers; CORS only for loopback development --------------
    @app.after_request
    def after(resp):
        # The dashboard is served same-origin, so CORS is not required for it.
        # A wildcard would let ANY website drive this pipeline, so it is only
        # enabled while the server is bound to loopback.
        if request.path.startswith("/api/") and _IS_LOCAL:
            resp.headers["Access-Control-Allow-Origin"] = "*"
            resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
            resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "SAMEORIGIN"
        resp.headers["Referrer-Policy"] = "no-referrer"
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://unpkg.com; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src https://fonts.gstatic.com; "
            "img-src 'self' data: blob:; "
            "connect-src 'self' https://unpkg.com https://cdn.jsdelivr.net; "
            "object-src 'none'; frame-ancestors 'self'")
        return resp

    @app.route("/api/<path:_>", methods=["OPTIONS"])
    def cors_preflight(_):
        return ("", 204)

    # -- frontend ----------------------------------------------------------
    @app.get("/")
    def index():
        target = (ROOT / "static" / "index.html").resolve()
        if not str(target).startswith(str(ROOT.resolve())) or not target.exists():
            return jsonify({"error": "static/index.html missing"}), 404
        return send_from_directory(target.parent, target.name)

    # the same pages addressed by file name, so relative links work both
    # on this server and on static hosting (GitHub Pages)
    @app.get("/mors.html")
    def mors_html():
        target = (ROOT / "static" / "mors.html").resolve()
        if not str(target).startswith(str(ROOT.resolve())) or not target.exists():
            return jsonify({"error": "static/mors.html missing"}), 404
        return send_from_directory(target.parent, target.name)

    @app.get("/static/<path:name>")
    def static_files(name: str):
        target = (ROOT / "static" / name).resolve()
        if not str(target).startswith(str(ROOT.resolve())) or not target.exists():
            return jsonify({"error": "not found"}), 404
        return send_from_directory(target.parent, target.name)

    # -- health ------------------------------------------------------------
    @app.get("/api/health")
    def health():
        return jsonify({
            "status": "ok",
            "gemini_configured": bool(GEMINI_API_KEY),
            "nasa_key_mode": "live" if NASA_API_KEY != "DEMO_KEY" else "demo",
            "agents": {"agent1": True, "agent2": True, "agent3": True, "agent4": True},
            "data_endpoints": [
                "/api/data/space-weather", "/api/data/neo", "/api/data/horizons",
                "/api/data/neo-matrix", "/api/data/light-pollution",
                "/api/data/kp-index", "/api/data/spectral", "/api/data/quantum",
            ],
            "timestamp": _utc(),
        })

    # -- pipeline ----------------------------------------------------------
    @app.post("/api/pipeline/run")
    def pipeline_run():
        snap = STATE.snapshot()
        if snap["status"] == "running":
            return jsonify({**snap, "message": "pipeline already running"}), 409
        body = request.get_json(silent=True) or {}
        threading.Thread(target=_pipeline_worker,
                         args=(bool(body.get("quick")),), daemon=True).start()
        return jsonify({"run_id": "starting", "status": "running",
                        "stages": [], "report": {}}), 202

    @app.get("/api/pipeline/status")
    def pipeline_status():
        return jsonify(STATE.snapshot())

    @app.get("/api/report")
    def report():
        rep = STATE.get_report()
        if not rep and LAST_REPORT_PATH.exists():
            try:
                rep = json.loads(LAST_REPORT_PATH.read_text(encoding="utf-8"))
                STATE.set_report(rep)
            except (OSError, json.JSONDecodeError) as exc:
                log.warning("last_report.json unreadable: %s", exc)
        if not rep:
            return jsonify({"error": "certified report not ready — run the pipeline"}), 503
        return jsonify(rep)

    # -- data endpoints ----------------------------------------------------
    @app.get("/api/data/space-weather")
    def data_space_weather():
        try:
            return jsonify(_donki_series())
        except Exception as exc:  # noqa: BLE001
            return jsonify({"error": str(exc)[:200], "series": [], "items": []}), 502

    @app.get("/api/data/neo")
    def data_neo():
        try:
            return jsonify(_neo_series())
        except Exception as exc:  # noqa: BLE001
            return jsonify({"error": str(exc)[:200], "series": [], "items": []}), 502

    @app.get("/api/data/horizons")
    def data_horizons():
        try:
            return jsonify(_horizons_series())
        except Exception as exc:  # noqa: BLE001
            return jsonify({"error": str(exc)[:200], "series": [], "body": "Earth"}), 502

    @app.get("/api/data/neo-matrix")
    def data_neo_matrix():
        try:
            return jsonify(_neo_matrix())
        except Exception as exc:  # noqa: BLE001
            return jsonify({"error": str(exc)[:200], "points": []}), 502

    @app.get("/api/data/light-pollution")
    def data_light_pollution():
        try:
            from agents import datasets as _ds
            return jsonify(_science("light_pollution", _ds.fetch_light_pollution))
        except Exception as exc:  # noqa: BLE001
            log.warning("light-pollution endpoint failed: %s", str(exc)[:200])
            return jsonify({"error": str(exc)[:200], "sites": [],
                            "model": {}, "source": {}}), 502

    @app.get("/api/data/kp-index")
    def data_kp_index():
        try:
            from agents import datasets as _ds
            return jsonify(_science("kp_index", _ds.fetch_kp_index, NASA_API_KEY))
        except Exception as exc:  # noqa: BLE001
            log.warning("kp-index endpoint failed: %s", str(exc)[:200])
            return jsonify({"error": str(exc)[:200], "kp": [], "flares": [],
                            "daily": [], "source": {}}), 502

    @app.get("/api/data/spectral")
    def data_spectral():
        try:
            from agents import datasets as _ds
            return jsonify(_science("spectral", _ds.build_spectral))
        except Exception as exc:  # noqa: BLE001
            log.warning("spectral endpoint failed: %s", str(exc)[:200])
            return jsonify({"error": str(exc)[:200], "bands": [],
                            "profiles": []}), 502

    @app.get("/api/data/quantum")
    def data_quantum():
        try:
            from agents import datasets as _ds
            return jsonify(_science("quantum", _ds.run_quantum))
        except Exception as exc:  # noqa: BLE001
            log.warning("quantum endpoint failed: %s", str(exc)[:200])
            return jsonify({"error": str(exc)[:200], "states": {},
                            "honesty": ""}), 502

    # ================================================== MORS COMMAND CENTER
    def _mors_report() -> Dict[str, Any]:
        rep = STATE.get_report()
        if not rep and LAST_REPORT_PATH.exists():
            try:
                rep = json.loads(LAST_REPORT_PATH.read_text(encoding="utf-8"))
                STATE.set_report(rep)
            except (OSError, json.JSONDecodeError) as exc:
                log.warning("last_report.json unreadable: %s", exc)
        return rep or {}

    _MORS_WITH_REPORT = {"home", "datahealth", "problems", "solutions",
                         "projects", "ai"}
    _MORS = {
        "home": mors_data.home,
        "datahealth": mors_data.data_health,
        "problems": mors_data.problems,
        "solutions": mors_data.solutions,
        "modules": mors_data.modules_catalog,
        "photometry": mors_data.photometry,
        "spectroscopy": mors_data.spectroscopy,
        "satellite": mors_data.satellites,
        "images": mors_data.images,
        "lightcurves": mors_data.lightcurves,
        "exoplanets": mors_data.exoplanets,
        "objects": mors_data.objects,
        "fits": mors_data.fits_headers,
        "quantum": mors_data.quantum_lab,
        "projects": mors_data.projects,
        "team": mors_data.team,
        "ai": mors_data.ai_workspace,
        "prompts": mors_data.prompt_library,
        "sources": sources_data.build,
    }

    @app.get("/mors")
    def mors_page():
        target = (ROOT / "static" / "mors.html").resolve()
        if not str(target).startswith(str(ROOT.resolve())) or not target.exists():
            return jsonify({"error": "static/mors.html missing"}), 404
        return send_from_directory(target.parent, target.name)

    @app.get("/api/mors")
    def mors_index():
        return jsonify({"page": "/mors", "modules": sorted(_MORS),
                        "with_report": sorted(_MORS_WITH_REPORT),
                        "ai_insight": "POST /api/mors/insight",
                        "acquisition_order": ["api", "ai_synthesis", "local_model"]})

    @app.get("/api/mors/<name>")
    def mors_endpoint(name: str):
        fn = _MORS.get(name)
        if fn is None:
            return jsonify({"error": f"unknown MORS module '{name}'",
                            "available": sorted(_MORS)}), 404
        try:
            out = fn(_mors_report()) if name in _MORS_WITH_REPORT else fn()
            return jsonify(out)
        except Exception as exc:  # noqa: BLE001
            log.warning("mors/%s failed: %s", name, str(exc)[:200])
            return jsonify({"error": str(exc)[:200]}), 502

    @app.post("/api/mors/insight")
    def mors_insight():
        body = request.get_json(silent=True) or {}
        question = str(body.get("question", "")).strip()
        if not question:
            return jsonify({"error": "question required"}), 400
        question = question[:2000]
        dataset = str(body.get("dataset", "auto"))[:64]
        try:
            return jsonify(mors_data.ai_insight(question, dataset, _mors_report()))
        except Exception as exc:  # noqa: BLE001
            log.warning("mors insight failed: %s", str(exc)[:200])
            return jsonify({"error": str(exc)[:200]}), 502

    # -- Agent 4 chat ------------------------------------------------------
    @app.post("/api/chat")
    def chat():
        body = request.get_json(silent=True) or {}
        message = str(body.get("message", "")).strip()
        # strip control characters (except newline/tab) — anti prompt-injection
        # hygiene and log-spoofing protection
        message = "".join(ch for ch in message
                          if ch in "\n\t" or (ch.isprintable()))
        message = message.replace("\x00", "").strip()
        if not message:
            return jsonify({"error": "message required"}), 400
        if len(message) > 4000:
            message = message[:4000]
        report = STATE.get_report()
        if not report and LAST_REPORT_PATH.exists():
            try:
                report = json.loads(LAST_REPORT_PATH.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                report = {}
        if not report:
            # allowed: Ai.Mors still answers with a "run the pipeline" guidance
            pass
        history = body.get("history") or []
        if not isinstance(history, list):
            history = []
        agent = AiMorsAgent(GEMINI_API_KEY, GEMINI_MODEL_PRO, GEMINI_MODEL_FALLBACK)
        result = agent.chat(message, history, report)
        return jsonify(result)

    return app


# ==================================================================== MAIN
def selftest() -> int:
    """Synchronous pipeline run without Flask — for CI / pre-flight checks."""
    log.info("SELFTEST: running full pipeline synchronously ...")
    out = run_pipeline(quick=True)
    rep = out.get("report", {})
    council = rep.get("council", {})
    print("\n" + "=" * 70)
    print("SELFTEST RESULT")
    print("=" * 70)
    print(f"status          : {out['status']}")
    for s in out["stages"]:
        print(f"  [{s['status']:>10}] {s['label']}: {s['detail']}")
    print(f"verdict         : {council.get('verdict')}")
    print(f"score           : {council.get('overall_score')}/100")
    print(f"council engine  : {council.get('engine')}")
    print(f"report keys     : {sorted(rep.keys())}")
    chat = AiMorsAgent(GEMINI_API_KEY, GEMINI_MODEL_PRO, GEMINI_MODEL_FALLBACK).chat("ما حالة الكواكب؟", [], rep)
    first = chat["reply"].splitlines()[0] if chat["reply"] else ""
    print(f"Ai.Mors greeting: {first!r} (ok={chat['greeting_ok']})")
    ok = out["status"] == "completed" and chat["greeting_ok"]
    print("SELFTEST        :", "PASS ✅" if ok else "FAIL ❌")
    print("=" * 70 + "\n")
    return 0 if ok else 1


def _warm_satellites() -> None:
    try:
        mors_data.satellites()
        log.info("Warm fetch: satellite catalog cached")
    except Exception as exc:  # pragma: no cover - network dependent
        log.warning("Warm fetch skipped: %s", str(exc)[:120])


def main() -> None:
    parser = argparse.ArgumentParser(description="ASI-HACK Space Analytics Engine")
    parser.add_argument("--selftest", action="store_true",
                        help="run the pipeline synchronously and exit")
    parser.add_argument("--port", type=int, default=FLASK_PORT)
    parser.add_argument("--host", default=FLASK_HOST)
    args = parser.parse_args()

    if args.selftest:
        sys.exit(selftest())

    if LAST_REPORT_PATH.exists():
        try:
            STATE.set_report(json.loads(LAST_REPORT_PATH.read_text(encoding="utf-8")))
            log.info("Loaded previous certified report from last_report.json")
        except (OSError, json.JSONDecodeError):
            log.warning("last_report.json exists but could not be parsed")

    app = create_app()
    # Warm the only cold-cache live fetch (CelesTrak / TLE mirror) in the
    # background: it can take a minute on a bad network, and the first
    # dashboard hit should not inherit that wait. The module caches itself.
    threading.Thread(target=_warm_satellites, daemon=True).start()
    banner = f"""
==========================================================================
  ASI-HACK SPACE ANALYTICS ENGINE  ·  Ai.Mors
================================================================----------
  Dashboard : http://{args.host}:{args.port}/
  Health    : http://{args.host}:{args.port}/api/health
  Gemini    : {'configured (' + GEMINI_API_KEY[:6] + '*** )' if GEMINI_API_KEY else 'NOT SET (fallback mode)'}
  NASA key  : {'live' if NASA_API_KEY != 'DEMO_KEY' else 'DEMO_KEY (rate-limited)'}
  Models    : pro={GEMINI_MODEL_PRO} | flash={GEMINI_MODEL_FLASH}
  Ctrl+C to stop
=========================================================================="""
    print(banner)
    # use_reloader=False: the pipeline uses background threads
    app.run(host=args.host, port=args.port, debug=FLASK_DEBUG, use_reloader=False)


if __name__ == "__main__":
    main()
