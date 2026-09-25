# ASI-HACK Space Analytics Engine — Shared API Contract (Backend ⇄ Frontend)
# كل نقطة نهاية إلزامية للتكامل بين main.py و static/index.html

BASE URL: http://127.0.0.1:5000

## 1) GET /  → يقدّم static/index.html
## 2) GET /api/health
Response:
{
  "status": "ok",
  "gemini_configured": true/false,
  "nasa_key_mode": "live" | "demo",
  "agents": {"agent1": true, "agent2": true, "agent3": true, "agent4": true},
  "data_endpoints": ["/api/data/space-weather", "/api/data/neo", "/api/data/horizons",
                     "/api/data/neo-matrix", "/api/data/light-pollution",
                     "/api/data/kp-index", "/api/data/spectral", "/api/data/quantum"],
  "timestamp": "ISO-8601 UTC"
}

## 3) POST /api/pipeline/run     (شغيل المخطط الكامل: Agent1 → Agent2 → Agent3)
Body (optional): {"quick": true}   // quick=true يختصر استدعاءات Gemini
Response:
{
  "run_id": "run-YYYYmmdd-HHMMSS-xxxx",
  "status": "completed" | "failed" | "running",
  "stages": [
    {"stage": "ingestion", "label": "Agent 1 — Ingest & Clean", "status": "completed", "detail": "..."},
    {"stage": "council",   "label": "Agent 2 — Council of 5",   "status": "completed", "detail": "..."},
    {"stage": "citations", "label": "Agent 3 — Citations",       "status": "completed", "detail": "..."}
  ],
  "report": { ...SEE /api/report... }
}

## 4) GET /api/pipeline/status
Response: { "run_id": "...", "status": "idle"|"running"|"completed"|"failed",
            "progress": 0-100, "current_stage": "ingestion|council|citations|idle",
            "updated_at": "ISO" }

## 5) GET /api/report   → آخر تقرير مُعتمد (يُخزَّن في حالة الذاكرة + last_report.json)
{
  "run_id": "...", "generated_at": "ISO",
  "dataset_summary": {
    "sources": [{"name":"DONKI CME","type":"nasa_api","endpoint":"https://api.nasa.gov/DONKI/CME","records":42},
                {"name":"NEOWS","type":"nasa_api","endpoint":"https://api.nasa.gov/neo/rest/v1/feed","records":18},
                {"name":"JPL Horizons","type":"nasa_api","endpoint":"https://ssd.jpl.nasa.gov/api/horizons.api","records":10},
                {"name":"reference_docs","type":"local","records":3}],
    "rows": <int>, "features": ["..."], "cleaning": ["StandardScaler applied", "IsolationForest anomalies: n", ...]
  },
  "cleaned_preview": [ {row objects, max 10 rows} ],
  "metrics": {
    "light_curve_snr": <float|null>, "anomaly_count": <int>,
    "cme_count": <int>, "neo_count": <int>,
    "closest_au": <float|null>, "solar_wind_avg_kms": <float|null>,
    "closest_ld": <float|null>, "kp_max": <float|null>,
    "flare_count_30d": <int>, "darkest_site_nelm": <float|null>,
    "brightest_site_nelm": <float|null>, "spectral_bands": <int>,
    "quantum_entropy_ebit": <float|null>
  },
  "council": {
    "verdict": "CERTIFIED"|"CERTIFIED_WITH_CORRECTIONS"|"REJECTED",
    "overall_score": 0-100,
    "experts": [{"id":1,"name":"Dr. Orbit","role":"...","score":95,"finding":"...","correction":null}, x5],
    "physics_check": {"formulas_verified": [...], "errors_found": [...]},
    "hallucinations_removed": [...], "corrections_applied": [...],
    "traceability_ok": true, "log": ["..."], "summary": "..."
  },
  "citations": {
    "formulas": [{"name":"Kepler's Third Law","equation":"T^2 = a^3 / GM","application":"...","source":"..."}],
    "traceability": [{"id":"TRC-001","source":"NASA DONKI","endpoint":"https://api.nasa.gov/DONKI/CME","timestamp":"ISO","local_ref":null}],
    "references": [{"title":"...","url":"https://...","doi":null,"publisher":"NASA/ESA/journal"}]
  },
  "science": {
    "light_pollution": { ...SAME SHAPE AS GET /api/data/light-pollution... },
    "kp_index":        { ...SAME SHAPE AS GET /api/data/kp-index... },
    "spectral":        { ...SAME SHAPE AS GET /api/data/spectral... },
    "quantum":         { ...SAME SHAPE AS GET /api/data/quantum... }
  }
}

## 6) GET /api/data/space-weather   (DONKI — للرسوم البيانية)
{
  "series": [{"t":"ISO","value":<float>,"label":"CME speed km/s"}],
  "items": [{"id":"...","startTime":"ISO","speed":<float|null>,"type":"..."}],
  "source": {"endpoint":"https://api.nasa.gov/DONKI/CME","fetched_at":"ISO"}
}

## 7) GET /api/data/neo   (NEOWS)
{
  "series": [{"t":"YYYY-MM-DD","value":<count per day>}],
  "items": [{"id":"...","name":"...","diameter_m":<float|null>,"miss_distance_au":<float|null>,
             "miss_distance_ld":<float|null>,
             "velocity_kms":<float|null>,"hazardous":bool,"absolute_magnitude_h":<float>}],
  "source": {"endpoint":"https://api.nasa.gov/neo/rest/v1/feed","fetched_at":"ISO"}
}

## 8) GET /api/data/horizons   (JPL Horizons — إحداثيات جرم)
{
  "series": [{"t":"JD","x_au":<float>,"y_au":<float>,"z_au":<float>}],   ← primary body only
  "orbits": {"Earth": [...], "Mars": [...]},     ← one track per body (never mixed)
  "bodies": ["Earth","Mars"],
  "body": "Earth" | "Mars" | ...,                ← labels `series`
  "frame": "ICRS/heliocentric",
  "source": {"endpoint":"https://ssd.jpl.nasa.gov/api/horizons.api","fetched_at":"ISO"}
}
`series` equals `orbits[body]`: the UI charts each body as its own dataset so no
line is ever drawn across two planets (radii: Earth 0.95–1.05 au, Mars 1.35–1.75 au).

## 9) GET /api/data/neo-matrix   (NEO hazard bubble matrix → widget 2)
{
  "points": [{"name":"...","x_ld":<miss distance in lunar distances>,"y_kms":<velocity>,
              "diameter_m":<float>,"hazardous":bool,"id":"..."}],
  "axes": {"x":"miss_distance_ld","y":"velocity_kms","size":"diameter_m"},
  "conversions": {"au_to_ld":<float>,"formula":"d[LD] = d[au] / 0.0025696","ld_km":384400.0},
  "source": {"endpoint":"https://api.nasa.gov/neo/rest/v1/feed","fetched_at":"ISO"}
}

## 10) GET /api/data/light-pollution   (NASA GIBS VIIRS Black Marble → widget 1)
{
  "sites": [{"name":"...","lon":<float>,"lat":<float>,"lights_index":0-1,
             "radiance_nw_cm2_sr":<float>,"sqm_mag_arcsec2":<float>,
             "nelm_mag":<float>,"bortle_model":1-9,"bortle_published":1-9}],
  "reference_curve": [{"index":0-1,"radiance_nw_cm2_sr":<float>,"nelm_mag":<float>,"bortle_model":n}],
  "model": {"radiance_to_sqm":"mu = 17.836 - 2.5*log10(L)",
            "nelm_formula":"NELM = mu - 14.6",
            "calibration":"...","calibration_anchors":"...",
            "gamma_de_rendering":<float>,"sqm_zero":<float>},
  "source": {"layer":"VIIRS_Black_Marble","time":"2016-01-01",
             "endpoint":"https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi",
             "live":bool,"fetched_at":"ISO"}
}
NOTE: the numbers are a CALIBRATED MODEL derived from real NASA night-light
pixels, not a photometric measurement. `model`/`calibration` state the mapping.

## 11) GET /api/data/kp-index   (NOAA SWPC Kp + NASA DONKI flares → widget 3)
{
  "kp": [{"t":"ISO","kp":<0-9>,"station_count":<int|null>}],
  "kp_smooth": [<float|null>, ...],                 // 3-sample moving average
  "flares": [{"t":"ISO","class":"C1.0".."X9.9","peak_flux_w_m2":<float>,
              "active_region":"...","flr_id":"..."}],
  "daily": [{"t":"YYYY-MM-DD","kp_max":<float|null>,"kp_mean":<float|null>,
             "kp_min":<float|null>,"flare_max_flux":<float|null>,
             "flare_class":<str|null>,"flare_count":<int>,"no_data"?:true}],
  "scale": {"kp_threshold_storm":5,"kp_threshold_extreme":9,
            "classes":{"B":1e-7,"C":1e-6,"M":1e-5,"X":1e-4},
            "class_formula":"peak_flux [W/m^2] = mantissa * 10^(letter exponent)",
            "kp_definition":"..."},
  "source": {"kp_endpoint":"https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json",
             "flare_endpoint":"https://api.nasa.gov/DONKI/FLR",
             "provider":"NOAA Space Weather Prediction Center + NASA DONKI",
             "kp_live":bool,"flare_live":bool,"fetched_at":"ISO"}
}
`daily` is padded to one entry per calendar day across the whole span so the
widget x-axis stays continuous; days with no source record carry
`no_data: true` and null metrics.

## 12) GET /api/data/spectral   (Sentinel-2 band indices → widget 4)
{
  "bands": [{"band":"B2".."B11","name":"...","nm":<int>,"width_nm":<int>}],
  "profiles": [{"land_cover":"Dense vegetation","reflectance":[<0-1> x n_bands]}],
  "indices": {"ndvi":"(B8-B4)/(B8+B4)","ndwi":"(B3-B8)/(B3+B8)","ndbi":"(B11-B8)/(B11+B8)"},
  "band_ids": ["B2","B3","B4","B8","B11"],
  "processing": {"pipeline":"...","n_samples":<int>,"n_features":<int>,
                 "explained_variance_ratio":[<float>,<float>]},
  "provenance": {"honesty_note":"...","type":"reference_spectra"},
  "source": {"endpoint":"...","fetched_at":"ISO"}
}
Reflectance values are documented library reference spectra, NOT a live
satellite acquisition; only the reduction pipeline (StandardScaler → PCA)
runs on real input.

## 13) GET /api/data/quantum   (statevector simulation)
{
  "states": {"bell": {"label":"|Phi+> = (|00>+|11>)/sqrt(2)",
                      "amplitudes":[[re,im] x 4],
                      "entanglement_entropy_ebit":1.0,
                      "reduced_purity":0.5,"schmidt_rank":2,
                      "expectation":{"XX":1.0,"YY":-1.0,"ZZ":1.0,"ZI":0.0}},
             "ghz": {"label":"|GHZ> = (|000>+|111>)/sqrt(2)",
                     "amplitudes":[[re,im] x 8],
                     "expectation":{"ZZI":1.0,"ZIZ":1.0,"IZZ":1.0,"XXX":1.0}}},
  "qho_levels": {"formula":"E_n = hbar*omega*(n + 1/2)","omega_rad_s":<float>,
                 "levels":[<float> x n]},
  "rabi_drive": [{"theta":<float>,"population":<float>}],
  "verification": {"entropy_bell_expected_ebit":1.0,"entropy_error":0.0,
                   "normalization_bell":1.0,"normalization_ghz":1.0,
                   "unitarity":"..."},
  "honesty": "Classical NumPy statevector simulation. No quantum processing unit
              was contacted; results are exact linear-algebra solutions of the
              Schrodinger equation.",
  "source": {"type":"local_simulation","engine":"numpy ...","fetched_at":"ISO"}
}

## 14) POST /api/chat   (Ai.Mors — Agent 4)
Body: {"message": "string", "history": [{"role":"user"|"model","parts":"string"}] (optional)}
Response: {"reply": "أهلاً وسهلاً بكم في الفضاء\n1- ...", "greeting_ok": true, "trace": ["TRC-..."], "timestamp":"ISO"}
errors: 400 {"error":"message required"} ; 503 {"error":"certified report not ready"} إذا لم يُشغَّل المخطط بعد


---

# MORS Scientific Command Center

## 15) GET /mors  → يقدّم static/mors.html (واجهة MORS)
Single-page app with 10 sidebar sections:
`home, ai, data, astronomy, satellite, quantum, problems, solutions,
projects, team` (hash router `#/home` ... `#/team`).
`data` and `astronomy` are composite views built client-side from
`datahealth`, `objects`, `exoplanets`, `fits`, `photometry`,
`spectroscopy`, `lightcurves`, `images`.

Settings persist in `localStorage` under `mors.settings.v1`
(theme, planet, accent, density, compact, particles, motion, contrast,
bigtext, grid, sci).

## 16) GET /api/mors   → فهرس الوحدات
{
  "page": "/mors",
  "modules": ["ai","datahealth","exoplanets","fits","home","images",
              "lightcurves","modules","objects","photometry","problems",
              "projects","quantum","satellite","solutions","spectroscopy",
              "team"],
  "with_report": ["ai","datahealth","home","problems","projects","solutions"],
  "acquisition_order": ["api","ai_synthesis","local_model"],
  "ai_insight": "POST /api/mors/insight"
}

## 17) GET /api/mors/<name>   → حمولة الوحدة
Modules that need the certified report take it as the single argument;
the rest are argument-free.

Common envelope (present on most modules):

{
  "badge": "[Source | 1.0.0 | pipeline | method | operator | ISO]",
  "trace": {
    "source": "...", "dataset_id": "MORS-<NAME>-v1.0.0",
    "dataset_version": "1.0.0", "processing_pipeline": "...",
    "method": "...", "operator_id": "agent:mors",
    "via": "api" | "ai_synthesis" | "local_model" | "pipeline",
    "endpoint": "...", "note": "...",
    "last_updated": "ISO", "timestamp": "ISO"
  },
  "source": {"via": "api"|"ai_synthesis"|"local_model", "live": bool},
  "count": <int>, "rows": [ ... ]
}

### home
{
  "headline": {"platform": "...", "domains": [...], "lifecycle": [...]},
  "domains": [{"key","label","desc"} x6],
  "metrics": {"rows","anomaly_count","cme_count","neo_count","kp_max",
              "closest_ld","light_curve_snr","quantum_entropy_ebit",
              "data_quality_score","missing_pct","formulas","references",
              "problems_open","problems_high"},
  "problems": [ ...SAME OBJECTS AS /api/mors/problems.problems (top 4)... ],
  "solutions_summary": [{"id","title","priority","expected_impact"}],
  "runs": [{"run_id","status","verdict","score","engine","rows",
            "sources","generated_at"}]
}

### datahealth
{
  "data_quality_score","missing_pct","duplicate_rows","duplicate_pct",
  "completeness_pct","accuracy_score","cells","rows","sources",
  "outlier_count","outliers_pct","last_sync","pipeline",
  "per_source": [{"source","rows","columns","cells","missing_cells",
                  "missing_pct","duplicate_rows","invalid_cells",
                  "completeness_pct","accuracy_score","status"} x N]
}
Quality is computed cell-by-cell over the whole ingested frame
(StandardScaler -> IsolationForest(contamination=0.1)); it is never
sampled. Empty until the pipeline has run once.

### problems
{
  "count": <int>,
  "by_priority": {"High": n, "Medium": n, "Low": n},
  "lifecycle": ["DATA","SIGNAL", ... x8],
  "problems": [{
    "problem_id": "P-001", "title": "...",
    "severity": "critical"|"high"|"medium"|"low",
    "category": "data"|"logic"|"api"|"ui"|"docs"|"infra"|"performance",
    "component": "agents/<file>.py",
    "symptom": "...",
    "root_cause": "...",
    "fix": ["..."],
    "evidence": ["..."],
    "priority": "High"|"Medium"|"Low",
    "priority_code": "P0"|"P1"|"P2",
    "priority_score": <0-100>,
    "priority_formula": "0.40*evidence + 0.35*impact + 0.25*confidence",
    "evidence_metric": <0-100>,
    "impact": "...", "impact_score": <0-100>,
    "confidence_level": <0-100>,
    "confidence_note": "Algorithmic estimation ... - not proof.",
    "domain": "...", "owner": "...",
    "analysis": "...", "suggestions": ["..."],
    "detected_at": "ISO", "id": "P-001"
  }]
}
Required keys on every card: problem_id, title, severity, category,
component, symptom, root_cause, fix, evidence ( + priority).
Forbidden keys: description, solution, notes, status, details.
`severity` is the qualitative band of the computed score (critical/high/
medium/low), `priority` is its score tier (High >= 75, Medium >= 50) and
`priority_code` is the planning code derived from that tier (High -> P0,
Medium -> P1, Low -> P2). The priority is metric-derived from
0.40*evidence + 0.35*impact + 0.25*confidence, never hand-picked.

### solutions
{
  "count": <int>,
  "summary": [{"id","title","priority"}],
  "solutions": [{
    "problem_id": "P-001", "title": "...", "owner": "...",
    "effort": "S"|"M"|"L", "confidence_level": <0-100>,
    "path": ["Problem","Evidence","Root cause","Analysis","Solution",
             "Suggestion","Action"],
    "steps": [{"step": n, "action": "...", "type": "automated"|"manual"}],
    "suggestions": ["..."],
    "expected_impact": [{"metric","now","target","delta"}]
  }]
}

### modules
{"count": n, "modules": [{"key","label","desc","icon","fields":[...]}]}

### projects
{"count": n, "projects": [{"id","name","problem","dataset","methodology",
  "analysis","visuals":[...],"issues":[...],"solutions":[...],
  "results","technologies":[...],"source_docs":[...]}]}

### team
{"count": n, "members": [{"id","name","name_latin","lead","title","role",
  "owns":[...],"skills":[...]}]}
Name policy: only the team leader is published by name (TM-1); TM-2..TM-4
are published by role, so no other personal name appears in any payload or
project file.

### prompts
{"count": n, "prompts": [{"id","title","domain","file","summary",
  "lines","chars","text","loaded"}], "trace", "badge"}
Six master prompts shipped in `prompts/`: aimors_scientific,
uiux_command_center, uiux_visualization, cyber_mors, analytics_report,
deep_audit. Read-only — the payload is a projection of those files.


### ai
{
  "engine": {"council","last_score","formula_coverage","data_quality"},
  "protocol": ["[Observed Data]","[Calculated Metric]","[AI Interpretation]",
               "[Hypothesis]","[Suggested Action]"],
  "models": [{"id","role","temperature","context","status"}],
  "tools": [{"name","type","records","status"}],
  "insights": [{"type","text"}],
  "recommendations": [{"priority","text"}],
  "research": [{"topic","owner","status"}]
}
Five-tier labelling is mandatory: every AI statement must say which tier
it is. AI never invents a measurement.

### satellite
{"rows": [{"name","norad_id","group","mission","object_type","epoch",
           "orbit_class","altitude_km","apogee_km","perigee_km",
           "velocity_kms","period_min","inclination_deg","eccentricity",
           "mean_motion_rev_day","sensor_type","resolution_m",
           "processing_level","swath_km","bbox","next_passes":[...],
           "telemetry":{...}}],
 "physics": {"semi_major_axis","circular_velocity","orbit_class",
             "GM_earth","R_earth"},
 "source": {"via": "api"}}
Source: CelesTrak GP groups `stations, science, weather, geo, gnss`,
class-balanced to LEO 24 / MEO 12 / GEO 14.
Physics: a = (GM/n^2)^(1/3), v = sqrt(GM/a), LEO < 2000 <= MEO < 35586 <= GEO.
`next_passes` are period-derived estimates (`estimate: true`).

### exoplanets / objects / images / fits / photometry /
### lightcurves / spectroscopy / quantum
Each returns `{"count","rows":[...],"trace","badge"}` with
module-specific row schemas (see the payload keys). Where the data is a
model rather than a measurement, `trace.note` says so explicitly
(no telescope exposure, no QPU contacted, reference spectra, ...).

## 18) POST /api/mors/insight   → رؤية ذكاء اصطناعي مُصنَّفة
Body: {"question": "string" (optional), "dataset": "<module name>" (optional)}
Response:
{
  "text": "...",
  "tier": "Observed Data"|"Calculated Metric"|"AI Interpretation"|
          "Hypothesis"|"Suggested Action",
  "dataset_id": "MORS-AIINSIGHT-v1.0.0",
  "engine": "gemini"|"local_model",
  "hallucination_policy": "Every claim must cite a dataset_id or a named source.",
  "trace": { ...same trace object... }
}
falls back to the deterministic local explainer when Gemini is quota-blocked.

## 19) بار صحة البيانات (يظهر في /mors أعلى كل صفحة)
`GET /api/mors/datahealth` feeds the six-tile health bar:
Data quality, Missing, Duplicates, Completeness, Accuracy, Last updated.
Every figure is measured, never asserted.

## 20) GET /api/mors/sources   → السجل العلمي للمصادر وشروط الهاكاثون
`agents/sources_data.py::build()` — a static registry (no network calls), so it
renders fully offline. Serves `SOURCES.MORS` and section 15 of
`docs/MORS_REPORT.pdf`.

```json
{
  "count": 16,
  "hackathon": [
    {"id":"S-01","no":1,"title":"Google Machine Learning Crash Course",
     "title_ar":"دورة Google المختصرة في تعلم الآلة",
     "phase":"Preparation|During|Research",
     "kind":"Course|Dataset|Research paper|...",
     "level":"Beginner|Intermediate|Advanced|All levels",
     "category":"ai_basics|data_handling|analysis_modelling|computer_vision|astronomical_data|generative_ai|predictive_automation|inspiration_research",
     "url":"https://... | null",
     "goal_ar":"...","learn_ar":"...","for_ar":"...","when_ar":"...",
     "used_in":["agents/agent1_ingestion.py", "..."]}
  ],
  "data_sources": [
    {"id":"D-01","name":"NASA DONKI (CME / FLR)","kind":"REST API",
     "url":"https://api.nasa.gov/DONKI/CME",
     "via":"api|ai_synthesis|local_model",
     "used_in":"agent1_ingestion.fetch_donki",
     "gives":"159 CME records + solar flares"}
  ],
  "conditions": [
    {"n":1,"key":"ai_basics","name":"AI & Machine-Learning basics",
     "name_ar":"فهم أساسيات الذكاء الاصطناعي وتعلم الآلة",
     "helps_ar":"تساعد المصادر ... الفرق على ...",
     "status":"core|extension",
     "sources":["S-01","S-02"],
     "used_in":["agents/agent1_ingestion.py — ..."],
     "evidence":"The pipeline applies ..."}
  ],
   "aggregates": {"by_phase":{"Preparation":7,"During":7,"Research":2},
                  "by_level":{...},"by_kind":{...},"by_category":{...},
                  "total":16,"live_data_sources":8,
                  "conditions_covered":8,"conditions_core":7,
                  "conditions_extension":1,"conditions_total":8},
  "disclaimer_ar":"لا يطلب من الفرق استخدام جميع المصادر أو اتباع ترتيب محدد ...",
  "trace": {"dataset_id":"MORS-SOURCES-v1.0.0", ...},
  "badge":"[ASI Hackathon source registry + project data sources | 1.0.0 | ...]"
}
```

The eight `conditions` rows are the brief's "how do the sources help the team?"
bullets; `status` is `core` when the repository already contains working code
for that condition, `extension` when it is documented as the next step
(Computer Vision is `extension`: image metadata and raster tiles are ingested
today, pixel-level segmentation is the declared extension path).

`conditions_covered` counts the conditions that have both mapped sources and
repository code (all 8); `conditions_core` and `conditions_extension` split
the same eight by `status`, so the honest split is always visible.