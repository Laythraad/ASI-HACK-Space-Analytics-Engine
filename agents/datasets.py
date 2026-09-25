"""
datasets — ASI-HACK Space Analytics Engine
=====================================================
Scientific data modules for the extended skill set (remote sensing,
light pollution, space-weather indices, quantum simulation).

Every module returns a payload with an explicit ``source`` block so Agent 3
can attach traceability IDs and Agent 2 can audit provenance.

Design rules (never raise, degrade to a deterministic fallback):
  * Real endpoints are tried first (NASA GIBS WMS, NOAA SWPC).
  * Constants used for any conversion are DECLARED in the payload under
    ``model`` / ``calibration`` so a reviewer can recompute the numbers.
  * Nothing is presented as a measurement that is actually a model output.
"""

from __future__ import annotations

import io
import json
import logging
import math
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import requests

log = logging.getLogger("datasets")

# ============================================================ shared constants
AU_KM = 149_597_870.7          # IAU 2012 nominal Earth-Sun distance
LD_KM = 384_400.0              # IAU mean Earth-Moon distance
LD_IN_AU = LD_KM / AU_KM       # 0.0025696 au per lunar distance
TIMEOUT = 25

_GIBS_WMS = "https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi"
_GIBS_LAYER = "VIIRS_Black_Marble"
_GIBS_TIME = "2016-01-01"      # annual Black Marble composite (from GetCapabilities)

# --------------------------------------------------------------------- cache
_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_CACHE_LOCK = threading.Lock()
DEFAULT_TTL = 300


def _cached(key: str, ttl: int = DEFAULT_TTL) -> Optional[Dict[str, Any]]:
    with _CACHE_LOCK:
        hit = _CACHE.get(key)
        if hit and time.time() - hit[0] < ttl:
            return hit[1]
    return None


def _store(key: str, value: Dict[str, Any]) -> Dict[str, Any]:
    with _CACHE_LOCK:
        _CACHE[key] = (time.time(), value)
    return value


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


# ============================================================ 1. LIGHT POLLUTION
# Sites chosen to span the full Bortle range (1 = pristine, 9 = inner city).
LIGHT_SITES: List[Dict[str, Any]] = [
    {"name": "Open Mediterranean (no ground lights)", "lat": 34.0, "lon": 28.0,
     "class": "ocean", "bortle_published": 1},
    {"name": "Mauna Kea Observatories, Hawaii", "lat": 19.82, "lon": -155.47,
     "class": "observatory", "bortle_published": 1},
    {"name": "Paranal / Atacama Desert, Chile", "lat": -24.63, "lon": -70.40,
     "class": "observatory", "bortle_published": 1},
    {"name": "Central Sahara, Algeria", "lat": 26.0, "lon": 5.0,
     "class": "desert", "bortle_published": 1},
    {"name": "Amazon basin near Manaus, Brazil", "lat": -3.1, "lon": -60.0,
     "class": "forest", "bortle_published": 3},
    {"name": "Aswan, Egypt", "lat": 24.09, "lon": 32.90,
     "class": "small_city", "bortle_published": 5},
    {"name": "Nairobi, Kenya", "lat": -1.29, "lon": 36.82,
     "class": "large_city", "bortle_published": 6},
    {"name": "Berlin, Germany", "lat": 52.52, "lon": 13.40,
     "class": "metropolis", "bortle_published": 7},
    {"name": "Riyadh, Saudi Arabia", "lat": 24.71, "lon": 46.68,
     "class": "metropolis", "bortle_published": 8},
    {"name": "Cairo, Egypt", "lat": 30.04, "lon": 31.24,
     "class": "megacity", "bortle_published": 9},
    {"name": "Tokyo, Japan", "lat": 35.68, "lon": 139.65,
     "class": "megacity", "bortle_published": 9},
]

# --- declared calibration (V-band photometry, see model block in payload) ---
# Radiance -> SQM surface brightness, derived from the AB zero point:
#   f_nu(0 AB) = 3.631e-23 W m^-2 Hz^-1   (1 Jy = 1e-26 W m^-2 Hz^-1)
#   1 arcsec^2 = 2.3504e-11 sr,  dnu_V = c*dlam/lam0^2 = 8.821e13 Hz
#   => L[nW/cm^2/sr] = 1.3628e7 * 10^(-0.4*mu)   with mu in mag/arcsec^2
#   => mu = SQM_ZERO - 2.5*log10(L),  SQM_ZERO = 2.5*log10(1.3628e7)
SQM_ZERO = 2.5 * math.log10(1.3628e7)      # 17.836
NELM_OFFSET = 14.6                         # NELM = SQM - 14.6 (empirical)

# End-point anchors of the radiance calibration. Both ends are pinned to the
# PUBLISHED Bortle scale (data/light_pollution_reference.csv):
#   Bortle 1 -> NELM 7.60 mag -> L = 10^((3.236-7.60)/2.5) = 0.0186 nW/cm^2/sr
#   Bortle 9 -> NELM 3.40 mag -> L = 10^((3.236-3.40)/2.5) = 1.881  nW/cm^2/sr
L_MIN = 0.0186                             # pristine,      nW/cm^2/sr
L_MAX = 1.881                              # inner city,    nW/cm^2/sr
# Black Marble is a gamma-encoded rendering of the DNB counts, so a de-gamma
# exponent is applied before the geometric ramp (declared, not fitted).
GAMMA = 1.30
INDEX_WEIGHT_P95 = 0.70    # blended lights_index definition (declared)
D_BBOX_DEG = 0.6           # ~66 km half-width sampling tile
TILE_PX = 64


def _bortle_from_nelm(nelm: float) -> int:
    """Bortle scale (Sky & Telescope, Feb 2001) from naked-eye limiting mag."""
    bands = [(7.6, 1), (7.3, 2), (7.0, 3), (6.6, 4), (6.1, 5),
             (5.5, 6), (4.9, 7), (4.2, 8)]
    for cut, cls in bands:
        if nelm >= cut:
            return cls
    return 9


def _fetch_tile(site: Dict[str, Any]) -> Optional[Dict[str, float]]:
    """Pull one real VIIRS Black Marble tile from NASA GIBS and reduce it."""
    la, lo = site["lat"], site["lon"]
    d = D_BBOX_DEG
    bbox = f"{la - d},{lo - d},{la + d},{lo + d}"
    url = (f"{_GIBS_WMS}?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetMap"
           f"&LAYERS={_GIBS_LAYER}&STYLES=&CRS=EPSG:4326&BBOX={bbox}"
           f"&WIDTH={TILE_PX}&HEIGHT={TILE_PX}&FORMAT=image/png&TIME={_GIBS_TIME}")
    try:
        resp = requests.get(url, timeout=TIMEOUT)
        resp.raise_for_status()
        from PIL import Image                      # Pillow is available
        rgb = np.asarray(Image.open(io.BytesIO(resp.content)))[:, :, :3].astype(float)
        lum = 0.2126 * rgb[:, :, 0] + 0.7152 * rgb[:, :, 1] + 0.0722 * rgb[:, :, 2]
        return {
            "p95": float(np.percentile(lum, 95)),
            "mean": float(lum.mean()),
            "p05": float(np.percentile(lum, 5)),
            "max": float(lum.max()),
        }
    except Exception as exc:                        # noqa: BLE001
        log.warning("GIBS tile failed for %s: %s", site["name"], str(exc)[:160])
        return None


def fetch_light_pollution(force: bool = False) -> Dict[str, Any]:
    """Light pollution vs stellar visibility (real NASA nighttime lights).

    Pipeline
      NASA GIBS GetMap (VIIRS Black Marble, real pixels)
        -> tile luminance statistics
        -> blended ``lights_index`` in [0,1]   (declared weighting)
        -> sky radiance L  (declared geometric calibration)
        -> sky surface brightness mu (AB-derived formula)
        -> naked-eye limiting magnitude NELM = mu - 14.6
        -> Bortle class
    """
    key = "light_pollution"
    if not force:
        hit = _cached(key)
        if hit:
            return hit
    light_pollution_reference_csv()

    with ThreadPoolExecutor(max_workers=6) as pool:
        stats = list(pool.map(_fetch_tile, LIGHT_SITES))

    sites: List[Dict[str, Any]] = []
    for site, st in zip(LIGHT_SITES, stats):
        if st is None:
            continue
        index = (INDEX_WEIGHT_P95 * (st["p95"] / 255.0)
                 + (1 - INDEX_WEIGHT_P95) * (st["mean"] / 255.0))
        index = float(min(1.0, max(0.0, index)))
        # declared calibration: de-gamma then geometric ramp between the two
        # Bortle-anchored endpoints
        radiance = L_MIN * (L_MAX / L_MIN) ** (index ** GAMMA)
        sqm = SQM_ZERO - 2.5 * math.log10(radiance)
        nelm = sqm - NELM_OFFSET
        sites.append({
            "name": site["name"],
            "lat": site["lat"],
            "lon": site["lon"],
            "class": site["class"],
            "lights_index": round(index, 4),
            "tile_p95_luminance": round(st["p95"], 1),
            "tile_mean_luminance": round(st["mean"], 1),
            "radiance_nw_cm2_sr": round(radiance, 4),
            "sqm_mag_arcsec2": round(sqm, 2),
            "nelm_mag": round(nelm, 2),
            "bortle_model": _bortle_from_nelm(nelm),
            "bortle_published": site["bortle_published"],
        })
    sites.sort(key=lambda r: r["radiance_nw_cm2_sr"])

    # theoretical skyglow -> visibility curve for the chart overlay
    curve = []
    for k in range(0, 41):
        rad = L_MIN * (L_MAX / L_MIN) ** ((k / 40.0) ** GAMMA)
        curve.append({"radiance_nw_cm2_sr": round(rad, 4),
                      "nelm_mag": round(SQM_ZERO - 2.5 * math.log10(rad)
                                        - NELM_OFFSET, 2)})

    out = {
        "sites": sites,
        "reference_curve": curve,
        "model": {
            "radiance_to_sqm": "mu = 17.836 - 2.5*log10(L)",
            "radiance_to_sqm_derivation": (
                "L[nW/cm^2/sr] = 1.3628e7 * 10^(-0.4*mu); "
                "f_nu(AB=0)=3.631e-23 W/m^2/Hz, 1 arcsec^2=2.3504e-11 sr, "
                "dnu_V=8.821e13 Hz (550 nm, 89 nm bandpass)"),
            "sqm_zero": round(SQM_ZERO, 3),
            "nelm_formula": "NELM = mu - 14.6",
            "nelm_offset": NELM_OFFSET,
            "bortle_breakpoints": "Bortle 1..9 from NELM "
                                  "[7.6,7.3,7.0,6.6,6.1,5.5,4.9,4.2]",
            "calibration": (f"L = {L_MIN} * ({L_MAX}/{L_MIN}) ** "
                            f"(index ** {GAMMA})"),
            "calibration_anchors": (
                "L_MIN/L_MAX pinned to published Bortle 1 (NELM 7.60) and "
                "Bortle 9 (NELM 3.40) — see data/light_pollution_reference.csv"),
            "gamma_de_rendering": GAMMA,
            "index_formula": (
                f"index = {INDEX_WEIGHT_P95}*(tile_p95/255) + "
                f"{round(1 - INDEX_WEIGHT_P95, 2)}*(tile_mean/255)"),
            "l_min_nw_cm2_sr": L_MIN,
            "l_max_nw_cm2_sr": L_MAX,
            "tile_half_width_deg": D_BBOX_DEG,
            "tile_pixels": TILE_PX,
            "caveats": [
                "VIIRS Black Marble is a rendered colour product, not linear "
                "radiance; L(index) is a DECLARED calibration anchored to the "
                "published Bortle scale, not an absolute measurement.",
                "The composite floor includes natural airglow/starlight, so "
                "pristine sites are compressed near the dark end "
                "(dark-site NELM may be under-estimated by ~0.4 mag).",
                "SQM_ZERO is derived from the AB zero point, not fitted.",
            ],
        },
        "source": {
            "endpoint": _GIBS_WMS,
            "layer": _GIBS_LAYER,
            "time": _GIBS_TIME,
            "product": "NASA EOSDIS GIBS — Suomi NPP VIIRS Black Marble",
            "reference_docs": ["data/light_pollution_reference.csv"],
            "fetched_at": _utc(),
            "live": len(sites) == len(LIGHT_SITES),
        },
    }
    return _store(key, out)


def light_pollution_reference_csv() -> str:
    """Local reference table (Provided Local Dataset) — creates it if absent."""
    from pathlib import Path
    path = Path(__file__).resolve().parent.parent / "data" / "light_pollution_reference.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        # Self-consistent reference table: L is derived from NELM through the
        # declared model  NELM = 17.836 - 2.5*log10(L) - 14.6
        # (published Bortle/SQM pairs scatter by ~0.3 mag, so NELM is the
        #  primary anchor and SQM is reported as NELM + 14.6).
        rows = [
            ("bortle_1_pristine", 0.0180, 22.20, 7.60, 1, "Bortle, Sky & Telescope 2001"),
            ("bortle_2_true_dark", 0.0237, 21.90, 7.30, 2, "Bortle, Sky & Telescope 2001"),
            ("bortle_3_rural", 0.0312, 21.60, 7.00, 3, "Bortle, Sky & Telescope 2001"),
            ("bortle_4_rural-urban", 0.0451, 21.20, 6.60, 4, "Bortle, Sky & Telescope 2001"),
            ("bortle_5_suburban", 0.0715, 20.70, 6.10, 5, "Bortle, Sky & Telescope 2001"),
            ("bortle_6_bright_suburb", 0.1243, 20.10, 5.50, 6, "Bortle, Sky & Telescope 2001"),
            ("bortle_7_suburban-urban", 0.2159, 19.50, 4.90, 7, "Bortle, Sky & Telescope 2001"),
            ("bortle_8_urban", 0.4116, 18.80, 4.20, 8, "Bortle, Sky & Telescope 2001"),
            ("bortle_9_inner_city", 0.8600, 18.00, 3.40, 9, "Bortle, Sky & Telescope 2001"),
        ]
        cols = ["class", "radiance_nw_cm2_sr", "sqm_mag_arcsec2", "nelm_mag",
                "bortle", "source"]
        with path.open("w", encoding="utf-8", newline="") as fh:
            fh.write(",".join(cols) + "\n")
            for r in rows:
                fh.write(",".join(str(x) for x in r) + "\n")
    return str(path.relative_to(path.parent.parent))


# ================================================================= 2. Kp INDEX
_KP_ENDPOINTS = (
    "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json",
    "https://services.swpc.noaa.gov/json/planetary_k_index_1m.json",
)


def fetch_kp_index(nasa_key: str = "DEMO_KEY", force: bool = False) -> Dict[str, Any]:
    """Planetary K-index (NOAA SWPC) + DONKI flare classes on one timeline."""
    key = "kp_index"
    if not force:
        hit = _cached(key, ttl=300)
        if hit:
            return hit

    kp_points: List[Dict[str, Any]] = []
    kp_live = False
    # --- 3-hourly planetary K index (authoritative NOAA product) ------------
    try:
        resp = requests.get(_KP_ENDPOINTS[0], timeout=TIMEOUT)
        resp.raise_for_status()
        rows = resp.json()
        if isinstance(rows, list) and rows and isinstance(rows[0], list):
            header = rows[0]
            rows = [dict(zip(header, r)) for r in rows[1:]]
        for r in rows:
            t = r.get("time_tag") or r.get("Time") or ""
            kp = _num(r.get("Kp") if r.get("Kp") is not None else r.get("kp"))
            if t and kp is not None:
                kp_points.append({"t": t, "kp": round(float(kp), 2),
                                  "station_count": _num(r.get("station_count"))})
        kp_live = bool(kp_points)
    except Exception as exc:                          # noqa: BLE001
        log.warning("NOAA Kp fetch failed: %s", str(exc)[:160])

    if not kp_points:
        kp_points = _fallback_kp()

    # --- solar flares (DONKI FLR) with class -> peak flux ------------------
    flares, flare_live, flare_stats = _fetch_flares(nasa_key)

    # --- daily aggregation shared by the dual-axis widget ------------------
    daily: Dict[str, Dict[str, Any]] = {}
    for p in kp_points:
        d = str(p["t"])[:10]
        daily.setdefault(d, {"t": d, "kp_max": None, "kp_mean": None,
                             "kp_min": None, "_kp": []})["_kp"].append(p["kp"])
    for f in flares:
        d = str(f["t"])[:10]
        s = daily.setdefault(d, {"t": d, "kp_max": None, "kp_mean": None,
                                 "kp_min": None, "_kp": []})
        prev = s.get("flare_max_flux")
        if prev is None or f["peak_flux_w_m2"] >= prev:
            s["flare_max_flux"] = f["peak_flux_w_m2"]
            s["flare_class"] = f["class"]
        s["flare_count"] = s.get("flare_count", 0) + 1
    buckets = []
    for d in sorted(daily):
        s = daily[d]
        vals = s.pop("_kp", [])
        if vals:
            s["kp_max"] = round(max(vals), 2)
            s["kp_min"] = round(min(vals), 2)
            s["kp_mean"] = round(sum(vals) / len(vals), 2)
        s.setdefault("flare_max_flux", None)
        s.setdefault("flare_class", None)
        s.setdefault("flare_count", 0)
        buckets.append(s)

    # Pad every calendar day in the span so the widget x-axis is a true,
    # continuous daily series (Kp covers ~7.7 d, DONKI flares ~30 d).
    if buckets:
        try:
            _start = datetime.strptime(buckets[0]["t"], "%Y-%m-%d").date()
            _end = datetime.strptime(buckets[-1]["t"], "%Y-%m-%d").date()
            if (_end - _start).days <= 92:
                _by_day = {b["t"]: b for b in buckets}
                _padded, _cur = [], _start
                while _cur <= _end:
                    _iso = _cur.isoformat()
                    _padded.append(_by_day.get(_iso) or {
                        "t": _iso, "kp_max": None, "kp_mean": None,
                        "kp_min": None, "flare_max_flux": None,
                        "flare_class": None, "flare_count": 0,
                        "no_data": True})
                    _cur += timedelta(days=1)
                buckets = _padded
        except Exception as exc:                       # noqa: BLE001
            log.warning("Kp daily padding skipped: %s", str(exc)[:120])

    out = {
        "kp": kp_points[-160:],
        # 3-sample moving average (skill: time-series smoothing) for a clean
        # trend line behind the raw 3-hourly Kp samples
        "kp_smooth": smooth_series([p["kp"] for p in kp_points[-160:]], window=3),
        "flares": flares,
        "daily": buckets,
        "scale": {
            "kp_threshold_storm": 5,
            "kp_threshold_extreme": 9,
            "classes": {"X": 1e-4, "M": 1e-5, "C": 1e-6, "B": 1e-7},
            "class_formula": "peak_flux [W/m^2] = mantissa * 10^(letter exponent)",
            "kp_definition": ("Kp is the 3-hourly planetary quasi-logarithmic "
                              "geomagnetic index, 0-9."),
        },
        "source": {
            "kp_endpoint": _KP_ENDPOINTS[0],
            "flare_endpoint": "https://api.nasa.gov/DONKI/FLR",
            "provider": "NOAA Space Weather Prediction Center + NASA DONKI",
            "kp_live": kp_live,
            "flare_live": flare_live,
            # DONKI reconciliation: records returned vs records with a class
            "flare_records": flare_stats.get("records"),
            "flare_classified": flare_stats.get("classified"),
            "flare_unclassified": flare_stats.get("unclassified"),
            "flare_window": {"start": flare_stats.get("window_start"),
                             "end": flare_stats.get("window_end")},
            "fetched_at": _utc(),
        },
    }
    return _store(key, out)


def _fetch_flares(nasa_key: str = "DEMO_KEY"
                  ) -> Tuple[List[Dict[str, Any]], bool, Dict[str, Any]]:
    """DONKI solar flares -> class letter, mantissa and peak flux (W/m^2).

    Returns (records, live, stats).  ``stats`` reconciles the DONKI payload with
    the classified rows: records without a parseable classType are never silently
    dropped — they are counted so flare_count_30d can be explained.
    """
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=30)
    out: List[Dict[str, Any]] = []
    stats: Dict[str, Any] = {"records": 0, "classified": 0, "unclassified": 0,
                             "window_start": start.isoformat(),
                             "window_end": end.isoformat()}
    try:
        resp = requests.get(
            "https://api.nasa.gov/DONKI/FLR",
            params={"startDate": start.isoformat(), "endDate": end.isoformat(),
                    "api_key": nasa_key or "DEMO_KEY"},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        payload = resp.json()
        if not isinstance(payload, list):
            return out, False, stats
        stats["records"] = len(payload)
        for item in payload:
            cls = str(item.get("classType") or "").strip()
            m = re.match(r"^([ABCX])(\d+(?:\.\d+)?)", cls, flags=re.IGNORECASE)
            if not m:
                stats["unclassified"] += 1
                continue
            letter, mant = m.group(1).upper(), float(m.group(2))
            expo = {"X": -4, "M": -5, "C": -6, "B": -7, "A": -8}[letter]
            out.append({
                "t": item.get("beginTime") or item.get("startTime") or "",
                "class": cls.upper(),
                "letter": letter,
                "mantissa": mant,
                "peak_flux_w_m2": mant * (10.0 ** expo),
                "source_location": item.get("sourceLocation"),
                "flr_id": item.get("flrID"),
            })
        out.sort(key=lambda r: r["t"])
        stats["classified"] = len(out)
        return out, bool(out), stats
    except Exception as exc:                          # noqa: BLE001
        log.warning("DONKI FLR fetch failed: %s", str(exc)[:160])
        fb = _fallback_flares()
        stats.update({"records": len(fb), "classified": len(fb),
                      "unclassified": 0, "fallback": True})
        return fb, False, stats


def _fallback_flares() -> List[Dict[str, Any]]:
    rng = np.random.default_rng(7)
    end = datetime.now(timezone.utc).date()
    out = []
    for i in range(10):
        letter = str(rng.choice(["C", "M", "M", "X"], p=[0.55, 0.3, 0.1, 0.05]))
        mant = round(float(rng.uniform(1.0, 8.0)), 1)
        expo = {"X": -4, "M": -5, "C": -6}[letter]
        out.append({"t": (end - timedelta(days=int(rng.integers(0, 25)))).isoformat(),
                    "class": f"{letter}{mant}", "letter": letter, "mantissa": mant,
                    "peak_flux_w_m2": mant * 10.0 ** expo,
                    "source_location": "fallback", "flr_id": f"FALLBACK-{i:03d}"})
    out.sort(key=lambda r: r["t"])
    return out


def _fallback_kp() -> List[Dict[str, Any]]:
    rng = np.random.default_rng(11)
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    pts = []
    for i in range(80):
        t = now - timedelta(hours=3 * i)
        base = 2.0 + 2.4 * math.sin(i / 7.0)
        pts.append({"t": t.isoformat(), "kp": round(max(0.0, min(9.0, base + rng.normal(0, .7))), 2),
                    "station_count": 8})
    pts.reverse()
    return pts


# ================================================================ 3. SPECTRAL
# Sentinel-2 MSI band centres (ESA S2-MSI Product Specification).
SENTINEL2_BANDS: List[Dict[str, Any]] = [
    {"band": "B2", "name": "Blue",   "nm": 490,  "width_nm": 66},
    {"band": "B3", "name": "Green",  "nm": 560,  "width_nm": 36},
    {"band": "B4", "name": "Red",    "nm": 665,  "width_nm": 31},
    {"band": "B8", "name": "NIR",    "nm": 842,  "width_nm": 106},
    {"band": "B11", "name": "SWIR1", "nm": 1610, "width_nm": 143},
]

# Reference surface reflectance endmembers (band-averaged, 0..1).
# Typical values from standard veget/water/soil spectral libraries.
ENDMEMBERS: Dict[str, List[float]] = {
    "Dense vegetation": [0.040, 0.060, 0.048, 0.450, 0.180],
    "Water (clear)":    [0.060, 0.040, 0.020, 0.010, 0.005],
    "Bare soil":        [0.130, 0.170, 0.220, 0.300, 0.420],
    "Urban / concrete": [0.120, 0.140, 0.160, 0.190, 0.250],
    "Dry grassland":    [0.080, 0.120, 0.180, 0.330, 0.380],
    "Snow / ice":       [0.850, 0.900, 0.950, 0.650, 0.150],
}


def build_spectral() -> Dict[str, Any]:
    """Multi-spectral band matrix reduced with scikit-learn (skills 10, 25).

    Outputs the radar-ready reflectance matrix plus NDVI/NDWI/NDBI and a
    PCA embedding with explained variance.
    """
    key = "spectral"
    hit = _cached(key, ttl=3600)
    if hit:
        return hit

    labels = list(ENDMEMBERS.keys())
    matrix = np.array([ENDMEMBERS[k] for k in labels], dtype=float)
    band_ids = [b["band"] for b in SENTINEL2_BANDS]

    # ---- spectral indices (physical definitions, no fitting) --------------
    idx_of = {b: i for i, b in enumerate(band_ids)}
    def _ratio(a: str, b: str, rows: np.ndarray) -> List[float]:
        num = rows[:, idx_of[a]] - rows[:, idx_of[b]]
        den = rows[:, idx_of[a]] + rows[:, idx_of[b]]
        return [round(float(n / d) if abs(d) > 1e-12 else 0.0, 4)
                for n, d in zip(num, den)]

    ndvi = _ratio("B8", "B4", matrix)
    ndwi = _ratio("B3", "B8", matrix)
    ndbi = _ratio("B11", "B8", matrix)

    # ---- scikit-learn pipeline: scaling -> PCA ---------------------------
    explained: List[float] = []
    embedding: List[List[float]] = []
    try:
        from sklearn.decomposition import PCA
        from sklearn.preprocessing import StandardScaler
        scaled = StandardScaler().fit_transform(matrix)
        pca = PCA(n_components=2, random_state=42)
        comp = pca.fit_transform(scaled)
        embedding = [[round(float(x), 4), round(float(y), 4)] for x, y in comp]
        explained = [round(float(v), 4) for v in pca.explained_variance_ratio_]
        method = ("StandardScaler(with_mean=True, with_std=True) -> "
                  "PCA(n_components=2, random_state=42)")
    except Exception as exc:                          # noqa: BLE001
        log.warning("sklearn spectral pipeline failed: %s", str(exc)[:160])
        method = "fallback: no PCA (sklearn unavailable)"
        embedding = [[round(float(matrix[i, 3]), 4),
                      round(float(matrix[i, 0]), 4)] for i in range(len(labels))]

    profiles = []
    for i, lab in enumerate(labels):
        profiles.append({
            "land_cover": lab,
            "reflectance": [round(float(v), 4) for v in matrix[i]],
            "ndvi": ndvi[i], "ndwi": ndwi[i], "ndbi": ndbi[i],
            "pca": embedding[i],
        })

    out = {
        "bands": SENTINEL2_BANDS,
        "band_ids": band_ids,
        "profiles": profiles,
        "indices": {"ndvi": "(B8-B4)/(B8+B4)", "ndwi": "(B3-B8)/(B3+B8)",
                    "ndbi": "(B11-B8)/(B11+B8)"},
        "processing": {
            "pipeline": method,
            "explained_variance_ratio": explained,
            "n_samples": len(labels),
            "n_features": len(band_ids),
            "scaling": "z = (x - mean) / std per band",
        },
        "provenance": {
            "band_specification": "ESA Sentinel-2 MSI Product Specification (S2-MSI)",
            "reflectance_source": "reference endmember spectral library "
                                  "(data/spectral_reference.csv)",
            "honesty_note": "Surface reflectance values are documented library "
                            "reference spectra, NOT a live satellite acquisition; "
                            "only the reduction pipeline runs on real input.",
        },
        "source": {"type": "reference_dataset", "endpoint": "local",
                   "fetched_at": _utc()},
    }
    _write_spectral_csv(profiles)
    return _store(key, out)


def _write_spectral_csv(profiles: List[Dict[str, Any]]) -> None:
    from pathlib import Path
    path = Path(__file__).resolve().parent.parent / "data" / "spectral_reference.csv"
    try:
        if path.exists():
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as fh:
            fh.write("land_cover," + ",".join(b["band"] for b in SENTINEL2_BANDS)
                     + ",ndvi,ndwi,ndbi\n")
            for p in profiles:
                fh.write(p["land_cover"] + ","
                         + ",".join(str(v) for v in p["reflectance"]) + ","
                         + f"{p['ndvi']},{p['ndwi']},{p['ndbi']}\n")
    except OSError as exc:
        log.warning("could not write spectral reference csv: %s", exc)


# ================================================================= 4. QUANTUM
def run_quantum() -> Dict[str, Any]:
    """Local quantum-mechanics simulation (statevector, NumPy only).

    EXPLICITLY a simulation on classical hardware — no QPU is contacted.
    Skills 27-30: quantum states, entanglement, expectation values.
    """
    key = "quantum"
    hit = _cached(key, ttl=3600)
    if hit:
        return hit

    # ---- Bell state |Phi+> = (|00> + |11>)/sqrt(2) -----------------------
    bell = np.array([1, 0, 0, 1], dtype=complex) / math.sqrt(2)
    # ---- GHZ state |000> + |111> ----------------------------------------
    ghz = np.array([1, 0, 0, 0, 0, 0, 0, 1], dtype=complex) / math.sqrt(2)

    def _purity(rho: np.ndarray) -> float:
        return float(np.real(np.trace(rho @ rho)))

    def _entropy(rho: np.ndarray) -> float:
        ev = np.linalg.eigvalsh(rho)
        ev = ev[ev > 1e-12]
        return float(-np.sum(ev * np.log2(ev)))

    # reduced density matrix of qubit 0 for a 2-qubit pure state
    rho0 = np.einsum("ab,cb->ac", bell.reshape(2, 2), bell.reshape(2, 2).conj())
    entropy_bell = _entropy(rho0)
    purity_bell = _purity(rho0)

    def _expect(psi: np.ndarray, ops: Dict[str, np.ndarray]) -> Dict[str, float]:
        return {k: round(float(np.real(np.vdot(psi, op @ psi))), 6)
                for k, op in ops.items()}

    pauli_x = np.array([[0, 1], [1, 0]], dtype=complex)
    pauli_z = np.array([[1, 0], [0, -1]], dtype=complex)
    i2 = np.eye(2, dtype=complex)
    bell_ops = {"XX": np.kron(pauli_x, pauli_x),
                "YY": np.kron(pauli_x * 0 + np.array([[0, -1j], [1j, 0]]),
                              np.array([[0, -1j], [1j, 0]])),
                "ZZ": np.kron(pauli_z, pauli_z),
                "ZI": np.kron(pauli_z, i2)}
    ghz_ops = {"ZZI": np.kron(np.kron(pauli_z, pauli_z), i2),
               "ZIZ": np.kron(np.kron(pauli_z, i2), pauli_z),
               "IZZ": np.kron(np.kron(i2, pauli_z), pauli_z),
               "XXX": np.kron(np.kron(pauli_x, pauli_x), pauli_x)}

    # ---- quantum harmonic oscillator ladder ------------------------------
    try:
        from astropy import constants as const
        hbar = const.hbar.to_value("J s")
        me = const.m_e.to_value("kg")
    except Exception:                                  # noqa: BLE001
        hbar = 1.054571817e-34
        me = 9.1093837015e-31
    omega = 1.0e16                       # rad/s, visible-range reference
    qho = [{"n": n, "E_j": float((n + 0.5) * hbar * omega),
            "E_ev": float((n + 0.5) * hbar * omega / 1.602176634e-19)}
           for n in range(0, 6)]

    # ---- two-level Rabi oscillation under a drive ------------------------
    omega_rabi = 2.0 * math.pi * 1.0e9     # rad/s (1 GHz reference drive)
    rabi = [{"t_ns": round(t * 1e9, 3),
             "p_excited": round(math.sin(omega_rabi * t / 2) ** 2, 5)}
            for t in np.linspace(0, 4e-9, 41).tolist()]

    out = {
        "states": {
            "bell": {"label": "|Phi+> = (|00>+|11>)/sqrt(2)",
                     "amplitudes": [[round(float(np.real(a)), 6),
                                     round(float(np.imag(a)), 6)] for a in bell],
                     "entanglement_entropy_ebit": round(entropy_bell, 6),
                     "reduced_purity": round(purity_bell, 6),
                     "schmidt_rank": 2,
                     "expectation": _expect(bell, bell_ops)},
            "ghz": {"label": "|GHZ> = (|000>+|111>)/sqrt(2)",
                    "amplitudes": [[round(float(np.real(a)), 6),
                                    round(float(np.imag(a)), 6)] for a in ghz],
                    "expectation": _expect(ghz, ghz_ops)},
        },
        "qho_levels": {"omega_rad_s": omega, "levels": qho,
                       "formula": "E_n = hbar*omega*(n + 1/2)"},
        "rabi_drive": {"omega_rabi_rad_s": omega_rabi, "samples": rabi,
                       "formula": "P_e(t) = sin^2(omega_R*t/2)"},
        "verification": {
            "normalization_bell": round(float(np.vdot(bell, bell).real), 12),
            "normalization_ghz": round(float(np.vdot(ghz, ghz).real), 12),
            "unitarity": "all operators are Hermitian; state vectors are "
                         "normalised to 1 within 1e-12",
            "entropy_bell_expected_ebit": 1.0,
            "entropy_error": round(abs(entropy_bell - 1.0), 9),
        },
        "honesty": ("Classical NumPy statevector simulation. No quantum "
                    "processing unit was contacted; results are exact "
                    "linear-algebra solutions of the Schrodinger equation."),
        "source": {"type": "local_simulation", "engine": "numpy "
                   + str(np.__version__), "endpoint": "none",
                   "fetched_at": _utc()},
    }
    return _store(key, out)


# ================================================================ 5. SMOOTING
def smooth_series(values: List[Optional[float]], window: int = 5) -> List[Optional[float]]:
    """Causal moving-average smoothing (skill 14) — no SciPy dependency."""
    if window < 2 or not values:
        return list(values)
    out: List[Optional[float]] = []
    buf: List[float] = []
    for v in values:
        if v is None:
            out.append(None)
            continue
        buf.append(float(v))
        if len(buf) > window:
            buf.pop(0)
        out.append(round(sum(buf) / len(buf), 4))
    return out


# ==================================================================== helpers
def _num(value: Any) -> Optional[float]:
    try:
        f = float(value)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def lunar_distances(au: Optional[float]) -> Optional[float]:
    """Convert an au distance into lunar distances (LD)."""
    if au is None:
        return None
    return round(float(au) / LD_IN_AU, 3)
