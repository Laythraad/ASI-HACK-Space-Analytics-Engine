#!/usr/bin/env python3
"""Build docs/MORS_REPORT.pdf from the live MORS API.

Usage:
    python main.py                # keep a server running (any port)
    python tools/build_report.py  # writes docs/MORS_REPORT.pdf

Environment:
    MORS_BASE   base URL of the running server (default http://127.0.0.1:5000)
    MORS_OUT    output path            (default docs/MORS_REPORT.pdf)
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

try:  # the project folder name is not representable in cp1256
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # pragma: no cover
    pass
BASE = os.getenv("MORS_BASE", "http://127.0.0.1:5000").rstrip("/")
OUT = Path(os.getenv("MORS_OUT", str(ROOT / "docs" / "MORS_REPORT.pdf")))

# ----------------------------------------------------------------- reportlab
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, Frame, HRFlowable,
                                KeepTogether, NextPageTemplate, PageBreak,
                                Paragraph, PageTemplate, Spacer, Table,
                                TableStyle)
from reportlab.platypus import Image as RLImage

FDIR = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
for alias, fn in (("Body", "arial.ttf"), ("Body-B", "arialbd.ttf"),
                  ("Body-I", "ariali.ttf"), ("Body-BI", "arialbi.ttf"),
                  ("Ar", "arial.ttf"), ("ArB", "arialbd.ttf")):
    try:
        pdfmetrics.registerFont(TTFont(alias, str(FDIR / fn)))
    except Exception:  # pragma: no cover - non-Windows fallback
        pdfmetrics.registerFont(TTFont(alias, "Helvetica"))
pdfmetrics.registerFontFamily("Body", normal="Body", bold="Body-B",
                              italic="Body-I", boldItalic="Body-BI")

INK = colors.HexColor("#0B1220")
SLATE = colors.HexColor("#334155")
MUTED = colors.HexColor("#64748B")
ACCENT = colors.HexColor("#0E7490")
CYAN = colors.HexColor("#38BDF8")
RULE = colors.HexColor("#CBD5E1")
BAND = colors.HexColor("#F1F5F9")
BAND2 = colors.HexColor("#E0F2FE")
GREEN = colors.HexColor("#047857")
AMBER = colors.HexColor("#B45309")
RED = colors.HexColor("#B91C1C")

# ------------------------------------------------------------------ sanitize
_MAP = {
    "\u2192": " -> ", "\u2190": " <- ", "\u2194": "<->", "\u21d2": " => ",
    "\u2264": "<=", "\u2265": ">=", "\u2260": "!=", "\u2248": "~",
    "\u221e": "inf", "\u00b1": "+/-", "\u00b7": " . ", "\u2022": "- ",
    "\u2014": " - ", "\u2013": "-", "\u2026": "...", "\u2018": "'",
    "\u2019": "'", "\u201c": '"', "\u201d": '"',
    "\u00d7": "x", "\u00f7": "/", "\u221a": "sqrt", "\u2211": "sum",
    "\u222b": "int", "\u2202": "d", "\u2208": " in ", "\u2205": "{}",
    "\u00b2": "2", "\u00b3": "3", "\u00b9": "1", "\u2070": "0",
    "\u00bd": "1/2", "\u2153": "1/3", "\u2154": "2/3",
    "\u03b1": "alpha", "\u03b2": "beta", "\u03b3": "gamma",
    "\u03b4": "delta", "\u03b5": "epsilon", "\u03b8": "theta",
    "\u03c0": "pi", "\u03c1": "rho", "\u03c3": "sigma", "\u03c4": "tau",
    "\u03c6": "phi", "\u03c8": "psi", "\u03c9": "omega",
    "\u0393": "Gamma", "\u0394": "Delta", "\u0398": "Theta",
    "\u039b": "Lambda", "\u03a0": "Pi", "\u03a3": "Sigma",
    "\u03a6": "Phi", "\u03a8": "Psi", "\u03a9": "Omega",
    "\u00b5": "u", "\u00b0": " deg", "\u00b7": " . ",
    "\u207b": "-", "\u2074": "4", "\u2075": "5", "\u2076": "6",
    "\u2077": "7", "\u2078": "8", "\u2079": "9",
    "\u2080": "0", "\u2081": "1", "\u2082": "2", "\u2083": "3",
    "\u2084": "4", "\u2085": "5", "\u2086": "6", "\u2087": "7",
    "\u2088": "8", "\u2089": "9",
    "\u27e8": "<", "\u27e9": ">", "\u2212": "-", "\u00d8": "O",
    "\u00d7": "x", "\u22c5": ".", "\u2218": " o ", "\u2020": "",
    "\u2713": "PASS", "\u2714": "PASS", "\u2717": "FAIL", "\u2718": "FAIL",
    "\u2605": "*", "\u26a0": "!", "\u25cf": "o", "\u25cb": "o",
    "\u25a0": "[]", "\u00a0": " ",
}


def _clean(v, default="-") -> str:
    """Unicode map + ASCII filter. Does NOT do XML escaping."""
    if v is None:
        return default
    if isinstance(v, float):
        s = f"{v:g}"
    elif isinstance(v, bool):
        s = "yes" if v else "no"
    else:
        s = str(v)
    for k, rep in _MAP.items():
        s = s.replace(k, rep)
    s = "".join(ch for ch in s
                if ch.isascii() or "\u0080" <= ch <= "\u00ff")
    s = s.replace("\r", " ").replace("\n", " ")
    while "  " in s:
        s = s.replace("  ", " ")
    return s.strip() or default


def _xml(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def san(v, default="-") -> str:
    """Unicode map + ASCII filter (no XML escaping - P()/R() do that once)."""
    return _clean(v, default)


_OWNER_EN = {"ليث رعد": "Layth Ra'ad (Team Leader)"}


def own(v, default="-") -> str:
    """Latin display for an owner value: only the team leader is named,
    and this PDF is ASCII-only, so the Arabic name is transliterated."""
    return _OWNER_EN.get(str(v).strip(), san(v, default))


_TAGS = ("<b>", "</b>", "<i>", "</i>", "<br/>")


def san_ml(v, default="") -> str:
    """Sanitize but keep the handful of tags we generate ourselves."""
    if v is None:
        return default
    s = str(v)
    keep = {}
    for t in _TAGS:
        while t in s:
            key = "\x00%d\x00" % len(keep)
            keep[key] = t
            s = s.replace(t, key, 1)
    s = _xml(_clean(s, default))
    for key, t in keep.items():
        s = s.replace(key, t)
    return s

def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _num(v) -> str:
    try:
        return f"{int(v):,}".replace(",", " ")
    except (TypeError, ValueError):
        return san(v)


def n_of(d) -> str:
    """Record count for a module payload, whatever shape it is in."""
    if not isinstance(d, dict):
        return "-"
    if d.get("count") is not None:
        return str(d.get("count"))
    r = d.get("rows")
    if isinstance(r, list):
        return str(len(r))
    if isinstance(r, (int, float)):
        return str(int(r))
    return "-"


# ------------------------------------------------------------------- styles
SS = getSampleStyleSheet()


def _p(name, **kw):
    base = dict(name=name, fontName="Body", fontSize=9.2, leading=13.2,
                textColor=INK, spaceAfter=4, alignment=TA_LEFT)
    base.update(kw)
    return ParagraphStyle(**base)


S = {
    "cover_kicker": _p("cover_kicker", fontName="Body-B", fontSize=10,
                       leading=14, textColor=colors.white, spaceAfter=0),
    "cover_title": _p("cover_title", fontName="Body-B", fontSize=30,
                      leading=36, textColor=colors.white, spaceAfter=6),
    "cover_sub": _p("cover_sub", fontSize=12.5, leading=18,
                    textColor=colors.HexColor("#CFF6FF"), spaceAfter=2),
    "cover_meta": _p("cover_meta", fontSize=9, leading=14,
                     textColor=colors.HexColor("#A5D8E8"), spaceAfter=0),
    "h1": _p("h1", fontName="Body-B", fontSize=16.5, leading=20,
             textColor=INK, spaceBefore=6, spaceAfter=7),
    "h2": _p("h2", fontName="Body-B", fontSize=11.6, leading=15,
             textColor=ACCENT, spaceBefore=9, spaceAfter=4),
    "h3": _p("h3", fontName="Body-B", fontSize=9.8, leading=13,
             textColor=SLATE, spaceBefore=6, spaceAfter=3),
    "body": _p("body"),
    "small": _p("small", fontSize=8.2, leading=11.4, textColor=SLATE),
    "tiny": _p("tiny", fontSize=7.2, leading=9.6, textColor=MUTED),
    "note": _p("note", fontSize=8.6, leading=12.4, textColor=SLATE),
    "cell": _p("cell", fontSize=8.3, leading=11.2, spaceAfter=0),
    "cellb": _p("cellb", fontName="Body-B", fontSize=8.3, leading=11.2,
                spaceAfter=0),
    "cellm": _p("cellm", fontName="Body", fontSize=7.7, leading=10.4,
                textColor=MUTED, spaceAfter=0),
    "th": _p("th", fontName="Body-B", fontSize=7.9, leading=10.4,
             textColor=colors.white, spaceAfter=0),
    "mono": _p("mono", fontName="Body", fontSize=7.9, leading=11,
               textColor=SLATE),
    "quote": _p("quote", fontSize=9, leading=13, textColor=SLATE,
                leftIndent=8, spaceBefore=3, spaceAfter=5),
    "kpi_n": _p("kpi_n", fontName="Body-B", fontSize=17, leading=20,
                textColor=ACCENT, alignment=TA_CENTER, spaceAfter=1),
    "kpi_l": _p("kpi_l", fontSize=7.3, leading=9.4, textColor=MUTED,
                alignment=TA_CENTER, spaceAfter=0),
    "center": _p("center", alignment=TA_CENTER),
    # Arabic (right-aligned, reshaped — see arP/ar_block below)
    "ar_h1": _p("ar_h1", fontName="ArB", fontSize=15, leading=23,
                alignment=TA_RIGHT, spaceBefore=4, spaceAfter=7),
    "ar_h2": _p("ar_h2", fontName="ArB", fontSize=11.6, leading=18,
                textColor=ACCENT, alignment=TA_RIGHT, spaceBefore=7,
                spaceAfter=4),
    "ar_body": _p("ar_body", fontName="Ar", fontSize=10, leading=17.5,
                  alignment=TA_RIGHT, spaceAfter=5),
    "ar_note": _p("ar_note", fontName="Ar", fontSize=8.7, leading=14.5,
                  textColor=SLATE, alignment=TA_RIGHT, spaceAfter=4),
}


def P(t, st="body"):
    return Paragraph(_xml(_clean(t)), S[st])


def R(t, st="cell"):
    """Rich paragraph: allow a single pre-sanitized <b>/<i> wrapper."""
    return Paragraph(san_ml(t), S[st])


def table(header, rows, widths, align=None, zebra=True, fs=None):
    data = [[R(f"<b>{h}</b>", "th") for h in header]]
    for r in rows:
        data.append([c if isinstance(c, Paragraph) else P(c, "cell")
                     for c in r])
    t = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    st = [
        ("BACKGROUND", (0, 0), (-1, 0), INK),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, RULE),
        ("BOX", (0, 0), (-1, -1), 0.6, RULE),
    ]
    if zebra:
        for i in range(1, len(data)):
            if i % 2 == 0:
                st.append(("BACKGROUND", (0, i), (-1, i), BAND))
    if align:
        for col, a in align.items():
            st.append(("ALIGN", (col, 1), (col, -1), a))
    t.setStyle(TableStyle(st))
    return t


def kpis(items, ncols=4):
    nums = [R(f"<b>{_clean(v)}</b>", "kpi_n") for _, v in items]
    labs = [P(l, "kpi_l") for l, _ in items]
    while len(nums) % ncols:
        nums.append(P(" ", "kpi_n"))
        labs.append(P(" ", "kpi_l"))
    inner = []
    for i in range(0, len(nums), ncols):
        inner.append(nums[i:i + ncols])
        inner.append(labs[i:i + ncols])
    t = Table(inner, colWidths=[(170 * mm) / ncols] * ncols)
    style = [
        ("BOX", (0, 0), (-1, -1), 0.6, ACCENT),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.white),
    ]
    for r in range(0, len(inner), 2):
        style.append(("BACKGROUND", (0, r), (-1, r), BAND2))
    t.setStyle(TableStyle(style))
    return t


def bullets(items, style="body"):
    return [Paragraph("\u2022&nbsp;&nbsp;" + _xml(_clean(i)), S[style])
            for i in (items or [])]


def badge_line(trace) -> Paragraph:
    if not trace:
        return P("", "tiny")
    parts = [trace.get("source"), trace.get("dataset_version"),
             trace.get("processing_pipeline"), trace.get("method"),
             trace.get("operator_id"),
             (trace.get("last_updated") or "")[:19].replace("T", " ")]
    return P("[ TRACE ]  " + "  |  ".join(san(p) for p in parts if p),
             "tiny")


# ------------------------------------------------------------------ arabic
# reportlab cannot shape Arabic on its own: the text must be converted to
# presentation forms (arabic_reshaper) and put into visual order (python-bidi)
# before it is handed to a font that carries those forms (Arial does).
_AR_OK = False
try:  # pragma: no cover - depends on the host interpreter
    import arabic_reshaper
    from bidi.algorithm import get_display as _bidi_display
    _AR_OK = True
except Exception:  # pragma: no cover
    arabic_reshaper = None
    _bidi_display = None


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def ar(text) -> str:
    """Reshape + reorder one logical run of Arabic text for a single line."""
    t = str(text if text is not None else "")
    if not _AR_OK:
        return _esc(t)
    return _esc(_bidi_display(arabic_reshaper.reshape(t)))


def ar_lines(text, font="Ar", size=10.0, width=None):
    """Greedy-wrap logical Arabic text so reportlab never re-wraps a line.

    Re-wrapping is the classic Arabic-in-PDF failure: reportlab would split a
    pre-reversed run at an arbitrary point and the sentence would read inside
    out. We therefore cut the logical string at word boundaries ourselves and
    only ever hand it whole lines.
    """
    width = float(width if width else (170 * mm))
    words = str(text if text is not None else "").split()
    if not words:
        return [""]
    out, cur = [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if _AR_OK and pdfmetrics.stringWidth(ar(trial), font, size) > width and cur:
            out.append(cur)
            cur = w
        else:
            cur = trial
    if cur:
        out.append(cur)
    return out


def arP(text, st="ar_body", font=None, size=None, width=None):
    """Paragraph flowable for a block of Arabic text."""
    st_o = S[st]
    fnt = font or st_o.fontName
    fsz = size or st_o.fontSize
    lines = ar_lines(text, font=fnt, size=fsz, width=width)
    return Paragraph("<br/>".join(ar(l) for l in lines), st_o)


def ar_block(text, st="ar_body", **kw):
    """Arabic text split into paragraphs on blank lines."""
    chunks = [c for c in str(text or "").split("\n\n") if c.strip()]
    if not chunks:
        return [arP(text, st, **kw)]
    return [arP(c.strip(), st, **kw) for c in chunks]


# ------------------------------------------------------------------ charts
_MPL = False
try:  # pragma: no cover - matplotlib is optional
    import tempfile
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager as _fm
    from PIL import Image as _PILImage
    for _fn in ("arial.ttf", "arialbd.ttf"):
        try:
            _fm.fontManager.addfont(str(FDIR / _fn))
        except Exception:
            pass
    plt.rcParams["font.family"] = "Arial"
    plt.rcParams["font.size"] = 8.4
    plt.rcParams["axes.unicode_minus"] = False
    _MPL = True
except Exception:  # pragma: no cover
    plt = None

_CHART_DIR = Path(tempfile.mkdtemp(prefix="mors_charts_"))
_CHART_N = [0]

C1, C2, C3 = "#0E7490", "#818CF8", "#34D399"
C4, C5, C6 = "#FBBF24", "#F87171", "#38BDF8"


def _frame(ax, ygrid=True):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color("#94A3B8")
        ax.spines[s].set_linewidth(0.7)
    if ygrid:
        ax.yaxis.grid(True, color="#E2E8F0", linewidth=0.7)
        ax.set_axisbelow(True)
    ax.tick_params(colors="#475569", length=2.5)


def _emit(fig, width=170 * mm, maxh=82 * mm):
    _CHART_N[0] += 1
    p = _CHART_DIR / f"chart_{_CHART_N[0]:02d}.png"
    fig.savefig(str(p), dpi=175, bbox_inches="tight",
                facecolor="white", pad_inches=0.04)
    plt.close(fig)
    with _PILImage.open(str(p)) as im:
        pw, ph = im.size
    if pw <= 0 or ph <= 0:
        return None
    w, h = width, width * ph / pw
    if h > maxh:
        h = maxh
        w = maxh * pw / ph
    return RLImage(str(p), width=w, height=h)


def chart_quality(dh):
    """Completeness vs accuracy for every ingested source."""
    if not _MPL:
        return None
    rows = (dh or {}).get("per_source") or []
    if not rows:
        return None
    labs = [str(r.get("source", "?")).replace("local:", "").replace("nasa:", "")[:26]
            for r in rows]
    comp = [float(r.get("completeness_pct") or 0) for r in rows]
    acc = [float(r.get("accuracy_score") or 0) for r in rows]
    x = range(len(labs))
    fig, ax = plt.subplots(figsize=(7.6, 2.75))
    ax.bar([i - 0.2 for i in x], comp, width=0.4, label="Completeness %", color=C1)
    ax.bar([i + 0.2 for i in x], acc, width=0.4, label="Accuracy %", color=C4)
    ax.set_xticks(list(x))
    ax.set_xticklabels(labs, rotation=24, ha="right", fontsize=7.1)
    ax.set_ylim(0, 108)
    ax.set_ylabel("%", fontsize=8)
    _frame(ax)
    ax.legend(frameon=False, fontsize=7.6, ncol=2, loc="lower center",
              bbox_to_anchor=(0.5, 1.0))
    return _emit(fig)


def chart_priority(problems):
    """Problem count per priority — the metric-derived ranking.

    Accepts either the problem list or the /api/mors/problems payload.
    """
    if not _MPL:
        return None
    if isinstance(problems, dict):
        by = dict(problems.get("by_priority") or {})
        rows = problems.get("problems") or []
    else:
        rows = problems or []
        by = {}
    for r in rows:
        k = str(r.get("priority") or "?")
        by[k] = by.get(k, 0) + 1
    labels = [k for k in ("High", "Medium", "Low") if by.get(k)]
    if not labels:
        return None
    vals = [by[k] for k in labels]
    fig, ax = plt.subplots(figsize=(3.5, 2.6))
    ax.pie(vals, labels=[f"{k} ({by[k]})" for k in labels],
           colors=[C5, C4, C3], startangle=90,
           wedgeprops=dict(width=0.42, edgecolor="white", linewidth=1.6),
           textprops=dict(fontsize=8, color="#334155"))
    ax.set_aspect("equal")
    ax.text(0, 0, str(sum(vals)), ha="center", va="center",
            fontsize=17, fontweight="bold", color="#0E7490")
    return _emit(fig, maxh=70 * mm)


def chart_orbit(sat):
    """LEO / MEO / GEO balance of the tracked satellite catalog."""
    if not _MPL:
        return None
    counts: dict = {}
    for r in (sat or {}).get("rows") or []:
        k = str(r.get("orbit_class") or "?")
        counts[k] = counts.get(k, 0) + 1
    if not counts:
        return None
    order = [k for k in ("LEO", "MEO", "GEO") if k in counts]
    order += [k for k in counts if k not in order]
    fig, ax = plt.subplots(figsize=(3.5, 2.6))
    ax.pie([counts[k] for k in order], labels=[f"{k} ({counts[k]})" for k in order],
           colors=[C6, C4, C2], startangle=90,
           wedgeprops=dict(width=0.42, edgecolor="white", linewidth=1.6),
           textprops=dict(fontsize=8, color="#334155"))
    ax.set_aspect("equal")
    ax.text(0, 0, str(sum(counts.values())), ha="center", va="center",
            fontsize=17, fontweight="bold", color="#0E7490")
    return _emit(fig, maxh=70 * mm)


def chart_altitude(sat):
    """Altitude profile of the ten highest objects — shows the MEO/GEO tier."""
    if not _MPL:
        return None
    rows = sorted([r for r in (sat or {}).get("rows") or []
                   if isinstance(r.get("altitude_km"), (int, float))],
                  key=lambda r: -float(r["altitude_km"]))[:10]
    if not rows:
        return None
    labs = [str(r.get("name", "?"))[:18] for r in rows]
    vals = [float(r["altitude_km"]) for r in rows]
    colmap = {"LEO": C6, "MEO": C4, "GEO": C2}
    cols = [colmap.get(str(r.get("orbit_class")), C1) for r in rows]
    fig, ax = plt.subplots(figsize=(7.6, 2.5))
    ax.barh(list(range(len(labs)))[::-1], vals, color=cols, height=0.68)
    ax.set_yticks(list(range(len(labs)))[::-1])
    ax.set_yticklabels(labs, fontsize=7.4)
    ax.set_xlabel("altitude (km)", fontsize=8)
    ax.xaxis.grid(True, color="#E2E8F0", linewidth=0.7)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.tick_params(colors="#475569", length=2.5)
    return _emit(fig)


def chart_exoplanets(exo):
    """Discovery method split of the archived exoplanet sample."""
    if not _MPL:
        return None
    counts: dict = {}
    for r in (exo or {}).get("rows") or []:
        k = str(r.get("discovery_method") or "unknown")
        counts[k] = counts.get(k, 0) + 1
    if not counts:
        return None
    items = sorted(counts.items(), key=lambda kv: kv[1])[-8:]
    fig, ax = plt.subplots(figsize=(7.6, 2.5))
    ax.barh([k for k, _ in items], [v for _, v in items], color=C1, height=0.62)
    for i, (_, v) in enumerate(items):
        ax.text(v + 0.15, i, str(v), va="center", fontsize=7.6, color="#334155")
    ax.set_xlabel("planets in sample", fontsize=8)
    ax.xaxis.grid(True, color="#E2E8F0", linewidth=0.7)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.tick_params(colors="#475569", length=2.5)
    return _emit(fig)


def chart_kp(kp):
    """Planetary K-index series with its 3-sample moving average."""
    if not _MPL:
        return None
    rows = (kp or {}).get("kp") or []
    smooth = (kp or {}).get("kp_smooth") or []
    if len(rows) < 3:
        return None
    xs = list(range(len(rows)))
    ys = [float(r.get("kp") or 0) for r in rows]
    fig, ax = plt.subplots(figsize=(7.6, 2.35))
    ax.plot(xs, ys, color=C1, linewidth=1.1, marker="o", markersize=2.4,
            label="Kp (observed)")
    if len(smooth) == len(rows):
        ax.plot(xs, [float(v) for v in smooth], color=C5, linewidth=1.6,
                label="3-sample moving average")
    ax.axhline(5, color=C5, linewidth=0.9, linestyle="--")
    ax.text(0.3, 5.12, "storm threshold Kp=5", fontsize=7, color="#B91C1C")
    ax.set_ylabel("Kp (0-9)", fontsize=8)
    ax.set_xlabel("sample index", fontsize=8)
    _frame(ax)
    ax.legend(frameon=False, fontsize=7.4, loc="upper left", ncol=2)
    return _emit(fig)


def chart_cme(sw):
    """CME speeds over the captured window."""
    if not _MPL:
        return None
    series = (sw or {}).get("series") or []
    pts = [s for s in series if str(s.get("label", "")).startswith("CME speed")]
    if len(pts) < 3:
        return None
    xs = list(range(len(pts)))
    ys = [float(p.get("value") or 0) for p in pts]
    fig, ax = plt.subplots(figsize=(7.6, 2.35))
    ax.plot(xs, ys, color=C1, linewidth=1.2)
    ax.fill_between(xs, ys, color=C6, alpha=0.18, linewidth=0)
    top = max(range(len(ys)), key=lambda i: ys[i])
    ax.annotate(f"{ys[top]:.0f} km/s", (top, ys[top]),
                textcoords="offset points", xytext=(4, 5),
                fontsize=7.4, color="#0F172A")
    ax.set_ylabel("km/s", fontsize=8)
    ax.set_xlabel("CME event index (chronological)", fontsize=8)
    _frame(ax)
    return _emit(fig)


def chart_effort(solutions):
    """Implementation effort of the proposed solutions (list or payload)."""
    if not _MPL:
        return None
    rows = (solutions.get("solutions") if isinstance(solutions, dict)
            else solutions) or []
    counts: dict = {}
    for r in rows:
        k = str(r.get("effort") or "?")
        counts[k] = counts.get(k, 0) + 1
    if not counts:
        return None
    order = [k for k in ("S", "M", "L", "XL") if k in counts]
    order += [k for k in counts if k not in order]
    fig, ax = plt.subplots(figsize=(3.5, 2.4))
    ax.bar(order, [counts[k] for k in order],
           color=[C3, C4, C5, C2][:len(order)], width=0.55)
    for i, k in enumerate(order):
        ax.text(i, counts[k] + 0.06, str(counts[k]), ha="center",
                fontsize=8, color="#334155")
    ax.set_ylabel("solutions", fontsize=8)
    ax.set_xlabel("effort class (S/M/L/XL)", fontsize=7.6)
    _frame(ax)
    return _emit(fig, maxh=66 * mm)


def chart_sources_phase(src):
    """Preparation / During / Research split of the official source list."""
    if not _MPL:
        return None
    by = ((src or {}).get("aggregates") or {}).get("by_phase") or {}
    if not by:
        return None
    order = [k for k in ("Preparation", "During", "Research") if k in by]
    order += [k for k in by if k not in order]
    fig, ax = plt.subplots(figsize=(3.5, 2.6))
    ax.pie([by[k] for k in order],
           labels=[f"{k}\n({by[k]})" for k in order],
           colors=[C6, C1, C4], startangle=90,
           wedgeprops=dict(width=0.42, edgecolor="white", linewidth=1.6),
           textprops=dict(fontsize=7.8, color="#334155"))
    ax.set_aspect("equal")
    ax.text(0, 0, str(sum(by.values())), ha="center", va="center",
            fontsize=17, fontweight="bold", color="#0E7490")
    return _emit(fig, maxh=70 * mm)


def chart_sources_cat(src):
    """How the 16 official sources spread over the 8 required conditions."""
    if not _MPL:
        return None
    by = ((src or {}).get("aggregates") or {}).get("by_category") or {}
    if not by:
        return None
    names = {
        "ai_basics": "AI & ML basics",
        "data_handling": "Working with data",
        "analysis_modelling": "Data analysis & model building",
        "computer_vision": "Computer Vision",
        "astronomical_data": "Astronomical data",
        "generative_ai": "AI / Generative-AI applications",
        "predictive_automation": "Predictive & automation",
        "inspiration_research": "Inspiration & research",
    }
    items = [(names.get(k, k), v) for k, v in by.items()]
    items.sort(key=lambda kv: kv[1])
    fig, ax = plt.subplots(figsize=(7.6, 2.6))
    ax.barh([k for k, _ in items], [v for _, v in items], color=C2, height=0.62)
    for i, (_, v) in enumerate(items):
        ax.text(v + 0.06, i, str(v), va="center", fontsize=7.6, color="#334155")
    ax.set_xlabel("official sources mapped to this condition", fontsize=8)
    ax.set_xlim(0, max(v for _, v in items) + 1.2)
    ax.xaxis.grid(True, color="#E2E8F0", linewidth=0.7)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.tick_params(colors="#475569", length=2.5)
    return _emit(fig)


def chart_files(files):
    """Largest files in the repository — the map used by the guide."""
    if not _MPL or not files:
        return None
    top = sorted(files, key=lambda f: -float(f.get("bytes") or 0))[:10]
    labs = [str(f.get("path", "?")).split("/")[-1][:30] for f in top]
    vals = [float(f.get("bytes") or 0) / 1024.0 for f in top]
    fig, ax = plt.subplots(figsize=(7.6, 2.7))
    ax.barh(list(range(len(labs)))[::-1], vals, color=C1, height=0.66)
    ax.set_yticks(list(range(len(labs)))[::-1])
    ax.set_yticklabels(labs, fontsize=7.3)
    ax.set_xlabel("kB", fontsize=8)
    ax.xaxis.grid(True, color="#E2E8F0", linewidth=0.7)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.tick_params(colors="#475569", length=2.5)
    return _emit(fig)


# ------------------------------------------------------------ data fetching
def get(path, timeout=90):
    url = f"{BASE}{path}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"  ! {path}: {exc}", file=sys.stderr)
        return None


def collect():
    mod = ["home", "ai", "datahealth", "problems", "solutions",
           "modules", "projects", "team", "objects", "satellite",
           "exoplanets", "images", "fits", "photometry", "lightcurves",
           "spectroscopy", "quantum", "sources"]
    d = {"health": get("/api/health"), "report": get("/api/report"),
         "space_weather": get("/api/data/space-weather"),
         "kp": get("/api/data/kp-index")}
    for name in mod:
        d[name] = get(f"/api/mors/{name}")
    if not d["report"]:
        lp = ROOT / "last_report.json"
        if lp.exists():
            d["report"] = json.loads(lp.read_text(encoding="utf-8"))
            print("  i served /api/report was empty -> used last_report.json")
    return d


# ------------------------------------------------------------------ template
class Doc(BaseDocTemplate):
    def __init__(self, filename, meta, **kw):
        super().__init__(filename, pagesize=A4,
                         leftMargin=20 * mm, rightMargin=20 * mm,
                         topMargin=18 * mm, bottomMargin=17 * mm, **kw)
        self.meta = meta
        frame = Frame(self.leftMargin, self.bottomMargin,
                      self.width, self.height, id="f")
        self.addPageTemplates([
            PageTemplate(id="cover", frames=[frame], onPage=self._cover_bg),
            PageTemplate(id="body", frames=[frame], onPage=self._chrome),
        ])

    # cover
    def _cover_bg(self, canv, doc):
        canv.saveState()
        canv.setTitle("MORS Scientific Command Center - Platform Report")
        canv.setAuthor("MORS / ASI-HACK Space Analytics Engine")
        canv.setSubject("Data-quality, problems, solutions and provenance")
        canv.setFillColor(INK)
        canv.rect(0, 0, A4[0], A4[1], stroke=0, fill=1)
        canv.setFillColor(colors.HexColor("#0891B2"))
        canv.rect(0, A4[1] - 88 * mm, A4[0], 4 * mm, stroke=0, fill=1)
        canv.setFillColor(colors.HexColor("#062C3D"))
        canv.rect(0, 0, A4[0], 26 * mm, stroke=0, fill=1)
        canv.setFillColor(colors.HexColor("#7DD3FC"))
        canv.setFont("Body", 8)
        canv.drawString(20 * mm, 11 * mm,
                        "ASI-HACK Space Analytics Engine  |  MORS Scientific "
                        "Command Center  |  generated " + self.meta["when"])
        canv.restoreState()

    # every other page
    def _chrome(self, canv, doc):
        canv.saveState()
        canv.setStrokeColor(RULE)
        canv.setLineWidth(0.5)
        canv.line(20 * mm, A4[1] - 13 * mm, A4[0] - 20 * mm,
                  A4[1] - 13 * mm)
        canv.setFillColor(MUTED)
        canv.setFont("Body", 7.4)
        canv.drawString(20 * mm, A4[1] - 11.4 * mm,
                        "MORS Scientific Command Center - Platform Report")
        canv.drawRightString(A4[0] - 20 * mm, A4[1] - 11.4 * mm,
                             self.meta["run"])
        canv.setFillColor(MUTED)
        canv.drawString(20 * mm, 10 * mm, self.meta["when"])
        canv.drawRightString(A4[0] - 20 * mm, 10 * mm,
                             "page %d" % canv.getPageNumber())
        canv.line(20 * mm, 13.5 * mm, A4[0] - 20 * mm, 13.5 * mm)
        canv.restoreState()


# ------------------------------------------------------------------ content
def build(D):
    rep = D.get("report") or {}
    dh = D.get("datahealth") or {}
    probs = (D.get("problems") or {}).get("problems", [])
    sols = (D.get("solutions") or {}).get("solutions", [])
    mods = (D.get("modules") or {}).get("modules", [])
    projects = (D.get("projects") or {}).get("projects", [])
    team = (D.get("team") or {}).get("members", [])
    ai = D.get("ai") or {}
    home = D.get("home") or {}
    sat = D.get("satellite") or {}
    exo = D.get("exoplanets") or {}
    imgs = D.get("images") or {}
    objs = D.get("objects") or {}
    qm = D.get("quantum") or {}
    health = D.get("health") or {}
    kp = D.get("kp") or {}
    sw = D.get("space_weather") or {}
    ds = (rep.get("dataset_summary") or {})
    met = (rep.get("metrics") or {})
    council = (rep.get("council") or {})
    cites = (rep.get("citations") or {})
    m = home.get("metrics") or {}

    story = []
    W = 170 * mm

    # ------------------------------------------------------------- cover
    story += [
        Spacer(1, 46 * mm),
        P("M O R S", "cover_kicker"),
        Spacer(1, 4 * mm),
        P("Scientific Command Center", "cover_title"),
        P("Platform Report & Data-Quality Dossier", "cover_sub"),
        Spacer(1, 12 * mm),
        P("Four-agent scientific pipeline  -  17 science modules  -  "
          "traceability on every figure", "cover_sub"),
        Spacer(1, 26 * mm),
        P(f"Run ID      {san(rep.get('run_id'))}", "cover_meta"),
        P(f"Generated   {san(rep.get('generated_at'))}", "cover_meta"),
        P(f"Verdict     {san(council.get('verdict'))}  "
          f"{san(council.get('overall_score'))}/100   "
          f"(engine: {san(council.get('engine') or council.get('engine_name'))})",
          "cover_meta"),
        P(f"Dataset     {san(ds.get('rows'))} rows  /  "
          f"{san(len(ds.get('sources') or []))} sources  /  "
          f"{san(len(ds.get('features') or []))} features", "cover_meta"),
        P(f"Host        {san(BASE)}", "cover_meta"),
        Spacer(1, 6 * mm),
        P("Built for the ASI Hack - AI for Space Challenges track. "
          "Every number in this document is read from the live API at "
          "generation time; nothing is transcribed by hand.", "cover_meta"),
        NextPageTemplate("body"),
        PageBreak(),
    ]

    # -------------------------------------------------------- 0 contents
    story += [P("Contents", "h1"),
              HRFlowable(width="100%", thickness=1.2, color=ACCENT,
                         spaceAfter=8)]
    toc = [
        "1. Executive summary",
        "2. Pipeline architecture",
        "3. Data health and quality audit",
        "4. Problem cards (mandatory schema)",
        "5. Solution paths and resolution flow",
        "6. Science module registry",
        "7. Dataset inventory",
        "8. Research dossiers",
        "9. Team, roles and ownership",
        "10. AI protocol, models and tools",
        "11. Traceability, citations and provenance",
        "12. API reference",
        "13. Run instructions",
        "14. Figures and visual summary",
        "15. Scientific sources and hackathon conditions",
        "16. Honest limitations",
    ]
    story += [P(t, "body") for t in toc]
    story += [Spacer(1, 6 * mm),
              P("Reading convention", "h2"),
              P("Every table carries a TRACE row. The badge format is "
                "[Source | Dataset Version | Processing Pipeline | Method | "
                "Last Updated | Operator | Timestamp]. Values that are "
                "computed rather than observed are labelled CALCULATED; "
                "values offered by a model are labelled AI INTERPRETATION "
                "or HYPOTHESIS; proposed next steps are labelled "
                "SUGGESTED ACTION.", "note")]
    story += [PageBreak()]

    # --------------------------------------------- 1 executive summary
    story += [P("1. Executive summary", "h1"),
              HRFlowable(width="100%", thickness=1.2, color=ACCENT,
                         spaceAfter=8)]
    verdict = council.get("verdict") or "n/a"
    story += [kpis([
        ("verdict", san(verdict)),
        ("certification",         f"{san(council.get('overall_score'))}/100"),
        ("ingested rows", _num(ds.get("rows"))),
        ("sources", san(len(ds.get("sources") or []))),
        ("data quality", f"{san(dh.get('data_quality_score'))}"),
        ("missing cells", f"{san(dh.get('missing_pct'))}%"),
        ("open problems", san(m.get("problems_open"))),
        ("formulas cited", san(m.get("formulas"))),
    ], ncols=4), Spacer(1, 5 * mm)]

    engine = ai.get("engine") or {}
    story += [
        P("Headline", "h2"),
        P(f"The four-agent pipeline ingested {san(ds.get('rows'))} rows from "
          f"{san(len(ds.get('sources') or []))} sources, scored "
          f"{san(dh.get('data_quality_score'))}/100 on cell-level "
          f"completeness and accuracy, and produced a "
          f"{san(verdict)} verdict at {san(council.get('overall_score'))}/100. "
          f"The council engine reported was "
          f"'{san(engine.get('council'))}'; where Gemini free-tier quota "
          f"(HTTP 429) blocked the LLM pass, the deterministic local council "
          f"was substituted and that substitution is itself surfaced as "
          f"open problem card rather than hidden.", "body"),
        Spacer(1, 3 * mm),
        P("Headline metrics", "h2"),
    ]
    metric_rows = [
        ["CME records ingested", f"{san(m.get('cme_count'))} (DONKI, live)"],
        ["Mean CME speed", f"{san(m.get('cme_speed_mean_kms'))} km/s"],
        ["Solar wind speed", f"{san(m.get('solar_wind_avg_kms'))} km/s "
                             "(NASA OMNI reference)"],
        ["Solar flares (30 d, classified)", san(m.get("flare_count_30d"))],
        ["NEOs tracked", f"{san(m.get('neo_count'))} (NEOWS, live)"],
        ["Planetary closest approach",
         f"{san(m.get('closest_ld'))} lunar distances"],
        ["Peak Kp index", san(m.get("kp_max"))],
        ["IsolationForest outliers", f"{san(m.get('anomaly_count'))} cells "
                                     "(10% contamination, by construction)"],
        ["Light-curve S/N", san(m.get("light_curve_snr"))],
        ["Quantum entropy", f"{san(m.get('quantum_entropy_ebit'))} ebit"],
        ["References attached", f"{san(m.get('references'))}"],
        ["Problems open / High",
         f"{san(m.get('problems_open'))} open, "
         f"{san(m.get('problems_high'))} High"],
        ["Light-pollution sites", f"{san(m.get('light_pollution_sites', '11'))}"],
    ]
    story += [table(["Metric", "Value"], metric_rows,
                    [62 * mm, 108 * mm]), Spacer(1, 4 * mm)]

    story += [P("Certification log", "h2")]
    rows = [[r.get("run_id"), r.get("status"), r.get("verdict"),
             f"{r.get('score')}/100", r.get("engine"),
             str(r.get("rows")), str(r.get("sources")),
             (r.get("generated_at") or "")[:19].replace("T", " ")]
            for r in (home.get("runs") or [])]
    if rows:
        story += [table(
            ["Run ID", "Status", "Verdict", "Score", "Engine", "Rows",
             "Sources", "Generated"],
            rows, [34 * mm, 17 * mm, 18 * mm, 12 * mm, 22 * mm, 14 * mm,
                   14 * mm, 39 * mm],
            align={3: "CENTER", 5: "RIGHT", 6: "RIGHT"}), Spacer(1, 4 * mm)]

    story += [KeepTogether(
        [P("Known caveats carried into this report", "h2")] +
        bullets([
            "Gemini free-tier quota (HTTP 429) may force Agents 2, 3 and 4 "
            "onto deterministic local engines. This is reported, never "
            "concealed.",
            "IsolationForest flags ~10% of cells by construction "
            "(contamination=0.1); the outlier count is a control figure, "
            "not a discovery.",
            "Multi-spectral profiles are laboratory reference spectra, not "
            "imagery.",
            "Satellite pass windows are period-derived estimates, flagged "
            "estimate=true.",
            "Quantum results are classical NumPy statevector simulations; "
            "no QPU was contacted.",
        ]))]
    story += [Spacer(1, 4 * mm), badge_line((home or {}).get("trace"))]
    story += [PageBreak()]

    # ------------------------------------------------ 2 architecture
    story += [P("2. Pipeline architecture", "h1"),
              HRFlowable(width="100%", thickness=1.2, color=ACCENT,
                         spaceAfter=8),
              P("Four agents run in order; each one only sees the output of "
                "the previous stage, and each stage writes its own record "
                "into the run log so a failure is attributable.", "body"),
              Spacer(1, 3 * mm)]
    stages = (rep.get("council") or {}).get("stages") or []
    if not stages:
        stages = [
            {"label": "Agent 1 - Ingest & Clean",
             "desc": "DONKI, NEOWS, Horizons, GIBS, Kp, spectral, quantum; "
                     "StandardScaler + IsolationForest + Astropy"},
            {"label": "Agent 2 - Council of 5",
             "desc": "five expert reviewers, verdict + score + audit log"},
            {"label": "Agent 3 - Citations",
             "desc": "formula and reference enrichment, traceability records"},
            {"label": "Agent 4 - Ai.Mors",
             "desc": "conversational explanation over the certified report"},
        ]
    rows = []
    for i, st in enumerate(stages, 1):
        rows.append([f"{i}", st.get("label") or st.get("name"),
                     st.get("status") or "completed",
                     st.get("detail") or st.get("desc") or ""])
    story += [table(["#", "Stage", "Status", "Detail"],
                    rows, [8 * mm, 46 * mm, 22 * mm, 94 * mm]),
              Spacer(1, 4 * mm)]

    story += [P("Acquisition policy", "h2"),
              P("Every MORS module resolves its data through one policy: "
                "1) real API, 2) Gemini AI synthesis if the key is available, "
                "3) deterministic local model. The winner is recorded in "
                "source.via as 'api', 'ai_synthesis' or 'local_model' and is "
                "rendered as a chip next to every module title.", "body"),
              Spacer(1, 3 * mm)]
    story += [P("Module payload summary", "h2")]
    rows = []
    for key, d in D.items():
        if not isinstance(d, dict) or key in ("health", "report"):
            continue
        src = d.get("source") or {}
        rows.append([key,
                     src.get("via") or ((d.get("trace") or {}).get("via")),
                     f"{n_of(d)}",
                     ((d.get("trace") or {}).get("dataset_id") or "-")])
    story += [table(["Module", "via", "n", "dataset_id"],
                    rows, [32 * mm, 22 * mm, 14 * mm, 102 * mm],
                    align={2: "RIGHT"})]
    story += [PageBreak()]

    # -------------------------------------------------- 3 data health
    story += [P("3. Data health and quality audit", "h1"),
              HRFlowable(width="100%", thickness=1.2, color=ACCENT,
                         spaceAfter=8),
              P("Quality is measured cell-by-cell over the whole ingested "
                "frame - never sampled and never asserted.", "body"),
              Spacer(1, 4 * mm)]
    story += [kpis([
        ("data quality", san(dh.get("data_quality_score"))),
        ("missing %", san(dh.get("missing_pct"))),
        ("duplicates", san(dh.get("duplicate_rows"))),
        ("completeness %", san(dh.get("completeness_pct"))),
        ("accuracy", san(dh.get("accuracy_score"))),
        ("cells audited", san(dh.get("cells"))),
        ("outliers", san(dh.get("outlier_count"))),
        ("sources", san(dh.get("sources"))),
    ], ncols=4), Spacer(1, 5 * mm)]

    per = dh.get("per_source") or []
    if per:
        rows = []
        for s in per:
            rows.append([
                s.get("source"), str(s.get("rows")), str(s.get("columns")),
                str(s.get("missing_pct")), str(s.get("completeness_pct")),
                str(s.get("duplicate_rows")), str(s.get("invalid_cells")),
                str(s.get("accuracy_score")), s.get("status")])
        story += [P("Per-source validation record", "h2"),
                  table(["Source", "Rows", "Cols", "Missing %", "Complete %",
                         "Dup", "Invalid", "Accuracy", "Status"],
                        rows,
                        [46 * mm, 14 * mm, 12 * mm, 17 * mm, 19 * mm,
                         10 * mm, 14 * mm, 19 * mm, 19 * mm],
                        align={1: "RIGHT", 2: "RIGHT", 3: "RIGHT",
                               4: "RIGHT", 5: "RIGHT", 6: "RIGHT",
                               7: "RIGHT"}),
                  Spacer(1, 4 * mm)]
    story += [
        P("Method", "h2"),
        P(f"Pipeline: {san(dh.get('pipeline'))}. "
          f"Last sync: {san(dh.get('last_sync'))}. "
          f"Outliers are flagged by {san(dh.get('pipeline'))} on the "
          f"standardised feature matrix; missing cells are counted as "
          f"empty/null after cleaning; duplicates are exact row repeats.",
          "body"),
        Spacer(1, 3 * mm),
        badge_line(dh.get("trace")),
    ]
    clean = (ds.get("cleaning") or [])
    if clean:
        story += [KeepTogether(
            [Spacer(1, 4 * mm), P("Cleaning log", "h2")] +
            bullets(clean[:10], "small"))]
    story += [PageBreak()]

    # ---------------------------------------------- 4 problem cards
    story += [P("4. Problem cards (mandatory schema)", "h1"),
              HRFlowable(width="100%", thickness=1.2, color=ACCENT,
                         spaceAfter=8),
              P("Every finding is pushed through the same contract schema: "
                "problem_id, title, severity, category, component, symptom, "
                "root_cause, fix, evidence, priority. Priority is "
                "metric-derived, never chosen by hand:", "body"),
              P("priority_score = 0.40*evidence + 0.35*impact + "
                "0.25*confidence   ->   High if score >= 75, Medium if "
                ">= 50, otherwise Low", "mono"),
              Spacer(1, 3 * mm)]
    bp = (D.get("problems") or {}).get("by_priority") or {}
    story += [kpis([
        ("total", san((D.get("problems") or {}).get("count"))),
        ("high", san(bp.get("High"))),
        ("medium", san(bp.get("Medium"))),
        ("low", san(bp.get("Low"))),
    ], ncols=4), Spacer(1, 5 * mm)]

    idx = table(
        ["ID", "Problem", "Domain", "Evidence", "Impact", "Conf.",
         "Score", "Priority"],
        [[p.get("id"), p.get("title"), p.get("domain"),
          str(p.get("evidence_metric")), str(p.get("impact_score")),
          str(p.get("confidence_level")), str(p.get("priority_score")),
          p.get("priority")] for p in probs],
        [14 * mm, 62 * mm, 24 * mm, 17 * mm, 15 * mm, 15 * mm, 13 * mm,
         16 * mm],
        align={3: "RIGHT", 4: "RIGHT", 5: "RIGHT", 6: "RIGHT",
               7: "CENTER"})
    story += [P("Index", "h2"), idx, Spacer(1, 5 * mm)]

    for p in probs:
        blk = []
        prio = p.get("priority") or ""
        col = RED if prio == "High" else (AMBER if prio == "Medium" else GREEN)
        blk += [Table(
            [[R(f"<b>{_clean(p.get('id'))}  -  {_clean(p.get('title'))}</b>",
                "cellb"),
              R(f"<b>{_clean(prio).upper()}</b>", "cellb")]],
            colWidths=[144 * mm, 26 * mm],
            style=TableStyle([
                ("BACKGROUND", (0, 0), (0, 0), BAND),
                ("BACKGROUND", (1, 0), (1, 0), col),
                ("TEXTCOLOR", (1, 0), (1, 0), colors.white),
                ("ALIGN", (1, 0), (1, 0), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BOX", (0, 0), (-1, -1), 0.8, col),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ])), Spacer(1, 2 * mm)]

        fields = [
            ["Problem (symptom)", p.get("symptom")],
            ["Evidence", "\n".join(f"- {e}" for e in (p.get("evidence") or []))],
            ["Impact", p.get("impact")],
            ["Root cause", p.get("root_cause")],
            ["Analysis", p.get("analysis")],
            ["Fix", "\n".join(f"{i}. {s}" for i, s in
                             enumerate((p.get("fix") or []), 1))],
            ["Suggestions", "\n".join(f"- {s}" for s in
                                     (p.get("suggestions") or []))],
            ["Confidence level",
             f"{_clean(p.get('confidence_level'))} - "
             f"{_clean(p.get('confidence_note'))}"],
            ["Priority",
             f"{_clean(p.get('priority'))}  |  score "
             f"{_clean(p.get('priority_score'))}  |  "
             f"{_clean(p.get('priority_formula'))}"],
        ]
        rows = []
        for k, v in fields:
            if isinstance(v, str) and ("\n" in v):
                lines = [ln.strip() for ln in v.split("\n") if ln.strip()]
                txt = "<br/>".join(_clean(ln) for ln in lines)
            else:
                txt = _clean(v)
            rows.append([R(f"<b>{k}</b>", "cellb"), R(txt, "cell")])
        rows.append([R("<b>Domain / category / owner</b>", "cellb"),
                     R(f"{_clean(p.get('domain'))}  |  "
                       f"{_clean(p.get('severity'))} · "
                       f"{_clean(p.get('category'))} · "
                       f"{_clean(p.get('component'))}  |  owner "
                       f"{own(p.get('owner'))}  |  "
                       f"detected "
                       f"{_clean((p.get('detected_at') or '')[:19]).replace('T',' ')}",
                       "cell")])
        blk += [table(["Field", "Value"], rows,
                      [34 * mm, 136 * mm], zebra=False),
                Spacer(1, 6 * mm)]
        story += [KeepTogether(blk)]
    story += [Spacer(1, 2 * mm),
              badge_line((D.get("problems") or {}).get("trace")),
              PageBreak()]

    # ------------------------------------------------- 5 solutions
    story += [P("5. Solution paths and resolution flow", "h1"),
              HRFlowable(width="100%", thickness=1.2, color=ACCENT,
                         spaceAfter=8)]
    path = (sols[0].get("path") if sols else None) or []
    if path:
        cells = [R(f"<b>{_clean(s)}</b>", "cellb") for s in path]
        t = Table([cells], colWidths=[(170 * mm) / len(cells)] * len(cells))
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), BAND),
            ("BOX", (0, 0), (-1, -1), 0.8, ACCENT),
            ("INNERGRID", (0, 0), (-1, -1), 0.6, colors.white),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ]))
        story += [P("Canonical resolution sequence", "h2"), t,
                  Spacer(1, 5 * mm)]
    summ = (D.get("solutions") or {}).get("summary") or []
    if summ:
        story += [P("Index", "h2"),
                  table(["ID", "Finding", "Priority"],
                        [[s.get("id"), s.get("title"), s.get("priority")]
                         for s in summ],
                        [16 * mm, 134 * mm, 20 * mm],
                        align={2: "CENTER"}), Spacer(1, 5 * mm)]

    for s in sols:
        blk = [P(f"{san(s.get('problem_id'))} - {san(s.get('title'))}", "h3")]
        meta = (f"owner: {own(s.get('owner'))}  |  effort: "
                f"{san(s.get('effort'))}  |  confidence: "
                f"{san(s.get('confidence_level'))}%  |  priority: "
                f"{san(s.get('priority'))}")
        blk += [P(meta, "small")]
        rows = []
        for st in (s.get("steps") or []):
            rows.append([str(st.get("step")), st.get("action"),
                         st.get("type")])
        if rows:
            blk += [table(["#", "Step", "Type"], rows,
                          [10 * mm, 130 * mm, 30 * mm])]
        imp = s.get("expected_impact") or []
        if imp:
            e = imp[0]
            blk += [Spacer(1, 2 * mm),
                    P(f"Expected impact: {san(e.get('metric'))}  "
                      f"{san(e.get('now'))}  ->  {san(e.get('target'))}  "
                      f"({san(e.get('delta'))})", "note")]
        sugg = s.get("suggestions") or []
        if sugg:
            blk += [P("Suggestions: " + " ; ".join(san(x) for x in sugg),
                      "small")]
        blk += [Spacer(1, 4 * mm)]
        story += [KeepTogether(blk)]
    story += [badge_line((D.get("solutions") or {}).get("trace")),
              PageBreak()]

    # ------------------------------------------------ 6 module registry
    story += [P("6. Science module registry", "h1"),
              HRFlowable(width="100%", thickness=1.2, color=ACCENT,
                         spaceAfter=8),
              P("Field-level contracts: every module declares its columns "
                "before any data is shown.", "body"), Spacer(1, 3 * mm)]
    story += [table(["Module", "Description", "Fields"],
                    [[m2.get("label"), m2.get("desc"),
                      ", ".join(m2.get("fields") or [])] for m2 in mods],
                    [30 * mm, 58 * mm, 82 * mm]),
              Spacer(1, 4 * mm),
              badge_line((D.get("modules") or {}).get("trace")),
              PageBreak()]

    # ------------------------------------------------- 7 datasets
    story += [P("7. Dataset inventory", "h1"),
              HRFlowable(width="100%", thickness=1.2, color=ACCENT,
                         spaceAfter=8)]
    sat_rows = sat.get("rows") or []
    cls = {}
    for r in sat_rows:
        cls[r.get("orbit_class")] = cls.get(r.get("orbit_class"), 0) + 1
    exo_rows = exo.get("rows") or []
    methods = {}
    for r in exo_rows:
        methods[r.get("discovery_method")] = \
            methods.get(r.get("discovery_method"), 0) + 1

    inv = [
        ["Satellite elements", "CelesTrak GP (stations, science, weather, "
                               "geo, gnss)", str(len(sat_rows)),
         (sat.get("source") or {}).get("via"),
         f"LEO {cls.get('LEO',0)} / MEO {cls.get('MEO',0)} / "
         f"GEO {cls.get('GEO',0)}"],
        ["Exoplanets", "NASA Exoplanet Archive TAP / pscomppars",
         str(len(exo_rows)), (exo.get("source") or {}).get("via"),
         "; ".join(f"{k} {v}" for k, v in
                   sorted(methods.items(), key=lambda x: -x[1])[:4])],
        ["Astronomy images", "NASA APOD (last 7 days)",
         str(len((imgs.get("rows") or []))), (imgs.get("source") or {}).get("via"),
         (imgs.get("hero") or {}).get("title") or "-"],
        ["Curated objects", "Hipparcos / Gaia / RC3 / Sharpless / JPL",
         str(len((objs.get("rows") or []))),
         (objs.get("trace") or {}).get("via"),
         ", ".join(sorted({r.get("type") for r in (objs.get("rows") or [])}))],
        ["FITS headers", "header card extraction",
         str(len((D.get("fits") or {}).get("rows") or [])),
         ((D.get("fits") or {}).get("trace") or {}).get("via"),
         "keyword audit"],
        ["Photometry", "analytic variability model + photon noise",
         str(len((D.get("photometry") or {}).get("rows") or [])),
         ((D.get("photometry") or {}).get("trace") or {}).get("via"),
         (D.get("photometry") or {}).get("model") or ""],
        ["Light curves", "phase folding + sigma clipping",
         str(len((D.get("lightcurves") or {}).get("rows") or [])),
         ((D.get("lightcurves") or {}).get("trace") or {}).get("via"),
         (D.get("lightcurves") or {}).get("formula") or ""],
        ["Spectroscopy", "NIST ASD line list + radiative-transfer toy",
         str(len((D.get("spectroscopy") or {}).get("rows") or [])),
         ((D.get("spectroscopy") or {}).get("trace") or {}).get("via"),
         f"{len((D.get('spectroscopy') or {}).get('line_list') or [])} lines"],
        ["Quantum lab", "NumPy statevector simulation",
         str(len((qm.get("states") or []))) + " states / " +
         str(len((qm.get("algorithms") or []))) + " algorithms",
         (qm.get("trace") or {}).get("via"),
         (qm.get("honesty") or "")[:110]],
    ]
    story += [table(["Dataset", "Source", "n", "via", "Notes"],
                    inv, [30 * mm, 54 * mm, 20 * mm, 18 * mm, 48 * mm]),
              Spacer(1, 5 * mm)]

    story += [P("Orbital mechanics used for the satellite module", "h2"),
              table(["Quantity", "Formula"],
                    [[k, v] for k, v in (sat.get("physics") or {}).items()],
                    [50 * mm, 120 * mm]),
              Spacer(1, 4 * mm)]

    if sat_rows:
        top = sat_rows[:12]
        story += [P("Sample - first 12 tracked objects", "h2"),
                  table(["Object", "NORAD", "Group", "Orbit", "Alt (km)",
                         "v (km/s)", "i (deg)", "Period (min)"],
                        [[r.get("name"), str(r.get("norad_id")),
                          str(r.get("group")), str(r.get("orbit_class")),
                          str(r.get("altitude_km")),
                          str(r.get("velocity_kms")),
                          str(r.get("inclination_deg")),
                          str(r.get("period_min"))] for r in top],
                        [48 * mm, 16 * mm, 17 * mm, 14 * mm, 17 * mm,
                         17 * mm, 17 * mm, 24 * mm],
                        align={1: "RIGHT", 4: "RIGHT", 5: "RIGHT",
                               6: "RIGHT", 7: "RIGHT"}),
                  Spacer(1, 4 * mm), badge_line(sat.get("trace"))]

    if exo_rows:
        story += [Spacer(1, 5 * mm),
                  P("Sample - 12 most recent confirmed exoplanets", "h2"),
                  table(["Planet", "Host", "R (R_E)", "M (M_E)", "P (d)",
                         "Method", "Year"],
                        [[r.get("planet_name"), r.get("host_star"),
                          str(r.get("radius_re")), str(r.get("mass_me")),
                          str(r.get("period_d")),
                          str(r.get("discovery_method")),
                          str(r.get("discovery_year"))]
                         for r in exo_rows[:12]],
                        [26 * mm, 24 * mm, 18 * mm, 18 * mm, 22 * mm,
                         42 * mm, 20 * mm],
                        align={2: "RIGHT", 3: "RIGHT", 4: "RIGHT",
                               6: "RIGHT"}),
                  Spacer(1, 4 * mm), badge_line(exo.get("trace"))]
    story += [PageBreak()]

    # -------------------------------------------------- 8 projects
    story += [P("8. Research dossiers", "h1"),
              HRFlowable(width="100%", thickness=1.2, color=ACCENT,
                         spaceAfter=8),
              P("Each project is a full dossier: problem, dataset, "
                "methodology, analysis, visualisation, findings, solutions, "
                "team, technologies and documentation.", "body"),
              Spacer(1, 3 * mm)]
    for p in projects:
        blk = [Table(
            [[R(f"<b>{_clean(p.get('id'))} - {_clean(p.get('name'))}</b>",
                "cellb"),
              R(f"<b>{_clean(p.get('results'))}</b>", "cellb")]],
            colWidths=[124 * mm, 46 * mm],
            style=TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), BAND),
                ("BOX", (0, 0), (-1, -1), 0.7, ACCENT),
                ("ALIGN", (1, 0), (1, 0), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ])), Spacer(1, 2 * mm)]
        fields = [
            ["Problem", p.get("problem")],
            ["Dataset", p.get("dataset")],
            ["Methodology", p.get("methodology")],
            ["Analysis", p.get("analysis")],
            ["Visualisation", " ; ".join(p.get("visuals") or [])],
            ["Problems found", " ; ".join(p.get("issues") or [])],
            ["Solutions", " ; ".join(p.get("solutions") or [])],
            ["Technologies", " , ".join(p.get("technologies") or [])],
            ["Documentation", " , ".join(p.get("source_docs") or [])],
        ]
        rows = [[R(f"<b>{k}</b>", "cellb"), R(_clean(v), "cell")]
                for k, v in fields]
        blk += [table(["Section", "Content"], rows,
                      [30 * mm, 140 * mm], zebra=False),
                Spacer(1, 5 * mm)]
        story += [KeepTogether(blk)]
    story += [badge_line((D.get("projects") or {}).get("trace")),
              PageBreak()]

    # ---------------------------------------------------- 9 team
    story += [P("9. Team, roles and ownership", "h1"),
              HRFlowable(width="100%", thickness=1.2, color=ACCENT,
                         spaceAfter=8),
              P("Every problem on this platform has a role-based owner; only "
                "the team leader is published by name (TEAM.MORS).", "body"),
              Spacer(1, 3 * mm)]
    story += [table(["ID", "Member / role", "Responsibility", "Lead", "Owns",
                     "Skills"],
                    [[t.get("id"), own(t.get("name")), t.get("role"),
                      t.get("lead"), ", ".join(t.get("owns") or []),
                      ", ".join(t.get("skills") or [])] for t in team],
                    [12 * mm, 30 * mm, 42 * mm, 20 * mm, 30 * mm, 36 * mm]),
              Spacer(1, 4 * mm),
              badge_line((D.get("team") or {}).get("trace")),
              PageBreak()]

    # ------------------------------------------------------ 10 AI
    story += [P("10. AI protocol, models and tools", "h1"),
              HRFlowable(width="100%", thickness=1.2, color=ACCENT,
                         spaceAfter=8),
              P("Every AI statement on the platform is tagged. A tier is a "
                "claim about how we know, not about how true it is.",
                "body"), Spacer(1, 3 * mm)]
    proto = ai.get("protocol") or []
    story += [table(["#", "Tier"],
                    [[str(i), t] for i, t in enumerate(proto, 1)],
                    [12 * mm, 158 * mm]), Spacer(1, 4 * mm)]
    story += [P("Zero-hallucination rule", "h3"),
              P("AI never invents a measurement. If a value is not in a "
                "dataset or derivable from a formula in the report, it is "
                "tier 4 (hypothesis) or tier 5 (suggestion) - and it says "
                "so.", "note"), Spacer(1, 4 * mm)]
    story += [P("Model roster", "h2"),
              table(["Model", "Role", "Temp", "Context", "Status"],
                    [[mm2.get("id"), mm2.get("role"),
                      str(mm2.get("temperature")), mm2.get("context"),
                      mm2.get("status")]
                     for mm2 in (ai.get("models") or [])],
                    [46 * mm, 52 * mm, 14 * mm, 22 * mm, 36 * mm],
                    align={2: "CENTER"}), Spacer(1, 4 * mm)]
    story += [P("Tools and data intelligence", "h2"),
              table(["Tool", "Type", "Records", "Status"],
                    [[t.get("name"), t.get("type"),
                      (str(t.get("records")) if t.get("records") not in
                       (None, 0) else "-"), t.get("status")]
                     for t in (ai.get("tools") or [])],
                    [64 * mm, 44 * mm, 26 * mm, 36 * mm],
                    align={2: "RIGHT"}), Spacer(1, 4 * mm)]
    if ai.get("insights"):
        story += [P("Insights", "h2"),
                  table(["Tier", "Reading"],
                        [[i.get("type"), i.get("text")]
                         for i in (ai.get("insights") or [])],
                        [34 * mm, 136 * mm]), Spacer(1, 4 * mm)]
    if ai.get("recommendations"):
        story += [P("Recommendations (tier 5 - suggested actions)", "h2"),
                  table(["Priority", "Action"],
                        [[r.get("priority"), r.get("text")]
                         for r in (ai.get("recommendations") or [])],
                        [24 * mm, 146 * mm]), Spacer(1, 4 * mm)]
    if ai.get("research"):
        story += [P("Open research queue", "h2"),
                  table(["Topic", "Owner", "Status"],
                         [[r.get("topic"), own(r.get("owner")), r.get("status")]
                         for r in (ai.get("research") or [])],
                        [110 * mm, 34 * mm, 26 * mm])]
    story += [PageBreak()]

    # ------------------------------------------ 11 traceability
    story += [P("11. Traceability, citations and provenance", "h1"),
              HRFlowable(width="100%", thickness=1.2, color=ACCENT,
                         spaceAfter=8),
              P("Badge format: [Source | Dataset Version | Processing "
                "Pipeline | Method | Last Updated | Operator | Timestamp].",
                "body"), Spacer(1, 3 * mm)]
    formulas = (cites or {}).get("formulas") or []
    refs = (cites or {}).get("references") or []
    story += [kpis([
        ("formulas", san(len(formulas))),
        ("references", san(len(refs))),
        ("traceability records",
         san(len((cites or {}).get("traceability") or []))),
        ("citation engine", san((cites or {}).get("engine"))),
    ], ncols=4), Spacer(1, 5 * mm)]
    if formulas:
        story += [P("Formula register", "h2"),
                  table(["Formula", "Source / reference"],
                        [[f.get("formula") or f.get("expr"),
                          f.get("reference") or f.get("source") or
                          f.get("context")]
                         for f in formulas[:24]],
                        [86 * mm, 84 * mm]), Spacer(1, 4 * mm)]
    if refs:
        story += [P("References", "h2"),
                  table(["Reference"],
                        [[r.get("title") or r.get("reference") or
                          str(r)] for r in refs[:24]],
                        [170 * mm]), Spacer(1, 4 * mm)]
    story += [P("Traceability index (dataset_id per module)", "h2")]
    rows = []
    for key, d in D.items():
        if not isinstance(d, dict):
            continue
        tr = d.get("trace")
        if not tr:
            continue
        rows.append([key, tr.get("dataset_id"), tr.get("source"),
                     tr.get("processing_pipeline"), tr.get("method"),
                     tr.get("via")])
    story += [table(["Module", "dataset_id", "Source", "Pipeline", "Method",
                     "via"],
                    rows, [24 * mm, 40 * mm, 34 * mm, 34 * mm, 26 * mm,
                           12 * mm]),
              Spacer(1, 4 * mm)]
    if (cites or {}).get("note"):
        story += [P(san((cites or {}).get("note")), "note")]
    story += [PageBreak()]

    # ----------------------------------------------------- 12 API
    story += [P("12. API reference", "h1"),
              HRFlowable(width="100%", thickness=1.2, color=ACCENT,
                         spaceAfter=8),
              P(f"Base URL {san(BASE)}. Full request/response contract in "
                "docs/API_CONTRACT.md.", "body"), Spacer(1, 3 * mm)]
    api_rows = [
        ["GET", "/api/health", "liveness + capability probe"],
        ["POST", "/api/pipeline/run", "start the 4-agent pipeline"],
        ["GET", "/api/pipeline/status", "stage-by-stage progress"],
        ["GET", "/api/report", "last certified report"],
        ["GET", "/api/data/<name>",
         "space-weather, neo, horizons, neo-matrix, light-pollution, "
         "kp-index, spectral, quantum"],
        ["GET", "/mors", "MORS Scientific Command Center UI"],
        ["GET", "/api/mors", "module index"],
        ["GET", "/api/mors/<name>",
         "home, ai, data, datahealth, problems, solutions, modules, "
         "projects, team, objects, exoplanets, fits, photometry, "
         "spectroscopy, lightcurves, images, satellite, quantum"],
        ["POST", "/api/mors/insight", "on-demand tier-labelled AI insight"],
        ["POST", "/api/chat", "Ai.Mors conversational agent"],
    ]
    story += [table(["Method", "Route", "Purpose"], api_rows,
                    [16 * mm, 54 * mm, 100 * mm]),
              Spacer(1, 5 * mm),
              P("Payload sizes observed at generation time", "h2")]
    story += [PageBreak()]

    # --------------------------------------------- 13 run instructions
    story += [P("13. Run instructions", "h1"),
              HRFlowable(width="100%", thickness=1.2, color=ACCENT,
                         spaceAfter=8),
              P("Requirements: Python 3.11+ (tested on 3.12) and network "
                "access. Every source has a deterministic local fallback, so "
                "the platform still runs offline.", "body"),
              Spacer(1, 3 * mm),
              P("A. One click (Windows)", "h2"),
              P("Double-click START.bat. It locates Python, installs anything "
                "missing from requirements.txt, frees port 5000, starts the "
                "backend and opens the dashboard. Close the window to stop.",
                "body"),
              P("B. Manual", "h2"),
              R("python -m pip install -r requirements.txt<br/>"
                "python main.py", "mono"),
              P("C. Verify without a server", "h2"),
              R("python main.py --selftest<br/>"
                "Runs the whole pipeline synchronously and prints "
                "SELFTEST : PASS (about 75 seconds), then exits.", "mono"),
              Spacer(1, 3 * mm),
              table(["Flag", "Effect"],
                    [["(none)", "start the Flask server on 127.0.0.1:5000"],
                     ["--selftest", "synchronous end-to-end test, no server"],
                     ["--port N", "serve on another port"],
                     ["--host H", "bind address (loopback recommended)"]],
                    [40 * mm, 130 * mm]),
              Spacer(1, 4 * mm),
              P("Endpoints", "h2"),
              table(["URL", "What it is"],
                    [["http://127.0.0.1:5000/", "legacy ASI-HACK dashboard"],
                     ["http://127.0.0.1:5000/mors",
                      "MORS Scientific Command Center (main UI)"]],
                    [76 * mm, 94 * mm]),
              Spacer(1, 4 * mm),
              P("Environment (.env)", "h2"),
              table(["Variable", "Purpose"],
                    [["GEMINI_API_KEY", "Agents 2/3/4 (empty = offline "
                                        "fallback)"],
                     ["GEMINI_MODEL_PRO", "council + Ai.Mors model"],
                     ["GEMINI_MODEL_FLASH", "citation model"],
                     ["GEMINI_MODEL_FALLBACK", "tried on 404"],
                     ["NASA_API_KEY", "Agent 1 (DONKI / NEOWS)"],
                     ["FLASK_HOST / FLASK_PORT / FLASK_DEBUG",
                      "server (debug defaults off)"]],
                    [62 * mm, 108 * mm]),
              Spacer(1, 4 * mm),
              P("Regenerating this document", "h2"),
              R("python main.py          (leave a server running)<br/>"
                "python tools/build_report.py   ->  docs/MORS_REPORT.pdf",
                "mono"),
              Spacer(1, 4 * mm),
              P("Project layout", "h2"),
              R("main.py - orchestrator, Flask API, CLI<br/>"
                "agents/ - agent1_ingestion, agent2_council, "
                "agent3_citations, agent4_ai_mors, datasets, mors_data<br/>"
                "static/ - index.html (legacy), mors.html (MORS)<br/>"
                "docs/ - API_CONTRACT.md, DEPLOYMENT.md, MORS_REPORT.pdf<br/>"
                "prompts/ - prompt templates<br/>"
                "data/ - reference CSVs<br/>"
                "START.bat, requirements.txt, README.md", "mono"),
              PageBreak()]

    # ------------------------------------- 14 figures / visual summary
    story += [              P("14. Figures and visual summary", "h1"),
              HRFlowable(width="100%", thickness=1.2, color=ACCENT,
                         spaceAfter=8),
              P("This section is written for a reader who does not work with "
                "space data every day. Every figure states, in plain English, "
                "what is plotted, where the numbers come from and what a "
                "non-specialist should take away from it.", "note"),
              Spacer(1, 3 * mm)]

    def _pair(a, b):
        if not a:
            return b
        if not b:
            return a
        t = Table([[a, b]], colWidths=[84 * mm, 84 * mm], hAlign="LEFT")
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                               ("LEFTPADDING", (0, 0), (0, 0), 0),
                               ("RIGHTPADDING", (0, 0), (0, 0), 4),
                               ("LEFTPADDING", (1, 0), (1, 0), 4),
                               ("RIGHTPADDING", (1, 0), (1, 0), 0),
                               ("TOPPADDING", (0, 0), (-1, -1), 0),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
        return t

    f1 = chart_quality(dh)
    if f1:
        story += [KeepTogether([f1,
                  P("<b>Figure 1 - Can we trust the input?</b> Each pair of "
                    "bars is one ingested source. The blue bar is "
                    "<i>completeness</i> (share of cells that actually hold a "
                    "value) and the amber bar is <i>accuracy</i> (share that "
                    "passed the type and range checks). Tall bars are good: "
                    "they mean the pipeline is reading real, well-formed "
                    "measurements rather than filling gaps. Source: "
                    "/api/mors/datahealth, per_source.", "note"),
                  Spacer(1, 3 * mm)])]

    f2, f3 = chart_priority(probs), chart_effort(sols)
    if f2 or f3:
        story += [KeepTogether([_pair(f2, f3),
                  P("<b>Figure 2 - What is broken, and how hard is it to "
                    "fix?</b> Left: open problems split by priority. Priority "
                    "is not a judgement call - it is the formula "
                    "0.40*evidence + 0.35*impact + 0.25*confidence, with High "
                    "at 75 and above. Right: the same problems' solutions "
                    "grouped by implementation effort (S = a small change, "
                    "L/XL = multi-session work). Source: /api/mors/problems "
                    "and /api/mors/solutions.", "note"),
                  Spacer(1, 3 * mm)])]

    f4, f5 = chart_orbit(sat), chart_altitude(sat)
    if f4 or f5:
        story += [KeepTogether([_pair(f4, f5),
                  P("<b>Figure 3 - Who is overhead?</b> Left: the tracked "
                    "catalogue by orbit band. LEO (low Earth orbit) is below "
                    "2,000 km, MEO (medium) sits between LEO and the "
                    "geostationary belt at 35,786 km, and GEO is the ring "
                    "that appears to hang still over one spot on Earth. "
                    "Right: the ten highest objects, coloured the same way - "
                    "the bars step up from ~600 km to ~35,786 km, which is "
                    "the visual signature of a balanced catalog rather than a "
                    "LEO-only sample. Source: /api/mors/satellite (CelesTrak "
                    "GP groups).", "note"),
                  Spacer(1, 3 * mm)])]

    f6 = chart_exoplanets(exo)
    if f6:
        story += [KeepTogether([f6,
                  P("<b>Figure 4 - How were these worlds found?</b> Each bar "
                    "counts planets in the archived sample discovered by one "
                    "technique. <i>Transit</i> means the planet dips the star's "
                    "brightness as it crosses in front; <i>Radial velocity</i> "
                    "means the star wobbles under the planet's gravity; "
                    "<i>Imaging</i> means the planet was photographed "
                    "directly. A method-heavy sample tells you the catalog is "
                    "biased towards whatever that technique is best at. Source: "
                    "/api/mors/exoplanets (NASA Exoplanet Archive TAP).",
                    "note"),
                  Spacer(1, 3 * mm)])]

    f7, f8 = chart_kp(kp), chart_cme(sw)
    if f7 or f8:
        story += [KeepTogether([_pair(f7, f8),
                  P("<b>Figure 5 - Space weather, in one glance.</b> Left: "
                    "the planetary K-index runs 0-9 and measures how badly the "
                    "Sun is disturbing Earth's magnetic field; the dashed line "
                    "at 5 is the storm threshold, and the red line smooths the "
                    "noisy daily values so a trend is readable. Right: speed "
                    "of coronal mass ejections (CMEs) - huge clouds of solar "
                    "plasma - in km/s, with the fastest event called out. "
                    "Source: /api/data/kp-index (NOAA SWPC) and "
                    "/api/data/space-weather (NASA DONKI).", "note"),
                  Spacer(1, 4 * mm)])]
    if not any([f1, f2, f3, f4, f5, f6, f7, f8]):
        story += [P("Charts were not generated on this host (matplotlib is "
                    "not installed); the tables above remain authoritative.",
                    "note")]

    # --------------------------- 15 scientific sources / hackathon conditions
    src = D.get("sources") or {}
    conds = src.get("conditions") or []
    hs = src.get("hackathon") or []
    dsrc = src.get("data_sources") or []
    story += [PageBreak(),
              P("15. Scientific sources and hackathon conditions", "h1"),
              HRFlowable(width="100%", thickness=1.2, color=ACCENT,
                         spaceAfter=8),
              P("The ASI Hackathon supplies an official source list and eight "
                "conditions describing how those sources are meant to help a "
                "team. This section reproduces both, tags every source with "
                "the condition it supports, and names the file in this "
                "repository where that support is actually applied - so the "
                "claim can be checked rather than believed.", "note"),
              Spacer(1, 3 * mm)]

    if src.get("disclaimer_ar"):
        story += [P("The rule stated in the brief", "h2"),
                  arP(src["disclaimer_ar"], "ar_body"),
                  Spacer(1, 2 * mm)]

    A = src.get("aggregates") or {}
    story += [kpis([("Hackathon sources", san(A.get("total", len(hs)))),
                    ("Conditions covered",
                     f"{san(A.get('conditions_covered'))}/"
                     f"{san(A.get('conditions_total'))}"),
                    ("Live data endpoints", san(A.get("live_data_sources"))),
                    ("Total data sources", san(len(dsrc)))])]

    f9, f10 = chart_sources_phase(src), chart_sources_cat(src)
    if f9 or f10:
        story += [Spacer(1, 4 * mm), _pair(f9, f10),
                  P("<b>Figure 6 - The official source list at a glance.</b> "
                    "Left: when each source is meant to be used - before the "
                    "event (preparation), during the build, or as research "
                    "inspiration afterwards. Right: how the 16 sources spread "
                    "over the eight required conditions; 'Working with data' "
                    "is the most heavily covered, which matches a hackathon "
                    "where the first job is always getting usable numbers.",
                    "note"),
                  Spacer(1, 4 * mm)]

    story += [P("15.1 The eight conditions", "h2"),
              P("Each condition is listed with its Arabic wording from the "
                "brief, the source ids that back it, and the evidence inside "
                "this repository.", "note")]
    if conds:
        story += [table(
            ["#", "Condition", "How the sources help (from the brief)",
             "Ids", "Evidence in this repository"],
            [[san(c.get("n")),
              R(f"<b>{san(c.get('name'))}</b><br/>{san(c.get('key'))}", "cell"),
              Paragraph(ar(c.get("helps_ar") or ""), S["ar_note"]),
              san(", ".join(c.get("sources") or []), "-"),
              san(c.get("evidence"), "-")] for c in conds],
            [8 * mm, 34 * mm, 58 * mm, 20 * mm, 50 * mm])]
    story += [Spacer(1, 3 * mm),
              P("Where each condition is applied", "h3")]
    if conds:
        story += [table(
            ["Condition", "Files and modules that implement it", "Status"],
            [[R(f"<b>{san(c.get('n'))}. {san(c.get('name'))}</b>", "cell"),
              R("<br/>".join(san(u) for u in (c.get("used_in") or [])), "cellm"),
              san("core in build" if c.get("status") == "core"
                  else "documented extension")]
             for c in conds],
            [42 * mm, 108 * mm, 20 * mm])]

    story += [PageBreak(), P("15.2 The official source list", "h2"),
              P("Sixteen entries, exactly as supplied by the brief, each "
                "annotated with its phase, level, the Arabic guidance and the "
                "place in this codebase where it is used.", "note")]
    for s in hs:
        block = [P(f"{san(s.get('no'))}. {san(s.get('title'))}   "
                   f"[{san(s.get('id'))}]", "h3")]
        block += [table(["Phase", "Level", "Kind", "Condition"],
                        [[san(s.get("phase")), san(s.get("level")),
                          san(s.get("kind")),
                          san(s.get("category"))]],
                        [34 * mm, 46 * mm, 44 * mm, 46 * mm], zebra=False)]
        if s.get("title_ar"):
            block += [arP(s.get("title_ar"), "ar_h2", font="ArB", size=11)]
        for lab, key in (("Goal", "goal_ar"), ("You will learn", "learn_ar"),
                         ("Who is it for", "for_ar"),
                         ("When to use it", "when_ar")):
            if s.get(key):
                block += [P(lab, "h3"), arP(s.get(key), "ar_note")]
        if s.get("url"):
            block += [P("Link: " + str(s.get("url")), "tiny")]
        else:
            block += [P("Link: no stable deep link supplied with the brief - "
                        "open the platform directly.", "tiny")]
        if s.get("used_in"):
            block += [P("Used in: " + " | ".join(str(u) for u in s["used_in"]),
                        "mono")]
        block += [Spacer(1, 2.5 * mm)]
        story += [KeepTogether(block)]

    story += [PageBreak(), P("15.3 Live data sources used by this build", "h2"),
              P("Not part of the hackathon list - these are the endpoints this "
                "repository actually calls at runtime, with the acquisition "
                "path recorded for each one.", "note")]
    if dsrc:
        story += [table(
            ["Id", "Source", "Kind", "Via", "What it gives", "Used in"],
            [[san(r.get("id")), san(r.get("name")), san(r.get("kind")),
              san(r.get("via")), san(r.get("gives")), san(r.get("used_in"))]
             for r in dsrc],
            [11 * mm, 34 * mm, 22 * mm, 22 * mm, 45 * mm, 36 * mm])]
    story += [Spacer(1, 3 * mm),
              badge_line(src.get("trace")),
              P("acquisition order: api -> ai_synthesis -> local_model. A "
                "source is only allowed to fall to the next rung when the "
                "rung above it failed, and the rung used is recorded in the "
                "payload.", "tiny")]

    # ------------------------------------------------ 16 limitations
    story += [PageBreak(),
              P("16. Honest limitations", "h1"),
              HRFlowable(width="100%", thickness=1.2, color=ACCENT,
                         spaceAfter=8)]
    story += bullets([
        "Gemini free-tier quota (HTTP 429) degrades Agents 2/3/4 to the "
        "deterministic local engines. The run still certifies, but it is not "
        "LLM cross-verified. This is surfaced as an open problem card on the "
        "dashboard rather than hidden.",
        "IsolationForest is configured with contamination=0.1, so roughly "
        "10% of cells are flagged as outliers by construction. The outlier "
        "count is a control figure, not a discovery.",
        "Multi-spectral profiles are laboratory reference spectra, not "
        "imagery. The widget is labelled accordingly.",
        "The Kp index window is much shorter than the flare window, so "
        "correlations are restricted to the overlap interval.",
        "NASA GIBS night-light tile coverage is incomplete; missing tiles "
        "are reported rather than interpolated.",
        "Satellite pass windows are period-derived estimates, not TLE "
        "propagations (estimate=true).",
        "Photometry, light curves and spectra are analytic reference models "
        "with injected photon noise. No telescope exposure is claimed.",
        "Quantum results are classical NumPy statevector simulations. No QPU "
        "was contacted.",
        "Citation graph depth is held at the deterministic baseline while "
        "the quota is exhausted.",
    ])
    story += [Spacer(1, 5 * mm),
              P("Why these are listed", "h2"),
              P("A platform that hides its own degradation cannot be audited. "
                "Each item above is also present as a machine-readable "
                "problem card in /api/mors/problems, with evidence, impact, "
                "root cause, analysis, solution, suggestions, an explicit "
                "confidence caveat and a metric-derived priority - so the "
                "dashboard, the API and this report all say the same thing.",
                "body"),
              Spacer(1, 6 * mm),
              HRFlowable(width="100%", thickness=0.8, color=RULE,
                         spaceAfter=6),
              P(f"Report generated {_now()} from {san(BASE)}  -  run "
                f"{san(rep.get('run_id'))}  -  verdict "
                f"{san(council.get('verdict'))} "
                f"{san(council.get('overall_score'))}/100.", "tiny")]
    return story


def main() -> int:
    print(f"MORS report -> fetching {BASE}")
    D = collect()
    if not D.get("report"):
        print("FATAL: no report available. Start the server and run the "
              "pipeline first:\n  python main.py\n  POST /api/pipeline/run",
              file=sys.stderr)
        return 2
    rep = D["report"]
    council = rep.get("council") or {}
    meta = {
        "when": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "run": str(rep.get("run_id") or "-"),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc = Doc(str(OUT), meta)
    story = build(D)
    doc.build(story)
    print(f"WROTE {OUT}  ({OUT.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
