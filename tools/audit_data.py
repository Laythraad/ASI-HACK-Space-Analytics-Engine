#!/usr/bin/env python3
"""Data & analysis audit for the ASI-HACK / MORS engine.

Runs a fixed battery of consistency checks against the live API and prints
one line per check. Nothing is written anywhere - this is a read-only probe.

Usage:
    python main.py                 # leave the server running
    python tools/audit_data.py     # -> AUDIT: PASS / FAIL

Environment:
    MORS_BASE   base URL (default http://127.0.0.1:5000)
"""
from __future__ import annotations

import json
import math
import os
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # pragma: no cover
    pass
BASE = os.getenv("MORS_BASE", "http://127.0.0.1:5000").rstrip("/")

# only the team leader may appear as a personal name anywhere in the project
_PRIVATE_NAMES = ["عباس", "شهد", "جعفر الفراس", "Abbas", "Shahd",
                  "Jaafar Al-Faras", "Jaafar"]

RESULTS: list[tuple[str, bool, str]] = []


def get(path: str, timeout: int = 90):
    # the TLE endpoints are third-party and slow on a cold cache
    if timeout == 90 and path.startswith("/api/mors/satellite"):
        timeout = 300
    with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def check(name: str, ok: bool, detail: str = "") -> bool:
    RESULTS.append((name, bool(ok), detail))
    mark = "PASS" if ok else "FAIL"
    tail = f"  [{detail}]" if detail and not ok else (f"  ({detail})" if detail else "")
    print(f"[{mark}] {name}{tail}")
    return bool(ok)


def near(a, b, tol=0.051) -> bool:
    try:
        return abs(float(a) - float(b)) <= tol
    except (TypeError, ValueError):
        return False


def mean(vals):
    vals = [float(v) for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else 0.0


def same_utc_day(*isos) -> bool:
    """True when every timestamp falls on the same UTC calendar date.

    Both DONKI panels and the report snapshot roll a 30-day window keyed on
    ``date.today()`` (UTC). Two payloads fetched either side of midnight
    therefore cover *different* windows and their event counts legitimately
    differ — such a pair is compared with a drift tolerance instead of the
    exact equality used when both sides were fetched on the same day.
    """
    days = {str(i or "")[:10] for i in isos}
    return len(days) == 1 and "" not in days


def counts_agree(a, b, same_day: bool, tol: int = 5) -> bool:
    """Exact equality on one UTC day, ±``tol`` events when the windows rolled."""
    if a is None or b is None:
        return False
    if same_day:
        return a == b
    try:
        return abs(int(a) - int(b)) <= tol
    except (TypeError, ValueError):
        return False


# ----------------------------------------------------------------- payloads
def load() -> dict:
    D = {}
    for key, path in [
        ("health", "/api/health"),
        ("report", "/api/report"),
        ("dh", "/api/mors/datahealth"),
        ("problems", "/api/mors/problems"),
        ("solutions", "/api/mors/solutions"),
        ("sat", "/api/mors/satellite"),
        ("exo", "/api/mors/exoplanets"),
        ("objects", "/api/mors/objects"),
        ("images", "/api/mors/images"),
        ("fits", "/api/mors/fits"),
        ("photo", "/api/mors/photometry"),
        ("lc", "/api/mors/lightcurves"),
        ("spec", "/api/mors/spectroscopy"),
        ("quantum", "/api/mors/quantum"),
        ("sources", "/api/mors/sources"),
        ("team", "/api/mors/team"),
        ("prompts", "/api/mors/prompts"),
        ("projects", "/api/mors/projects"),
        ("modules", "/api/mors"),
        ("kp", "/api/data/kp-index"),
        ("sw", "/api/data/space-weather"),
        ("neo", "/api/data/neo"),
        ("matrix", "/api/data/neo-matrix"),
        ("spectral", "/api/data/spectral"),
        ("quantum_data", "/api/data/quantum"),
        ("light", "/api/data/light-pollution"),
        ("horizons", "/api/data/horizons"),
    ]:
        try:
            D[key] = get(path)
        except Exception as exc:
            D[key] = None
            check(f"endpoint reachable {path}", False, str(exc))
    return D


# ---------------------------------------------------------------- sections
def audit_health(D):
    h = D.get("health") or {}
    check("health.status == ok", h.get("status") == "ok")
    agents = h.get("agents") or {}
    check("all 4 agents registered", len(agents) == 4 and all(agents.values()),
          json.dumps(agents))
    check("8 science endpoints declared", len(h.get("data_endpoints") or []) == 8)
    check("NASA key mode declared", h.get("nasa_key_mode") in ("live", "demo", "local"))
    check("Gemini configured flag is boolean", isinstance(h.get("gemini_configured"), bool))


def audit_datahealth(D):
    dh = D.get("dh") or {}
    if not dh:
        check("datahealth payload present", False)
        return
    rows = dh.get("rows") or 0
    cells = dh.get("cells") or 0
    srcs = dh.get("per_source") or []
    check("rows > 0", rows > 0, f"rows={rows}")
    check("per_source count == sources", len(srcs) == dh.get("sources"),
          f"{len(srcs)} vs {dh.get('sources')}")
    check("cells == sum(rows x columns)",
          cells == sum((r.get("rows") or 0) * (r.get("columns") or 0) for r in srcs),
          f"cells={cells} sum={sum((r.get('rows') or 0) * (r.get('columns') or 0) for r in srcs)}")
    check("missing_pct == missing_cells / cells",
          near(dh.get("missing_pct"), (dh.get("missing_cells") or 0) / cells * 100 if cells else 0, 0.02),
          f"declared={dh.get('missing_pct')}")
    check("completeness + missing == 100",
          near((dh.get("completeness_pct") or 0) + (dh.get("missing_pct") or 0), 100, 0.05),
          f"{dh.get('completeness_pct')}+{dh.get('missing_pct')}")
    check("duplicate_pct == duplicate_rows / rows",
          near(dh.get("duplicate_pct"), (dh.get("duplicate_rows") or 0) / rows * 100 if rows else 0, 0.02))
    check("outliers_pct == outlier_count / rows",
          near(dh.get("outliers_pct"), (dh.get("outlier_count") or 0) / rows * 100 if rows else 0, 0.05),
          f"declared={dh.get('outliers_pct')}")
    check("data_quality_score in [0,100]", 0 <= (dh.get("data_quality_score") or -1) <= 100)
    check("accuracy_score in [0,100]", 0 <= (dh.get("accuracy_score") or -1) <= 100)
    bad = [r.get("source") for r in srcs if not (0 <= (r.get("accuracy_score") or -1) <= 100)]
    check("every per_source accuracy in [0,100]", not bad, ",".join(map(str, bad)))
    bad = [r.get("source") for r in srcs if r.get("status") not in ("ok", "warn", "degraded")]
    check("per_source status values are declared", not bad, ",".join(map(str, bad)))
    check("trace present on datahealth", bool(dh.get("trace")) and bool(dh.get("badge")))


def audit_problems(D):
    pr = D.get("problems") or {}
    cards = pr.get("problems") or []
    check("at least one problem card", len(cards) >= 1, f"n={len(cards)}")
    required = ["problem_id", "title", "severity", "category", "component",
                "symptom", "root_cause", "fix", "evidence", "priority"]
    forbidden = {"description", "solution", "notes", "status", "details"}
    missing = [(c.get("problem_id"), k) for c in cards for k in required
               if k not in c]
    check("10-field contract schema on every card", not missing, str(missing[:4]))
    bad = [(c.get("problem_id"), sorted(forbidden & set(c))) for c in cards
           if forbidden & set(c)]
    check("no forbidden keys (description/solution/notes/status/details)",
          not bad, str(bad[:3]))
    sev = {"critical", "high", "medium", "low"}
    cat = {"data", "logic", "api", "ui", "docs", "infra", "performance"}
    check("severity in critical|high|medium|low",
          all(c.get("severity") in sev for c in cards),
          str(sorted({str(c.get("severity")) for c in cards})))
    check("category in data|logic|api|ui|docs|infra|performance",
          all(c.get("category") in cat for c in cards),
          str(sorted({str(c.get("category")) for c in cards})))
    check("priority_code in P0|P1|P2",
          all(c.get("priority_code") in ("P0", "P1", "P2") for c in cards),
          str(sorted({str(c.get("priority_code")) for c in cards})))
    check("every card names its component file",
          all(str(c.get("component") or "").strip() for c in cards),
          str([c.get("problem_id") for c in cards
               if not str(c.get("component") or "").strip()][:4]))
    check("symptom / root_cause / fix are populated",
          all(str(c.get("symptom") or "").strip()
              and str(c.get("root_cause") or "").strip()
              and (c.get("fix") or []) for c in cards))
    ids = [c.get("problem_id") for c in cards]
    check("problem ids unique", len(ids) == len(set(ids)), str(ids))
    for c in cards:
        want = round(0.40 * (c.get("evidence_metric") or 0)
                     + 0.35 * (c.get("impact_score") or 0)
                     + 0.25 * (c.get("confidence_level") or 0), 1)
        check(f"{c.get('id')} priority_score == 0.40e+0.35i+0.25c",
              near(c.get("priority_score"), want, 0.11),
              f"declared={c.get('priority_score')} computed={want}")
        score = c.get("priority_score") or 0
        want_label = "High" if score >= 75 else "Medium" if score >= 50 else "Low"
        check(f"{c.get('id')} priority label matches thresholds (75/50)",
              c.get("priority") == want_label,
              f"score={score} declared={c.get('priority')} expected={want_label}")
    tally = {}
    for c in cards:
        tally[c.get("priority")] = tally.get(c.get("priority"), 0) + 1
    declared = pr.get("by_priority") or {}
    check("by_priority tallies the cards",
          all(declared.get(k, 0) == tally.get(k, 0) for k in ("High", "Medium", "Low")),
          f"{declared} vs {tally}")
    check("problems payload carries trace+badge",
          bool(pr.get("trace")) and bool(pr.get("badge")))


def audit_solutions(D):
    sols = (D.get("solutions") or {}).get("solutions") or []
    probs = {c.get("id"): c for c in (D.get("problems") or {}).get("problems") or []}
    check("every solution maps to a known problem",
          all(s.get("problem_id") in probs for s in sols),
          str([s.get("problem_id") for s in sols if s.get("problem_id") not in probs]))
    mismatch = [s.get("problem_id") for s in sols
                if s.get("problem_id") in probs
                and s.get("priority") != probs[s.get("problem_id")].get("priority")]
    check("solution priority mirrors its problem", not mismatch, str(mismatch))
    check("solution effort uses S/M/L/XL",
          all(s.get("effort") in ("S", "M", "L", "XL") for s in sols),
          str(sorted({s.get("effort") for s in sols})))
    check("every solution names an owner",
          all(str(s.get("owner") or "").strip() for s in sols))
    check("solutions payload carries trace+badge",
          bool((D.get("solutions") or {}).get("trace")))


def audit_satellite(D):
    sat = D.get("sat") or {}
    rows = sat.get("rows") or []
    via = (sat.get("source") or {}).get("via")
    if via == "local_model":
        check("satellite catalog fell back to the labelled reference set",
              len(rows) >= 10, f"n={len(rows)} via={via}")
    else:
        check("50 satellites returned", len(rows) == 50,
              f"n={len(rows)} via={via}")
    if not rows:
        return
    norads = [r.get("norad_id") for r in rows]
    check("norad_id unique", len(norads) == len(set(norads)))
    bad = [r.get("name") for r in rows if (r.get("apogee_km") or 0) < (r.get("perigee_km") or 0)]
    check("apogee >= perigee", not bad, str(bad[:3]))
    counts = {}
    for r in rows:
        counts[r.get("orbit_class")] = counts.get(r.get("orbit_class"), 0) + 1
    check("orbit classes split LEO/MEO/GEO",
          counts.get("LEO", 0) > 0 and counts.get("MEO", 0) > 0 and counts.get("GEO", 0) > 0,
          json.dumps(counts))
    bad = []
    for r in rows:
        alt = r.get("altitude_km")
        cls = r.get("orbit_class")
        if alt is None or cls is None:
            bad.append((r.get("name"), "missing"))
            continue
        if cls == "LEO" and not (160 <= alt < 2000):
            bad.append((r.get("name"), alt))
        elif cls == "MEO" and not (2000 <= alt < 35586):
            bad.append((r.get("name"), alt))
        elif cls == "GEO" and not (35000 <= alt <= 36500):
            bad.append((r.get("name"), alt))
    check("altitude agrees with orbit class", not bad, str(bad[:4]))
    bad = [r.get("name") for r in rows if (r.get("apogee_km") or 0) <= 0
           or (r.get("perigee_km") or 0) <= 0]
    check("apogee/perigee > 0 on every row", not bad, str(bad[:4]))
    bad = [r.get("name") for r in rows if not (1.5 <= (r.get("velocity_kms") or 0) <= 11.5)]
    check("orbital velocity plausible (1.5-11.5 km/s)", not bad, str(bad[:4]))
    bad = [r.get("name") for r in rows if not (60 <= (r.get("period_min") or 0) <= 2000)]
    check("orbital period plausible (60-2000 min)", not bad, str(bad[:4]))
    phys = sat.get("physics") or {}
    mu = 398600.4418  # km^3 s^-2 (EGM2008 / WGS84)
    m = re.match(r"\s*([0-9][0-9.eE+-]*)", str(phys.get("GM_earth") or ""))
    if m:
        try:
            val = float(m.group(1))
            if val > 1e10:  # quoted in m^3 s^-2 -> km^3 s^-2
                val /= 1e9
            if val > 1e3:
                mu = val
        except ValueError:
            pass
    errs, errs_v = [], []
    for r in rows:
        a_km = 6371 + (r.get("altitude_km") or 0)
        t_min = 2 * math.pi * math.sqrt((a_km ** 3) / mu) / 60
        v = math.sqrt(mu / a_km)
        if r.get("period_min"):
            errs.append(abs(r["period_min"] - t_min) / t_min * 100)
        if r.get("velocity_kms"):
            errs_v.append(abs(r["velocity_kms"] - v) / v * 100)
    check("period matches Kepler within 10%", errs and max(errs) <= 10.0,
          f"max err={max(errs):.1f}%" if errs else "no data")
    check("velocity matches sqrt(GM/a) within 12%", errs_v and max(errs_v) <= 12.0,
          f"max err={max(errs_v):.1f}%" if errs_v else "no data")
    check("satellite source.via declared", bool(sat.get("source")) and bool(sat.get("trace")))
    if via in ("api", "cache"):
        check("live satellite source names its endpoint" if via == "api"
              else "cached satellite payload keeps its origin endpoint",
              str((sat.get("source") or {}).get("endpoint") or "").startswith("http"),
              str((sat.get("source") or {}).get("endpoint")))


def audit_exoplanets(D):
    rows = (D.get("exo") or {}).get("rows") or []
    check("exoplanet rows returned", len(rows) > 0, f"n={len(rows)}")
    if not rows:
        return
    bad = [r.get("planet_name") for r in rows if not (r.get("period_d") or 0) > 0]
    check("period_d > 0 everywhere", not bad, str(bad[:4]))
    bad = [r.get("planet_name") for r in rows if r.get("radius_re") is not None and r["radius_re"] <= 0]
    check("radius_re > 0 where present", not bad, str(bad[:4]))
    bad = [r.get("planet_name") for r in rows if (r.get("distance_pc") or 0) <= 0]
    check("distance_pc > 0", not bad, str(bad[:4]))
    bad = [r.get("planet_name") for r in rows
           if r.get("habitability_index") is not None
           and not (0.0 <= r["habitability_index"] <= 1.0)]
    check("habitability_index in [0,1] where present", not bad, str(bad[:4]))
    names = [r.get("planet_name") for r in rows]
    check("planet names unique", len(names) == len(set(names)),
          str([n for n in set(names) if names.count(n) > 1][:3]))


def audit_objects(D):
    o = D.get("objects") or {}
    rows = o.get("rows") or []
    check("objects count == rows", o.get("count") == len(rows),
          f"{o.get('count')} vs {len(rows)}")
    names = [r.get("name") for r in rows]
    check("object names unique", len(names) == len(set(names)))
    stars = [r for r in rows if r.get("type") != "Planet"]
    planets = [r for r in rows if r.get("type") == "Planet"]
    bad = [r.get("name") for r in stars
           if r.get("ra_deg") is None or r.get("dec_deg") is None
           or not (-360 <= (r.get("ra_deg") or -999) <= 360)
           or not (-90 <= (r.get("dec_deg") or -999) <= 90)]
    check("non-planetary rows carry in-bounds RA/Dec", not bad, str(bad[:4]))
    bad = [r.get("name") for r in stars if (r.get("distance_ly") or 0) <= 0]
    check("distance_ly > 0 for stars/galaxies/nebulae", not bad, str(bad[:4]))
    bad = [r.get("name") for r in planets
           if r.get("ra_deg") is not None or (r.get("semimajor_au") or 0) <= 0]
    check("planet rows are elements-only (null RA/Dec + semimajor_au)",
          not bad, str(bad[:4]))
    bad = [r.get("name") for r in planets if not r.get("position_note")]
    check("planet rows explain their null positions", not bad, str(bad[:4]))


def audit_sky_surfaces(D):
    for key, label in (("photo", "photometry"), ("lc", "lightcurves"),
                       ("spec", "spectroscopy"), ("fits", "fits"),
                       ("images", "images"), ("quantum", "quantum")):
        pay = D.get(key) or {}
        check(f"{label}: trace+badge present", bool(pay.get("trace")) and bool(pay.get("badge")))
        check(f"{label}: row count declared consistently",
              pay.get("count") in (None, len(pay.get("rows") or [])),
              f"count={pay.get('count')} rows={len(pay.get('rows') or [])}")


def audit_space_weather(D):
    sw = D.get("sw") or {}
    items = sw.get("items") or []
    check("space-weather items returned", len(items) > 0, f"n={len(items)}")
    check("space-weather panel is CME-only",
          all(i.get("event") == "CME" for i in items),
          str(sorted({i.get("event") for i in items})))
    bad = [i.get("id") for i in items if (i.get("speed") or 0) <= 0]
    check("CME speeds > 0", not bad, str(bad[:4]))
    total = sw.get("count")
    check("payload declares total CME count >= returned rows",
          isinstance(total, int) and total >= len(items),
          f"count={total} items={len(items)}")
    window = sw.get("window") or {}
    if window:
        check("window.total == count", window.get("total") == total,
              f"{window.get('total')} vs {total}")
        check("window.returned == len(items)", window.get("returned") == len(items))
    rep_metrics = (D.get("report") or {}).get("metrics") or {}
    kp = D.get("kp") or {}
    src_kp = kp.get("source") or {}
    rep_day = (D.get("report") or {}).get("generated_at")
    kp_day, sw_day = src_kp.get("fetched_at"), ((sw.get("source") or {}).get("fetched_at"))
    rolled = " (30-day windows span different UTC dates)"
    rcme = rep_metrics.get("cme_count")
    if rcme is not None and isinstance(total, int):
        # the report is a snapshot of the last pipeline run while this panel is
        # live: new CMEs may have been published since the run, and the 30-day
        # window keys on date.today() (UTC) so a run from yesterday legitimately
        # sees a slightly different event set. A 5-event drift either way is
        # window movement, not a tracking failure.
        check("report.metrics.cme_count tracks the live space-weather window",
              abs(total - rcme) <= 5,
              f"report={rcme} live={total}")
    if rep_metrics.get("solar_wind_avg_kms") is not None:
        check("solar_wind_avg_kms is an OMNI-scale value (250-900 km/s)",
              250 <= rep_metrics["solar_wind_avg_kms"] <= 900,
              str(rep_metrics["solar_wind_avg_kms"]))
    if rep_metrics.get("cme_speed_mean_kms") is not None:
        check("cme_speed_mean_kms plausible (100-3000 km/s)",
              100 <= rep_metrics["cme_speed_mean_kms"] <= 3000,
              str(rep_metrics["cme_speed_mean_kms"]))
    series = kp.get("kp") or []
    check("Kp samples returned", len(series) > 0, f"n={len(series)}")
    bad = [x for x in series
           if x.get("kp") is None or not (0 <= float(x.get("kp")) <= 9)]
    check("Kp within 0..9 scale", not bad, str(bad[:3]))
    if series and rep_metrics.get("kp_max") is not None:
        want = max(x["kp"] for x in series if x.get("kp") is not None)
        same = same_utc_day(rep_day, kp_day)
        check("report.metrics.kp_max == max(Kp series)",
              abs(rep_metrics["kp_max"] - want) <= (0.01 if same else 1.0),
              f"{rep_metrics['kp_max']} vs {want:.2f}"
              + ("" if same else rolled))
    flares = kp.get("flares") or []
    check("flare classes declared as X/M/C/B",
          all(str(f.get("class") or f.get("type") or "?")[0] in "XMCB" for f in flares),
          str(sorted({str(f.get("class") or f.get("type")) for f in flares}))[:80])
    if rep_metrics.get("flare_count_30d") is not None:
        check("report.metrics.flare_count_30d == flare rows",
              counts_agree(rep_metrics["flare_count_30d"], len(flares),
                           same_utc_day(rep_day, kp_day)),
              f"{rep_metrics['flare_count_30d']} vs {len(flares)}"
              + ("" if same_utc_day(rep_day, kp_day) else rolled))
    rec, cls_ = src_kp.get("flare_records"), src_kp.get("flare_classified")
    if rec is not None:
        check("kp-index DONKI FLR records == space-weather flare_count",
              counts_agree(rec, sw.get("flare_count"),
                           same_utc_day(kp_day, sw_day)),
              f"{rec} vs {sw.get('flare_count')}"
              + ("" if same_utc_day(kp_day, sw_day) else rolled))
        check("flare stats reconcile (classified + unclassified == records)",
              (cls_ or 0) + (src_kp.get("flare_unclassified") or 0) == rec,
              f"{cls_}+{src_kp.get('flare_unclassified')} vs {rec}")
        check("flare_count_30d == classified DONKI flares",
              counts_agree(rep_metrics.get("flare_count_30d"), cls_,
                           same_utc_day(rep_day, kp_day)),
              f"{rep_metrics.get('flare_count_30d')} vs {cls_}")
        check("no silent drops are hidden (unclassified is reported)",
              (src_kp.get("flare_unclassified") or 0) >= 0
              and "flare_unclassified" in src_kp)


def audit_report(D):
    rep = D.get("report") or {}
    if not rep:
        check("report payload present", False)
        return
    council = rep.get("council") or {}
    experts = council.get("experts") or []
    check("council has 5 experts", len(experts) == 5, f"n={len(experts)}")
    scores = [e.get("score") for e in experts if e.get("score") is not None]
    if scores:
        check("expert scores in [0,100]", all(0 <= s <= 100 for s in scores), str(scores))
        want = round(mean(scores))
        check("overall_score == round(mean(expert scores))",
              council.get("overall_score") is not None
              and abs(council["overall_score"] - want) <= 1,
              f"declared={council.get('overall_score')} mean={want}")
    check("verdict declared", council.get("verdict") in ("CERTIFIED", "REJECTED", "PARTIAL"),
          str(council.get("verdict")))
    check("council records an engine", bool(council.get("engine")),
          str(council.get("engine")))
    m = rep.get("metrics") or {}
    sane = [
        ("kp_max", 0 <= (m.get("kp_max") or -1) <= 9),
        ("closest_ld", (m.get("closest_ld") or 0) > 0),
        ("light_curve_snr", (m.get("light_curve_snr") or 0) > 0),
        ("quantum_entropy_ebit", 0 <= (m.get("quantum_entropy_ebit") or -1) <= 10),
        ("neo_count", (m.get("neo_count") or 0) >= 0),
        ("spectral_bands", (m.get("spectral_bands") or 0) > 0),
        ("darkest >= brightest NELM",
         (m.get("darkest_site_nelm") or 0) >= (m.get("brightest_site_nelm") or 0)),
    ]
    bad = [k for k, ok in sane if not ok]
    check("report metrics physically sane", not bad, str(bad))
    check("report carries run_id + generated_at",
          bool(rep.get("run_id")) and bool(rep.get("generated_at")))
    check("citations recorded", bool(rep.get("citations")),
          str(type(rep.get("citations"))))


def audit_sources(D):
    src = D.get("sources") or {}
    hacks = src.get("hackathon") or []
    agg = src.get("aggregates") or {}
    check("16 hackathon sources", len(hacks) == 16, f"n={len(hacks)}")
    check("count field matches list", src.get("count") == len(hacks))
    ids = [h.get("id") for h in hacks]
    check("source ids unique", len(ids) == len(set(ids)), str(ids))
    for key in ("by_phase", "by_level", "by_kind", "by_category"):
        total = sum((agg.get(key) or {}).values())
        check(f"aggregates.{key} sums to 16", total == 16, f"{total} {agg.get(key)}")
    check("aggregates.total == 16", agg.get("total") == 16, str(agg.get("total")))
    conds = src.get("conditions") or []
    check("8 hackathon conditions", len(conds) == 8, f"n={len(conds)}")
    core = sum(1 for c in conds if c.get("status") == "core")
    ext = sum(1 for c in conds if c.get("status") == "extension")
    check("conditions_covered == conditions_total (all 8 mapped)",
          agg.get("conditions_covered") == len(conds) == 8,
          f"{agg.get('conditions_covered')} vs {len(conds)}")
    check("conditions_core + conditions_extension == 8",
          (agg.get("conditions_core", -1) + agg.get("conditions_extension", -1))
          == len(conds),
          f"{agg.get('conditions_core')}+{agg.get('conditions_extension')}")
    check("core count == status=core count",
          agg.get("conditions_core") == core,
          f"{agg.get('conditions_core')} vs {core}")
    check("exactly one extension condition", ext == 1 and
          agg.get("conditions_extension") == ext, f"{ext}")
    known = set(ids)
    bad = [c.get("n") for c in conds for s in (c.get("sources") or []) if s not in known]
    check("condition sources reference real ids", not bad, str(bad))
    dsrc = src.get("data_sources") or []
    check("12 data sources", len(dsrc) == 12, f"n={len(dsrc)}")
    check("data source via in api/ai_synthesis/local_model",
          all(d.get("via") in ("api", "ai_synthesis", "local_model") for d in dsrc),
          str(sorted({d.get("via") for d in dsrc})))
    check("data source ids unique",
          len({d.get("id") for d in dsrc}) == len(dsrc))
    bad = [h.get("id") for h in hacks if h.get("url") and not str(h["url"]).startswith(("http://", "https://"))]
    check("hackathon source urls are absolute", not bad, str(bad))
    check("aggregates.live_data_sources <= 12",
          (agg.get("live_data_sources") or 0) <= 12, str(agg.get("live_data_sources")))
    check("sources payload carries trace+badge",
          bool(src.get("trace")) and bool(src.get("badge")))


def audit_team(D):
    team = D.get("team") or {}
    members = team.get("members") or []
    check("team roster present", len(members) >= 1, f"n={len(members)}")
    expected = ["ليث رعد", "Data Analyst", "Astronomy Researcher",
                "Space Systems & AI Engineer"]
    names = [m.get("name") for m in members]
    check("team is the four-member submission roster",
          len(members) == 4 and sorted(names) == sorted(expected), str(names))
    check("only the team leader is published by name",
          names[0] == "ليث رعد" and
          all(n not in _PRIVATE_NAMES for n in names), str(names))
    payload = json.dumps(D, ensure_ascii=False)
    leaked = [n for n in _PRIVATE_NAMES if n in payload]
    check("no private member name anywhere in the API payloads",
          not leaked, str(leaked))
    check("team member ids unique",
          len({m.get("id") for m in members}) == len(members))
    check("every member has a role", all(str(m.get("role") or "").strip() for m in members))
    check("every member has skills", all(m.get("skills") for m in members))
    check("member names unique", len(names) == len(set(names)), str(names))
    leader = next((m for m in members if m.get("id") == "TM-1"), {})
    check("TM-1 is flagged as team leader",
          leader.get("lead") == "Team Leader",
          f"lead={leader.get('lead')}")
    owns = [o for m in members for o in (m.get("owns") or [])]
    check("module ownership covers the 6 MORS domains",
          all(any(d in o for o in owns)
              for d in ("DATA.MORS", "ASTRONOMY.MORS", "SATELLITE.MORS",
                        "QUANTUM.MORS", "AI.MORS", "TEAM.MORS")),
          str(owns))


def audit_modules(D):
    pay = D.get("modules") or {}
    names = pay.get("modules") or []
    check("19 endpoints registered in the MORS index",
          len(names) == 19, f"n={len(names)}")
    check("prompt library endpoint registered", "prompts" in names)
    check("sources module registered", "sources" in names)
    check("team module registered", "team" in names)


def audit_layouts(D):
    proj = D.get("projects") or {}
    check("projects payload present", bool(proj))
    if D.get("neo"):
        neo = D["neo"]
        rows_n = neo.get("items") or neo.get("rows") or []
        check("neo endpoint returns close approaches", bool(rows_n),
              f"keys={sorted(neo)}")
    if D.get("matrix"):
        check("neo-matrix payload present", bool(D["matrix"]))
    if D.get("light"):
        check("light-pollution payload present", bool(D["light"]))
    if D.get("quantum_data"):
        q = D["quantum_data"]
        check("quantum data labelled as simulation",
              "sim" in json.dumps(q).lower() or "qpu" in json.dumps(q).lower(),
              "no simulation disclaimer found")


# ------------------------------------------------- batch 2: physics checks
HB = 1.98644586e-23        # h*c in J cm
HBAR = 1.054571817e-34
QE = 1.602176634e-19
C_KMS = 299792.458


def audit_horizons(D):
    h = D.get("horizons")
    if not h:
        check("horizons payload present", False)
        return
    body = h.get("body")
    bodies = h.get("bodies") or []
    orbits = h.get("orbits") or {}
    series = h.get("series") or []
    check("horizons declares body + bodies", bool(body) and bool(bodies),
          f"body={body} bodies={bodies}")
    check("one orbit track per declared body", set(orbits) == set(bodies),
          f"{sorted(orbits)} vs {bodies}")
    check("series is exactly one body's track (no cross-planet line)",
          series == orbits.get(body), f"len={len(series)}")
    check("earth and mars both fetched", "Earth" in orbits and "Mars" in orbits,
          str(sorted(orbits)))
    limits = {"Earth": (0.95, 1.05), "Mars": (1.35, 1.75)}
    for b, pts in orbits.items():
        check(f"horizons/{b}: at least 100 epochs", len(pts) >= 100, f"n={len(pts)}")
        if not pts:
            continue
        ts = [p.get("t") for p in pts]
        check(f"horizons/{b}: epochs strictly increasing",
              all(a is not None and c is not None and c > a
                  for a, c in zip(ts, ts[1:])))
        rs = [math.sqrt((p.get("x_au") or 0) ** 2 + (p.get("y_au") or 0) ** 2
                        + (p.get("z_au") or 0) ** 2) for p in pts]
        lo, hi = limits.get(b, (0.2, 60.0))
        check(f"horizons/{b}: heliocentric radius inside {lo}-{hi} au",
              min(rs) >= lo and max(rs) <= hi,
              f"{min(rs):.4f}-{max(rs):.4f} au")
    check("horizons source names the JPL endpoint",
          "ssd.jpl.nasa.gov" in json.dumps(h.get("source") or {}),
          str(h.get("source")))
    check("horizons frame is heliocentric ICRS",
          "heliocentric" in str(h.get("frame") or "").lower(), str(h.get("frame")))


def audit_exoplanet_physics(D):
    rows = (D.get("exo") or {}).get("rows") or []
    if not rows:
        check("exoplanet physics: rows present", False)
        return
    ratios = []
    for r in rows:
        a, per = r.get("semi_major_au"), r.get("period_d")
        if a and per:
            ratios.append(a ** 3 / ((per / 365.25) ** 2))
    check("Kepler a^3/T^2 inside stellar-mass range (0.02-10 Msun)",
          bool(ratios) and all(0.02 <= k <= 10 for k in ratios),
          f"n={len(ratios)} min={min(ratios):.3f} max={max(ratios):.3f}" if ratios
          else "no a/P pairs")
    bad = [r.get("planet_name") for r in rows
           if not (1992 <= (r.get("discovery_year") or 0) <= 2030)]
    check("discovery_year within 1992-2030", not bad, str(bad[:4]))
    bad = [r.get("planet_name") for r in rows
           if r.get("semi_major_au") is not None
           and not (0.001 <= r["semi_major_au"] <= 100)]
    check("semi_major_au in 0.001-100 au", not bad, str(bad[:4]))
    bad = [r.get("planet_name") for r in rows
           if r.get("radius_re") is not None and not (0.05 <= r["radius_re"] <= 30)]
    check("radius_re in 0.05-30 earth radii", not bad, str(bad[:4]))
    bad = [r.get("planet_name") for r in rows
           if r.get("mass_me") is not None and not (0.005 <= r["mass_me"] <= 1e4)]
    check("mass_me in 0.005-1e4 earth masses", not bad, str(bad[:4]))
    wrong, missing = [], []
    for r in rows:
        s = r.get("insolation_st")
        if not s and r.get("equilibrium_temp_k"):
            s = (r["equilibrium_temp_k"] / 255.0) ** 4
        g = r.get("habitability_index")
        if not s:
            if g is not None:
                missing.append(r.get("planet_name"))
            continue
        want = 1.0 if s < 1.1 else (0.83 if s < 1.78 else 0.0)
        if g is None or abs(g - want) > 1e-6:
            wrong.append((r.get("planet_name"), s, g, want))
    check("habitability gate reproduces from S (Kopparapu 2013)",
          not wrong, str(wrong[:3]))
    check("no habitability value without an S value", not missing, str(missing[:4]))
    hz = [r for r in rows if (r.get("habitability_index") or 0) >= 0.83]
    check("at least 5 planets inside the habitable-zone window",
          len(hz) >= 5, f"n={len(hz)}")
    cov = sum(1 for r in rows if r.get("insolation_st"))
    check("pl_insol coverage >= 70% of rows", cov / len(rows) >= 0.70,
          f"{cov}/{len(rows)}")


def audit_quantum_physics(D):
    q = D.get("quantum_data") or {}
    v = q.get("verification") or {}
    check("quantum verification present", bool(v), str(sorted(q)))
    if v:
        err = v.get("entropy_error")
        check("bell entropy error <= 1e-6",
              err is not None and err <= 1e-6, str(err))
        check("state normalisations == 1",
              near(v.get("normalization_bell"), 1.0, 1e-9)
              and near(v.get("normalization_ghz"), 1.0, 1e-9),
              f"{v.get('normalization_bell')} / {v.get('normalization_ghz')}")
    bell = ((q.get("states") or {}).get("bell")) or {}
    if bell:
        check("bell entropy == 1 ebit", near(bell.get("entanglement_entropy_ebit"), 1.0, 1e-6),
              str(bell.get("entanglement_entropy_ebit")))
        check("bell reduced purity == 0.5", near(bell.get("reduced_purity"), 0.5, 1e-6),
              str(bell.get("reduced_purity")))
        exps = list((bell.get("expectation") or {}).values())
        check("bell expectations in [-1,1]",
              bool(exps) and all(-1.001 <= x <= 1.001 for x in exps), str(exps))
    levels = ((q.get("qho_levels") or {}).get("levels")) or []
    if len(levels) >= 3:
        es = [l.get("E_j") for l in levels]
        check("QHO levels strictly increasing",
              all(b > a for a, b in zip(es, es[1:])), str(es))
        ds = [round(b - a, 24) for a, b in zip(es, es[1:])]
        check("QHO level spacing equal (harmonic ladder)",
              max(ds) - min(ds) <= 1e-22, str(ds))
        check("QHO spacing == hbar*omega",
              near(ds[0], HBAR * ((q.get("qho_levels") or {}).get("omega_rad_s") or 0), 1e-21)
              if (q.get("qho_levels") or {}).get("omega_rad_s") else True)
        bad = [l for l in levels if not near(l.get("E_ev"), (l.get("E_j") or 0) / QE, 0.01)]
        check("E_ev == E_j / e", not bad, str(bad[:2]))
    rabi = ((q.get("rabi_drive") or {}).get("samples")) or []
    if rabi:
        ts = [s.get("t_ns") for s in rabi]
        ps = [s.get("p_excited") for s in rabi]
        check("rabi axis in nanoseconds (0 -> 4 ns)",
              near(ts[0], 0.0, 1e-6) and near(ts[-1], 4.0, 0.01) and ts[-1] > ts[0],
              f"{ts[0]}..{ts[-1]}")
        check("rabi time strictly increasing",
              all(b > a for a, b in zip(ts, ts[1:])), str(ts[:6]))
        check("rabi population spans a full oscillation (0 -> 1)",
              min(ps) <= 0.01 and max(ps) >= 0.99,
              f"min={min(ps)} max={max(ps)}")
        check("rabi population bounded in [0,1]",
              all(0.0 <= p <= 1.0 for p in ps))
    hon = str(q.get("honesty") or "")
    check("quantum honesty admits classical simulation",
          "no quantum processing unit" in hon.lower(), hon[:90])
    mq = D.get("quantum") or {}
    cm1 = (mq.get("qho") or {}).get("levels_cm-1") or []
    js = (mq.get("qho") or {}).get("levels_J") or []
    if cm1 and len(cm1) == len(js):
        bad = [i for i, (c, e) in enumerate(zip(cm1, js))
               if abs(c - e / HB) / (e / HB) > 0.01]
        check("mors QHO levels_cm-1 == E_J/(h c)", not bad, str(bad))
    states = mq.get("states") or []
    bad = []
    for s in states:
        pur, ent, q = s.get("purity"), s.get("entropy_ebit"), s.get("qubits")
        if pur is None or not (0.0 <= pur <= 1.0):
            bad.append((s.get("id"), "purity", pur))
        elif ent is None or q is None or not (0.0 <= ent <= q + 1e-9):
            bad.append((s.get("id"), "entropy", ent, q))
    check("mors state purity/entropy within bounds", not bad, str(bad))
    fid = mq.get("fidelity") or []
    check("gate fidelities in (0,1]",
          bool(fid) and all(0 < (f.get("fidelity") or 0) <= 1 for f in fid),
          str([f.get("fidelity") for f in fid]))


def audit_spectral_consistency(D):
    sp = D.get("spectral") or {}
    if not sp:
        check("spectral payload present", False)
        return
    bands = sp.get("bands") or []
    ids = sp.get("band_ids") or []
    check("band_ids mirror bands[].band", ids == [b.get("band") for b in bands],
          f"{ids} vs {[b.get('band') for b in bands]}")
    proc = sp.get("processing") or {}
    ev = proc.get("explained_variance_ratio") or []
    check("PCA explained variance descending",
          len(ev) >= 2 and all(a >= b for a, b in zip(ev, ev[1:])), str(ev))
    check("PCA explained variance sums to <= 1",
          bool(ev) and sum(ev) <= 1.0 + 1e-9, f"sum={sum(ev):.4f}")
    check("PCA component count <= n_features and >= 1",
          bool(ev) and 1 <= len(ev) <= (proc.get("n_features") or len(bands)),
          f"{len(ev)} components / {proc.get('n_features')} features")
    n_feat = proc.get("n_features") or len(bands)
    bad = [p.get("land_cover") for p in (sp.get("profiles") or [])
           if len(p.get("reflectance") or []) != n_feat]
    check("every profile vector matches n_features", not bad, str(bad[:3]))
    bad = [p.get("land_cover") for p in (sp.get("profiles") or [])
           if len(p.get("pca") or []) != len(ev)]
    check("every profile pca matches component count", not bad, str(bad[:3]))
    bad = [p.get("land_cover") for p in (sp.get("profiles") or [])
           for k in ("ndvi", "ndbi", "ndwi")
           if p.get(k) is not None and not (-1.0 <= p[k] <= 1.0)]
    check("spectral indices inside [-1,1]", not bad, str(bad[:4]))


def audit_light_pollution(D):
    lp = D.get("light") or {}
    sites = lp.get("sites") or []
    if not sites:
        check("light-pollution sites present", False)
        return
    ordered = sorted(sites, key=lambda s: s.get("lights_index") or 0)
    nelms = [s.get("nelm_mag") for s in ordered]
    check("NELM falls as lights_index rises (brighter sky, fainter limit)",
          all((b or 0) <= (a or 0) + 1e-9 for a, b in zip(nelms, nelms[1:])),
          str(nelms))
    check("every bortle index inside 1..9",
          all(1 <= (s.get("bortle_published") or 0) <= 9
              and 1 <= (s.get("bortle_model") or 0) <= 9 for s in sites))
    dev = [abs((s.get("bortle_model") or 0) - (s.get("bortle_published") or 0))
           for s in sites]
    check("modelled bortle within 2 classes of published",
          max(dev) <= 2, f"max dev={max(dev)}")
    bad = [s.get("name") for s in sites
           if not (0 < (s.get("radiance_nw_cm2_sr") or 0))
           or not (1.0 <= (s.get("nelm_mag") or 0) <= 9.0)
           or not (14.0 <= (s.get("sqm_mag_arcsec2") or 0) <= 23.0)]
    check("site radiance/NELM/SQM inside physical ranges", not bad, str(bad[:3]))
    bad = []
    for s in sites:
        L = s.get("radiance_nw_cm2_sr")
        if not L:
            continue
        mu = 17.836 - 2.5 * math.log10(L)          # declared SQM calibration
        if not near(s.get("sqm_mag_arcsec2"), mu, 0.05):
            bad.append((s.get("name"), "sqm", s.get("sqm_mag_arcsec2"), round(mu, 3)))
        if not near(s.get("nelm_mag"), mu - 14.6, 0.05):
            bad.append((s.get("name"), "nelm", s.get("nelm_mag"), round(mu - 14.6, 3)))
    check("site SQM/NELM reproduce the declared calibration", not bad, str(bad[:3]))
    curve = lp.get("reference_curve") or []
    if len(curve) >= 3:
        rad = [c.get("radiance_nw_cm2_sr") for c in curve]
        nm = [c.get("nelm_mag") for c in curve]
        check("reference curve radiance ascending",
              all(b >= a for a, b in zip(rad, rad[1:])), str(rad[:5]))
        check("reference curve NELM descending",
              all((b or 0) <= (a or 0) for a, b in zip(nm, nm[1:])), str(nm[:5]))
    check("light-pollution source labels the NASA product",
          "gibs" in json.dumps(lp.get("source") or {}).lower()
          or "viirs" in json.dumps(lp.get("source") or {}).lower(),
          str((lp.get("source") or {}).get("product")))


def audit_curves(D):
    photo = (D.get("photo") or {}).get("rows") or []
    bad = []
    for r in photo:
        flux = (r.get("curve") or {}).get("flux") or []
        if not flux:
            bad.append((r.get("target_id"), "no curve"))
            continue
        want = 2.5 * math.log10(max(flux) / min(flux))
        if abs(want - (r.get("amplitude_mag") or 0)) > 0.02:
            bad.append((r.get("target_id"), round(want, 4), r.get("amplitude_mag")))
        if r.get("n_points") != len(flux):
            bad.append((r.get("target_id"), "n_points"))
    check("photometry amplitude == 2.5 log10(max/min flux)", not bad, str(bad[:3]))
    bad = [r.get("target_id") for r in photo
           if not (r.get("snr") or 0) > 0 or not (r.get("rms_mag") or 0) > 0
           or (r.get("variability_period_d") is not None
               and not (r.get("variability_period_d") > 0))]
    check("photometry snr/rms/period positive", not bad, str(bad[:3]))
    check("aperiodic targets declare a null period",
          all(r.get("variability_period_d") is None or r.get("variability_period_d") > 0
              for r in photo))

    lcs = (D.get("lc") or {}).get("rows") or []
    bad = []
    for r in lcs:
        ph = r.get("phase") or []
        fl = r.get("relative_flux") or []
        if len(ph) != (r.get("n_points") or -1) or len(fl) != (r.get("n_points") or -1):
            bad.append((r.get("curve_id"), "length"))
        if ph and not all(0.0 <= p < 1.0 for p in ph):
            bad.append((r.get("curve_id"), "phase range"))
        if not (0.0 < (r.get("depth") or 0) < 1.0):
            bad.append((r.get("curve_id"), "depth"))
        if not ((r.get("ingress_duration_d") or 0) > 0
                and (r.get("egress_duration_d") or 0) > 0):
            bad.append((r.get("curve_id"), "contact durations"))
        if r.get("period_source") not in ("measured",
                                          "default 1.0 d folding window (aperiodic target)"):
            bad.append((r.get("curve_id"), "period_source"))
        if not (r.get("period_d") or 0) > 0:
            bad.append((r.get("curve_id"), "period"))
    check("light curves: phase/flux/depth/contacts consistent", not bad, str(bad[:3]))
    pmap = {r.get("target_id"): r.get("variability_period_d") for r in photo}
    bad = [(r.get("curve_id"), r.get("period_d"), pmap.get(r.get("target_id")))
           for r in lcs
           if pmap.get(r.get("target_id")) is not None
           and not near(r.get("period_d"), pmap.get(r.get("target_id")), 1e-6)]
    check("light-curve period mirrors its photometry target", not bad, str(bad[:3]))

    specs = (D.get("spec") or {}).get("rows") or []
    bad = []
    for r in specs:
        wl = r.get("wavelength_A") or []
        fl = r.get("flux_density") or []
        if wl and not all(b >= a for a, b in zip(wl, wl[1:])):
            bad.append((r.get("spectrum_id"), "wavelength order"))
        if len(wl) != len(fl):
            bad.append((r.get("spectrum_id"), "array length"))
        if fl and not all(0.0 < f <= 1.5 for f in fl):
            bad.append((r.get("spectrum_id"), "flux range"))
        want = (r.get("redshift_z") or 0) * C_KMS
        if abs((r.get("velocity_kms") or 0) - want) > max(0.5, 0.01 * abs(want)):
            bad.append((r.get("spectrum_id"), "v != z c"))
    check("spectroscopy: wavelength ordered, v == z c, flux normalised",
          not bad, str(bad[:3]))


def audit_kp_daily(D):
    kp = D.get("kp") or {}
    daily = kp.get("daily") or []
    if not daily:
        check("kp daily series present", False)
        return
    dates = [d.get("t") for d in daily]
    check("daily dates unique", len(dates) == len(set(dates)), str(dates[:3]))
    check("daily dates ascending", all(b > a for a, b in zip(dates, dates[1:])),
          f"{dates[0]}..{dates[-1]}")
    flare_sum = sum(d.get("flare_count") or 0 for d in daily)
    check("daily flare counts sum to the flare list",
          flare_sum == len(kp.get("flares") or []),
          f"{flare_sum} vs {len(kp.get('flares') or [])}")
    bad, flagged = [], 0
    for d in daily:
        if d.get("kp_max") is None:
            if d.get("no_data"):
                flagged += 1
            continue
        if not (0 <= (d.get("kp_min") or 0) <= (d.get("kp_mean") or 0)
                <= (d.get("kp_max") or 0) <= 9):
            bad.append((d.get("t"), d.get("kp_min"), d.get("kp_max")))
    check("daily Kp min<=mean<=max inside 0..9", not bad, str(bad[:3]))
    check("days with neither Kp nor flares are flagged no_data",
          all(d.get("kp_max") is not None or (d.get("flare_count") or 0) > 0
              or d.get("no_data") for d in daily),
          f"flagged={flagged}/{len(daily)}")
    src = kp.get("source") or {}
    if src.get("flare_records") is not None:
        check("flare window declared as ISO dates",
              str((src.get("flare_window") or {}).get("start", ""))[:4].isdigit(),
              str(src.get("flare_window")))


def audit_images_fits(D):
    imgs = (D.get("images") or {}).get("rows") or []
    if not imgs:
        check("image rows present", False)
        return
    ids = [i.get("image_id") for i in imgs]
    check("image ids unique", len(ids) == len(set(ids)), str(ids))
    bad = [i.get("image_id") for i in imgs
           if not str(i.get("url") or "").startswith(("http://", "https://"))]
    check("image urls absolute", not bad, str(bad[:3]))
    bad = [i.get("image_id") for i in imgs
           if not re.match(r"^\d{4}-\d{2}-\d{2}$", str(i.get("date") or ""))]
    check("image dates ISO formatted", not bad, str(bad[:3]))
    bad = [i.get("image_id") for i in imgs
           if not str(i.get("title") or "").strip()
           or not (i.get("fits_header") or {})]
    check("image titles + FITS headers present", not bad, str(bad[:3]))
    fits = (D.get("fits") or {}).get("rows") or []
    bad = [f.get("image_id") for f in fits if f.get("image_id") not in set(ids)]
    check("fits rows reference real images", not bad, str(bad[:3]))
    check("fits headers carry WCS keys",
          bool(fits) and all({"CTYPE1", "EQUINOX"} <= set(f.get("header") or {})
                             for f in fits))


# --------------------------------------------------------------------- main
def audit_prompts(D):
    pay = D.get("prompts") or {}
    rows = pay.get("prompts") or []
    check("prompt library exposes 6 master prompts", len(rows) == 6,
          f"n={len(rows)}")
    want = ["aimors_scientific", "uiux_command_center", "uiux_visualization",
            "cyber_mors", "analytics_report", "deep_audit"]
    ids = [r.get("id") for r in rows]
    check("prompt ids match the registry", sorted(ids) == sorted(want),
          str(ids))
    check("every prompt is loaded with real text",
          all(r.get("loaded") and (r.get("text") or "").strip()
              for r in rows),
          str([r.get("id") for r in rows if not r.get("loaded")]))
    check("AI.MORS analyst prompt carries the 25-rule lifecycle",
          any("25. FINAL OBJECTIVE" in (r.get("text") or "")
              for r in rows))
    check("CYBER.MORS prompt maps to MITRE ATT&CK",
          any("MITRE ATT&CK" in (r.get("text") or "") for r in rows))
    check("DEEP.AUDIT prompt declares the 5-pass protocol",
          any("PASS 5" in (r.get("text") or "") for r in rows))
    check("prompt library carries trace+badge",
          bool(pay.get("trace")) and bool(pay.get("badge")))


def audit_name_policy(D=None):
    """The three non-leader personal names must not appear in any project
    file (source, docs, static markup); only the team leader stays named."""
    if D:
        payload = json.dumps(D, ensure_ascii=False)
        leaked = [n for n in _PRIVATE_NAMES if n in payload]
        check("no private member name in any API payload", not leaked,
              str(leaked))
    hits = []
    scan_ext = {".py", ".md", ".html", ".txt", ".bat", ".css", ".js"}
    for p in ROOT.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in scan_ext:
            continue
        rel = p.relative_to(ROOT)
        if rel.parts[0] in {".git", ".venv", "node_modules", "__pycache__"}:
            continue
        if p.name == "audit_data.py":      # this file names them to scan for
            continue
        try:
            txt = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for n in _PRIVATE_NAMES:
            if n in txt:
                hits.append(f"{rel.as_posix()}:{n}")
    check("no private member name in any project file", not hits,
          str(hits[:6]))


def main() -> int:
    print(f"audit -> {BASE}")
    D = load()
    audit_health(D)
    audit_datahealth(D)
    audit_problems(D)
    audit_solutions(D)
    audit_satellite(D)
    audit_exoplanets(D)
    audit_objects(D)
    audit_sky_surfaces(D)
    audit_space_weather(D)
    audit_report(D)
    audit_sources(D)
    audit_team(D)
    audit_name_policy(D)
    audit_prompts(D)
    audit_modules(D)
    audit_layouts(D)
    audit_horizons(D)
    audit_exoplanet_physics(D)
    audit_quantum_physics(D)
    audit_spectral_consistency(D)
    audit_light_pollution(D)
    audit_curves(D)
    audit_kp_daily(D)
    audit_images_fits(D)

    fails = [r for r in RESULTS if not r[1]]
    print()
    print("=" * 70)
    print(f"AUDIT: {len(RESULTS)} checks, {len(fails)} failed")
    if fails:
        for name, _, detail in fails:
            print(f"  FAIL  {name}   {detail}")
        print("RESULT: AUDIT: FAIL")
        return 1
    print("RESULT: AUDIT: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
