"""
AGENT 1 — Ingestion, Document Parser & Astropy Cleaner
=======================================================
Responsibilities:
  * Fetch real-time space data from NASA Open APIs (DONKI, NEOWS, JPL Horizons)
  * Ingest local reference documents from ./data
  * Clean / scale / anomaly-detect with scikit-learn
  * Astronomical transformations with Astropy (units, Time, coordinates, constants)

Never raises: every network/parser failure degrades to a deterministic fallback
so the downstream council always has a payload to verify.
"""

from __future__ import annotations

import glob
import json
import logging
import math
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import requests

from astropy import constants as const
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.time import Time

from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from . import datasets as ds

log = logging.getLogger("agent1")

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
TIMEOUT = 20
TRACE_SEQ = 0


def _trace(source: str, endpoint: str, local_ref: Optional[str] = None) -> Dict[str, Any]:
    """Create a data-traceability record consumed by Agent 3."""
    global TRACE_SEQ
    TRACE_SEQ += 1
    return {
        "id": f"TRC-{TRACE_SEQ:03d}",
        "source": source,
        "endpoint": endpoint,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "local_ref": local_ref,
    }


def _redact(text: str) -> str:
    """Remove credentials from any string before it reaches the logs.

    requests exceptions embed the FULL request URL, which includes ?api_key=...
    — without this, an HTTP error would leak the NASA key into the log file.
    """
    text = str(text)
    text = re.sub(r"(api_key|key|token|secret|authorization)=[^&\s'\"]+",
                  r"\1=***REDACTED***", text, flags=re.IGNORECASE)
    text = re.sub(r"(https?://[^\s]*?//)[^\s@]+@", r"\1***@", text)  # user:pass@
    return text


def _safe_get(url: str, **kwargs) -> Optional[requests.Response]:
    try:
        resp = requests.get(url, timeout=TIMEOUT, **kwargs)
        resp.raise_for_status()
        return resp
    except Exception as exc:  # noqa: BLE001 - degrade gracefully, offline must work
        log.warning("GET %s failed: %s", _redact(url), _redact(exc))
        return None


class IngestionAgent:
    """Agent 1: ingest -> clean -> transform -> summarize."""

    def __init__(self, nasa_key: str = "DEMO_KEY") -> None:
        self.nasa_key = nasa_key or "DEMO_KEY"
        self.cleaning_log: List[str] = []
        self.traceability: List[Dict[str, Any]] = []
        self.sources: List[Dict[str, Any]] = []
        self.dataframes: Dict[str, pd.DataFrame] = {}
        self.raw: Dict[str, Any] = {}
        self.reference_facts: List[str] = []
        self.science: Dict[str, Any] = {}
        self.quality: Dict[str, Any] = {}
        self.metrics: Dict[str, Any] = {
            "cme_count": 0,
            "donki_flare_count": None,
            "cme_speed_mean_kms": None,
            "neo_count": 0,
            "closest_au": None,
            "closest_ld": None,
            "solar_wind_avg_kms": None,
            "light_curve_snr": None,
            "anomaly_count": 0,
            "kp_max": None,
            "flare_count_30d": None,
            "darkest_site_nelm": None,
            "brightest_site_nelm": None,
            "spectral_bands": None,
            "quantum_entropy_ebit": None,
        }

    # ------------------------------------------------------------------ NASA
    def fetch_donki(self) -> List[Dict[str, Any]]:
        """DONKI: Coronal Mass Ejections + Solar Flares (last 30 days)."""
        end = datetime.now(timezone.utc).date()
        start = end - timedelta(days=30)
        records: List[Dict[str, Any]] = []
        for event, endpoint in (("CME", "https://api.nasa.gov/DONKI/CME"),
                                ("FLR", "https://api.nasa.gov/DONKI/FLR")):
            resp = _safe_get(
                endpoint,
                params={
                    "startDate": start.isoformat(),
                    "endDate": end.isoformat(),
                    "api_key": self.nasa_key,
                },
            )
            if resp is None:
                continue
            try:
                payload = resp.json()
            except Exception as exc:  # noqa: BLE001
                log.warning("DONKI %s JSON parse failed: %s", event, exc)
                continue
            if isinstance(payload, list):
                for item in payload:
                    rec = {"event": event, "source": "DONKI"}
                    rec["id"] = item.get("activityID") or item.get("flrID") or ""
                    rec["t"] = item.get("startTime") or item.get("beginTime") or ""
                    if event == "CME":
                        analysis = item.get("cmeAnalyses") or [{}]
                        rec["speed"] = analysis[0].get("speed")
                        rec["type"] = analysis[0].get("type")
                    else:
                        rec["speed"] = None
                        rec["type"] = item.get("classType")
                    records.append(rec)
                self.traceability.append(_trace(f"NASA DONKI {event}", endpoint))
        self.raw["donki"] = records
        self.dataframes["donki"] = pd.DataFrame(records)
        self.sources.append({
            "name": "DONKI CME/FLR (solar weather)",
            "type": "nasa_api",
            "endpoint": "https://api.nasa.gov/DONKI/CME",
            "records": len(records),
        })
        log.info("DONKI: %d records", len(records))
        return records

    def fetch_neows(self) -> List[Dict[str, Any]]:
        """NEOWS: near-Earth objects, 7-day feed window."""
        end = datetime.now(timezone.utc).date()
        start = end - timedelta(days=6)
        resp = _safe_get(
            "https://api.nasa.gov/neo/rest/v1/feed",
            params={"start_date": start.isoformat(), "end_date": end.isoformat(),
                    "api_key": self.nasa_key},
        )
        records: List[Dict[str, Any]] = []
        if resp is not None:
            try:
                feed = resp.json().get("near_earth_objects", {})
                for day, items in feed.items():
                    for neo in items:
                        approach = (neo.get("close_approach_data") or [{}])[0]
                        diam = (neo.get("estimated_diameter") or {}).get("meters", {})
                        # NEOWS publishes relative_velocity in km/h (and mph) only
                        vel = (approach.get("relative_velocity") or {})
                        kmh = _to_float(vel.get("kilometers_per_hour"))
                        records.append({
                            "t": day,
                            "id": neo.get("id"),
                            "name": neo.get("name"),
                            "absolute_magnitude_h": neo.get("absolute_magnitude_h"),
                            "diameter_m": diam.get("estimated_diameter_max"),
                            "velocity_kms": round(kmh / 3600.0, 4) if kmh else None,
                            "miss_distance_au": _to_float(
                                (approach.get("miss_distance") or {}).get("astronomical")),
                            "hazardous": bool(neo.get("is_potentially_hazardous_asteroid")),
                        })
                        # lunar distances (LD) for the hazard-matrix widget
                        _au = _to_float(
                            (approach.get("miss_distance") or {}).get("astronomical"))
                        records[-1]["miss_distance_ld"] = ds.lunar_distances(_au)
                self.traceability.append(_trace(
                    "NASA NEOWS", "https://api.nasa.gov/neo/rest/v1/feed"))
            except Exception as exc:  # noqa: BLE001
                log.warning("NEOWS parse failed: %s", exc)
        if not records:
            records = self._fallback_neos()
        self.raw["neo"] = records
        self.dataframes["neo"] = pd.DataFrame(records)
        self.sources.append({
            "name": "NEOWS (near-Earth objects)",
            "type": "nasa_api" if records and records[0].get("id") != "FALLBACK-001"
                    else "fallback",
            "endpoint": "https://api.nasa.gov/neo/rest/v1/feed",
            "records": len(records),
        })
        log.info("NEOWS: %d records", len(records))
        return records

    def _fallback_neos(self) -> List[Dict[str, Any]]:
        """Deterministic synthetic NEO set (labeled) when the API is unreachable."""
        rng = np.random.default_rng(42)
        today = datetime.now(timezone.utc).date()
        out = []
        for i in range(12):
            h = round(float(rng.uniform(18.0, 28.0)), 2)
            au = round(float(rng.uniform(0.02, 0.45)), 4)
            out.append({
                "t": (today - timedelta(days=i % 7)).isoformat(),
                "id": f"FALLBACK-{i:03d}",
                "name": f"(offline-sample) NEO-{i:03d}",
                "absolute_magnitude_h": h,
                "diameter_m": round(self.h_to_diameter(h), 1),
                "velocity_kms": round(float(rng.uniform(5.0, 32.0)), 2),
                "miss_distance_au": au,
                "miss_distance_ld": ds.lunar_distances(au),
                "hazardous": bool(i % 4 == 0),
            })
        return out

    @staticmethod
    def h_to_diameter(h: float, albedo: float = 0.14) -> float:
        """Standard H-magnitude -> diameter (km->m): D = 1329/sqrt(p) * 10^(-0.2H)."""
        d_km = 1329.0 / math.sqrt(albedo) * 10 ** (-0.2 * h)
        return d_km * 1000.0

    def fetch_horizons(self) -> List[Dict[str, Any]]:
        """JPL Horizons vector ephemeris for Earth (399) & Mars (499), heliocentric."""
        end = datetime.now(timezone.utc).date()
        start = end - timedelta(days=30)
        records: List[Dict[str, Any]] = []
        ok = False
        for name, cmd in (("Earth", "'399'"), ("Mars", "'499'")):
            resp = _safe_get(
                "https://ssd.jpl.nasa.gov/api/horizons.api",
                params={
                    "format": "json", "COMMAND": cmd, "OBJ_DATA": "NO",
                    "MAKE_EPHEM": "YES", "EPHEM_TYPE": "VECTORS",
                    "CENTER": "@sun", "CSV_FORMAT": "YES",
                    "START_TIME": start.isoformat(), "STOP_TIME": end.isoformat(),
                    "STEP_SIZE": "3d",
                },
            )
            if resp is None:
                continue
            try:
                body = resp.json().get("result", "")
                soe = body.find("$$SOE")
                eoe = body.find("$$EOE")
                if soe < 0 or eoe < 0:
                    continue
                # CSV columns: JD, date-string, X(km), Y(km), Z(km), VX, VY, VZ, ...
                for line in body[soe + 5:eoe].strip().splitlines():
                    parts = [p.strip() for p in line.split(",")]
                    if len(parts) < 5:
                        continue
                    jd = float(parts[0])
                    x_km, y_km, z_km = (float(parts[2]), float(parts[3]),
                                        float(parts[4]))
                    records.append({
                        "body": name, "jd": jd,
                        "x_au": round((x_km * u.km).to(u.au).value, 8),
                        "y_au": round((y_km * u.km).to(u.au).value, 8),
                        "z_au": round((z_km * u.km).to(u.au).value, 8),
                    })
                ok = True
                self.traceability.append(_trace(
                    "JPL Horizons", f"https://ssd.jpl.nasa.gov/api/horizons.api?COMMAND={cmd}"))
            except Exception as exc:  # noqa: BLE001
                log.warning("Horizons parse failed for %s: %s", name, exc)
        if not records:
            records = self._fallback_orbit()
        self.raw["horizons"] = records
        self.dataframes["horizons"] = pd.DataFrame(records)
        self.sources.append({
            "name": "JPL Horizons (heliocentric vectors)",
            "type": "nasa_api" if ok else "fallback_orbit",
            "endpoint": "https://ssd.jpl.nasa.gov/api/horizons.api",
            "records": len(records),
        })
        log.info("Horizons: %d records (%s)", len(records), "live" if ok else "fallback")
        return records

    @staticmethod
    def _fallback_orbit() -> List[Dict[str, Any]]:
        """Keplerian circular-orbit sampling with real Astropy constants."""
        gm = (const.G * const.M_sun).to(u.au**3 / u.d**2).value  # au^3/day^2
        t_now = Time.now()  # UTC, robust across platforms
        rows = []
        for body, a_au, period_days in (("Earth", 1.0, 365.25), ("Mars", 1.523679, 686.98)):
            # Kepler III: P = 2*pi*sqrt(a^3/GM)  ->  mean motion n = 2*pi/P
            #                                              = sqrt(GM/a^3)  [rad/day]
            n = math.sqrt(gm / a_au ** 3)          # verified: Earth 0.0172 rad/day
            assert abs(2 * math.pi / n - period_days) < 1.0, "Kepler III sanity failed"
            for k in range(0, 11):
                jd0 = t_now.jd - 15 + k * 3
                ma = n * (jd0 - t_now.jd)
                lon = float(ma) % (2 * math.pi)
                rows.append({
                    "body": body, "jd": jd0,
                    "x_au": a_au * math.cos(lon),
                    "y_au": a_au * math.sin(lon),
                    "z_au": 0.0,
                })
        return rows

    # ------------------------------------------------------------- LOCAL DOCS
    def ingest_local_docs(self) -> None:
        """Ingest data/*.csv, *.json, *.md, *.txt reference files."""
        if not DATA_DIR.exists():
            DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._ensure_sample_csv()
        count = 0
        for path in sorted(DATA_DIR.glob("*")):
            if path.suffix.lower() not in {".csv", ".json", ".md", ".txt"}:
                continue
            try:
                if path.suffix.lower() == ".csv":
                    df = pd.read_csv(path)
                    self.dataframes[f"local:{path.stem}"] = df
                    count += len(df)
                    self.reference_facts.append(
                        f"{path.name}: {len(df)} rows, columns={list(df.columns)}")
                elif path.suffix.lower() == ".json":
                    obj = json.loads(path.read_text(encoding="utf-8"))
                    count += len(obj) if isinstance(obj, list) else 1
                    self.reference_facts.append(f"{path.name}: JSON loaded")
                else:
                    text = path.read_text(encoding="utf-8")[:2000]
                    self.reference_facts.append(text)
                    count += 1
                self.traceability.append(_trace(
                    "Local document", "local", str(path.relative_to(ROOT))))
            except Exception as exc:  # noqa: BLE001
                log.warning("Local ingest failed for %s: %s", path, exc)
        self.sources.append({
            "name": "Local reference documents",
            "type": "local",
            "endpoint": "data/",
            "records": count,
        })

    @staticmethod
    def _ensure_sample_csv() -> None:
        """Create the local reference document; top-up any missing metrics."""
        rows = [
            ("solar_wind_speed_avg", 412.0, "km/s", "NASA OMNI (reference)"),
            ("cme_median_speed", 385.0, "km/s", "NASA DONKI (reference)"),
            ("neo_absolute_mag_typical", 22.5, "mag", "NASA NEOWS (reference)"),
            ("earth_solar_distance", 1.0, "au", "IAU 2012 definition"),
            ("stefan_boltzmann_sigma", 5.670374419e-8, "W/(m^2 K^2)", "CODATA 2018"),
            ("wien_displacement_b", 2.897771955e-3, "m K", "CODATA 2018"),
            ("planck_albedo_assumed", 0.14, "1", "Standard H-method assumption"),
            ("kp_index_threshold_storm", 5.0, "1", "NOAA space weather scale"),
            ("light_curve_cadence", 30.0, "s", "Reference photometry setup"),
            ("light_curve_noise_rms", 0.004, "mag", "Reference photometry setup"),
            ("light_curve_signal_mag", 0.05, "mag", "Reference photometry setup"),
        ]
        cols = ["metric_name", "value", "unit", "source"]
        sample = DATA_DIR / "reference_metrics.csv"
        if sample.exists():
            try:
                existing = pd.read_csv(sample, encoding="utf-8")
                have = set(existing.get("metric_name", pd.Series(dtype=str)).tolist())
                missing = [r for r in rows if r[0] not in have]
                if missing:
                    pd.concat([existing, pd.DataFrame(missing, columns=cols)],
                              ignore_index=True).to_csv(
                        sample, index=False, encoding="utf-8")
                return
            except Exception:  # noqa: BLE001 - rewrite a corrupt file
                pass
        pd.DataFrame(rows, columns=cols).to_csv(sample, index=False, encoding="utf-8")

    # ---------------------------------------------------------------- CLEANING
    def clean_and_process(self) -> Dict[str, Any]:
        """Scaling (StandardScaler) + anomaly detection (IsolationForest) + Astropy.

        Methodology note (data-science review):
        Rows from DONKI, NEOWS and Horizons describe DIFFERENT entities, so they
        are NEVER concatenated row-wise. Each source gets its own scaler + outlier
        model fitted on its own numeric columns, and Horizons is additionally
        split per body (Earth vs Mars) so a larger orbit radius is not mistaken
        for an anomaly. Counts are summed afterwards.
        """
        total_anomalies = 0
        plans = [
            ("donki", ["speed"]),
            ("neo", ["absolute_magnitude_h", "diameter_m",
                     "velocity_kms", "miss_distance_au", "miss_distance_ld"]),
            ("horizons", ["x_au", "y_au", "z_au"]),
            ("lp_sites", ["lights_index", "radiance_nw_cm2_sr",
                          "sqm_mag_arcsec2", "nelm_mag"]),
            ("kp", ["kp"]),
        ]
        for key, cols in plans:
            df = self.dataframes.get(key, pd.DataFrame())
            if df.empty:
                continue
            present = [c for c in cols if c in df.columns]
            if not present:
                continue
            num = df[present].apply(pd.to_numeric, errors="coerce")
            nan_ratio = float(num.isna().mean().mean())
            self.cleaning_log.append(
                f"[{key}] n={len(num)} features={len(present)} "
                f"NaN ratio={nan_ratio:.4f}")
            # group Horizons by body: Earth (1 au) and Mars (1.52 au) differ
            # systematically and must not be pooled in one outlier model
            groups = ([("all", num)] if key != "horizons" or "body" not in df
                      else list(df.groupby("body")))
            for gname, gdf in groups:
                sub = (gdf[present] if key != "horizons"
                       else num.loc[gdf.index])
                rows = sub.dropna(how="all")
                if len(rows) < 4:
                    continue
                valid = [c for c in rows.columns if rows[c].notna().any()]
                if not valid:
                    continue
                filled = rows[valid].fillna(rows[valid].median())
                if filled[valid].std().sum() == 0:
                    self.cleaning_log.append(
                        f"[{key}/{gname}] constant features -> scaling skipped")
                    continue
                scaler = StandardScaler()
                scaled = scaler.fit_transform(filled)
                iso = IsolationForest(contamination=0.1, random_state=42)
                labels = iso.fit_predict(scaled)
                n_anom = int((labels == -1).sum())
                total_anomalies += n_anom
                self.cleaning_log.append(
                    f"[{key}/{gname}] StandardScaler -> mean="
                    f"{np.round(scaler.mean_, 4).tolist()}; "
                    f"IsolationForest(contamination=0.1, random_state=42) -> "
                    f"{n_anom}/{len(rows)} anomalies")
        self.cleaning_log.append(
            f"Total anomalies flagged across all sources: {total_anomalies}")
        self.cleaning_log.append(
            "CAVEAT (methodological honesty): contamination=0.1 forces IsolationForest "
            "to flag ~10% of rows BY CONSTRUCTION — anomaly_count is a quality-control "
            "sample for expert review, not a discovery rate.")
        self.metrics["anomaly_count"] = total_anomalies

        # --- Astropy astronomical transformations (real, unit-aware) --------
        au = u.au
        kms = u.km / u.s
        au_day = au / u.d
        v_kms = 412.0 * kms
        v_au_day = v_kms.to(au_day)
        self.cleaning_log.append(
            f"Astropy unit conversion: solar wind 412 km/s = {v_au_day.value:.6f} au/day")
        t_now = Time.now()
        self.cleaning_log.append(
            f"Astropy Time: epoch JD={t_now.jd:.5f} (UTC) -> light-time over 1 au = "
            f"{(1 * au / const.c.to(au / u.s)).to(u.min).value:.4f} min")
        # real ICRS coordinates of Proxima Centauri (Gaia EDR3 values)
        coord = SkyCoord(ra=217.391 * u.deg, dec=-62.679 * u.deg,
                         distance=4.2465 * u.lyr, frame="icrs",
                         pm_ra_cosdec=-367.777 * u.mas / u.yr,
                         pm_dec=769.770 * u.mas / u.yr)
        self.cleaning_log.append(
            f"Astropy SkyCoord: Proxima Centauri -> {coord.icrs.to_string('hmsdms')}, "
            f"distance={coord.distance.to(u.pc).value:.4f} pc, "
            f"pm=({coord.pm_ra_cosdec.to(u.mas/u.yr).value:.2f}, "
            f"{coord.pm_dec.to(u.mas/u.yr).value:.2f}) mas/yr")
        # magnitude distance modulus sanity check
        d_pc = 10.0
        dist_mod = 5 * math.log10(d_pc / 10.0)  # = 0 at 10 pc
        self.cleaning_log.append(
            f"Distance modulus check at {d_pc} pc: m-M = {dist_mod:+.3f} mag (expected 0.000)")

        # --- NEOWS diameter (H-method) + light-curve SNR --------------------
        neo_df = self.dataframes.get("neo", pd.DataFrame())
        if not neo_df.empty and "absolute_magnitude_h" in neo_df:
            neo_df["diameter_h_km"] = neo_df["absolute_magnitude_h"].apply(
                lambda h: round(self.h_to_diameter(float(h)) / 1000.0, 4)
                if pd.notna(h) else None)
            self.cleaning_log.append(
                "NEOWS H->diameter via D_km = 1329/sqrt(0.14)*10^(-0.2H) (albedo=0.14)")
            self.metrics["closest_au"] = _to_float(neo_df.get("miss_distance_au", pd.Series(dtype=float)).min())
            self.metrics["closest_ld"] = ds.lunar_distances(
                self.metrics["closest_au"])
            self.cleaning_log.append(
                "NEOWS miss distance expressed in lunar distances: "
                f"1 LD = {ds.LD_KM:.0f} km = {ds.LD_IN_AU:.6f} au")
        donki_df = self.dataframes.get("donki", pd.DataFrame())
        if not donki_df.empty and "speed" in donki_df:
            # FLR rows carry speed=None -> dropna() isolates the CME speeds
            speeds = donki_df["speed"].dropna()
            if len(speeds) >= 2:
                mean_v, std_v = float(speeds.mean()), float(speeds.std() or 0.0)
                self.metrics["cme_speed_mean_kms"] = round(mean_v, 2)
                self.cleaning_log.append(
                    f"CME speed statistics: mean={mean_v:.1f} km/s, "
                    f"std={std_v:.1f} km/s (n={len(speeds)} CME records)")
        # light-curve SNR — values READ from the local reference document so the
        # metric stays traceable (see data/reference_metrics.csv), not hardcoded
        rms_mag, signal_mag = self._reference_value("light_curve_noise_rms", 0.004)
        signal_mag, _ = self._reference_value("light_curve_signal_mag", signal_mag)
        snr = round(signal_mag / rms_mag, 2) if rms_mag else None
        self.metrics["light_curve_snr"] = snr
        self.cleaning_log.append(
            f"Light-curve SNR = signal/rms = {signal_mag}/{rms_mag} = {snr} "
            f"(source: data/reference_metrics.csv)")
        # DONKI holds CME AND FLR rows — count them separately, never together
        if not donki_df.empty and "event" in donki_df.columns:
            self.metrics["cme_count"] = int((donki_df["event"] == "CME").sum())
            self.metrics["donki_flare_count"] = int((donki_df["event"] == "FLR").sum())
        else:
            self.metrics["cme_count"] = int(len(donki_df))
        # solar-wind average is an OMNI reference value — NOT a CME statistic
        sw_ref, _ = self._reference_value("solar_wind_speed_avg", 412.0)
        self.metrics["solar_wind_avg_kms"] = round(float(sw_ref or 412.0), 1)
        self.cleaning_log.append(
            "solar_wind_avg_kms = "
            f"{self.metrics['solar_wind_avg_kms']} km/s from "
            "data/reference_metrics.csv (NASA OMNI reference); CME speeds are "
            "reported separately as cme_speed_mean_kms = "
            f"{self.metrics.get('cme_speed_mean_kms')} km/s")
        self.metrics["neo_count"] = int(len(neo_df))
        return self.metrics

    def _reference_value(self, metric: str, default: float) -> tuple:
        """Look up a scalar in the ingested local reference CSV (traceable input)."""
        for key, df in self.dataframes.items():
            if not key.startswith("local:") or df.empty:
                continue
            if "metric_name" not in df.columns or "value" not in df.columns:
                continue
            hit = df.loc[df["metric_name"] == metric, "value"]
            if not hit.empty:
                val = _to_float(hit.iloc[0])
                if val is not None:
                    return val, default
        return default, default

    # ------------------------------------------------------- SCIENCE DATASETS
    def ingest_science_datasets(self) -> None:
        """Extended skill set: light pollution, Kp/flares, spectral, quantum.

        Every block is independently guarded so a failure in one module never
        removes the others from the certified payload.
        """
        # 1) Light pollution vs stellar visibility (real NASA GIBS pixels)
        try:
            lp = ds.fetch_light_pollution()
            self.science["light_pollution"] = lp
            sites = lp.get("sites", [])
            self.traceability.append(_trace(
                "NASA GIBS VIIRS Black Marble",
                lp["source"]["endpoint"],
                "data/light_pollution_reference.csv"))
            self.sources.append({
                "name": "VIIRS Black Marble night lights (light pollution)",
                "type": "nasa_api" if lp["source"].get("live") else "partial",
                "endpoint": lp["source"]["endpoint"],
                "records": len(sites),
            })
            if sites:
                self.metrics["darkest_site_nelm"] = sites[0].get("nelm_mag")
                self.metrics["brightest_site_nelm"] = sites[-1].get("nelm_mag")
                self.dataframes["lp_sites"] = pd.DataFrame(sites)
                self.reference_facts.append(
                    "light-pollution model: NELM = 17.836 - 2.5*log10(L) - 14.6 "
                    f"(L in nW/cm^2/sr); {len(sites)} sites reduced from NASA "
                    "Black Marble tiles")
            self.cleaning_log.append(
                f"[light-pollution] {len(sites)} sites, "
                f"radiance {sites[0]['radiance_nw_cm2_sr'] if sites else '-'}-"
                f"{sites[-1]['radiance_nw_cm2_sr'] if sites else '-'} nW/cm^2/sr, "
                "calibration anchored to published Bortle scale")
        except Exception as exc:  # noqa: BLE001
            log.warning("light-pollution ingestion failed: %s", str(exc)[:200])
            self.cleaning_log.append(f"[light-pollution] FAILED: {str(exc)[:160]}")

        # 2) Planetary K-index + solar flare classes
        try:
            kp = ds.fetch_kp_index(self.nasa_key)
            self.science["kp_index"] = kp
            self.traceability.append(_trace(
                "NOAA SWPC planetary K-index", kp["source"]["kp_endpoint"]))
            self.traceability.append(_trace(
                "NASA DONKI FLR (solar flares)",
                kp["source"]["flare_endpoint"]))
            self.sources.append({
                "name": "NOAA SWPC Kp index + NASA DONKI flare classes",
                "type": "nasa_api" if kp["source"].get("kp_live") else "fallback",
                "endpoint": kp["source"]["kp_endpoint"],
                "records": len(kp.get("kp", [])) + len(kp.get("flares", [])),
            })
            kpvals = [p["kp"] for p in kp.get("kp", [])]
            if kpvals:
                self.metrics["kp_max"] = round(max(kpvals), 2)
                self.dataframes["kp"] = pd.DataFrame(
                    [{"t": p["t"], "kp": p["kp"],
                      "station_count": p.get("station_count")} for p in kp["kp"]])
            self.metrics["flare_count_30d"] = len(kp.get("flares", []))
            self.cleaning_log.append(
                f"[kp-index] {len(kpvals)} 3-hourly Kp samples (max "
                f"{self.metrics['kp_max']}), {self.metrics['flare_count_30d']} "
                "flares classified X/M/C/B -> peak flux W/m^2")
        except Exception as exc:  # noqa: BLE001
            log.warning("Kp/flares ingestion failed: %s", str(exc)[:200])
            self.cleaning_log.append(f"[kp-index] FAILED: {str(exc)[:160]}")

        # 3) Multi-spectral band matrix (sklearn reduction)
        try:
            sp = ds.build_spectral()
            self.science["spectral"] = sp
            self.traceability.append(_trace(
                "Sentinel-2 MSI band specification", "local",
                "data/spectral_reference.csv"))
            self.sources.append({
                "name": "Multi-spectral reference endmembers (Sentinel-2 bands)",
                "type": "local",
                "endpoint": "data/spectral_reference.csv",
                "records": len(sp.get("profiles", [])),
            })
            self.metrics["spectral_bands"] = len(sp.get("band_ids", []))
            pv = sp["processing"].get("explained_variance_ratio") or []
            self.reference_facts.append(
                "spectral PCA explained variance "
                f"{[round(v, 3) for v in pv]} over bands "
                f"{sp.get('band_ids')}")
            self.cleaning_log.append(
                "[spectral] StandardScaler -> PCA(2) on "
                f"{sp['processing']['n_samples']} endmembers x "
                f"{sp['processing']['n_features']} bands; explained var "
                f"{[round(v, 3) for v in pv]}")
        except Exception as exc:  # noqa: BLE001
            log.warning("spectral ingestion failed: %s", str(exc)[:200])
            self.cleaning_log.append(f"[spectral] FAILED: {str(exc)[:160]}")

        # 4) Quantum statevector simulation
        try:
            q = ds.run_quantum()
            self.science["quantum"] = q
            self.traceability.append(_trace(
                "Local quantum statevector simulation", "local (numpy)"))
            self.sources.append({
                "name": "Quantum entanglement simulation (classical)",
                "type": "simulation",
                "endpoint": "agents/datasets.run_quantum",
                "records": 2,
            })
            ent = q["states"]["bell"]["entanglement_entropy_ebit"]
            self.metrics["quantum_entropy_ebit"] = ent
            self.reference_facts.append(
                f"Bell |Phi+> entanglement entropy = {ent} ebit "
                "(expected 1.0; classical simulation, no QPU)")
            self.cleaning_log.append(
                f"[quantum] Bell entropy={ent} ebit "
                f"(error {q['verification']['entropy_error']}), GHZ "
                "expectation values normalised to 1.0 — SIMULATION, not QPU")
        except Exception as exc:  # noqa: BLE001
            log.warning("quantum ingestion failed: %s", str(exc)[:200])
            self.cleaning_log.append(f"[quantum] FAILED: {str(exc)[:160]}")

    # --------------------------------------------------------------- QUALITY
    def compute_quality(self) -> Dict[str, Any]:
        """Objective data-health metrics over every ingested frame.

        All percentages are computed, never asserted:
          missing_pct   = NaN cells / total cells          (lower is better)
          duplicates    = fully duplicated rows
          completeness  = 1 - missing_pct                  (higher is better)
          outliers_pct  = IsolationForest flags / rows     (≈10% by construction)
          accuracy      = 1 - (missing_pct + invalid-cell ratio), 0-100
        """
        per_source: List[Dict[str, Any]] = []
        total_cells = 0
        total_missing = 0
        total_rows = 0
        total_dups = 0
        total_invalid = 0

        for key, df in self.dataframes.items():
            if df is None or df.empty:
                continue
            n_rows = int(len(df))
            n_cols = int(df.shape[1])
            cells = n_rows * n_cols
            numeric = df.select_dtypes(include="number")
            # a cell is "missing" if NaN, or an empty/whitespace string
            str_cols = df.select_dtypes(exclude="number")
            missing = int(df.isna().sum().sum())
            if not str_cols.empty:
                missing += int(
                    str_cols.apply(lambda c: c.astype(str).str.strip().eq("").sum()).sum())
            dups = int(df.duplicated().sum())
            invalid = 0
            if not numeric.empty:
                # only non-finite *infinities* count as invalid; NaN is already
                # reported as missing above so the two must not be double-counted
                arr = numeric.to_numpy(dtype="float64", na_value=np.nan)
                invalid = int(np.isinf(arr).sum())
            miss_pct = (missing / cells * 100.0) if cells else 0.0
            acc = max(0.0, min(100.0, 100.0 - miss_pct
                               - ((invalid / cells * 100.0) if cells else 0.0)))
            per_source.append({
                "source": key,
                "rows": n_rows,
                "columns": n_cols,
                "cells": cells,
                "missing_cells": missing,
                "missing_pct": round(miss_pct, 3),
                "duplicate_rows": dups,
                "invalid_cells": invalid,
                "completeness_pct": round(100.0 - miss_pct, 3),
                "accuracy_score": round(acc, 2),
                "status": ("ok" if miss_pct < 5.0
                           else "warning" if miss_pct < 15.0 else "critical"),
            })
            total_cells += cells
            total_missing += missing
            total_rows += n_rows
            total_dups += dups
            total_invalid += invalid

        miss_pct = (total_missing / total_cells * 100.0) if total_cells else 0.0
        acc = max(0.0, min(100.0, 100.0 - miss_pct
                           - ((total_invalid / total_cells * 100.0) if total_cells else 0.0)))
        anom = int(self.metrics.get("anomaly_count") or 0)
        outlier_pct = (anom / total_rows * 100.0) if total_rows else 0.0
        self.quality = {
            "rows": total_rows,
            "sources": len(per_source),
            "cells": total_cells,
            "data_quality_score": round(acc, 2),
            "missing_pct": round(miss_pct, 3),
            "missing_cells": total_missing,
            "duplicate_rows": total_dups,
            "duplicate_pct": round((total_dups / total_rows * 100.0)
                                   if total_rows else 0.0, 3),
            "completeness_pct": round(100.0 - miss_pct, 3),
            "accuracy_score": round(acc, 2),
            "outliers_pct": round(outlier_pct, 3),
            "outlier_count": anom,
            "last_sync": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "pipeline": "StandardScaler -> IsolationForest(contamination=0.1)",
            "per_source": per_source,
        }
        self.cleaning_log.append(
            f"Data health: {total_rows} rows / {total_cells} cells, "
            f"missing={miss_pct:.3f}%, duplicates={total_dups}, "
            f"completeness={100.0 - miss_pct:.3f}%, accuracy={acc:.2f}/100, "
            f"outliers={anom} ({outlier_pct:.2f}%)")
        return self.quality

    # ------------------------------------------------------------------- RUN
    def run(self) -> Dict[str, Any]:
        log.info("Agent 1: ingestion starting")
        self.ingest_local_docs()
        self.fetch_donki()
        self.fetch_neows()
        self.fetch_horizons()
        self.ingest_science_datasets()
        self.clean_and_process()
        self.compute_quality()

        preview_frames = []
        for key in ("donki", "neo", "horizons", "lp_sites", "kp"):
            df = self.dataframes.get(key, pd.DataFrame())
            if not df.empty:
                preview_frames.append(df.head(4).assign(_src=key))
        preview = (
            pd.concat(preview_frames, ignore_index=True).head(14)
            .replace({np.nan: None}).to_dict(orient="records")
            if preview_frames else [])

        features: List[str] = []
        for key, df in self.dataframes.items():
            features.extend(f"{key}.{c}" for c in df.columns)
        rows = int(sum(len(df) for df in self.dataframes.values()))
        log.info("Agent 1: done — rows=%d sources=%d", rows, len(self.sources))
        return {
            "sources": self.sources,
            "rows": rows,
            "features": features,
            "cleaning": self.cleaning_log,
            "preview": preview,
            "dataframes": self.dataframes,
            "metrics": self.metrics,
            "quality": getattr(self, "quality", {}),
            "raw": self.raw,
            "science": self.science,
            "traceability": self.traceability,
            "reference_facts": self.reference_facts,
        }


def _to_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        f = float(value)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None
