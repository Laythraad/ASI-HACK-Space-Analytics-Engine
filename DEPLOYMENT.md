# 🚀 ASI-HACK Space Analytics Engine — Deployment & Operations Guide

End-to-end Python AI workflow for the **ASI Hack — AI for Space Challenges** track:
a scientifically validated space-analytics engine plus an interactive 3D agent, **Ai.Mors**.

---

## 0. One-click launch (recommended)

Double-click **`START.bat`**.

It will, automatically:
1. Locate Python 3.11+ (`py -3` → `python` → `python3`)
2. Install anything missing from `requirements.txt`
3. Free port 5000 if an old instance is holding it
4. Start the backend (`main.py`) minimized
5. Poll `/api/health` until the API is up (max 60 s)
6. Open **http://127.0.0.1:5000/** in your default browser

Close the `START.bat` window to stop the server.

---

## 1. Manual launch

```powershell
# from the project folder
python -m pip install -r requirements.txt
python main.py            # serves http://127.0.0.1:5000
```

Useful flags:

| Command | Effect |
|---|---|
| `python main.py` | Start the Flask server |
| `python main.py --selftest` | Run the whole pipeline synchronously, print a PASS/FAIL summary, exit |
| `python main.py --port 8080` | Serve on another port |
| `python main.py --host 0.0.0.0` | Expose on the LAN (see §5 security) |

---

## 2. Credentials (`.env`)

Loaded automatically with `python-dotenv` from the project root.

| Variable | Purpose | Default |
|---|---|---|
| `GEMINI_API_KEY` | Agents 2 (Council), 3 (Citations), 4 (Ai.Mors) | — (runs offline fallback if empty) |
| `GEMINI_MODEL_PRO` | Council + Ai.Mors model | `gemini-3.1-pro-preview` |
| `GEMINI_MODEL_FLASH` | Citations model | `gemini-3.6-flash` |
| `GEMINI_MODEL_FALLBACK` | Tried when the preferred model returns 404 | `gemini-flash-latest` |
| `NASA_API_KEY` | Agent 1 (DONKI / NEOWS) | `DEMO_KEY` (heavily rate-limited) |
| `FLASK_HOST` / `FLASK_PORT` / `FLASK_DEBUG` | Server | `127.0.0.1` / `5000` / `1` |
| `OPENCODE_API_KEY` | OpenCode platform credential (not used by the pipeline) | — |

> **Note:** JPL Horizons needs **no** key.
> **Never commit `.env`.** Rotate any key that has been posted publicly.

---

## 3. Architecture

```
main.py  (Orchestrator + Flask API)
│
├── agents/agent1_ingestion.py   NASA DONKI + NEOWS + JPL Horizons + ./data
│                                + light pollution / Kp / spectral / quantum
│                                → StandardScaler, IsolationForest, Astropy transforms
├── agents/agent2_council.py     Council of 5 experts (Gemini) → verdict + score + log
├── agents/agent3_citations.py   Formulas + Traceability IDs + references (Gemini)
├── agents/agent4_aimors.py      Ai.Mors chat, restricted to the certified report
├── agents/datasets.py           Extended science datasets (never raises, TTL cache)
│                                · NASA GIBS VIIRS Black Marble → light pollution
│                                · NOAA SWPC Kp + NASA DONKI FLR → space weather
│                                · Sentinel-2 bands → NDVI/NDWI/NDBI + PCA
│                                · NumPy statevector quantum simulation
│
├── prompts/council_prompt.txt   System prompt — Agent 2
├── prompts/aimors_prompt.txt    System prompt — Agent 4
├── static/index.html            Three.js + Chart.js dashboard (single file,
│                                incl. the 4 extended-science widgets)
├── docs/API_CONTRACT.md         Backend ⇄ Frontend contract
├── data/reference_metrics.csv   Local reference document (ingested by Agent 1)
├── data/*_reference.csv         Auto-generated reference curves (recomputable)
├── last_report.json             Written after every successful run (auto-reloaded)
└── .env                         Credentials (git-ignored)
```

**Every agent degrades gracefully:** if Gemini or NASA is unreachable, the pipeline still
completes using deterministic local fallbacks (reported via the `engine` field).

---

## 4. API surface

Full shapes in [`docs/API_CONTRACT.md`](docs/API_CONTRACT.md).

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/` | Dashboard |
| GET | `/api/health` | Key/config status + available data endpoints |
| POST | `/api/pipeline/run` | Start Agent 1 → 2 → 3 in a background thread |
| GET | `/api/pipeline/status` | `{status, progress, current_stage}` (poll 1 s) |
| GET | `/api/report` | Last certified report (incl. `science` block) |
| GET | `/api/data/space-weather` | DONKI CME/FLR series |
| GET | `/api/data/neo` | NEOWS counts + items (`miss_distance_ld` included) |
| GET | `/api/data/horizons` | Heliocentric x/y/z (au) |
| GET | `/api/data/neo-matrix` | NEO hazard bubble matrix (LD × km/s × size) |
| GET | `/api/data/light-pollution` | NASA GIBS night lights → radiance / NELM / Bortle |
| GET | `/api/data/kp-index` | NOAA Kp + DONKI flare classes, daily buckets |
| GET | `/api/data/spectral` | Sentinel-2 bands, indices, PCA reduction |
| GET | `/api/data/quantum` | Statevector simulation (Bell/GHZ/QHO/Rabi) |
| POST | `/api/chat` | Ai.Mors conversation |

Typical session: **Run Pipeline** → watch the progress bar → verdict banner appears →
charts populate → the **Extended Science Matrix** fills in (4 widgets) →
ask Ai.Mors a question.

The four extended endpoints serve the pipeline's cached copy when one exists and
otherwise fetch on demand (cached for `DATA_TTL`). Each returns HTTP 502 with a
partial payload rather than failing the page if its upstream is unreachable.

---

## 5. Security notes

- The server binds to **`127.0.0.1`** by default — not reachable from other machines.
  Only use `--host 0.0.0.0` behind a reverse proxy with TLS.
- API keys live only in `.env`; they are **masked in logs** (first 6 chars) and are
  **never** embedded in `static/index.html`.
- Response headers set: `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`.
- Static serving validates the resolved path stays inside the project root (no traversal).
- Chat input is length-capped (4000 chars); NASA responses are size-capped before
  being sent to Gemini.
- Add to `.gitignore` before publishing: `.env`, `last_report.json`, `__pycache__/`.

---

## 6. Rate limits & troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `429 … quota exceeded` in logs | Gemini free tier ≈ 5 req/min/model | Automatic backoff retries; wait ~1 min or upgrade the key |
| `404 … model is no longer available` | Deprecated model name | Set `GEMINI_MODEL_PRO` / `FLASH` to a model from `list_models()` |
| `engine: local_fallback` in report | Gemini unreachable | Check `GEMINI_API_KEY`; pipeline still completes |
| NASA returns few records | `DEMO_KEY` rate limit | Get a free key at https://api.nasa.gov |
| Charts empty | Pipeline not run yet, or offline | Press **Run Pipeline**, check `/api/health` |
| Port already in use | Old instance | `START.bat` kills it automatically, or change `FLASK_PORT` |
| `Horizons: … (fallback)` | ssd.jpl.nasa.gov unreachable | Deterministic Keplerian fallback is used and labeled |
| `GIBS tile failed … Read timed out` | gibs.earthdata.nasa.gov slow | That site drops out of the widget; the rest keep rendering (`live: false` is reported) |
| Light-pollution widget says `partial` | One or more tiles unavailable | Re-run the pipeline; `source.live` tells you whether all tiles came back |
| Kp widget line stops early | NOAA feed only carries ~7.7 days | Expected — `daily` is padded with `no_data: true` days, flares still fill 30 d |

---

## 7. Validation

```powershell
python main.py --selftest
```

Expected tail:

```
  [ completed] Agent 1 — Ingest & Clean: ~1714 rows, 8 sources
  [ completed] Agent 2 — Council of 5: CERTIFIED 98/100 [gemini:gemini-flash-latest]
  [ completed] Agent 3 — Citations: 18 formulas, 11 refs  (grows when Gemini responds)
verdict         : CERTIFIED
report keys     : [... 'science']
Ai.Mors greeting: 'أهلاً وسهلاً بكم في الفضاء' (ok=True)
SELFTEST        : PASS ✅
```

It runs all three agents, prints the verdict/score, verifies Ai.Mors starts with the
mandatory Arabic greeting, and exercises the extended datasets (`science` block).
`engine: local_fallback` just means Gemini's free tier returned 429 during the run.

### 7.1 Data & analysis audit

```powershell
python tools\audit_data.py
```

Expected tail:

```
AUDIT: 224 checks, 0 failed
RESULT: AUDIT: PASS
```

The exact count tracks how many problem cards are active in that run (two
checks per card): expect **223–227**, always with `0 failed`.

A read-only probe of the live API (nothing is written): priority-formula math,
Kepler period/velocity agreement, apogee/perigee integrity, CME-vs-FLR counting,
habitability-gate reproduction, per-body Horizons radii, quantum normalisation
and unit conversions, spectral PCA, light-pollution direction, the team
roster and the 8-condition / 16-source mapping from the hackathon brief.
Defects found this way — with before/after numbers — are documented in
`المشكلات_التي_تم_حلها.md`.

---

## 8. Deploying beyond localhost (options)

- **Static demo (published):** <https://laythraad.github.io/ASI-HACK-Space-Analytics-Engine/>
  — GitHub Pages from `main` (`index.html` launcher, `.nojekyll` present). Pages cannot run
  Flask, so `GET` endpoints are snapshotted into `static/api/**.json` by
  `python tools/build_static_api.py`; both frontends fall back to that snapshot when
  `/api/health` is unreachable and show the "وضع العرض الثابت" banner. The chat, insight and
  **Run Pipeline** controls keep working offline via `static/offline_assistant.js`
  (`engine: static:snapshot`), while live Gemini/NASA answers and a real pipeline run need
  the local server. Refresh the snapshot after every pipeline run (`python main.py` in one
  terminal, then the script) and push.
- **LAN demo:** `python main.py --host 0.0.0.0` + allow the port in Windows Firewall.
- **Cloud (Render — prepared):** `render.yaml` at the repo root describes the whole service.
  Render → **New → Blueprint** → pick this repository → enter `GEMINI_API_KEY` and
  `NASA_API_KEY` when asked → Deploy. It runs
  `gunicorn -w 1 --threads 4 --timeout 180 -b 0.0.0.0:$PORT main:app` (one process, so the
  in-memory report and caches stay consistent), health check `/api/health`, Python 3.12 from
  `.python-version`, `FLASK_DEBUG=0`. Manual alternative: **New → Web Service** with the same
  build command (`pip install -r requirements.txt`), the same start command and the same two
  environment variables. What the hosted server adds over the static mirror: live Gemini chat,
  live NASA/NOAA/CelesTrak data, a real `POST /api/pipeline/run`, and the same URLs Pages
  publishes (`/index.html` launcher, `/docs/*.pdf`, `/presentation/*`, `/README.md`) — NASA APOD
  thumbnails load because `img-src` allows `https://*.nasa.gov`. Free instances sleep after
  ~15 minutes idle (first request then takes ~50 s).
- **Cloud (Railway/Fly.io):** same build/start commands and the same two env vars.
- **Docker:** `FROM python:3.12-slim` → copy → `pip install -r requirements.txt` →
  `EXPOSE 5000` → `CMD ["python","main.py","--host","0.0.0.0"]`.

---

## 9. Hackathon deliverables map

| Requirement | Where |
|---|---|
| `main.py` multi-agent pipeline | root |
| System prompts (Agents 2 & 4) | `prompts/` |
| `index.html` 3D dashboard | `static/index.html` |
| Extended science widgets (4) | `static/index.html` + `agents/datasets.py` |
| Execution instructions | this file + `START.bat` |
| Astropy / scikit-learn / pandas / numpy / requests | `requirements.txt` |
| NASA + Gemini + NOAA integration | `agents/agent1..4`, `agents/datasets.py` |


---

## 10. MORS Scientific Command Center (primary UI)

Open **http://127.0.0.1:5000/mors** while the server is running.
`static/mors.html` is a dependency-light single-page app (one inline script,
Chart.js from jsDelivr) served by the same Flask process — no build step.

### 10.1 Sections

| Sidebar item | Backed by |
|---|---|
| MORS Home | `GET /api/mors/home` |
| AI.MORS | `GET /api/mors/ai` |
| DATA.MORS | `GET /api/mors/datahealth` (+ report metrics) |
| ASTRONOMY.MORS | `objects, exoplanets, fits, photometry, spectroscopy, lightcurves, images` |
| SATELLITE.MORS | `GET /api/mors/satellite` |
| QUANTUM.MORS | `GET /api/mors/quantum` |
| Problems → Solutions | `GET /api/mors/problems` |
| Solutions Center | `GET /api/mors/solutions` |
| PROJECTS.MORS | `GET /api/mors/projects` |
| SOURCES.MORS | `GET /api/mors/sources` |
| TEAM.MORS | `GET /api/mors/team` |

Module index: `GET /api/mors`. Contract: `docs/API_CONTRACT.md` §15–20.

### 10.2 Theme engine — "Customize MORS"

The drawer in the top bar exposes 8 themes (Dark, Light, Planet + Earth,
Mars, Jupiter, Saturn, Neptune, Moon), 6 accent colours, density / compact
grid, particles, motion, high contrast, larger type and a background grid.
Choices are written to `localStorage` under **`mors.settings.v1`** and
re-applied on load. The planet themes shift hue only — layout and hierarchy
never change, and no theme uses neon or decorative clutter.

### 10.3 Data-health bar

Six tiles pinned under the top bar: **Data quality · Missing · Duplicates ·
Completeness · Accuracy · Last updated**, plus `quality NN/100` and
`N open problems` pills. All figures come from
`GET /api/mors/datahealth`, which is empty until the pipeline has run once —
start the server and `POST /api/pipeline/run` (or run `--selftest` first)
so the bar has real numbers.

### 10.4 Mandatory conventions

- **Problem schema (9 fields):** Problem, Evidence, Impact, Root Cause,
  Analysis, Solution, Suggestions, Confidence Level (with its algorithmic
  caveat), Priority. Priority is metric-derived:
  `0.40·evidence + 0.35·impact + 0.25·confidence`.
- **Traceability badge:** `[Source | Dataset Version | Processing Pipeline |
  Method | Last Updated | Operator | Timestamp]` — rendered from `trace` on
  every module and next to every chart.
- **5-tier AI protocol:** Observed Data · Calculated Metric · AI
  Interpretation · Hypothesis · Suggested Action. AI never invents a
  measurement.
- **Acquisition order:** real API → Gemini synthesis → deterministic local
  model, surfaced in `source.via` as `api` / `ai_synthesis` / `local_model`.

### 10.5 Regenerating the PDF documents

```powershell
python main.py                  # leave a server running
python tools\audit_data.py      # confirm the data layer -> AUDIT: PASS
python tools\build_report.py    # writes docs\MORS_REPORT.pdf
python tools\build_guide.py     # writes docs\PROJECT_GUIDE.pdf
python tools\build_committee.py # writes 00_COMMITTEE_GUIDE.md + docs\COMMITTEE_GUIDE.pdf
python tools\build_zip.py       # writes 00_MANIFEST.txt + the submission zip
```

Requires the optional PDF stack from `requirements.txt`:
`reportlab`, `arabic-reshaper`, `python-bidi` (Arabic in the source section)
and `matplotlib` (the figures). `build_report.py` pulls every figure from the
live API so it always matches the dashboard; `build_guide.py` scans the
working tree so it always matches the files on disk.

### 10.6 MORS-specific troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Health bar shows 0 / "awaiting pipeline" | No certified report yet | `POST /api/pipeline/run`, then reload `/mors` |
| Satellite module says `local model`, 10 rows | CelesTrak **and** the TLE mirror unreachable | Wait 60 s and reload; `source.via` tells you which path ran (`api` uses `https://tle.ivanstanojevic.me/api/tle/`) |
| `quality 0` in the top pill after a fresh clone | `dataset_summary.quality` empty | Re-run the pipeline (`quality` is only written by Agent 1) |
| Charts blank on `/mors` | Chart.js CDN blocked | Allow `cdn.jsdelivr.net` (CSP also permits `unpkg.com`) |
| `GET /api/mors/data` returns 404 | Not a module — DATA.MORS is a composite view | Use `/api/mors/datahealth` |
| Report PDF is empty | Server down, no report | Start `main.py` and run the pipeline first |

---

## 11. Deliverables addendum (MORS)

| Requirement | Where |
|---|---|
| MORS command-center UI | `static/mors.html` |
| MORS data layer (19 API modules, API → AI → local) | `agents/mors_data.py` |
| `/mors`, `/api/mors/*`, `/api/mors/insight` | `main.py` |
| Scientific source registry + 8 hackathon conditions | `agents/sources_data.py` → `GET /api/mors/sources` → `SOURCES.MORS` |
| Ai.Mors clarified (greeting, numbered steps, live chat, engine ladder) | `static/mors.html` → `AI.MORS` + `POST /api/chat` |
| Data & analysis audit (224 read-only checks, 223–227 as cards activate) | `tools/audit_data.py` → `RESULT: AUDIT: PASS` |
| Problems solved — data/analysis defect log (Arabic) | `المشكلات_التي_تم_حلها.md` |
| Platform report (PDF) with figures and the sources section | `docs/MORS_REPORT.pdf` via `tools/build_report.py` |
| File-by-file project guide (PDF) | `docs/PROJECT_GUIDE.pdf` via `tools/build_guide.py` |
| Judging-committee guide (Arabic MD + PDF) | `00_COMMITTEE_GUIDE.md` + `docs/COMMITTEE_GUIDE.pdf` via `tools/build_committee.py` |
| Package manifest (size + SHA-256 per file) | `00_MANIFEST.txt` via `tools/build_zip.py` |
| Run instructions | `README.md` + this file + `START.bat` |
| API contract incl. MORS | `docs/API_CONTRACT.md` §15–20 |
| Pitch deck, 10 slides (PPTX + PDF) | `presentation/MORS_ASI-HACK-2026_Deck.pptx` / `.pdf` via `tools/build_deck.py` |
| Pitch video, Arabic voiceover | `presentation/MORS_Pitch_2min.mp4` via `tools/build_video.py` (edge-tts `ar-SA-HamedNeural` + ffmpeg) |
| Launcher cards for deck + video | root `index.html` (site front door) |