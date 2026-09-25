# MORS — Scientific Command Center
### ASI-HACK Space Analytics Engine

A four-agent scientific pipeline (ingest → council → citations → Ai.Mors) plus a
10-section command-center UI that turns NASA / NOAA / CelesTrak / Exoplanet-Archive
feeds into **provenance-labelled** findings, problem cards, solution paths and charts.

---

## 1. Requirements

| | |
|---|---|
| Python | 3.10+ (developed and tested on **3.12**) |
| OS | Windows / macOS / Linux |
| Network | optional — every source has a local deterministic fallback |
| Browser | Chromium-based or Firefox, any resolution (responsive) |

Install the dependencies:

```powershell
python -m pip install -r requirements.txt
```

`requirements.txt` covers `flask`, `pandas`, `numpy`, `requests`, `scikit-learn`,
`astropy`, `google-generativeai`, `python-dotenv`.
Optional extras used by the report tooling: `reportlab` (PDF export).

---

## 2. Run it

### Option A — one click (Windows)

Double-click **`START.bat`**.
It finds Python, installs missing packages, frees port 5000, starts the backend
and opens <http://127.0.0.1:5000/> in your browser. Close the window to stop.

### Option B — manual

```powershell
# from the project folder
python -m pip install -r requirements.txt
python main.py                 # http://127.0.0.1:5000
```

Then open:

| URL | What it is |
|---|---|
| <http://127.0.0.1:5000/> | legacy ASI-HACK dashboard |
| <http://127.0.0.1:5000/mors> | **MORS Scientific Command Center** (main UI) |

### Option C — verify without a server

```powershell
python main.py --selftest
```

Runs the entire four-agent pipeline synchronously and prints
`SELFTEST : PASS ✅` (roughly 75 s) or a failure diagnosis, then exits.

### Option D — audit the data & analysis layer

```powershell
python main.py                 # leave the server running
python tools\audit_data.py     # -> RESULT: AUDIT: PASS
```

Read-only battery of **225+ checks** against the live API: priority-formula
math, Kepler period/velocity consistency, habitability-gate reproduction,
CME-vs-FLR counting, per-body Horizons radii, quantum normalisation and unit
conversions, spectral PCA, light-pollution direction, the team roster, the
prompt library, the leader-only name policy and the mapping of all **8 brief
conditions** onto their 16 sources (7 core + 1
documented extension).
Nothing is written anywhere; the run prints one line per check and exits
`0` only when every check passes.

Every defect this audit (and earlier review rounds) caught is documented with
its before/after numbers in **`المشكلات_التي_تم_حلها.md`** — *Problems solved*.

### Useful flags

| Command | Effect |
|---|---|
| `python main.py` | start the Flask server on `127.0.0.1:5000` |
| `python main.py --selftest` | synchronous end-to-end test, no server |
| `python main.py --port 8080` | serve on another port |
| `python main.py --host 0.0.0.0` | expose on the LAN (see §5 security) |

Environment variables are read from **`.env`** in the project root
(`GEMINI_API_KEY`, `NASA_API_KEY`, `GEMINI_MODEL_*`, `FLASK_HOST`, `FLASK_PORT`,
`FLASK_DEBUG`). Never commit `.env`.

---

## 3. What the UI gives you

**Sidebar sections (10):** MORS Home · AI.MORS · DATA.MORS · ASTRONOMY.MORS ·
SATELLITE.MORS · QUANTUM.MORS · Problems → Solutions · Solutions Center ·
PROJECTS.MORS · TEAM.MORS.

* **Customize MORS** drawer — 8 colour themes (Dark, Light, Planet + Earth/Mars/
  Jupiter/Saturn/Neptune/Moon), 6 accents, density, contrast, particles, type size;
  every choice is persisted in `localStorage` under `mors.settings.v1`.
* **Data-health bar** — data quality, missing %, duplicates, completeness,
  accuracy and last sync, all measured cell-by-cell across the ingested frame.
* **Problem cards** with the mandatory schema:
  *Problem · Evidence · Impact · Root Cause · Analysis · Solution · Suggestions ·
  Confidence Level (algorithmic caveat) · Priority* —
  priority is metric-derived from
  `0.40·evidence + 0.35·impact + 0.25·confidence`.
* **Traceability badge** on every figure:
  `[Source | Dataset Version | Processing Pipeline | Method | Last Updated | Operator | Timestamp]`.
* **5-tier AI protocol** — *Observed Data · Calculated Metric · AI Interpretation ·
  Hypothesis · Suggested Action*. AI never invents a measurement.
* Charts (Chart.js), full-screen search (`Ctrl/⌘ + K`), record modals, hash router.

---

## 4. API

Base URL `http://127.0.0.1:5000`. Full contract in
[`docs/API_CONTRACT.md`](docs/API_CONTRACT.md).

| Method | Route | Purpose |
|---|---|---|
| GET | `/api/health` | liveness + capability probe |
| POST | `/api/pipeline/run` | start the 4-agent pipeline |
| GET | `/api/pipeline/status` | stage-by-stage progress |
| GET | `/api/report` | last certified report |
| GET | `/api/data/<name>` | science endpoints (`space-weather`, `neo`, `horizons`, `neo-matrix`, `light-pollution`, `kp-index`, `spectral`, `quantum`) |
| GET | `/mors` | MORS command center |
| GET | `/api/mors` | module index |
| GET | `/api/mors/<name>` | module payload (`home`, `ai`, `data`, `astronomy`, `satellite`, `quantum`, `problems`, `solutions`, `projects`, `team`, `objects`, `exoplanets`, `fits`, `photometry`, `spectroscopy`, `lightcurves`, `images`, `datahealth`, `sources`) |
| POST | `/api/mors/insight` | on-demand AI insight (tier-labelled) |
| POST | `/api/chat` | Ai.Mors conversational agent |

Quick check from another shell:

```powershell
Invoke-RestMethod http://127.0.0.1:5000/api/mors/datahealth
Invoke-RestMethod http://127.0.0.1:5000/api/mors/problems
```

---

## 5. Security notes

* `FLASK_DEBUG` defaults to **off** and is forcibly disabled on non-loopback hosts —
  the Werkzeug debugger is a remote-code-execution surface.
* Bind to `127.0.0.1` unless you intend to share the server.
* Keep `.env` out of version control (`.gitignore` already excludes it) and rotate
  any key that has been posted publicly.

---

## 6. Project layout

```
00_COMMITTEE_GUIDE.md    judging-committee guide (Arabic, plain text)
00_MANIFEST.txt          size + SHA-256 of every packaged file
المشكلات_التي_تم_حلها.md  problems solved — data/analysis defects, before → after
main.py                  orchestrator + Flask API + CLI (--selftest / --port / --host)
agents/
  agent1_ingestion.py    NASA DONKI, NEOWS, JPL Horizons, ./data + cleaning, QC, quality audit
  agent2_council.py      Council of 5 experts (Gemini) → verdict, score, log
  agent3_citations.py    formula + reference enrichment, traceability records
  agent4_aimors.py       Ai.Mors conversational agent (Arabic greeting, numbered steps)
  datasets.py            science dataset builders reused by the MORS layer
  mors_data.py           MORS data layer — 17 modules, API → AI → local acquisition
  sources_data.py        scientific source registry + the 8 hackathon conditions
static/
  index.html             legacy ASI-HACK dashboard
  mors.html              MORS Scientific Command Center (SPA, incl. SOURCES.MORS)
tools/
  audit_data.py          read-only data & analysis audit (225+ checks -> AUDIT: PASS)
  build_report.py        generates docs/MORS_REPORT.pdf (figures + sources section)
  build_guide.py         generates docs/PROJECT_GUIDE.pdf (file-by-file guide)
  build_committee.py     generates 00_COMMITTEE_GUIDE.md + docs/COMMITTEE_GUIDE.pdf
docs/
  API_CONTRACT.md        request/response contract for every endpoint
  MORS_REPORT.pdf        generated platform report (see §7)
  PROJECT_GUIDE.pdf      generated file-by-file project guide (see §7)
  COMMITTEE_GUIDE.pdf    printable Arabic edition of the committee guide
prompts/                 prompt templates used by the agents
data/                    reference CSVs (light pollution, spectra, Kp, metrics)
DEPLOYMENT.md            deployment & operations guide
START.bat                one-click Windows launcher
requirements.txt
```

---

## 7. Regenerating the documents

```powershell
python main.py                  # keep a server running so the pipeline has a report
# then, from a second shell:
python tools\audit_data.py      # confirm the data layer first -> AUDIT: PASS
python tools\build_report.py    # writes docs\MORS_REPORT.pdf
python tools\build_guide.py     # writes docs\PROJECT_GUIDE.pdf
python tools\build_committee.py # writes 00_COMMITTEE_GUIDE.md + docs\COMMITTEE_GUIDE.pdf
```

The report pulls live figures from `/api/report` and `/api/mors/*`, so it always
matches the numbers shown in the UI. The guide scans the working tree, so it
always matches the files on disk. Both need the optional PDF stack listed at
the bottom of `requirements.txt` (`reportlab`, `arabic-reshaper`,
`python-bidi`, `matplotlib`).

---

## 8. Honest limitations

* Gemini free-tier quota (HTTP 429) degrades Agents 2/3/4 to the deterministic
  **local fallback** engines. The report still certifies, but it is *not*
  LLM cross-verified — this is surfaced as problem **P-001** on the dashboard.
* Satellite pass windows are period-derived estimates, not TLE propagations
  (`estimate=true`).
* Quantum results are classical NumPy statevector simulations — no QPU is contacted.
* Reference multi-spectral profiles are spectra, not imagery.

---

## 9. License / credits

Built for the **ASI Hack — AI for Space Challenges** track.
Data: NASA (DONKI, NEOWS, Horizons, GIBS, APOD, Exoplanet Archive), NOAA SWPC,
CelesTrak. Terms of each provider apply.
