#!/usr/bin/env python3
"""Build the 10-slide ASI-HACK pitch deck (16:9, dark glassmorphism).

    python tools/build_deck.py   -> presentation/MORS_ASI-HACK-2026_Deck.pptx

Every slide carries the team-logo placeholder (top left) and the live URL
(bottom right). Screenshots come from presentation/frames/ (captured from the
published site with Chrome headless) and the QR from presentation/qr_live.png.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parents[1]
FRAMES = ROOT / "presentation" / "frames"
QR = ROOT / "presentation" / "qr_live.png"
OUT = ROOT / "presentation" / "MORS_ASI-HACK-2026_Deck.pptx"
URL = "laythraad.github.io/ASI-HACK-Space-Analytics-Engine/"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # pragma: no cover
    pass

BG = RGBColor(0x03, 0x07, 0x12)
PANEL = RGBColor(0x0F, 0x17, 0x2A)
PANEL2 = RGBColor(0x11, 0x1A, 0x2C)
ACCENT = RGBColor(0x38, 0xBD, 0xF8)
WARN = RGBColor(0xFB, 0xBF, 0x24)
GREEN = RGBColor(0x34, 0xD3, 0x99)
TEXT = RGBColor(0xE2, 0xE8, 0xF0)
MUTED = RGBColor(0x94, 0xA3, 0xB8)
LINE = RGBColor(0x1E, 0x3A, 0x5F)

HEAD_FONT = "Orbitron"
BODY_FONT = "Segoe UI"
MONO_FONT = "Consolas"

W, H = 13.333, 7.5


def rect(slide, x, y, w, h, fill=PANEL, line=LINE, radius=True, line_w=1.0):
    shp = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE,
        Inches(x), Inches(y), Inches(w), Inches(h))
    if fill is None:
        shp.fill.background()
    else:
        shp.fill.solid()
        shp.fill.fore_color.rgb = fill
    if line is None:
        shp.line.fill.background()
    else:
        shp.line.color.rgb = line
        shp.line.width = Pt(line_w)
    shp.shadow.inherit = False
    try:
        shp.adjustments[0] = 0.08
    except Exception:
        pass
    return shp


def text(slide, x, y, w, h, lines, size=12.5, color=TEXT, font=BODY_FONT,
         bold=False, align=PP_ALIGN.LEFT, space=6, anchor=MSO_ANCHOR.TOP):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    if isinstance(lines, str):
        lines = [lines]
    for i, ln in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.space_after = Pt(space)
        if isinstance(ln, tuple):
            ln, opts = ln
        else:
            opts = {}
        run = p.add_run()
        run.text = ln
        f = run.font
        f.size = Pt(opts.get("size", size))
        f.bold = opts.get("bold", bold)
        f.color.rgb = opts.get("color", color)
        f.name = opts.get("font", font)
    return box


def chip(slide, x, y, w, h, label, color=ACCENT, size=10.5, fill=PANEL2):
    shp = rect(slide, x, y, w, h, fill=fill, line=color, line_w=0.75)
    tf = shp.text_frame
    tf.word_wrap = False
    tf.margin_left = tf.margin_right = Inches(0.04)
    tf.margin_top = tf.margin_bottom = Inches(0.02)
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    r.text = label
    r.font.size = Pt(size)
    r.font.bold = True
    r.font.color.rgb = color
    r.font.name = MONO_FONT
    return shp


def chrome(slide, n, total=10, logo=True):
    if logo:
        m = rect(slide, 0.35, 0.24, 0.42, 0.42, fill=ACCENT, line=None)
        tf = m.text_frame
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        r = p.add_run()
        r.text = "M"
        r.font.size = Pt(15)
        r.font.bold = True
        r.font.color.rgb = BG
        r.font.name = HEAD_FONT
        text(slide, 0.85, 0.24, 2.4, 0.45,
             [("MORS", {"size": 15, "bold": True, "color": TEXT, "font": HEAD_FONT}),
              ("DATA · SPACE · QUANTUM", {"size": 8, "color": MUTED, "font": MONO_FONT})],
             space=0)
    text(slide, 7.0, 7.05, 5.9, 0.32, URL, size=9, color=MUTED,
         font=MONO_FONT, align=PP_ALIGN.RIGHT)
    text(slide, 0.4, 7.05, 2.0, 0.32, f"{n:02d} / {total}", size=9,
         color=MUTED, font=MONO_FONT)


def title(slide, t, sub=None):
    text(slide, 0.5, 0.82, 12.4, 0.55, t, size=25, color=TEXT,
         font=HEAD_FONT, bold=True, space=0)
    if sub:
        text(slide, 0.5, 1.34, 12.4, 0.32, sub, size=11.5, color=ACCENT,
             font=MONO_FONT, space=0)


def picture(slide, name, x, y, w):
    path = FRAMES / name
    if not path.exists():
        return rect(slide, x, y, w, w * 9 / 16, fill=PANEL2, line=ACCENT)
    pic = slide.shapes.add_picture(str(path), Inches(x), Inches(y), width=Inches(w))
    frame = rect(slide, x, y, w, w * 9 / 16, fill=None, line=ACCENT, line_w=1.25)
    frame.text_frame.text = ""
    return pic


def caption(slide, x, y, w, t, size=9.5):
    text(slide, x, y, w, 0.3, t, size=size, color=MUTED, font=MONO_FONT, space=0)


def new_slide(prs):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    rect(s, -0.05, -0.05, W + 0.1, H + 0.1, fill=BG, line=None, radius=False)
    return s


def build() -> int:
    prs = Presentation()
    prs.slide_width = Inches(W)
    prs.slide_height = Inches(H)

    # ---------------------------------------------------------------- 1
    s = new_slide(prs)
    text(s, 0.7, 1.45, 5.9, 1.0, "MORS", size=54, color=ACCENT,
         font=HEAD_FONT, bold=True, space=0)
    text(s, 0.7, 2.5, 5.9, 0.9,
         ["Scientific Space Analytics Engine"],
         size=22, color=TEXT, font=HEAD_FONT, bold=True, space=4)
    text(s, 0.7, 3.25, 5.9, 0.9,
         ["Autonomous Space Telemetry Auditing,",
          "Anomaly Detection & Verification"],
         size=13, color=MUTED, font=BODY_FONT, space=2)
    text(s, 0.7, 4.05, 5.9, 0.4,
         "منصة تحليل الفضاء العلمية — تدقيق واكتشاف الشذوذ والتحقق",
         size=12.5, color=GREEN, font=BODY_FONT, space=0)
    chip(s, 0.7, 4.7, 2.05, 0.42, "ASI HACK 2026", WARN)
    chip(s, 2.9, 4.7, 2.35, 0.42, "CERTIFIED 96/100", GREEN)
    chip(s, 5.4, 4.7, 2.05, 0.42, "8/8 CONDITIONS", ACCENT)
    picture(s, "01_launcher.png", 7.15, 1.45, 5.6)
    caption(s, 7.55, 4.7, 5.2, "live deployment · static host · no install")
    text(s, 0.7, 5.5, 6.4, 0.9,
         ["4 agents  ·  18 modules  ·  1,711 rows  ·  225 audit checks  ·  0 failures",
          "16 curated sources + 12 data sources  ·  report PDF: 44 pages"],
         size=10.5, color=TEXT, font=MONO_FONT, space=4)
    chrome(s, 1)

    # ---------------------------------------------------------------- 2
    s = new_slide(prs)
    title(s, "THE CHALLENGE — VERIFY BEFORE YOU MODEL",
          "raw volume without verification is noise")
    bullets = [
        "Most tools push ML onto telemetry before anyone audits the data itself.",
        "Our own run proved it: the IsolationForest flag rate followed the "
        "contamination setting, not real outliers (card P-003).",
        "Data reality after cleaning: 0.192% missing cells · 0 duplicates · "
        "167 QC flags · light-curve S/N 12.5.",
        "Verdict written by the platform: “review-ready, not discovery-grade” — "
        "an unfalsifiable model looks scientific while proving nothing.",
    ]
    y = 1.85
    for b in bullets:
        rect(s, 0.5, y, 0.06, 0.78, fill=ACCENT, line=None, radius=False)
        text(s, 0.72, y - 0.04, 5.55, 0.85, b, size=12, color=TEXT, space=0)
        y += 1.05
    picture(s, "02_mors_home.png", 6.75, 1.75, 6.1)
    caption(s, 6.75, 5.3, 6.1, "DATA.MORS data-health · 8,840 cells audited per run")
    for i, (k, v) in enumerate([("MISSING", "0.192%"), ("DUPLICATES", "0"),
                                ("COMPLETENESS", "99.808%"), ("QC FLAGS", "167")]):
        x = 6.75 + i * 1.55
        rect(s, x, 5.65, 1.45, 1.0, fill=PANEL, line=LINE)
        text(s, x + 0.08, 5.75, 1.3, 0.3, k, size=8.5, color=MUTED, font=MONO_FONT, space=0)
        text(s, x + 0.08, 6.05, 1.3, 0.45, v, size=15, color=ACCENT,
             font=HEAD_FONT, bold=True, space=0)
    chrome(s, 2)

    # ---------------------------------------------------------------- 3
    s = new_slide(prs)
    title(s, "MORS METHODOLOGY — 9-STAGE SCIENTIFIC LIFECYCLE",
          "prompts/aimors_analyst_prompt.txt · 25 operating rules")
    steps = [("1", "RAW DATA", "ingest + source badge"),
             ("2", "DATA QUALITY", "completeness · duplicates · outliers"),
             ("3", "ANALYSIS", "EDA · statistics · signals"),
             ("4", "DISCOVERY", "patterns worth a question"),
             ("5", "PROBLEM", "10-key problem card"),
             ("6", "EVIDENCE", "quantified · reproducible"),
             ("7", "SOLUTION", "steps + expected delta"),
             ("8", "VERIFICATION", "council of five experts"),
             ("9", "RECOMMENDATION", "report · trace · publish")]
    x, y = 0.5, 1.85
    for i, (n, name, note) in enumerate(steps):
        col, row = i % 5, i // 5
        cx = 0.5 + col * 2.55
        cy = 1.85 + row * 1.5
        rect(s, cx, cy, 2.4, 1.3, fill=PANEL, line=LINE)
        chip(s, cx + 0.12, cy + 0.12, 0.4, 0.3, n, ACCENT, size=10)
        text(s, cx + 0.6, cy + 0.12, 1.7, 0.3, name, size=11, color=TEXT,
             font=HEAD_FONT, bold=True, space=0)
        text(s, cx + 0.12, cy + 0.55, 2.15, 0.65, note, size=9.5, color=MUTED, space=0)
    rect(s, 0.5, 5.0, 12.35, 1.7, fill=PANEL, line=ACCENT)
    text(s, 0.75, 5.15, 11.9, 0.35,
         "TWO HARD RULES", size=11, color=ACCENT, font=HEAD_FONT, bold=True, space=0)
    text(s, 0.75, 5.5, 5.8, 1.1,
         ["1 · Do not use AI for the sake of AI — if statistics answer the "
          "question, use statistics."],
         size=12, color=TEXT, space=0)
    text(s, 6.8, 5.5, 5.8, 1.1,
         ["2 · Every published value carries source · timestamp · method · "
          "operator (traceability badge)."],
         size=12, color=TEXT, space=0)
    chrome(s, 3)

    # ---------------------------------------------------------------- 4
    s = new_slide(prs)
    title(s, "SATELLITE.MORS — FLEET TELEMETRY INSPECTOR",
          "TLE → Keplerian elements → orbit class · live module")
    bullets = [
        "50 satellites tracked: altitude 167–36,163 km (LEO → GEO), velocity, "
        "inclination, period, perigee/apogee, NORAD ID.",
        "Physics is shown, not hidden: a = (GM/n²)^(1/3), v = sqrt(GM/a), "
        "LEO < 2,000 km ≤ MEO ≤ GEO belt.",
        "Sensor layer: multispectral imager · 30 m resolution · 290 km swath · "
        "telemetry mode · next 5 passes with max elevation.",
        "Spectral bands Blue 490 · Green 560 · Red 665 · NIR 842 · SWIR1 1610 nm "
        "→ NDVI / NDWI / NDBI + PCA (94.6% variance in 2 components).",
    ]
    y = 1.85
    for b in bullets:
        rect(s, 0.5, y, 0.06, 0.95, fill=ACCENT, line=None, radius=False)
        text(s, 0.72, y - 0.04, 5.55, 1.05, b, size=11.5, color=TEXT, space=0)
        y += 1.2
    picture(s, "04_satellite.png", 6.75, 1.75, 6.1)
    caption(s, 6.75, 5.3, 6.1, "SATELLITE.MORS · fleet table + orbit map + band tabs")
    for i, (k, v) in enumerate([("SATELLITES", "50"), ("ALT RANGE", "167–36,163 km"),
                                ("RESOLUTION", "30 m"), ("SWATH", "290 km")]):
        x = 6.75 + i * 1.55
        rect(s, x, 5.65, 1.45, 1.0, fill=PANEL, line=LINE)
        text(s, x + 0.08, 5.75, 1.3, 0.3, k, size=8.5, color=MUTED, font=MONO_FONT, space=0)
        text(s, x + 0.08, 6.05, 1.3, 0.45, v, size=13, color=ACCENT,
             font=HEAD_FONT, bold=True, space=0)
    chrome(s, 4)

    # ---------------------------------------------------------------- 5
    s = new_slide(prs)
    title(s, "PROBLEMS → SOLUTIONS ENGINE",
          "evidence · root cause · fix · measurable delta")
    bullets = [
        "Every anomaly is a 10-key card: symptom · root cause · fix · evidence · "
        "severity · category · component · priority code.",
        "Priority is arithmetic, not opinion: 0.40·evidence + 0.35·impact + "
        "0.25·confidence, printed on the card.",
        "Live card P-001: council runs local_fallback under Gemini 429 → expected "
        "delta  council.engine: local_fallback → gemini.",
        "Live card P-006: spectral indices are reference-labelled → delta  "
        "spectral.provenance: reference spectra → scene-identified L2A.",
    ]
    y = 1.85
    for b in bullets:
        rect(s, 0.5, y, 0.06, 0.95, fill=WARN, line=None, radius=False)
        text(s, 0.72, y - 0.04, 5.55, 1.05, b, size=11.5, color=TEXT, space=0)
        y += 1.2
    picture(s, "06_solutions.png", 6.75, 1.75, 6.1)
    caption(s, 6.75, 5.3, 6.1, "SOLUTIONS.MORS · path, steps, effort, expected delta")
    for i, (k, v) in enumerate([("OPEN CARDS", "5"), ("HIGH", "3"), ("MEDIUM", "2"),
                                ("SCHEMA KEYS", "10")]):
        x = 6.75 + i * 1.55
        rect(s, x, 5.65, 1.45, 1.0, fill=PANEL, line=LINE)
        text(s, x + 0.08, 5.75, 1.3, 0.3, k, size=8.5, color=MUTED, font=MONO_FONT, space=0)
        text(s, x + 0.08, 6.05, 1.3, 0.45, v, size=15, color=WARN,
             font=HEAD_FONT, bold=True, space=0)
    chrome(s, 5)

    # ---------------------------------------------------------------- 6
    s = new_slide(prs)
    title(s, "TRUSTWORTHY AI — CONFIDENCE TAXONOMY",
          "what the platform actually prints on every answer")
    rect(s, 0.5, 1.8, 6.0, 3.9, fill=PANEL, line=LINE)
    text(s, 0.75, 1.95, 5.5, 0.35, "STANDARD AI PIPELINE", size=12,
         color=WARN, font=HEAD_FONT, bold=True, space=0)
    text(s, 0.75, 2.4, 5.5, 3.1,
         ["▪ Model runs first, data quality never inspected.",
          "▪ Single number published, no error bounds.",
          "▪ No source, no timestamp, no operator recorded.",
          "▪ Failure mode looks like a confident answer.",
          "▪ Cannot be re-run or falsified by a judge."],
         size=12, color=MUTED, space=10)
    rect(s, 6.85, 1.8, 6.0, 3.9, fill=PANEL, line=ACCENT, line_w=1.5)
    text(s, 7.1, 1.95, 5.5, 0.35, "MORS XAI ENGINE", size=12,
         color=ACCENT, font=HEAD_FONT, bold=True, space=0)
    text(s, 7.1, 2.4, 5.5, 3.1,
         ["▪ Data audit first — ML only when statistics are insufficient.",
          "▪ Confidence level + priority formula published per card.",
          "▪ Every value carries source · timestamp · method · operator.",
          "▪ Engine honesty: local_fallback is labelled, never disguised.",
          "▪ Council of five experts cross-checks and corrects claims."],
         size=12, color=TEXT, space=10)
    text(s, 0.5, 5.85, 6.0, 0.3, "5-TIER PROTOCOL ON EVERY AI ANSWER",
         size=10.5, color=MUTED, font=MONO_FONT, space=0)
    tiers = ["[Observed Data]", "[Calculated Metric]", "[AI Interpretation]",
             "[Hypothesis]", "[Suggested Action]"]
    for i, t in enumerate(tiers):
        chip(s, 0.5 + i * 2.5, 6.2, 2.35, 0.42, t, GREEN, size=9.5)
    chrome(s, 6)

    # ---------------------------------------------------------------- 7
    s = new_slide(prs)
    title(s, "HIGH-DENSITY SCIENTIFIC UI / UX",
          "dark glassmorphism · Orbitron + IBM Plex Mono + Cairo")
    picture(s, "02_mors_home.png", 0.5, 1.75, 6.1)
    picture(s, "03_theme_mars.png", 6.75, 1.75, 6.1)
    caption(s, 0.5, 5.3, 6.1, "EARTH CYAN · dark glass panels · lifecycle ribbon")
    caption(s, 6.75, 5.3, 6.1, "MARS RUST · planet theme engine · one click")
    rect(s, 0.5, 5.7, 6.1, 1.15, fill=PANEL, line=LINE)
    text(s, 0.7, 5.82, 5.7, 0.95,
         ["Planet themes: Earth · Mars · Jupiter · Saturn · Neptune · Moon,",
          "plus light/dark, accent layers, grid and particle toggles."],
         size=11.5, color=TEXT, space=3)
    rect(s, 6.75, 5.7, 6.1, 1.15, fill=PANEL, line=LINE)
    text(s, 6.95, 5.82, 5.7, 0.95,
         ["Accordion sidebar: DATA · ASTRONOMY · SATELLITE · QUANTUM · AI ·",
          "PROBLEMS→SOLUTIONS, with global search and instant switching."],
         size=11.5, color=TEXT, space=3)
    chrome(s, 7)

    # ---------------------------------------------------------------- 8
    s = new_slide(prs)
    title(s, "ENGINEERING CAPABILITIES — TEAM MATRIX",
          "4 members · published roles · module ownership")
    members = [
        ("TEAM LEADER", "ليث رعد · Layth Ra'ad",
         ["System Architecture", "Pipeline Orchestration", "Scientific Computing",
          "Technical Review", "Scientific Visualization"],
         "owns: MORS architecture · HOME · PROJECTS · TEAM", ACCENT),
        ("DATA ANALYST", "role seat",
         ["Data Cleaning", "EDA", "Statistical Analysis", "Time Series",
          "Anomaly Detection", "SQL", "Feature Engineering"],
         "owns: DATA.MORS · PROBLEMS.MORS · SOLUTIONS.MORS", GREEN),
        ("ASTRONOMY RESEARCHER", "role seat",
         ["Astropy", "FITS Analysis", "Photometry", "Spectroscopy",
          "Light-Curve Analysis", "Sky Coordinates"],
         "owns: ASTRONOMY.MORS · SOURCES.MORS", WARN),
        ("SPACE SYSTEMS & AI ENGINEER", "role seat",
         ["Satellite & Orbit Analysis", "AI Model Integration",
          "Quantum Computing", "Remote Sensing", "Scientific Computing"],
         "owns: AI.MORS · SATELLITE.MORS · QUANTUM.MORS", ACCENT),
    ]
    for i, (role, seat, skills, owns, color) in enumerate(members):
        col, row = i % 2, i // 2
        x = 0.5 + col * 6.35
        y = 1.8 + row * 2.55
        rect(s, x, y, 6.0, 2.35, fill=PANEL, line=color, line_w=1.25)
        text(s, x + 0.2, y + 0.13, 4.4, 0.3, role, size=11.5, color=color,
             font=HEAD_FONT, bold=True, space=0)
        text(s, x + 0.2, y + 0.45, 5.6, 0.3, seat, size=10, color=MUTED,
             font=MONO_FONT, space=0)
        text(s, x + 0.2, y + 0.8, 5.6, 1.1, " · ".join(skills), size=11,
             color=TEXT, space=0)
        text(s, x + 0.2, y + 1.92, 5.6, 0.3, owns, size=9.5, color=MUTED,
             font=MONO_FONT, space=0)
    chrome(s, 8)

    # ---------------------------------------------------------------- 9
    s = new_slide(prs)
    title(s, "MEASURABLE PLATFORM IMPACT",
          "every number below is printed by the live platform")
    kpis = [("225", "automated checks", "0 failures · ~1 min run", ACCENT),
            ("99.81%", "data quality", "8,840 cells · 1,711 rows", GREEN),
            ("100%", "traceability", "source · time · method · operator", WARN),
            ("96/100", "council verdict", "CERTIFIED · 5 experts", ACCENT)]
    for i, (num, lab, note, color) in enumerate(kpis):
        x = 0.5 + i * 3.15
        rect(s, x, 1.85, 2.95, 2.1, fill=PANEL, line=color, line_w=1.25)
        text(s, x + 0.15, 2.05, 2.7, 0.7, num, size=30, color=color,
             font=HEAD_FONT, bold=True, space=0)
        text(s, x + 0.15, 2.8, 2.7, 0.3, lab.upper(), size=10.5, color=TEXT,
             font=MONO_FONT, space=0)
        text(s, x + 0.15, 3.15, 2.7, 0.6, note, size=10, color=MUTED, space=0)
    rect(s, 0.5, 4.25, 12.35, 2.35, fill=PANEL, line=LINE)
    text(s, 0.75, 4.4, 11.9, 0.35, "SUPPORTING EVIDENCE", size=11,
         color=ACCENT, font=HEAD_FONT, bold=True, space=0)
    facts = ["21 cited formulas · 14 references",
             "16 curated sources + 12 data sources",
             "8 live endpoints (NASA · NOAA · CelesTrak · GIBS)",
             "8/8 challenge conditions (7 core + 1 extension)",
             "18 UI modules · 19 registered endpoints",
             "6 published master prompts",
             "5 problem cards · 10-key schema each",
             "44-page scientific report, auto-generated"]
    for i, f in enumerate(facts):
        col, row = i % 2, i // 2
        text(s, 0.75 + col * 6.1, 4.8 + row * 0.42, 5.9, 0.35,
             "▸ " + f, size=11.5, color=TEXT, font=BODY_FONT, space=0)
    chrome(s, 9)

    # --------------------------------------------------------------- 10
    s = new_slide(prs)
    title(s, "THE FUTURE OF SPACE DATA ANALYTICS",
          "build · learn · innovate")
    text(s, 0.7, 1.9, 7.4, 0.5, "Try the live engine — no install, no account:",
         size=14, color=TEXT, space=0)
    text(s, 0.7, 2.35, 9.0, 0.55, "https://" + URL, size=21, color=ACCENT,
         font=HEAD_FONT, bold=True, space=0)
    text(s, 0.7, 3.15, 7.6, 2.6,
         ["Next: deeper NASA / ESA live integration,",
          "real Sentinel-2 L2A scene ingestion for the spectral module,",
          "and scaling the quantum block beyond the classical statevector",
          "(labelled honestly today as simulation, never as QPU output)."],
         size=13, color=TEXT, space=10)
    rect(s, 0.7, 5.35, 7.6, 1.3, fill=PANEL, line=ACCENT, line_w=1.25)
    text(s, 0.9, 5.5, 7.2, 1.0,
         ["CERTIFIED 96/100 · 225 checks · 0 failures · 8/8 conditions",
          "Open the link above and click through every module yourself."],
         size=12.5, color=GREEN, font=MONO_FONT, space=4)
    if QR.exists():
        s.shapes.add_picture(str(QR), Inches(9.6), Inches(2.1), height=Inches(2.6))
        text(s, 9.6, 4.8, 3.2, 0.3, "SCAN → LIVE DEMO", size=10, color=MUTED,
             font=MONO_FONT, align=PP_ALIGN.CENTER, space=0)
    text(s, 9.0, 5.4, 4.0, 0.9,
         [("Team", {"size": 10, "color": MUTED, "font": MONO_FONT}),
          ("ليث رعد (Team Leader)", {"size": 13, "color": TEXT, "bold": True}),
          ("Data Analyst · Astronomy Researcher ·", {"size": 10.5, "color": MUTED}),
          ("Space Systems & AI Engineer", {"size": 10.5, "color": MUTED})],
         space=2, align=PP_ALIGN.CENTER)
    chrome(s, 10)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(OUT))
    print(f"slides={len(prs.slides._sldIdLst)} -> {OUT} ({OUT.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(build())
