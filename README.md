# MORS — Scientific Command Center
### ASI-HACK Space Analytics Engine

A four-agent scientific pipeline (**ingest → council → citations → Ai.Mors**) plus a
command-center UI that turns NASA / NOAA / CelesTrak / Exoplanet-Archive feeds into
**provenance-labelled** findings, problem cards, solution paths and charts — with an
honest fallback layer so the site also works as a pure static page.

**Live demo:** <https://laythraad.github.io/ASI-HACK-Space-Analytics-Engine/>
— a launcher page with both UIs, the deck, the pitch video and the generated PDFs.

---

## 1. Run locally

### Option A — static site (no backend, mirrors the live demo exactly)

```bash
git clone https://github.com/laythraad/ASI-HACK-Space-Analytics-Engine.git
cd ASI-HACK-Space-Analytics-Engine && python3 -m http.server 8000
```

Open <http://localhost:8000/> — you get the launcher with both dashboards at
`/static/index.html` and `/static/mors.html`, byte-identical to GitHub Pages.
The two commands are also copyable from the UI via the **⌘ Run Locally** button
(root launcher, dashboard header, and the MORS sidebar footer).

Static mode serves everything from the committed JSON snapshot in `static/api/`
(regenerate with `python tools/build_static_api.py`); chat, insights and
**Run Pipeline** keep working offline through `static/offline_assistant.js`,
which labels itself `static:snapshot` and shows the
`[MORS OFFLINE SIMULATION MODE]` badge.

### Option B — full backend (live Gemini, live NASA, real pipeline)

```bash
# from the project folder
python -m pip install -r requirements.txt
python main.py                 # http://127.0.0.1:5000
```

Windows one-click: double-click **`START.bat`** (finds Python, installs missing
packages, frees port 5000, starts the server, opens the browser).

| URL | What it is |
|---|---|
| <http://127.0.0.1:5000/> | legacy ASI-HACK dashboard |
| <http://127.0.0.1:5000/mors> | **MORS Scientific Command Center** (main UI) |

### Option C — verify without a server

```bash
python main.py --selftest
```

Runs the entire four-agent pipeline synchronously and prints
`SELFTEST : PASS ✅` (roughly 75 s) or a failure diagnosis, then exits.

### Option D — audit the data & analysis layer

```bash
python main.py                 # leave the server running
python tools\audit_data.py     # -> RESULT: AUDIT: PASS
```

Read-only battery of **224 checks** (223–227 as problem cards activate):
priority-formula math, Kepler period/velocity consistency, habitability-gate
reproduction, CME-vs-FLR counting, per-body Horizons radii, quantum
normalisation and unit conversions, spectral PCA, light-pollution direction,
the team roster, the prompt library, the leader-only name policy and the
mapping of all **8 brief conditions** onto their 16 sources. Nothing is
written; the run exits `0` only when every check passes. Every defect this
audit caught is documented, before → after, in **`المشكلات_التي_تم_حلها.md`**.

### Useful flags & configuration

| Command | Effect |
|---|---|
| `python main.py` | start the Flask server on `127.0.0.1:5000` |
| `python main.py --selftest` | synchronous end-to-end test, no server |
| `python main.py --port 8080` | serve on another port |
| `python main.py --host 0.0.0.0` | expose on the LAN (see §8 security) |

Environment variables are read from **`.env`** in the project root
(`GEMINI_API_KEY`, `NASA_API_KEY`, `GEMINI_MODEL_*`, `FLASK_HOST`, `FLASK_PORT`,
`FLASK_DEBUG`). Never commit `.env`.

### Requirements

Python **3.11+** (tested on 3.12) on Windows / macOS / Linux. Network access is
*optional* — every source has a local deterministic fallback. Browser: any
modern Chromium/Firefox, responsive down to mobile.

```bash
python -m pip install -r requirements.txt
```

`requirements.txt` covers `flask`, `pandas`, `numpy`, `requests`,
`scikit-learn`, `astropy`, `google-generativeai`, `python-dotenv`; optional
PDF tooling (`reportlab`, `arabic-reshaper`, `python-bidi`, `matplotlib`) is
listed at the bottom.

---

## 2. Architecture & mission

**Mission:** give the judging committee one surface where raw space-data feeds
become *traceable* decisions — every figure carries
`[Source | Dataset Version | Processing Pipeline | Method | Last Updated | Operator | Timestamp]`
and every AI statement carries its evidence tier.

```
Agent 1  Ingestion     NASA DONKI / NEOWS / JPL Horizons / ./data → clean frame + QC
   ↓
Agent 2  Council       5 expert personas (Gemini) → verdict, score, log
   ↓
Agent 3  Citations     formula + reference enrichment → traceability records
   ↓
Agent 4  Ai.Mors       conversational face: Arabic greeting, numbered steps,
                       5-tier protocol, Traceability IDs
   ↓
UI layer               /static/mors.html (SPA, 11 sections)
                       /static/index.html (analytics charts)
                       / (launcher: dashboards + PDFs + video)
```

**Fallback chain (why static hosting works):** every frontend call goes
`live /api/... → static/api/<name>.json snapshot → static/offline_assistant.js`
— the snapshot is generated from a certified run, and each degraded step is
*labelled in the UI* (snapshot banner, `[MORS OFFLINE SIMULATION MODE]` badge,
`static:snapshot` engine tag, `local_fallback` chips). Nothing silently pretends
to be live.

---

## 3. What the UI gives you

**Sidebar sections (11):** MORS Home · AI.MORS · DATA.MORS · ASTRONOMY.MORS ·
SATELLITE.MORS · QUANTUM.MORS · Problems → Solutions · Solutions Center ·
PROJECTS.MORS · SOURCES.MORS · TEAM.MORS. Every section maps 1:1 to a
`GET /api/mors/<name>` payload (19 modules registered in that index).

* **SATELLITE.MORS** — satellite registry, pass-window estimates
  (`estimate=true`, period-derived, not TLE propagation), ground-track canvases.
* **ASTRONOMY.MORS** — deep-sky object browser, exoplanet and FITS/photometry
  views, animated sky map.
* **QUANTUM.MORS** — state library with Bloch sphere, Rabi oscillation and
  entanglement views driven by a **local NumPy statevector simulator** (no QPU
  is contacted — see §10).
* **Problems → Solutions** — problem cards with the mandatory schema
  *Problem · Evidence · Impact · Root Cause · Analysis · Solution ·
  Suggestions · Confidence Level · Priority*, priority derived as
  `0.40·evidence + 0.35·impact + 0.25·confidence`, each card linked to its
  solution path.
* **Customize MORS** drawer — 8 colour themes (Dark, Light, Planet + Earth/
  Mars/Jupiter/Saturn/Neptune/Moon), 6 accents, density, contrast, particles,
  type size; persisted in `localStorage` (`mors.settings.v1`), with
  WCAG-checked contrast pairs and reduced-motion support.
* **Data-health bar** — quality, missing %, duplicates, completeness, accuracy
  and last sync, measured cell-by-cell.
* **Traceability badge** on every figure; **5-tier AI protocol** —
  *Observed Data · Calculated Metric · AI Interpretation · Hypothesis ·
  Suggested Action* — AI never invents a measurement.
* Charts (Chart.js), collapsible/responsive chat, full-screen search
  (`Ctrl/⌘ + K`), record modals, hash router, run-locally modal.

---

## 4. Integrations (honest table)

| Source / service | Used for | Live backend | Static (Pages) |
|---|---|---|---|
| NASA **DONKI** | CME / FLR / SEP events | live fetch | snapshot in `static/api/` |
| NASA **NEOWS** | near-Earth objects | live fetch | snapshot |
| NASA **GIBS** / APOD | imagery references | live fetch | snapshot |
| NASA **Exoplanet Archive** | exoplanet table | live fetch | snapshot |
| NASA **JPL Horizons** | per-body orbital radii | live fetch | snapshot |
| **NOAA SWPC** Kp index | geomagnetic activity | live fetch | snapshot |
| **CelesTrak** | satellite TLE registry | live fetch | snapshot |
| **Google Gemini** (`gemini:3.1-pro` ladder) | Agents 2/3/4 + chat | live (needs `GEMINI_API_KEY`) | deterministic local answers (`static:snapshot`) |
| **Local quantum simulator** (NumPy statevector) | Bloch / Rabi / entanglement | always local | always local |
| Chart.js, three.js (CDN) | charts, 3-D scene | cached by browser | cached by browser |

Without keys every provider degrades to its deterministic local fallback —
surfaced as an open problem card (**P-001**, only present while the condition
is live) on the dashboard rather than hidden.

---

## 5. Tech stack

* **Backend:** Python 3.11+, Flask, pandas / NumPy, scikit-learn, astropy,
  `google-generativeai`.
* **Frontend:** vanilla ES2020 single-file SPAs (`static/mors.html`,
  `static/index.html`) — no build step, no framework, no bundler; Chart.js for
  charts, three.js for the hero scene, hand-drawn canvases for sky map /
  ground track / Bloch sphere.
* **Data:** `tools/build_static_api.py` snapshots the certified API into
  `static/api/*.json`; `static/offline_assistant.js` provides offline chat.
* **Docs:** `tools/build_report.py`, `build_guide.py`, `build_committee.py`,
  `build_deck.py`, `build_video.py` regenerate the PDFs, deck and pitch video.
* **Hosting:** GitHub Pages for the static site; the same tree runs the full
  backend anywhere Python runs (`render.yaml` kept as an optional blueprint).

---

## 6. API

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

## 7. Project layout

```
00_COMMITTEE_GUIDE.md    judging-committee guide (Arabic, plain text)
00_MANIFEST.txt          size + SHA-256 of every packaged file
المشكلات_التي_تم_حلها.md  problems solved — data/analysis defects, before → after
index.html               launcher (dashboards + PDFs + video + run-locally modal)
main.py                  orchestrator + Flask API + CLI (--selftest / --port / --host)
agents/
  agent1_ingestion.py    NASA DONKI, NEOWS, JPL Horizons, ./data + cleaning, QC, quality audit
  agent2_council.py      Council of 5 experts (Gemini) → verdict, score, log
  agent3_citations.py    formula + reference enrichment, traceability records
  agent4_aimors.py       Ai.Mors conversational agent (Arabic greeting, numbered steps)
  datasets.py            science dataset builders reused by the MORS layer
  mors_data.py           MORS data layer — 19 API modules, API → AI → local acquisition
  sources_data.py        scientific source registry + the 8 hackathon conditions
static/
  index.html             analytics dashboard (charts, chat, offline hardening)
  mors.html              MORS Scientific Command Center (SPA, incl. SOURCES.MORS)
  api/*.json             certified snapshot served on GitHub Pages
  offline_assistant.js   offline chat / insight / pipeline engine (static:snapshot)
tools/
  audit_data.py          read-only data & analysis audit (224 checks -> AUDIT: PASS)
  build_static_api.py    regenerates static/api/*.json from a live run
  build_report.py        generates docs/MORS_REPORT.pdf (figures + sources section)
  build_guide.py         generates docs/PROJECT_GUIDE.pdf (file-by-file guide)
  build_committee.py     generates 00_COMMITTEE_GUIDE.md + docs/COMMITTEE_GUIDE.pdf
docs/
  API_CONTRACT.md        request/response contract for every endpoint
  MORS_REPORT.pdf        generated platform report (see §9)
  PROJECT_GUIDE.pdf      generated file-by-file project guide (see §9)
  COMMITTEE_GUIDE.pdf    printable Arabic edition of the committee guide
presentation/
  MORS_ASI-HACK-2026_Deck.pptx / .pdf  10-slide pitch deck (16:9)
  MORS_Pitch_2min.mp4    pitch video (Arabic voiceover, edge-tts + ffmpeg)
  frames/                1920x1080 UI captures used by both builders
prompts/                 prompt templates used by the agents
data/                    reference CSVs (light pollution, spectra, Kp, metrics)
DEPLOYMENT.md            deployment & operations guide
START.bat                one-click Windows launcher
render.yaml              optional Render blueprint (full backend, needs a card)
requirements.txt
```

---

## 7.1 Screens (live)

* <https://laythraad.github.io/ASI-HACK-Space-Analytics-Engine/> — launcher
* <https://laythraad.github.io/ASI-HACK-Space-Analytics-Engine/static/mors.html>
* <https://laythraad.github.io/ASI-HACK-Space-Analytics-Engine/static/index.html>

---

## 8. Security notes

* `FLASK_DEBUG` defaults to **off** and is forcibly disabled on non-loopback
  hosts — the Werkzeug debugger is a remote-code-execution surface.
* Bind to `127.0.0.1` unless you intend to share the server.
* Keep `.env` out of version control (`.gitignore` already excludes it) and
  rotate any key that has been posted publicly.
* The static site ships **no secrets**: keys only ever exist in a local `.env`
  on a machine you control; GitHub Pages receives only the certified snapshot.

---

## 9. Regenerating the documents

```powershell
python main.py                  # keep a server running so the pipeline has a report
# then, from a second shell:
python tools\audit_data.py      # confirm the data layer first -> AUDIT: PASS
python tools\build_report.py    # writes docs\MORS_REPORT.pdf
python tools\build_guide.py     # writes docs\PROJECT_GUIDE.pdf
python tools\build_committee.py # writes 00_COMMITTEE_GUIDE.md + docs\COMMITTEE_GUIDE.pdf
python tools\build_deck.py      # writes presentation\MORS_ASI-HACK-2026_Deck.pptx (+ .pdf/.png via PowerPoint)
python tools\build_video.py     # writes presentation\MORS_Pitch_2min.mp4 (edge-tts ar-SA + ffmpeg)
```

The report pulls live figures from `/api/report` and `/api/mors/*`, so it
always matches the numbers shown in the UI. The guide scans the working tree,
so it always matches the files on disk. Both need the optional PDF stack at
the bottom of `requirements.txt`.

---

## 10. Honest limitations

* Gemini free-tier quota (HTTP 429) degrades Agents 2/3/4 to the
  deterministic **local fallback** engines; the report still certifies but is
  *not* LLM cross-verified — surfaced as an open problem card (**P-001**
  while that condition holds).
* On GitHub Pages (no backend) everything runs from the snapshot: answers are
  canned-but-labelled, the pipeline is simulated stage-by-stage, and the badge
  `[MORS OFFLINE SIMULATION MODE]` is shown.
* Satellite pass windows are period-derived estimates, not TLE propagations
  (`estimate=true`).
* Quantum results are classical NumPy statevector simulations — no QPU is
  contacted.
* Reference multi-spectral profiles are spectra, not imagery.
* Chart.js / three.js / fonts load from CDNs (jsDelivr / unpkg / Google
  Fonts); the rest of the site degrades gracefully offline.

---

## 11. License / credits

Source code is released under the [MIT License](LICENSE) (third-party data
terms apply — see the note inside the LICENSE file).

Built for the **ASI Hack — AI for Space Challenges** track.
Data: NASA (DONKI, NEOWS, Horizons, GIBS, APOD, Exoplanet Archive), NOAA SWPC,
CelesTrak — terms of each provider apply. Team: ليث رعد (Team Leader) ·
Data Analyst · Astronomy Researcher · Space Systems & AI Engineer.
