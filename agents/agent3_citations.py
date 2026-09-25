"""
AGENT 3 — Proofs, Equations & Research-Paper Citations Engine
=============================================================
Enriches the certified report (Gemini 1.5 Flash) with:
  1. Applied physics / astrodynamics formulas actually used by the pipeline
  2. Data traceability IDs (NASA endpoint, satellite timestamp, local docs)
  3. Official peer-reviewed / agency citations & links (never fabricated)

The formula baseline is deterministic; Gemini (when available) annotates it.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List

log = logging.getLogger("agent3")

# Deterministic baseline — real, verifiable formulas used by Agent 1.
BASELINE_FORMULAS: List[Dict[str, str]] = [
    {
        "name": "Kepler's Third Law (harmonic form)",
        "equation": "T^2 = a^3 / (G*M_sun)",
        "application": "Fallback heliocentric orbit sampling for Earth/Mars "
                       "(Astropy constants G, M_sun; au^3/day^2 units).",
        "source": "Kepler, J. (1619), Harmonices Mundi; NASA SPICE/Kepler docs",
    },
    {
        "name": "Stefan-Boltzmann Law",
        "equation": "L = 4*pi*R^2*sigma*T^4   (sigma = 5.670374419e-8 W m^-2 K^-4)",
        "application": "Radiant power of solar/stellar bodies in the physics checks.",
        "source": "Boltzmann, Sitzungsber. Akad. Wiss. Wien 79 (1879); CODATA 2018",
    },
    {
        "name": "Wien Displacement Law",
        "equation": "lambda_max = b / T   (b = 2.897771955e-3 m K)",
        "application": "Peak-wavelength / colour-temperature reasoning in spectra checks.",
        "source": "Wien, W. (1893); CODATA 2018",
    },
    {
        "name": "Distance Modulus",
        "equation": "m - M = 5*log10(d/10 pc)",
        "application": "Magnitude/distance consistency audit (0.000 mag at 10 pc).",
        "source": "IAU standards; Carroll & Ostlie, An Introduction to Modern Astrophysics",
    },
    {
        "name": "NEOWS H-magnitude diameter estimate",
        "equation": "D_km = (1329 / sqrt(p)) * 10^(-0.2*H),  p = 0.14 (assumed)",
        "application": "Convert absolute magnitude H to estimated diameter (metres).",
        "source": "Harris, Icarus 126 (1997) 145-186; NASA JPL CNEOS",
    },
    {
        "name": "Light-curve Signal-to-Noise Ratio",
        "equation": "SNR = signal_mag / rms_mag",
        "application": "Photometric quality metric from the reference observation setup.",
        "source": "Howell, S. N., Handbook of CCD Astronomy (2000)",
    },
    {
        "name": "Cosmic light-time delay",
        "equation": "t = d / c   (1 au / c = 499.005 s = 8.317 min)",
        "application": "Ephemeris timestamp correction between observation and event.",
        "source": "IAU 2012 Resolution B3; NASA JPL Horizons documentation",
    },
    # ---------------- light pollution / stellar visibility -------------------
    {
        "name": "Sky surface brightness from V-band radiance",
        "equation": ("mu [mag/arcsec^2] = 17.836 - 2.5*log10(L), "
                     "L in nW/cm^2/sr"),
        "application": "Converts VIIRS Black Marble sky radiance into an SQM-"
                       "style surface brightness. 17.836 = 2.5*log10(1.3628e7); "
                       "1.3628e7 comes from f_nu(AB=0)=3.631e-23 W/m^2/Hz, "
                       "1 arcsec^2 = 2.3504e-11 sr and dnu_V = 8.821e13 Hz "
                       "(550 nm centre, 89 nm bandpass).",
        "source": "Derived from the AB magnitude system; Bortle, J. "
                  "\"The New Visible-Limit Magnitude Scale\", Sky & Telescope "
                  "101 (2001) Feb issue",
    },
    {
        "name": "Naked-eye limiting magnitude (NELM)",
        "equation": "NELM [mag] = mu [mag/arcsec^2] - 14.6",
        "application": "Turns sky surface brightness into the faintest star "
                       "visible to an unaided eye; Bortle class is then read "
                       "from the NELM breakpoints "
                       "[7.6, 7.3, 7.0, 6.6, 6.1, 5.5, 4.9, 4.2].",
        "source": "Empirical sky-quality relation; Bortle, Sky & Telescope "
                  "101 (2001); Falchi et al., Science Advances 2 (2016) e1600155",
    },
    {
        "name": "Night-light index to radiance calibration",
        "equation": ("L = L_min * (L_max/L_min) ** (index ** 1.30), "
                     "L_min = 0.0186, L_max = 1.881 nW/cm^2/sr"),
        "application": "DECLARED calibration of the rendered NASA GIBS "
                       "VIIRS Black Marble tile statistics (index = 0.70*"
                       "tile_p95/255 + 0.30*tile_mean/255) onto absolute "
                       "V-band radiance. Anchored at both ends to the published "
                       "Bortle 1 (NELM 7.60) and Bortle 9 (NELM 3.40) values.",
        "source": "data/light_pollution_reference.csv; NASA EOSDIS GIBS "
                  "VIIRS Black Marble (WMS GetMap)",
    },
    {
        "name": "GOES solar-flare class to peak flux",
        "equation": ("peak_flux [W/m^2] = mantissa * 10^(X:-4, M:-5, C:-6, "
                     "B:-7)"),
        "application": "Orders DONKI FLR classType strings (e.g. M1.2) on a "
                       "continuous logarithmic axis for the dual-axis widget.",
        "source": "NOAA GOES X-ray flare classification; NASA DONKI FLR API",
    },
    {
        "name": "Planetary K-index (Kp)",
        "equation": ("Kp in [0,9], 3-hourly, quasi-logarithmic; "
                     "geomagnetic storm >= Kp 5, extreme >= Kp 9"),
        "application": "NOAA SWPC planetary index plotted against flare class "
                       "on a secondary axis; also drives the storm threshold "
                       "in data/reference_metrics.csv.",
        "source": "NOAA Space Weather Prediction Center, "
                  "https://www.swpc.noaa.gov/products/noaa-planetary-k-index",
    },
    {
        "name": "Lunar distance conversion",
        "equation": "1 LD = 384400 km = 0.0025696 au;  d[LD] = d[au] / 0.0025696",
        "application": "Expresses NEOWS miss distances in lunar distances for "
                       "the hazard bubble matrix (IAU-defined mean radius).",
        "source": "IAU 2012 Resolution B3 (au definition); NASA CNEOS",
    },
    {
        "name": "Spectral vegetation / water / built indices",
        "equation": ("NDVI = (B8-B4)/(B8+B4);  NDWI = (B3-B8)/(B3+B8);  "
                     "NDBI = (B11-B8)/(B11+B8)"),
        "application": "Derived from Sentinel-2 MSI band centres "
                       "B2=490, B3=560, B4=665, B8=842, B11=1610 nm for the "
                       "multi-spectral radar widget; NDVI in [-1, 1].",
        "source": "Rouse et al. (1973); McFeeters (1996); ESA Sentinel-2 "
                  "MSI Product Specification",
    },
    # ------------------------ quantum mechanics ------------------------------
    {
        "name": "Quantum expectation value",
        "equation": "<O> = <psi|O|psi> = sum_i c_i^* (O c)_i",
        "application": "Pauli expectation values for the Bell/GHZ states "
                       "(XX=+1, ZZ=+1, XXX=+1) used as the quantum check.",
        "source": "Nielsen & Chuang, Quantum Computation and Quantum "
                  "Information, Cambridge University Press (2000)",
    },
    {
        "name": "von Neumann / entanglement entropy",
        "equation": ("S(rho) = -tr(rho * log2(rho)) = "
                     "-sum lambda_i log2 lambda_i   [ebit]"),
        "application": "Reduced density matrix of qubit 0 of |Phi+> must "
                       "give S = 1.000 ebit (maximally entangled pair).",
        "source": "von Neumann, Z. Phys. 57 (1929) 447-466; "
                  "Nielsen & Chuang (2000)",
    },
    {
        "name": "Quantum harmonic oscillator ladder",
        "equation": "E_n = hbar*omega*(n + 1/2),  n = 0, 1, 2, ...",
        "application": "Reference energy-level ladder reported alongside the "
                       "statevector results (astropy.constants hbar, m_e).",
        "source": "Landau & Lifshitz, Quantum Mechanics (non-relativistic "
                  "theory), Pergamon",
    },
    {
        "name": "Rabi oscillation population",
        "equation": "P_excited(t) = sin^2(omega_R * t / 2)",
        "application": "Two-level drive response sampled at 0-4 ns for the "
                       "quantum verification block.",
        "source": "Rabi, I. I., Phys. Rev. 51 (1937) 652-654",
    },
]

BASELINE_REFERENCES: List[Dict[str, Any]] = [
    {"title": "NASA DONKI API — Space Weather Database Of Notifications, "
              "Knowledge, Information",
     "url": "https://api.nasa.gov", "doi": None, "publisher": "NASA"},
    {"title": "NASA NeoWs — Near Earth Object Web Service API",
     "url": "https://api.nasa.gov", "doi": None, "publisher": "NASA CNEOS/JPL"},
    {"title": "JPL Horizons System Ephemeris API",
     "url": "https://ssd.jpl.nasa.gov/api/horizons.api", "doi": None,
     "publisher": "NASA/JPL Solar System Dynamics"},
    {"title": "Astropy: A Community-Developed Core Python Package for Astronomy",
     "url": "https://www.astropy.org", "doi": "10.3847/1538-4357/abb348",
     "publisher": "The Astrophysical Journal"},
    {"title": "Scikit-learn: Machine Learning in Python",
     "url": "https://scikit-learn.org", "doi": "10.5555/1953048.2078195",
     "publisher": "JMLR 12"},
    {"title": "NASA Space Weather Program — Geomagnetic Storm Scales (Kp/Dst)",
     "url": "https://www.swpc.noaa.gov", "doi": None, "publisher": "NOAA SWPC / NASA"},
    {"title": "NASA EOSDIS Global Imagery Browse Services (GIBS) — WMS with the "
              "VIIRS Black Marble nighttime-lights layer",
     "url": "https://nasa-gibs.github.io/nasa-gibs-api-docs/",
     "doi": None, "publisher": "NASA EOSDIS GIBS"},
    {"title": "NOAA SWPC Planetary K-index product (3-hourly Kp, 0-9 scale)",
     "url": "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json",
     "doi": None, "publisher": "NOAA Space Weather Prediction Center"},
    {"title": "The New World Atlas of Artificial Night Sky Brightness",
     "url": "https://www.science.org/doi/10.1126/sciadv.1600155",
     "doi": "10.1126/sciadv.1600155",
     "publisher": "Falchi, F. et al., Science Advances 2 (2016)"},
    {"title": "Sentinel-2 MSI Product Specification (band centres B2-B11)",
     "url": "https://sentinels.copernicus.eu/documents/247904/685211/"
            "Sentinel-2_MSIL1C_Product_Specification",
     "doi": None, "publisher": "European Space Agency (ESA)"},
    {"title": "Quantum Computation and Quantum Information (entanglement entropy)",
     "url": "https://doi.org/10.1017/CBO9781139022684",
     "doi": "10.1017/CBO9781139022684",
     "publisher": "Nielsen, M. A. & Chuang, I. L., Cambridge Univ. Press"},
]


class CitationAgent:
    """Agent 3: formulas + traceability + references (Gemini 1.5 Flash)."""

    def __init__(self, api_key: str | None, model: str = "gemini-3.6-flash",
                 fallback_model: str = "gemini-flash-latest") -> None:
        self.api_key = api_key
        self.model = model
        self.fallback_model = fallback_model

    # ------------------------------------------------------------------ run
    def enrich(self, council: Dict[str, Any], ingestion: Dict[str, Any]) -> Dict[str, Any]:
        traceability = [dict(t) for t in ingestion.get("traceability", [])]
        formulas = [dict(f) for f in BASELINE_FORMULAS]
        references = [dict(r) for r in BASELINE_REFERENCES]
        engine = "deterministic_baseline"

        if self.api_key:
            import time

            chain = [self.model] + ([self.fallback_model]
                                    if self.fallback_model and
                                    self.fallback_model != self.model else [])
            for model_name in chain:
                for attempt in range(2):
                    try:
                        flash = self._call_flash(council, ingestion, model_name)
                        engine = f"gemini:{model_name}"
                        # merge conservatively — model may ADD entries only
                        seen_f = {f["name"] for f in formulas}
                        for f in flash.get("formulas", []):
                            if isinstance(f, dict) and f.get("name") and f["name"] not in seen_f:
                                formulas.append(f)
                                seen_f.add(f["name"])
                        seen_r = {r["url"] for r in references}
                        for r in flash.get("references", []):
                            url = str((r or {}).get("url", ""))
                            if url.startswith("http") and url not in seen_r:
                                references.append(r)
                                seen_r.add(url)
                        break
                    except Exception as exc:  # noqa: BLE001
                        msg = str(exc)
                        is_quota = "429" in msg or "quota" in msg.lower()
                        if is_quota and attempt == 0:
                            # clamped wait (never longer than 15 s)
                            m = re.search(r"seconds:\s*(\d+)", msg)
                            delay = max(min(int(m.group(1)), 15), 3) if m else 8
                            log.warning("Citation quota hit, backing off %ss (%s)",
                                        delay, model_name)
                            time.sleep(delay)
                            continue
                        log.warning("Citation model %s failed (%s)",
                                    model_name, msg[:200])
                        break  # next model
                if engine.startswith("gemini"):
                    break  # success — stop iterating the chain

        # annotate formulas with the council's verified list when present
        verified = set((council.get("physics_check") or {}).get("formulas_verified") or [])
        for f in formulas:
            f.setdefault("council_verified", any(
                key.split("(")[0].strip().lower() in f["name"].lower()
                for key in verified))
        return {
            "formulas": formulas,
            "traceability": traceability,
            "references": references,
            "engine": engine,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    # ---------------------------------------------------------------- flash
    def _call_flash(self, council: Dict[str, Any], ingestion: Dict[str, Any],
                    model_name: str) -> Dict[str, Any]:
        import json
        import re

        import google.generativeai as genai

        genai.configure(api_key=self.api_key)
        model = genai.GenerativeModel(model_name=model_name, system_instruction=(
            "You are Agent 3 of an ASI-HACK space analytics pipeline. Given a council "
            "verification summary, return STRICT JSON: {\"formulas\": [{\"name\", "
            "\"equation\", \"application\", \"source\"}], \"references\": [{\"title\", "
            "\"url\", \"doi\", \"publisher\"}]}. Only include formulas genuinely relevant "
            "to the data, and ONLY real, verifiable URLs (NASA/ESA/NOAA/journals). "
            "Never invent DOIs. If unsure, return empty arrays."))
        payload = json.dumps({
            "council_verdict": council.get("verdict"),
            "score": council.get("overall_score"),
            "metrics": ingestion.get("metrics", {}),
            "sources": [s.get("name") for s in ingestion.get("sources", [])],
        }, ensure_ascii=False)
        resp = model.generate_content(
            payload,
            generation_config={"temperature": 0.3, "response_mime_type": "application/json"})
        text = (resp.text or "").strip()
        text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start, end = text.find("{"), text.rfind("}")
            return json.loads(text[start:end + 1]) if 0 <= start < end else {}
