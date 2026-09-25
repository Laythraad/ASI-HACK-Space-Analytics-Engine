#!/usr/bin/env python3
"""Build docs/PROJECT_GUIDE.pdf — a file-by-file map of this repository.

Usage:
    python tools/build_guide.py          # writes docs/PROJECT_GUIDE.pdf
    MORS_OUT=... python tools/build_guide.py

The guide answers three questions for every file in the project:
    what is it, what does it do, and who depends on it.
"""
from __future__ import annotations

import ast
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # pragma: no cover
    pass

import build_report as br  # noqa: E402  (tools/ is sys.path[0] when run directly)
from reportlab.lib import colors  # noqa: E402
from reportlab.lib.enums import TA_LEFT  # noqa: E402
from reportlab.lib.units import mm  # noqa: E402
from reportlab.platypus import (HRFlowable, KeepTogether, PageBreak,  # noqa: E402
                                Paragraph, Spacer)

OUT = Path(os.getenv("GUIDE_OUT", str(ROOT / "docs" / "PROJECT_GUIDE.pdf")))

P, R, S = br.P, br.R, br.S
table, kpis, bullets = br.table, br.kpis, br.bullets
san, badge_line = br.san, br.badge_line
ACCENT, RULE, MUTED = br.ACCENT, br.RULE, br.MUTED

SKIP_DIRS = {"__pycache__", ".git", "node_modules", ".pytest_cache", ".venv",
             "venv"}

# ---------------------------------------------------------------------------
# Curated description of every shipped file.
#   role  - one line, used in the index table
#   what  - what the file actually does
#   io    - what it reads / writes
#   deps  - what it depends on, and what depends on it
#   where - where the reader sees its effect
# ---------------------------------------------------------------------------
FILES = {
    "main.py": {
        "role": "Flask orchestrator, HTTP API and CLI entry point",
        "what": [
            "Builds the Flask application: loads .env, constructs the four "
            "agents, runs the pipeline when asked and serves every endpoint "
            "the two front ends call.",
            "Legacy ASI-HACK surface: GET /, GET /api/report, GET "
            "/api/data/<name> (space-weather, neo, horizons, neo-matrix, "
            "light-pollution, kp-index, spectral, quantum), POST "
            "/api/pipeline/run, GET /api/pipeline/status, GET /api/health.",
            "MORS surface: GET /mors serves the SPA, GET /api/mors lists the "
            "module registry, GET /api/mors/<name> dispatches into "
            "agents/mors_data.py, POST /api/mors/insight answers a grounded "
            "question, POST /api/chat runs Agent 4 (Ai.Mors).",
            "CLI: --selftest runs the whole pipeline offline and prints "
            "SELFTEST : PASS; --host/--port override the bind address.",
        ],
        "io": "reads .env, prompts/*.txt, last_report.json; writes HTTP JSON "
              "responses and the in-memory STATE report.",
        "deps": "imports all four agents, agents.datasets, agents.mors_data "
                "and agents.sources_data; started by START.bat; called by "
                "tools/build_report.py, tools/build_guide.py and both HTML "
                "front ends.",
        "where": "the address bar of both dashboards and every API call "
                 "listed in docs/API_CONTRACT.md.",
    },
    "START.bat": {
        "role": "Windows launcher with environment checks",
        "what": [
            "Checks that python is on PATH, that .env exists and that the "
            "required packages import; frees the port if a previous instance "
            "is still bound; then starts main.py and opens the browser.",
            "Written with `for /f \"tokens=5\"` to read the PID portably and "
            "saved with CRLF line endings so cmd.exe parses it correctly.",
        ],
        "io": "reads requirements.txt and .env; spawns a python process.",
        "deps": "invoked by a double-click; not used by the selftest.",
        "where": "the project root — the fastest way to run option 1.",
    },
    "requirements.txt": {
        "role": "Python dependency list",
        "what": ["Pins the runtime libraries (google-generativeai, astropy, "
                 "scikit-learn, pandas, numpy, requests, flask, "
                 "python-dotenv) and lists the optional PDF stack "
                 "(reportlab, arabic-reshaper, python-bidi, matplotlib)."],
        "io": "read by pip; read by START.bat.",
        "deps": "required by every Python file in the project.",
        "where": "README.md step 0 and START.bat preflight.",
    },
    "README.md": {
        "role": "Front door: how to run, what it does, what it does not do",
        "what": ["Requirements, three run options (START.bat, manual, "
                 "--selftest), the UI feature list, the API table, security "
                 "notes, the project layout, how to regenerate the report, "
                 "and an honest limitations section."],
        "io": "read by humans and by anyone evaluating the submission.",
        "deps": "documents main.py, both HTML files and the docs folder.",
        "where": "the first file a reviewer opens.",
    },
    "DEPLOYMENT.md": {
        "role": "Operations and deliverables manual",
        "what": ["Environment variables, ports, the pipeline lifecycle, "
                 "troubleshooting, the MORS UI section map, the theme "
                 "engine, mandatory problem/AI conventions, how to "
                 "regenerate both PDFs, and the deliverables checklist."],
        "io": "read by an operator bringing the service up on another host.",
        "deps": "references main.py routes and the docs folder.",
        "where": "the second document a reviewer opens.",
    },
    ".env": {
        "role": "Secrets — never committed",
        "what": ["Holds GEMINI_API_KEY, NASA_API_KEY and the model names. "
                 "Loaded by python-dotenv at import time in main.py."],
        "io": "read only; excluded by .gitignore.",
        "deps": "required by Agents 2, 3 and 4 and by every NASA fetch in "
                "Agent 1.",
        "where": "never rendered anywhere — the UI only shows the engine "
                 "name, never the key.",
    },
    ".gitignore": {
        "role": "Keeps secrets and runtime artifacts out of the repository",
        "what": ["Ignores .env, last_report.json, __pycache__/, *.pyc, "
                 "*.log, virtualenvs and node_modules."],
        "io": "read by git.",
        "deps": "protects .env and last_report.json.",
        "where": "invisible at runtime.",
    },
    "last_report.json": {
        "role": "Persisted copy of the most recent pipeline report",
        "what": ["Written after a successful pipeline run and read back when "
                 "the process restarts, so /api/chat and "
                 "tools/build_report.py still have a certified report to "
                 "quote before the pipeline is re-run."],
        "io": "written by main.py; read by main.py and tools/build_report.py.",
        "deps": "produced by Agent 2 + Agent 3 output.",
        "where": "the health bar and the report PDF both fall back to it.",
    },
    "ASI-HACK-Space-Analytics-Engine.zip": {
        "role": "Submission archive",
        "what": ["The deliverable handed in: source, static assets, docs, "
                 "prompts, data and reports — rebuilt by the zip builder "
                 "after every change and verified by extracting it and "
                 "running `python main.py --selftest` on the copy."],
        "io": "written by the packaging step; read by the evaluator.",
        "deps": "must contain every file this guide describes except "
                "secrets and caches.",
        "where": "the submission portal.",
    },

    # ---------------------------------------------------------------- agents
    "agents/__init__.py": {
        "role": "Package façade for the four agents",
        "what": ["Re-exports IngestionAgent, CouncilAgent, CitationAgent and "
                 "AiMorsAgent so main.py can import all of them from one "
                 "place."],
        "io": "none.",
        "deps": "imported by main.py.",
        "where": "invisible — it is only a convenience module.",
    },
    "agents/agent1_ingestion.py": {
        "role": "Agent 1 — Ingest & Clean",
        "what": [
            "Fetches NASA DONKI (CME + flares), NASA NEOWS (near-Earth "
            "objects), JPL Horizons (heliocentric vectors), NASA GIBS "
            "night-light tiles and the NOAA SWPC planetary K-index, plus the "
            "three local reference CSVs.",
            "Cleans and types every column, flags duplicates, and runs the "
            "cell-level quality audit: completeness, accuracy, outlier count "
            "(StandardScaler + IsolationForest, contamination=0.1) and a "
            "single 0-100 data-quality score.",
            "Applies astropy Time/SkyCoord transforms to the Horizons vectors "
            "and a 3-sample moving average to the Kp series.",
        ],
        "io": "reads .env (NASA key) and data/*.csv; writes a rows/sources "
              "record into the in-memory report.",
        "deps": "calls agents.datasets; called by main.py run_pipeline(); "
                "its quality dict is what DATA.MORS and the health bar show.",
        "where": "the four science widgets on the legacy dashboard, "
                 "DATA.MORS, and section 3 of the report.",
    },
    "agents/agent2_council.py": {
        "role": "Agent 2 — Council of Five",
        "what": [
            "Runs a five-expert verification pass over the ingested dataset "
            "(data, science, engineering, QA, reproducibility) and turns "
            "their scores into one verdict with an overall score.",
            "Calls Gemini when quota allows and otherwise falls back to the "
            "deterministic local council; whichever engine answered is "
            "recorded as council.engine and printed in the header pill.",
        ],
        "io": "reads prompts/council_prompt.txt and the Agent 1 record; "
              "writes council + metrics into the report.",
        "deps": "depends on Agent 1; read by Agent 3, Agent 4, both UIs and "
                "the report cover.",
        "where": "the verdict badge on both dashboards and the cover page of "
                 "MORS_REPORT.pdf.",
    },
    "agents/agent3_citations.py": {
        "role": "Agent 3 — Citations & traceability",
        "what": [
            "Builds the TRC-### traceability ids, the citation list and the "
            "provenance graph that links every figure back to a NASA/NOAA "
            "endpoint and a processing step.",
            "Runs Gemini citation enrichment when quota allows and degrades "
            "to the deterministic baseline otherwise.",
        ],
        "io": "reads the Agent 1 + Agent 2 records; writes citations into "
              "the report.",
        "deps": "depends on Agents 1 and 2; consumed by Agent 4 (it quotes "
                "the trace ids) and by section 11 of the report.",
        "where": "the [TRACE] badges everywhere and the citations panel on "
                 "AI.MORS.",
    },
    "agents/agent4_aimors.py": {
        "role": "Agent 4 — Ai.Mors conversational agent",
        "what": [
            "Answers free-text questions about the certified report. It has a "
            "hard constraint: the reply must open with "
            "\u0623\u0647\u0644\u0627\u064b \u0648\u0633\u0647\u0644\u0627\u064b "
            "\u0628\u0643\u0645 \u0641\u064a \u0627\u0644\u0641\u0636\u0627\u0621 "
            "— if the model omits it the agent prepends it.",
            "Engine ladder: gemini:3.1-pro -> gemini:3.6-flash -> "
            "gemini-flash-latest -> deterministic offline template. The rung "
            "that answered is echoed back in the `engine` field.",
            "The offline template answers in numbered Arabic steps with the "
            "trace ids, so the UI is never empty even with no quota.",
        ],
        "io": "reads prompts/aimors_prompt.txt, the report and the chat "
              "history; returns reply/greeting_ok/trace/engine/timestamp.",
        "deps": "instantiated per request by POST /api/chat in main.py; used "
                "by the legacy chat card and the AI.MORS chat box.",
        "where": "the Ai.Mors chat card on index.html and the 'Ask Ai.Mors "
                 "directly' box on AI.MORS.",
    },
    "agents/datasets.py": {
        "role": "Dataset builders for the science widgets",
        "what": [
            "Produces the light-pollution / sky-brightness model from NASA "
            "GIBS VIIRS and Black-Marble tiles, the spectral reference "
            "matrix, the reference metrics table and the Kp + flare series.",
            "Every builder records where the numbers came from and whether "
            "they are observed, calculated or modelled.",
        ],
        "io": "reads data/*.csv; calls NASA GIBS and NOAA SWPC.",
        "deps": "used by Agent 1 and by the light-pollution / spectral "
                "endpoints in main.py.",
        "where": "the legacy dashboard charts and PROJECT PRJ-002.",
    },
    "agents/mors_data.py": {
        "role": "MORS data layer — the 17 science modules",
        "what": [
            "One module per MORS view: data_health, problems, solutions, "
            "home, photometry, spectroscopy, lightcurves, images, "
            "exoplanets, objects, fits_headers, satellites, quantum_lab, "
            "ai_workspace, projects, team, modules_catalog and ai_insight.",
            "Implements the acquisition policy every module obeys: live API "
            "first, Gemini synthesis second, deterministic local model last, "
            "with the chosen rung recorded in trace.via.",
            "Owns the trace()/badge() helpers that stamp "
            "[Source | Version | Pipeline | Method | Updated | Operator] on "
            "every payload, and a 300 s TTL cache.",
        ],
        "io": "calls CelesTrak, NASA APOD, the Exoplanet Archive TAP, DONKI, "
              "NEOWS, Horizons, GIBS and NOAA; reads the report.",
        "deps": "dispatched by GET /api/mors/<name>; imported by "
                "tools/build_report.py and agents/sources_data.py.",
        "where": "every view of the MORS SPA except the legacy dashboard.",
    },
    "agents/sources_data.py": {
        "role": "Scientific source registry and hackathon condition map",
        "what": [
            "Holds the 16 official ASI Hackathon sources (phase, level, "
            "Arabic guidance, link, and the file in this repo that uses them) "
            "and the 12 live data sources this build actually calls.",
            "Holds the eight 'how do the sources help the team?' conditions, "
            "each with its Arabic wording, its supporting source ids and its "
            "evidence inside the repository.",
            "build() returns the payload served at GET /api/mors/sources.",
        ],
        "io": "static — no network access, so it renders fully offline.",
        "deps": "imported by main.py; feeds SOURCES.MORS and section 15 of "
                "MORS_REPORT.pdf.",
        "where": "the SOURCES.MORS view and section 15 of the report.",
    },

    # ---------------------------------------------------------------- static
    "static/index.html": {
        "role": "Legacy ASI-HACK dashboard (single file, no build step)",
        "what": [
            "The original submission UI: pipeline run button, four-agent "
            "stage log, science widgets for space weather, near-Earth "
            "objects, light pollution and spectra, a Three.js star field, "
            "and the Ai.Mors chat card.",
            "Self-contained: CSS, JavaScript and the import map for three.js "
            "all live inside the one file, so it works from a plain static "
            "server.",
        ],
        "io": "fetches /api/report, /api/data/*, POST /api/pipeline/run and "
              "POST /api/chat.",
        "deps": "served by GET / in main.py; shares the same API as the MORS "
                "SPA.",
        "where": "http://127.0.0.1:5000/",
    },
    "static/mors.html": {
        "role": "MORS Scientific Command Center SPA",
        "what": [
            "A single-page application with a sidebar router: MORS Home, "
            "AI.MORS, DATA.MORS, ASTRONOMY / SATELLITE / QUANTUM, "
            "Problems -> Solutions, Solutions Center, PROJECTS, SOURCES and "
            "TEAM.",
            "Chart.js visualisations, a global search index over every "
            "payload, theme engine (dark/light + six planet accents) stored "
            "in localStorage under mors.settings.v1, and a health bar that "
            "re-reads data health on every view.",
            "The SOURCES view renders the 16 official sources with their "
            "Arabic guidance and the eight-condition compliance matrix; the "
            "AI view explains who Ai.Mors is and offers a live chat box.",
        ],
        "io": "fetches /api/mors/<name> for every view plus /api/chat and "
              "/api/mors/insight.",
        "deps": "served by GET /mors in main.py; Chart.js comes from "
                "cdn.jsdelivr.net (allowed by the CSP).",
        "where": "http://127.0.0.1:5000/mors",
    },

    # ----------------------------------------------------------------- tools
    "tools/build_report.py": {
        "role": "Generates docs/MORS_REPORT.pdf",
        "what": [
            "Fetches every module from the running server (or falls back to "
            "last_report.json), sanitises text for reportlab, and lays out a "
            "16-section dossier: cover, contents, executive summary, "
            "architecture, data-health audit, problem cards, solutions, "
            "module registry, dataset inventory, research dossiers, team, "
            "AI protocol, traceability, API reference, run instructions, "
            "figures, scientific sources and honest limitations.",
            "Arabic support: arabic_reshaper + python-bidi + Arial, wrapped "
            "word by word so reportlab never re-wraps a pre-reversed line.",
            "Chart helpers (matplotlib, Agg) render the six figures used in "
            "section 14 and 15 as PNGs embedded in the PDF.",
        ],
        "io": "reads the live API or last_report.json; writes "
              "docs/MORS_REPORT.pdf.",
        "deps": "needs reportlab (+ optional arabic-reshaper, python-bidi, "
                "matplotlib); imported by tools/build_guide.py for its "
                "shared styles.",
        "where": "docs/MORS_REPORT.pdf",
    },
    "tools/build_guide.py": {
        "role": "Generates this document (docs/PROJECT_GUIDE.pdf)",
        "what": [
            "Walks the repository, parses each Python file with the ast "
            "module to list its top-level symbols, and prints a card for "
            "every file: role, what it does, inputs/outputs, dependencies "
            "and where the reader sees its effect.",
            "Shares styles, tables and the file-size chart with "
            "tools/build_report.py by importing it.",
        ],
        "io": "reads the working tree; writes docs/PROJECT_GUIDE.pdf.",
        "deps": "requires reportlab, arabic-reshaper, python-bidi and "
                "matplotlib.",
        "where": "docs/PROJECT_GUIDE.pdf",
    },

    # ---------------------------------------------------------------- prompts
    "prompts/council_prompt.txt": {
        "role": "System prompt for Agent 2 (Council of Five)",
        "what": ["Instructs the five experts on how to score the dataset, "
                 "what a defensible verdict looks like, and that fabricated "
                 "sources are an automatic failure."],
        "io": "read at each council call; never modified at runtime.",
        "deps": "used by agents/agent2_council.py.",
        "where": "its effect is the verdict badge on the dashboard.",
    },
    "prompts/aimors_prompt.txt": {
        "role": "System prompt for Agent 4 (Ai.Mors)",
        "what": ["Defines the persona, the numbered-step answer format, the "
                 "mandatory Arabic greeting, and the rule that answers may "
                 "only be grounded in the certified report."],
        "io": "read at each chat call.",
        "deps": "used by agents/agent4_aimors.py.",
        "where": "the replies in both chat boxes.",
    },
    "prompts/aimors_analyst_prompt.txt": {
        "role": "AI.MORS scientific space-data analyst prompt",
        "what": ["The 25-rule scientific lifecycle: data profile, quality "
                 "audit, problem discovery, evidence, root cause, solution, "
                 "verification and the no-hallucination safety rules."],
        "io": "read by the prompt library endpoint, never modified at runtime.",
        "deps": "served by GET /api/mors/prompts.",
        "where": "the Prompt library card of AI.MORS.",
    },
    "prompts/uiux_command_center_prompt.txt": {
        "role": "Frontend UI/UX & satellite command center specification",
        "what": ["Collapsible sidebar navigation, the SATELLITE.MORS "
                 "dashboard scope, the Problems -> Solutions pipeline and "
                 "the dark design system."],
        "io": "read by the prompt library endpoint.",
        "deps": "served by GET /api/mors/prompts.",
        "where": "the design scope behind static/mors.html.",
    },
    "prompts/uiux_visualization_prompt.txt": {
        "role": "Astronomical & satellite visualization lead prompt",
        "what": ["Celestial theme engine, astronomy / satellite / quantum "
                 "component specifications and the pipeline card standard."],
        "io": "read by the prompt library endpoint.",
        "deps": "served by GET /api/mors/prompts.",
        "where": "the chart and card conventions in static/mors.html.",
    },
    "prompts/cyber_mors_prompt.txt": {
        "role": "CYBER.MORS threat intelligence & sensor audit prompt",
        "what": ["CISO role, MITRE ATT&CK / NIST mapping and the structured "
                 "incident assessment format."],
        "io": "read by the prompt library endpoint.",
        "deps": "served by GET /api/mors/prompts.",
        "where": "the Prompt library card of AI.MORS.",
    },
    "prompts/report_generator_prompt.txt": {
        "role": "ANALYTICS.REPORT file analysis prompt",
        "what": ["File integrity audit methodology and the standard "
                 "technical report template."],
        "io": "read by the prompt library endpoint.",
        "deps": "served by GET /api/mors/prompts.",
        "where": "the report structure mirrored by tools/build_report.py.",
    },
    "prompts/deep_audit_prompt.txt": {
        "role": "DEEP.AUDIT five-pass audit prompt",
        "what": ["The mandatory five-pass refine protocol and the final "
                 "audit report format."],
        "io": "read by the prompt library endpoint.",
        "deps": "served by GET /api/mors/prompts.",
        "where": "the self-verification workflow of the toolchain.",
    },

    # ------------------------------------------------------------------- data
    "data/light_pollution_reference.csv": {
        "role": "Reference night-light / sky-brightness table",
        "what": ["Eleven sites with radiance, sky brightness and Bortle-class "
                 "reference values used to calibrate the light-pollution "
                 "model."],
        "io": "read by agents/datasets.py and Agent 1.",
        "deps": "feeds PRJ-002 and problem P-002.",
        "where": "the light-pollution widget and the DATA.MORS table.",
    },
    "data/reference_metrics.csv": {
        "role": "Reference metrics for the quality audit",
        "what": ["Expected ranges and units used when the ingestion layer "
                 "decides whether a cell is valid."],
        "io": "read by Agent 1 during cleaning.",
        "deps": "feeds the accuracy score.",
        "where": "the completeness / accuracy tiles.",
    },
    "data/spectral_reference.csv": {
        "role": "Laboratory emission-line list",
        "what": ["Wavelengths and intensities used to build the synthetic "
                 "spectra shown in the spectroscopy module."],
        "io": "read by agents/datasets.py.",
        "deps": "feeds the spectral widget and P-003.",
        "where": "ASTRONOMY.MORS spectroscopy and the legacy spectral chart.",
    },

    # ------------------------------------------------------------------- docs
    "docs/API_CONTRACT.md": {
        "role": "Machine-readable-ish API contract",
        "what": ["Sections 1-14 document the legacy endpoints with example "
                 "request/response bodies; sections 15-19 document the MORS "
                 "UI, every /api/mors module schema and the health bar."],
        "io": "read by a client author.",
        "deps": "mirrors main.py — keep both in sync.",
        "where": "the reference used when adding a new endpoint.",
    },
    "docs/MORS_REPORT.pdf": {
        "role": "Generated platform report (43 pages)",
        "what": ["The evidence document: quality audit, problem and solution "
                 "cards, module registry, figures with plain-English "
                 "captions, the full scientific source list and the honest "
                 "limitations."],
        "io": "written by tools/build_report.py.",
        "deps": "requires a running server (or last_report.json).",
        "where": "the submission package.",
    },
    "docs/PROJECT_GUIDE.pdf": {
        "role": "This document",
        "what": ["A file-by-file explanation of the repository so a reviewer "
                 "can find any behaviour in one lookup."],
        "io": "written by tools/build_guide.py.",
        "deps": "requires reportlab and the optional PDF stack.",
        "where": "the submission package.",
    },
    "00_COMMITTEE_GUIDE.md": {
        "role": "Submission guide for the judging committee (Markdown)",
        "what": ["Arabic walk-through of the package: what was built, how to "
                 "score it in five minutes, the eight hackathon conditions, "
                 "the sixteen scientific sources, the mandatory conventions "
                 "and the self-test evidence.",
                 "Same content as docs/COMMITTEE_GUIDE.pdf, in plain text so "
                 "it can be read without a PDF reader."],
        "io": "written by tools/build_committee.py.",
        "deps": "reads the live API; falls back to cached numbers.",
        "where": "the first file listed in the package.",
    },
    "00_MANIFEST.txt": {
        "role": "Package manifest (size + SHA-256 per file)",
        "what": ["Every file in the zip with its byte size, its SHA-256 "
                 "digest and the role it plays, so a reviewer can prove the "
                 "package was not altered in transit."],
        "io": "written by tools/build_zip.py while the archive is packed.",
        "deps": "hashes the files as they are compressed.",
        "where": "the second file listed in the package.",
    },
    "docs/COMMITTEE_GUIDE.pdf": {
        "role": "Submission guide for the judging committee (PDF)",
        "what": ["The printable Arabic edition of 00_COMMITTEE_GUIDE.md, with "
                 "tables, KPI cards and page numbers."],
        "io": "written by tools/build_committee.py.",
        "deps": "requires reportlab, arabic-reshaper and python-bidi.",
        "where": "the submission package.",
    },
    "tools/build_committee.py": {
        "role": "Generates 00_COMMITTEE_GUIDE.md and docs/COMMITTEE_GUIDE.pdf",
        "what": ["One content model rendered twice - Markdown for quick "
                 "reading, PDF for printing - so the two can never drift "
                 "apart."],
        "io": "reads the live API and the file registry; writes the two "
              "committee documents.",
        "deps": "imports tools/build_report.py for styles and the Arabic "
                "text helpers, and tools/build_guide.py for the file registry.",
        "where": "regenerate with: python tools/build_committee.py",
    },
    "tools/audit_data.py": {
        "role": "Read-only data & analysis audit (225+ checks)",
        "what": [
            "Probes the running API and prints one line per check; exits 0 "
            "only when every check passes (RESULT: AUDIT: PASS).",
            "Covers the priority formula and its 75/50 labels, Kepler period "
            "/velocity agreement, apogee/perigee integrity, CME-vs-FLR "
            "counting, habitability-gate reproduction, per-body Horizons "
            "radii, quantum normalisation and unit conversions, spectral "
            "PCA, light-pollution calibration direction and the team roster.",
            "Batch 2 added physics checks (horizons, exoplanet gates, "
            "quantum, spectral, light pollution, curves, Kp daily, images).",
        ],
        "io": "reads HTTP only; writes nothing.",
        "deps": "needs a running server (python main.py); used before every "
                "document regeneration.",
        "where": "RESULT: AUDIT: PASS on the console.",
    },
    "tools/build_zip.py": {
        "role": "Portable packager — writes the submitted archive",
        "what": [
            "Zips exactly the files the judges receive: sources, docs, "
            "datasets, prompts, the Arabic problems log and the generator "
            "scripts, skipping __pycache__, .git and virtualenvs.",
            "Resolves the repository root from __file__, so it runs from any "
            "working directory; prints entry count, raw size and zipped size.",
        ],
        "io": "reads the project tree; writes ASI-HACK-Space-Analytics-"
              "Engine.zip at the project root.",
        "deps": "stdlib zipfile only; run last, after audit_data.py and the "
                "three document builders.",
        "where": "ASI-HACK-Space-Analytics-Engine.zip and 00_MANIFEST.txt.",
    },
    "المشكلات_التي_تم_حلها.md": {
        "role": "Problems solved — data & analysis defect log (Arabic)",
        "what": [
            "Every defect found while building and auditing the engine, each "
            "with symptom, root cause (file:line), fix, before/after numbers "
            "and the audit check that now guards it.",
            "Includes the velocity unit bug, apogee/perigee zeros, the "
            "CelesTrak 403 fallback, CME/FLR counting, the habitability gate, "
            "the mixed Earth+Mars Horizons track, the cm-1 and Rabi unit "
            "errors, and the phase/period honesty fields.",
            "Ends with the four-member team roster and the commands needed "
            "to re-run the whole verification chain.",
        ],
        "io": "written by hand; referenced by README.md and DEPLOYMENT.md.",
        "deps": "quotes tools/audit_data.py check names.",
        "where": "project root, next to README.md.",
    },
}

ORDER = ["00_COMMITTEE_GUIDE.md", "00_MANIFEST.txt", "main.py", "START.bat",
         "requirements.txt", "README.md",
         "المشكلات_التي_تم_حلها.md",
         "DEPLOYMENT.md", ".env", ".gitignore", "last_report.json",
         "agents/__init__.py", "agents/agent1_ingestion.py",
         "agents/agent2_council.py", "agents/agent3_citations.py",
         "agents/agent4_aimors.py", "agents/datasets.py",
         "agents/mors_data.py", "agents/sources_data.py",
         "static/index.html", "static/mors.html",
         "tools/audit_data.py", "tools/build_report.py",
         "tools/build_guide.py",
         "tools/build_committee.py", "tools/build_zip.py",
         "prompts/council_prompt.txt", "prompts/aimors_prompt.txt",
         "data/light_pollution_reference.csv", "data/reference_metrics.csv",
         "data/spectral_reference.csv",
         "docs/API_CONTRACT.md", "docs/MORS_REPORT.pdf",
         "docs/PROJECT_GUIDE.pdf", "docs/COMMITTEE_GUIDE.pdf"]

FOLDER_BLURB = {
    "": "Entry points, secrets, packaging and the two human-readable manuals.",
    "agents/": "The four-agent pipeline plus the data layer behind MORS.",
    "static/": "The two front ends — no bundler, no framework, no build step.",
    "tools/": "The read-only data audit plus the document generators that "
              "turn the live API into PDFs.",
    "prompts/": "System prompts handed to the Gemini models.",
    "data/": "Small reference tables that keep the models honest offline.",
    "docs/": "Contract, report and this guide.",
}


# ---------------------------------------------------------------- scanning
def _read(p: Path) -> str:
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return p.read_text(encoding=enc)
        except (UnicodeDecodeError, OSError):
            continue
    return ""


def _py_symbols(text: str):
    """Top-level functions/classes with their line numbers."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return [], 0
    out = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            kind = "class" if isinstance(node, ast.ClassDef) else "def"
            out.append((kind, node.name, node.lineno))
    return out, len(text.splitlines())


def _md_headings(text: str):
    heads = []
    for line in text.splitlines():
        if line.startswith("#"):
            lvl = len(line) - len(line.lstrip("#"))
            if lvl <= 3:
                heads.append(line.lstrip("# ").strip())
    return heads


def _html_facts(text: str):
    import re as _re
    scripts = len(_re.findall(r"<script\b", text))
    styles = len(_re.findall(r"<style\b", text))
    ids = _re.findall(r'id="([A-Za-z][\w-]{2,})"', text)
    title = _re.search(r"<title>(.*?)</title>", text, _re.S)
    return {
        "scripts": scripts,
        "styles": styles,
        "ids": len(set(ids)),
        "title": (title.group(1).strip() if title else "-"),
        "lines": len(text.splitlines()),
    }


def _csv_facts(text: str):
    rows = [r for r in text.splitlines() if r.strip()]
    cols = len(rows[0].split(",")) if rows else 0
    return {"rows": max(0, len(rows) - 1), "cols": cols,
            "lines": len(text.splitlines())}


def scan():
    out = []
    for rel in ORDER:
        p = ROOT / rel
        if not p.exists():
            continue
        raw = p.read_bytes()
        text = _read(p)
        ext = p.suffix.lower() or ("(none)" if rel.startswith(".") else "")
        parent = "/".join(rel.split("/")[:-1])
        info = {"path": rel, "folder": (parent + "/" if parent else ""),
                "name": rel.split("/")[-1], "bytes": len(raw),
                "ext": ext, "symbols": [], "lines": None, "extra": None}
        if ext == ".py":
            info["symbols"], info["lines"] = _py_symbols(text)
        elif ext == ".html":
            info["extra"] = _html_facts(text)
            info["lines"] = info["extra"]["lines"]
        elif ext == ".md":
            info["extra"] = {"headings": _md_headings(text)}
            info["lines"] = len(text.splitlines())
        elif ext == ".csv":
            info["extra"] = _csv_facts(text)
            info["lines"] = info["extra"]["lines"]
        elif ext in (".bat", ".txt", ""):
            info["lines"] = len(text.splitlines())
            info["extra"] = {"chars": len(text)}
        out.append(info)
    return out


def _kind(ext: str) -> str:
    return {".py": "Python module", ".html": "Single-file web app",
            ".md": "Markdown document", ".bat": "Batch script",
            ".csv": "CSV dataset", ".json": "JSON document",
            ".txt": "Text / prompt", ".pdf": "Generated PDF",
            ".zip": "Archive", "": "Configuration",
            ".env": "Secrets"}.get(ext, ext or "file")


def _symbol_line(info) -> str:
    syms = info.get("symbols") or []
    if not syms:
        return ""
    parts = [f"{k} {n} ({ln})" for k, n, ln in syms[:14]]
    if len(syms) > 14:
        parts.append(f"... +{len(syms) - 14} more")
    return "\n".join(parts)


def _has_arabic(s) -> bool:
    return any("؀" <= ch <= "ۿ" for ch in str(s or ""))


def _path_para(rel: str):
    """Card heading. An Arabic file name needs the Arabic font, otherwise
    reportlab drops every glyph and the name comes out as '___'."""
    if _has_arabic(rel):
        st = S["ar_body"].clone("path_ar", alignment=TA_LEFT, fontName="ArB",
                                fontSize=11.5, leading=16)
        return Paragraph(br.ar(rel), st)
    return P(rel, "h3")


def card(info) -> list:
    rel, meta = info["path"], FILES.get(info["path"], {})
    role = meta.get("role", "no curated description yet")
    out = [_path_para(rel)]
    out += [table(["Role", "Kind", "Size", "Lines"],
                  [[role, _kind(info["ext"]),
                    f"{info['bytes'] / 1024:.1f} kB",
                    br._num(info.get("lines"))]],
                  [86 * mm, 34 * mm, 25 * mm, 25 * mm], zebra=False)]
    what = meta.get("what") or []
    if what:
        out += [P("What it does", "h3")] + bullets(what, "small")
    extra = info.get("extra") or {}
    if info["ext"] == ".html" and extra:
        out += [table(["Title", "script blocks", "style blocks", "element ids"],
                      [[extra.get("title", "-"), str(extra.get("scripts", 0)),
                        str(extra.get("styles", 0)), str(extra.get("ids", 0))]],
                      [76 * mm, 32 * mm, 32 * mm, 30 * mm], zebra=False)]
    elif info["ext"] == ".csv" and extra:
        out += [table(["Rows", "Columns"],
                      [[str(extra.get("rows", 0)), str(extra.get("cols", 0))]],
                      [85 * mm, 85 * mm], zebra=False)]
    elif info["ext"] == ".md" and extra.get("headings"):
        hs = extra["headings"][:14]
        out += [P("Sections", "h3")]
        if any(_has_arabic(h) for h in hs):
            out += [br.arP(h, "ar_note", width=170 * mm) for h in hs]
        else:
            out += [R(" &#183; ".join(san(h) for h in hs), "mono")]
    sym = _symbol_line(info)
    if sym:
        out += [P("Top-level symbols", "h3"),
                R(br._esc(sym).replace("\n", "<br/>"), "mono")]
    if meta.get("io"):
        out += [P("Inputs and outputs", "h3"), P(meta["io"], "small")]
    if meta.get("deps"):
        out += [P("Dependencies", "h3"), P(meta["deps"], "small")]
    if meta.get("where"):
        out += [P("Where you see it", "h3"), P(meta["where"], "small")]
    out += [Spacer(1, 3 * mm),
            HRFlowable(width="100%", thickness=0.5, color=RULE,
                       spaceAfter=3)]
    return [KeepTogether(out)]


def build() -> list:
    rows = scan()
    folders = {}
    for r in rows:
        folders.setdefault(r["folder"], []).append(r)
    total = sum(r["bytes"] for r in rows)
    py_lines = sum(r["lines"] or 0 for r in rows if r["ext"] == ".py")
    html_lines = sum(r["lines"] or 0 for r in rows if r["ext"] == ".html")

    story = []
    # ------------------------------------------------------------- cover
    story += [
        Spacer(1, 46 * mm),
        P("M O R S", "cover_kicker"),
        Spacer(1, 4 * mm),
        P("Project Guide", "cover_title"),
        P("Every file, and what it is for", "cover_sub"),
        Spacer(1, 12 * mm),
        P("ASI-HACK Space Analytics Engine  -  MORS Scientific Command "
          "Center", "cover_sub"),
        Spacer(1, 26 * mm),
        P(f"Files        {len(rows)}", "cover_meta"),
        P(f"Source       {py_lines + html_lines} lines of Python and HTML",
          "cover_meta"),
        P(f"Tree size    {total / 1024:.1f} kB", "cover_meta"),
        P(f"Generated    {br._now()}", "cover_meta"),
        br.NextPageTemplate("body"),
        PageBreak(),
    ]

    # ---------------------------------------------------------- contents
    story += [P("How to use this guide", "h1"),
              HRFlowable(width="100%", thickness=1.2, color=ACCENT,
                         spaceAfter=8),
              P("Read it top to bottom once, then keep it open next to the "
                "code. Every file gets one card with the same five blocks: "
                "role, what it does, inputs and outputs, dependencies, and "
                "where in the product you can see its effect.", "body"),
              P("Python files also list their top-level symbols with line "
                "numbers, so the card doubles as an index.", "note"),
              Spacer(1, 5 * mm),
              P("Contents", "h2")]
    toc = ["1. The repository at a glance",
           "2. How a request flows end to end"]
    n = 2
    for folder in ["", "agents/", "static/", "tools/", "prompts/", "data/",
                   "docs/"]:
        if folder in folders:
            n += 1
            toc.append(f"{n}. {folder or 'Project root'}")
    toc.append(f"{n + 1}. Regenerating the documents")
    story += [P(t, "body") for t in toc]
    story += [PageBreak()]

    # -------------------------------------------- 1 repository at a glance
    story += [P("1. The repository at a glance", "h1"),
              HRFlowable(width="100%", thickness=1.2, color=ACCENT,
                         spaceAfter=8),
              kpis([("Files", str(len(rows))),
                    ("Tree size", f"{total / 1024:.1f} kB"),
                    ("Python lines", str(py_lines)),
                    ("HTML lines", str(html_lines))])]
    fig = br.chart_files(rows)
    if fig:
        story += [Spacer(1, 4 * mm), fig,
                  P("<b>Figure 1 - Where the bytes are.</b> The two HTML "
                    "files and agents/mors_data.py dominate the tree; "
                    "everything else is comparatively small. Large is not "
                    "the same as complex - mors_data.py is one module per "
                    "science view.", "note")]
    story += [Spacer(1, 4 * mm),
              P("Folders", "h2"),
              table(["Folder", "Files", "kB", "What lives there"],
                    [[f or "project root", str(len(v)),
                      f"{sum(x['bytes'] for x in v) / 1024:.1f}",
                      FOLDER_BLURB.get(f, "")]
                     for f, v in folders.items()],
                    [34 * mm, 16 * mm, 18 * mm, 102 * mm])]

    # ---------------------------------------- 2 request flow end to end
    story += [PageBreak(),
              P("2. How a request flows end to end", "h1"),
              HRFlowable(width="100%", thickness=1.2, color=ACCENT,
                         spaceAfter=8),
              P("Two front ends, one API, four agents.", "note"),
              Spacer(1, 3 * mm)]
    story += [table(
        ["Step", "File", "What happens"],
        [["1", "static/index.html or static/mors.html",
          "The browser asks for a page and then for JSON."],
         ["2", "main.py",
          "GET /mors (or /) serves the HTML; GET /api/mors/<name> looks the "
          "module up in the _MORS dispatch table."],
         ["3", "agents/mors_data.py (or sources_data.py)",
          "The module runs its acquisition policy: live API -> Gemini -> "
          "local model, and stamps a trace badge on the payload."],
         ["4", "agents/agent1_ingestion.py",
          "On POST /api/pipeline/run: fetch, clean, audit, score."],
         ["5", "agents/agent2_council.py",
          "Five experts score the result and issue a verdict."],
         ["6", "agents/agent3_citations.py",
          "TRC ids, citations and provenance are attached."],
         ["7", "agents/agent4_aimors.py",
          "POST /api/chat turns the certified report into an answer that "
          "opens with the mandatory Arabic greeting."],
         ["8", "docs/MORS_REPORT.pdf",
          "tools/build_report.py reads the same API and freezes it into the "
          "evidence document."]],
        [12 * mm, 56 * mm, 102 * mm])]
    story += [Spacer(1, 4 * mm),
              P("Reading order for a reviewer", "h2")]
    story += bullets([
        "README.md - how to start it in one command.",
        "Problems solved - the data/analysis defects found and fixed, with "
        "before/after numbers. The file carries an Arabic name (shown on the "
        "line below):",
    ], "small")
    story += [br.arP("المشكلات_التي_تم_حلها.md", "ar_note", width=170 * mm)]
    story += bullets([
        "docs/API_CONTRACT.md - what every endpoint returns.",
        "docs/MORS_REPORT.pdf - the evidence: quality, problems, figures, "
        "sources and limitations.",
        "docs/PROJECT_GUIDE.pdf (this file) - where each behaviour lives.",
        "DEPLOYMENT.md - how to run it somewhere else.",
        "tools/audit_data.py - 225+ read-only checks -> RESULT: AUDIT: PASS.",
    ], "small")

    # -------------------------------------------------- per-folder sections
    n = 2
    for folder in ["", "agents/", "static/", "tools/", "prompts/", "data/",
                   "docs/"]:
        if folder not in folders:
            continue
        n += 1
        title = folder.rstrip("/") or "Project root"
        story += [PageBreak(),
                  P(f"{n}. {title}", "h1"),
                  HRFlowable(width="100%", thickness=1.2, color=ACCENT,
                             spaceAfter=8),
                  P(FOLDER_BLURB.get(folder, ""), "note"),
                  Spacer(1, 3 * mm)]
        for info in folders[folder]:
            story += card(info)

    # -------------------------------------------------- regeneration note
    n += 1
    story += [PageBreak(),
              P(f"{n}. Regenerating the documents", "h1"),
              HRFlowable(width="100%", thickness=1.2, color=ACCENT,
                         spaceAfter=8),
              table(["Command", "Output"],
                    [["python main.py", "server on http://127.0.0.1:5000"],
                     ["python main.py --selftest",
                      "offline pipeline check, prints SELFTEST : PASS"],
                     ["python tools/build_report.py",
                      "docs/MORS_REPORT.pdf (needs the server running)"],
                     ["python tools/build_guide.py",
                      "docs/PROJECT_GUIDE.pdf (this file)"]],
                    [76 * mm, 94 * mm]),
              Spacer(1, 4 * mm),
              P("Both generators read the live API first and fall back to "
                "last_report.json, so they work either way. The optional PDF "
                "stack is listed at the bottom of requirements.txt.", "note"),
              Spacer(1, 5 * mm),
              HRFlowable(width="100%", thickness=0.8, color=RULE,
                         spaceAfter=6),
              P(f"Guide generated {br._now()} from {br.san(str(ROOT))} - "
                f"{len(rows)} files scanned.", "tiny")]
    return story


def main() -> int:
    print(f"MORS guide -> scanning {ROOT}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    meta = {"when": br.datetime.now(br.timezone.utc)
                      .strftime("%Y-%m-%d %H:%M UTC"),
            "run": "project guide"}
    doc = br.Doc(str(OUT), meta)
    doc.build(build())
    print(f"WROTE {OUT}  ({OUT.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


