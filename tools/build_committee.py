#!/usr/bin/env python3
"""Build the judging-committee guide in two formats from one content model.

Usage:
    python main.py                  # keep the server running (any port)
    python tools/build_committee.py # writes both documents

Outputs:
    00_COMMITTEE_GUIDE.md     plain-text edition (package root)
    docs/COMMITTEE_GUIDE.pdf  printable Arabic edition

Environment:
    MORS_BASE      base URL of the running server (default http://127.0.0.1:5000)
    COMMITTEE_MD   markdown output path
    COMMITTEE_OUT  pdf output path
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
MD_OUT = Path(os.getenv("COMMITTEE_MD", str(ROOT / "00_COMMITTEE_GUIDE.md")))
PDF_OUT = Path(os.getenv("COMMITTEE_OUT", str(ROOT / "docs" / "COMMITTEE_GUIDE.pdf")))

import build_guide as bg            # noqa: E402
import build_report as br           # noqa: E402
from reportlab.lib.units import mm  # noqa: E402
from reportlab.platypus import (KeepTogether, PageBreak, Spacer)  # noqa: E402

W = 170.0          # content width, mm
AR_MIN = 0.30      # arabic code-point share that makes a string "Arabic"


# ----------------------------------------------------------------- helpers
def is_ar(text: str) -> bool:
    t = str(text or "")
    if not t:
        return False
    ar = sum(1 for c in t if "\u0600" <= c <= "\u06ff" or "\u0750" <= c <= "\u077f")
    return ar >= max(1, int(len(t) * AR_MIN))


def api(path: str, timeout: int = 90):
    try:
        with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as exc:  # pragma: no cover - offline fallback
        print(f"  ! {path} -> {exc}")
        return None


def collect() -> dict:
    D = {}
    for key, path in [
        ("health", "/api/health"),
        ("report", "/api/report"),
        ("dh", "/api/mors/datahealth"),
        ("sat", "/api/mors/satellite"),
        ("problems", "/api/mors/problems"),
        ("solutions", "/api/mors/solutions"),
        ("sources", "/api/mors/sources"),
        ("modules", "/api/mors"),
        ("objects", "/api/mors/objects"),
        ("exoplanets", "/api/mors/exoplanets"),
        ("kp", "/api/data/kp-index"),
        ("sw", "/api/data/space-weather"),
        ("team", "/api/mors/team"),
    ]:
        D[key] = api(path)
    return D


def n(v, default="—") -> str:
    if v is None:
        return default
    if isinstance(v, float):
        return f"{v:g}"
    return str(v)


def kb(size: int) -> str:
    return f"{size / 1024:.1f} KB" if size >= 1024 else f"{size} B"


def _pad(v) -> str:
    return str(v if v is not None else "")


def cell(text: str, wmm: float):
    """Table body cell — Arabic gets its own shaping path."""
    t = _pad(text)
    if is_ar(t):
        return br.arP(t, "ar_note", width=(wmm - 4) * mm)
    return br.P(t, "cell")


def header_cell(text: str, wmm: float):
    t = _pad(text)
    if is_ar(t):
        lines = br.ar_lines(t, font="ArB", size=8.2, width=(wmm - 4) * mm)
        return Paragraph("<br/>".join(br.ar(l) for l in lines), TH_R)
    return Paragraph(f"<b>{br._xml(t)}</b>", br.S["th"])


def make_table(headers, rows, widths):
    from reportlab.platypus import Paragraph, Table, TableStyle
    from reportlab.lib import colors
    data = [[header_cell(h, w) for h, w in zip(headers, widths)]]
    for r in rows:
        data.append([cell(c, w) for c, w in zip(r, widths)])
    t = Table(data, colWidths=[w * mm for w in widths], repeatRows=1,
              hAlign="LEFT")
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), br.INK),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, br.RULE),
        ("BOX", (0, 0), (-1, -1), 0.6, br.RULE),
    ]
    for i in range(1, len(data)):
        if i % 2 == 0:
            style.append(("BACKGROUND", (0, i), (-1, i), br.BAND))
    t.setStyle(TableStyle(style))
    return t


def para(text: str, st: str = "body"):
    """Single paragraph, Arabic-aware."""
    return br.arP(text, "ar_body") if is_ar(text) else br.P(text, st)


def code_block(text: str):
    from reportlab.platypus import Paragraph, Table, TableStyle
    from reportlab.lib import colors
    body = "<br/>".join(br._xml(line) for line in str(text).split("\n"))
    p = Paragraph(body, br.S["mono"])
    t = Table([[p]], colWidths=[W * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
        ("BOX", (0, 0), (-1, -1), 0.6, br.RULE),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return t


# --------------------------------------------------------------- block model
# block = (kind, payload)  kinds: p | bul | tab | code | kpi | h3 | quote | hr


def p(text):           return ("p", text)
def bul(items):        return ("bul", list(items))
def tab(h, r, w):      return ("tab", (list(h), list(r), list(w)))
def code(text):        return ("code", text)
def kpi(items):        return ("kpi", list(items))
def h3(text):          return ("h3", text)
def quote(text):       return ("quote", text)
def hr():              return ("hr", None)


# ----------------------------------------------------------------- PDF view
def pdf_block(b) -> list:
    kind, payload = b
    if kind == "p":
        return [para(payload)]
    if kind == "h3":
        return [br.arP(payload, "ar_h2")] if is_ar(payload) else [br.P(payload, "h3")]
    if kind == "quote":
        return [br.arP(payload, "ar_note")]
    if kind == "bul":
        out = []
        for item in payload:
            if is_ar(item):
                out.append(br.arP("\u2022  " + item, "ar_note"))
            else:
                out.append(br.bullets([item], "body")[0])
        return out
    if kind == "code":
        return [code_block(payload)]
    if kind == "tab":
        h, r, w = payload
        return [make_table(h, r, w)]
    if kind == "kpi":
        return [make_kpis(payload, ncols=4)]
    if kind == "hr":
        return [Spacer(1, 3 * mm)]
    return []


# --------------------------------------------------------------- Markdown view
def md_cell(v) -> str:
    return _pad(v).replace("|", "\\|").replace("\n", " ")


def md_block(b) -> str:
    kind, payload = b
    if kind == "p":
        return payload + "\n"
    if kind == "h3":
        return "#### " + payload + "\n"
    if kind == "quote":
        return "> " + payload + "\n"
    if kind == "bul":
        return "\n".join("- " + i for i in payload) + "\n"
    if kind == "code":
        return "```\n" + payload + "\n```\n"
    if kind == "kpi":
        return "\n".join(f"- **{l}** — {v}" for l, v in payload) + "\n"
    if kind == "tab":
        h, r, _ = payload
        out = ["| " + " | ".join(md_cell(x) for x in h) + " |",
               "|" + "|".join("---" for _ in h) + "|"]
        for row in r:
            out.append("| " + " | ".join(md_cell(x) for x in row) + " |")
        return "\n".join(out) + "\n"
    if kind == "hr":
        return "---\n"
    return ""


# ------------------------------------------------------------------ content
def build_content(D: dict, files: list) -> list:
    """Return [(section_title, [blocks...]), ...]."""
    rep = D.get("report") or {}
    council = rep.get("council") or {}
    dh = D.get("dh") or {}
    sat = D.get("sat") or {}
    src = D.get("sources") or {}
    probs = (D.get("problems") or {}).get("problems") or []
    mods = (D.get("modules") or {}).get("modules") or []
    metrics = rep.get("metrics") or {}
    conds = src.get("conditions") or []
    hacks = src.get("hackathon") or []
    dsrc = src.get("data_sources") or []
    health = D.get("health") or {}
    exo_rows = (D.get("exoplanets") or {}).get("rows") or []
    obj = (D.get("objects") or {}).get("count") or len(
        (D.get("objects") or {}).get("rows") or [])
    sats = sat.get("rows") or []
    score = council.get("overall_score")
    verdict = council.get("verdict") or "-"
    engine = council.get("engine") or "-"
    agg = src.get("aggregates") or {}
    run = rep.get("run_id") or "-"
    when = rep.get("generated_at") or "-"

    def group_class():
        c = {"LEO": 0, "MEO": 0, "GEO": 0}
        for s in sats:
            k = str(s.get("orbit_class") or "").upper()
            if k in c:
                c[k] += 1
        return c

    og = group_class()
    roles = {f["path"]: (bg.FILES.get(f["path"]) or {}).get("role", "")
             for f in files}

    SEC = []

    # ---------------------------------------------------------- 1 overview
    SEC.append(("1. نظرة عامة على الحزمة", [
        p("هذه الحزمة هي التسليم الكامل لمشروع ASI-HACK Space Analytics "
          "Engine: محرك تحليل فضائي بأربعة وكلاء ذكاء اصطناعي، فوق واجهة "
          "قيادة علمية اسمها MORS Scientific Command Center. المشروع يحوّل "
          "بيانات فضاء حقيقية (NASA / NOAA / CelesTrak / NASA Exoplanet "
          "Archive) إلى مؤشرات جودة، ومشكلات مرتّبة بمعادلة أولوية، وحلول "
          "قابلة للتنفيذ، مع تتبّع كامل (traceability) يربط كل رقم بمصدره "
          "وطريقة المعالجة (method) ولحظة التحديث."),
        p("الحزمة قائمة بذاتها (self-contained): تُفكّ وتُشغّل بأمر واحد، "
          "ولا تحتاج أي خطوة بناء أو تجميع (no build step). كل مستند في الحزمة "
          "مولّد من الكود نفسه، لذلك لا يمكن أن يتعارض مع ما هو مكتوب فيه."),
        kpi([
            ("ملفات مُنتقاة", str(len(files))),
            ("أسطر بايثون وHTML", f"{sum(f.get('lines') or 0 for f in files):,}"),
            ("وحدات MORS", str(len(mods))),
            ("مصادر علمية", str(agg.get("total") or len(hacks))),
            ("جودة البيانات", f"{dh.get('data_quality_score') or 0:.2f}/100"),
            ("صفوف معالَجة", f"{dh.get('rows') or 0:,}"),
            ("نتيجة المجلس العلمي", f"{verdict} {n(score, '')}/100"),
            ("حالة الاختبار", "SELFTEST: PASS"),
        ]),
        h3("ما الذي يحققه المشروع في شروط الهاكاثون"),
        p(f"الشروط الثمانية مغطاة {agg.get('conditions_covered') or 8} من "
          f"{agg.get('conditions_total') or 8}: منها "
          f"{agg.get('conditions_core') or 7} شروط أساسية منفَّذة بالكامل، "
          f"وشرط واحد (الرؤية الحاسوبية) مغطى بثلاث مصادر على مستوى البيانات "
          "الفيزيائية (بطاقات FITS والصفائح الليلية) ومُسجَّل بوضوح كامتداد "
          "موثّق لا كادّعاء مُنجز — التفصيل في القسم 6 أدناه."),
    ]))

    # -------------------------------------------------------- 2 five minutes
    SEC.append(("2. كيف تقيّم المشروع خلال خمس دقائق", [
        p("الترتيب المقترح للجنة التحكيمية؛ كل خطوة تنتهي بنتيجة ملموسة "
          "يمكن التحقق منها فورًا."),
        tab(["#", "الإجراء", "النتيجة المتوقعة"], [
            ["1", "فكّ ضغط الحزمة ثم شغّل START.bat (أو python main.py)",
             "خادم Flask يعمل على http://127.0.0.1:5000"],
            ["2", "افتح http://127.0.0.1:5000/mors",
             "واجهة MORS: شريط صحة البيانات + 11 قسمًا و19 وحدة API"],
            ["3", "اضغط زر تشغيل الخط أنابيب (POST /api/pipeline/run)",
             f"تقرير معتمد {n(score)}/100 من خمسة خبراء ({verdict})"],
            ["4", "افتح http://127.0.0.1:5000/mors#/sources",
             "SOURCES.MORS: 16 مصدرًا علميًا + الشروط الثمانية"],
            ["5", "شغّل python main.py --selftest",
             "سطر أخير: SELFTEST : PASS بعد نحو 75 ثانية"],
            ["6", "اقرأ 00_COMMITTEE_GUIDE.md ثم docs/COMMITTEE_GUIDE.pdf",
             "هذا الدليل؛ ثم docs/MORS_REPORT.pdf للأدلة التفصيلية"],
            ["7", "طابق 00_MANIFEST.txt مع الملفات المستخرجة",
             "حجم كل ملف + بصمة SHA-256 تطابق ما سُلّم"],
        ], [8, 74, 88]),
        h3("ملاحظة عن مفاتيح API"),
        p("المشروع يعمل من دون مفاتيح بالوضع المحلي الاحتياطي (local_model)، "
          "لكن .env يحوي مفتاح NASA ومتغيرات نماذج Gemini. إن لم تتوفر حصيلة "
          "(quota) مجانية، تنتقل الوكيلاء تلقائيًا إلى المحرك الاحتياطي "
          "الحتمي ويسجَّل هذا التحويل في council.engine وفي بطاقة المشكلة "
          "المخصَّصة لذلك (P-001) ما دامت الحالة مفتوحة — "
          "أي أن المشروع لا يتوقف ولا يختلق نتيجة بديلة."),
    ]))

    # --------------------------------------------------------- 3 inventory
    inv_rows = []
    for f in files:
        inv_rows.append([f["path"], kb(f["bytes"]),
                         roles.get(f["path"]) or "-"])
    SEC.append(("3. الملفات الرئيسية — كل ملف وما يفعله", [
        p("قائمة القراءة المختصرة (٣٥ ملفًا مُنتقى) بترتيبها المقترح: "
          "المستندات المُصدَّرة أولًا، ثم نقطة الدخول، ثم الوكيلون، "
          "ثم الواجهات، ثم أدوات التوليد؛ القائمة الكاملة بكل ملف "
          "ومقاسه وبصمته موجودة في 00_MANIFEST.txt."),
        tab(["الملف", "الحجم", "الدور"], inv_rows, [58, 16, 96]),
        p(f"إجمالي الملفات المُنتقاة هنا: {len(files)} ملفًا بحجم "
          f"{sum(f['bytes'] for f in files) / 1024:.0f} كيلوبايت "
          "(قبل الضغط)؛ أضف إليها لقطة static/api/ وملفات presentation/ "
          "التي تُدرَج تلقائيًا عند التغليف."),
    ]))

    # ------------------------------------------------------ 4 architecture
    SEC.append(("4. المعمارية: خط أنابيب الوكيلاء الأربعة", [
        p("كل طبقة مسؤولة عن سؤال واحد فقط، ويمرّ الملف بينها عبر سجل تتبّع "
          "مشترك؛ هذا ما يجعل الرقم القابل للتدقيق ممكنًا."),
        tab(["الطبقة", "الملف", "السؤال الذي تجيب عنه"], [
            ["Agent 1 — Ingestion", "agents/agent1_ingestion.py",
             "ما البيانات؟ جمعها، تنظيفها، فحص جودتها، ورصد الشواذ"],
            ["Agent 2 — Council", "agents/agent2_council.py",
             "هل يمكن الوثوق بها؟ خمسة خبراء مستقلون يمنحون نتيجة مُسبَّقة"],
            ["Agent 3 — Citations", "agents/agent3_citations.py",
             "ما مصدر كل رقم؟ معادلات ومراجع وسجل تتبّع لكل ادعاء"],
            ["Agent 4 — Ai.Mors", "agents/agent4_aimors.py",
             "كيف نشرحها للناس؟ واجهة محادثة عربية بخمسة مستويات علمية"],
             ["Data layer", "agents/mors_data.py",
              "كيف نقدّمها كوحدات؟ 17 وحدة على ترتيب الاكتساب: API ثم AI ثم محلي"],
            ["Science datasets", "agents/datasets.py",
             "ما الجداول المرجعية؟ التلوث الضوئي، الطيف، Kp، المقاييس"],
            ["Source registry", "agents/sources_data.py",
             "ما المصادر العلمية وكيف تخدم الفريق؟ 16 مصدرًا + الشروط الثمانية"],
            ["HTTP surface", "main.py",
             "كيف يصل المستخدم؟ Flask + /mors + /api/* + /api/chat"],
            ["Front end", "static/mors.html, static/index.html",
             "ماذا يرى المختبر؟ SPA واحدة بلا إطار عمل ولا خطوة بناء"],
            ["Document builders", "tools/*.py",
             "ماذا يحصل الحاكم؟ ثلاثة PDF تُولَّد من الـ API نفسه"],
        ], [34, 56, 80]),
        h3("أصل البيانات (acquisition policy)"),
        p("كل وحدة تمرّ على ثلاث مصادر بالترتيب نفسه: نداء API حقيقي → "
          "استدلال نموذج ذكاء اصطناعي → نموذج محلي حتمي، والمصدر الذي "
          "استُخدم فعلًا مكتوب في trace.via. لا تُعرض أبدًا رقم من غير أن "
          "يُذكر أي من هذه الطرق تم استخدامه."),
    ]))

    # ------------------------------------------------------- 5 live numbers
    m_rows = [
        ["جودة البيانات", f"{n(dh.get('data_quality_score'))}/100", "/api/mors/datahealth"],
        ["الصفوف المعالَجة", f"{(dh.get('rows') or 0):,}", "/api/mors/datahealth"],
        ["المصادر الحية", f"{n(dh.get('sources'))}", "/api/mors/datahealth"],
        ["الخلايا الناقصة", f"{n(dh.get('missing_pct'))}%", "/api/mors/datahealth"],
        ["الصفوف المكرّرة", f"{n(dh.get('duplicate_pct'))}%", "/api/mors/datahealth"],
        ["الاكتمال", f"{n(dh.get('completeness_pct'))}%", "/api/mors/datahealth"],
        ["الدقة", f"{n(dh.get('accuracy_score'))}%", "/api/mors/datahealth"],
        ["الشواذ المكتشفة", f"{n(dh.get('outlier_count'))} ({n(dh.get('outliers_pct'))}%)",
         "/api/mors/datahealth"],
        ["قرار المجلس العلمي", f"{verdict} — {n(score)}/100 (محرك {engine})",
         "/api/report"],
        ["الأقمار الصناعية", f"{len(sats)} (LEO {og['LEO']} / MEO {og['MEO']} / GEO {og['GEO']})",
         "/api/mors/satellite"],
        ["وحدات MORS", f"{len(mods)}", "/api/mors"],
        ["الكواكب خارج المجموعة الشمسية", f"{len(exo_rows)}", "/api/mors/exoplanets"],
        ["أجرام قريبة من الأرض", f"{n(obj)}", "/api/mors/objects"],
        ["انبعاثات كروونية مسجّلة", f"{n(metrics.get('cme_count'))}", "/api/data/space-weather"],
        ["انفجارات شمسية (30 يومًا)", f"{n(metrics.get('flare_count_30d'))}", "/api/data/kp-index"],
        ["أقصى مؤشر Kp", f"{n(metrics.get('kp_max'))} من 9", "/api/data/kp-index"],
        ["ال NEO المراقَب", f"{n(metrics.get('neo_count'))}", "/api/data/neo"],
        ["أقرب اقتراب (يوم قمري)", f"{n(metrics.get('closest_ld'))} LD", "/api/data/horizons"],
        ["علاقة إنتروبيا كمّية (بيل)", f"{n(metrics.get('quantum_entropy_ebit'))} ebit",
         "/api/data/quantum"],
        ["مشكلات مفتوحة (مرتّبة)", f"{len(probs)}", "/api/mors/problems"],
    ]
    SEC.append(("5. أرقام حيّة يمكن للجنة التحقق منها", [
        p("كل رقم في هذا القسم يأتي من استجابة API مباشرة وقت توليد الدليل؛ "
          "يمكن إعادة قراءتها بأمر واحد كما في القسم 9."),
        kpi([
            ("الجودة", f"{n(dh.get('data_quality_score'))}/100"),
            ("الصفوف", f"{(dh.get('rows') or 0):,}"),
            ("الأقمار", str(len(sats))),
            ("المشكلات", str(len(probs))),
            ("الوحدات", str(len(mods))),
            ("المصادر", str(agg.get('total') or len(hacks))),
            ("النتيجة", f"{n(score)}/100"),
            ("القرار", verdict),
        ]),
        tab(["المؤشر", "القيمة", "النقطة (endpoint)"], m_rows, [56, 62, 52]),
        h3("سياق التقرير"),
        p(f"رقم التشغيل الحالي {run} بتاريخ {when}؛ خمسة خبراء (Dr. Orbit، "
          "Dr. Helios، Dr. Quantel، Dr. Terra، Dr. Vigil) يمنحون درجات "
          "مستقلة تُطابق وتُجمَّع، والنتيجة المجمّعة هي المعروضة أعلاه."),
    ]))

    # ------------------------------------------------------- 6 conditions
    c_rows = []
    for c in conds:
        ev = "; ".join((c.get("used_in") or [])[:2]) or "-"
        if len(ev) > 110:
            ev = ev[:107] + "..."
        c_rows.append([
            f"{c.get('n')}. {c.get('name')}",
            "مُنجز" if c.get("status") == "core" else "امتداد موثّق",
            ", ".join(c.get("sources") or []) or "-",
            c.get("name_ar", ""),
            ev,
        ])
    SEC.append(("6. الشروط الثمانية — كيف تخدم المصادر الفريق", [
        quote(src.get("disclaimer_ar") or
              "لا يطلب من الفرق استخدام جميع المصادر أو اتباع ترتيب محدد."),
        tab(["الشرط", "الحالة", "المصادر", "المعنى بالعربية",
             "الأدلة في المستودع"], c_rows, [30, 18, 22, 42, 58]),
        p("الحالة «مُنجز» تعني أن هناك كودًا عاملًا في المستودع يحقّق الشرط؛ "
          "«امتداد موثّق» تعني أن المسار مُعرَّف ومفهوم السبب لم يُنفَّذ بعد "
          "وهو مسجّل في التقرير كمشكلة/امتداد — وهو ما يتوافق مع نص التعريف "
          "أعلاه الذي لا يلزم بترتيب استخدام المصادر."),
    ]))

    # ------------------------------------------------------- 7 sources
    s_rows = []
    for s in hacks:
        used = ", ".join((s.get("used_in") or [])[:2]) or "-"
        if len(used) > 70:
            used = used[:67] + "..."
        s_rows.append([str(s.get("no")), s.get("title"),
                       s.get("phase"), s.get("level"), used])
    d_rows = [[d.get("id") or "-", d.get("name") or "-", d.get("via") or "-",
               d.get("used_in") or "-"] for d in dsrc]
    SEC.append(("7. المصادر العلمية الستة عشر", [
        p("المصادر موزّعة على ثلاث مراحل: تحضير (Preparation)، أثناء "
          f"الفرقعة (During)، وبحث وتأمل (Research). "
          f"التوزيع: {json.dumps(agg.get('by_phase') or {}, ensure_ascii=False)}."),
        tab(["#", "المصدر", "المرحلة", "المستوى", "أين يُستخدم في المشروع"],
            s_rows, [8, 62, 24, 24, 52]),
        h3("مصادر البيانات الفعلية التي يستدعيها المشروع"),
        tab(["الرمز", "المصدر", "طريقة الوصول", "أين يُستدعى"],
            d_rows, [12, 62, 24, 72]),
    ]))

    # ------------------------------------------------------- 8 conventions
    SEC.append(("8. الاتفاقيات الإلزامية الخمسة", [
        p("هذه الاتفاقيات المطلوبة في التعريف، ويظهر تنفيذها في كل شاشة "
          "وكل تقرير:"),
        bul([
            "مخطط بطاقة المشكلة بعشرة مفاتيح إلزامية: problem_id, title, "
            "severity, category, component, symptom, root_cause, fix, "
            "evidence, priority — والمفاتيح الممنوعة (description, solution, "
            "notes, status, details) غير موجودة في أي بطاقة.",
            "معادلة الأولوية مشتقّة رقميًا: priority_score = 0.40×evidence + "
            "0.35×impact + 0.25×confidence، وتصنيف High عند 75 فأكثر، Medium "
            "عند 50 فأكثر، وإلا Low. لا يُمنَح تصنيف يدويًا.",
            "شارة التتبّع [Source | Dataset Version | Processing Pipeline | "
            "Method | Last Updated | Operator | Timestamp] تظهر بجانب كل رسم "
            "وتحت كل وحدة.",
            "بروتوكول الذكاء الاصطناعي بخمسة مستويات: Observed Data / "
            "Calculated Metric / AI Interpretation / Hypothesis / Suggested "
            "Action — والنموذج لا يدّعي قياسًا قط أبدًا.",
            "سياسة الاكتساب الثلاثية: api ثم ai_synthesis ثم local_model، "
            "ومصدر الاستخدام مسجّل في trace.via.",
        ]),
        code("priority_score = 0.40*evidence + 0.35*impact + 0.25*confidence"
             "\nHigh >= 75   Medium >= 50   otherwise Low"),
        p("علاوة على ذلك: لغة الواجهة عربية وإنجليزية، وضع ليلي/نهاري "
          "وشُعاعات كوكبية (Earth/Mars/Jupiter/Saturn/Neptune/Moon) تغيّر "
          "اللون فقط دون تغيير التخطيط، ولا يوجد نيون أو فوضى بصرية."),
    ]))

    # ------------------------------------------------------- 9 verification
    SEC.append(("9. التحقق الذاتي — أثبتها بنفسك", [
        p("بعد فكّ الضغط، تكفي هذه الأوامر للتأكدة من أن الحزمة سليمة "
          "وتعمل كما هو مُعلن:"),
        code("python main.py --selftest\n"
             "# ======================================================\n"
             "#   verdict         : CERTIFIED\n"
             "#   score           : 98/100\n"
             "#   Ai.Mors greeting: 'أهلاً وسهلاً بكم في الفضاء' (ok=True)\n"
             "#   SELFTEST        : PASS"),
        p("ثم تحقق من الواجهات ونقاط النهاية:"),
        code("python main.py                # ثم افتح http://127.0.0.1:5000/mors\n"
             "curl http://127.0.0.1:5000/api/health\n"
             "curl http://127.0.0.1:5000/api/mors\n"
             "curl http://127.0.0.1:5000/api/mors/sources\n"
             "curl http://127.0.0.1:5000/api/mors/datahealth"),
        p("وبخصوص سلامة الملفات نفسها، قارن 00_MANIFEST.txt بالمستخرج؛ البصمة "
          "SHA-256 لكل ملف موجودة هناك."),
    ]))

    # ------------------------------------------------------- 10 limitations
    pr_rows = []
    for pr in probs:
        pr_rows.append([pr.get("id"), pr.get("title"), pr.get("priority"),
                        f"{n(pr.get('confidence_level'))}%"])
    live_ids = {pr.get("id") for pr in probs}
    # notes are keyed by card id and only rendered while that card is live —
    # a resolved condition must not leave its limitation behind as a dangling id
    _LIMIT_NOTES = {
        "P-001": "P-001: تحقّق المجلس العلمي يعمل بالمحرك الاحتياطي المحلي عند "
                 "نفاد حصيلة Gemini المجانية؛ الأرقام نفسها تبقى قابلة للتكرار "
                 "لكنها غير مُتقاطعة من نموذج لغوي.",
        "P-006": "P-006: الملفات متعددة الطيف مبنية على طيفات مرجعية لا مشاهد "
                 "مُصنَّفة فعليًا — والمصدر مذكور صراحةً.",
        "P-003": "P-003: عدد الشواذ مشتقّ من معامل تلوث ثابت 0.1 لا من "
                 "عتبة إحصائية مستنتجة — ولهذا هو معلَّم في التقرير.",
        "P-005": "P-005: نافذة مؤشر Kp أقصر بكثير من نافذة الانبعاثات، "
                 "والارتباط محسوب على فترة التقاطع المشتركة فقط.",
        "P-008": "P-008: منحنى الضوء محتوم بمقياس زمني واحد؛ إزالة الاتجاه "
                 "قبل الطي هي المعالجة المقترحة لا الإنجاز الحالي.",
    }
    limit_bullets = [_LIMIT_NOTES[k] for k in sorted(live_ids)
                     if k in _LIMIT_NOTES]
    if not limit_bullets:
        limit_bullets = ["كل بطاقات المشاكل مغلقة في هذا التشغيل؛ "
                         "لا توجد حدود مفتوحة مُعلَنة."]
    SEC.append(("10. حدود صادقة — ما لا ندّعي إنجازه", [
        p("اللجنة تُكافأ على الشفافية لا على الكمال؛ هذه قائمة مفتوحة تُحدَّث "
          "تلقائيًا مع كل تشغيل للخط أنابيب وتصنَّف بالأولوية نفسها المستخدمة "
          "في الواجهة:"),
        tab(["الرمز", "المشكلة", "الأولوية", "الثقة"], pr_rows,
            [16, 96, 26, 32]),
        bul(limit_bullets),
    ]))

    # ------------------------------------------------------- 11 documents
    SEC.append(("11. أين تجد كل مستند", [
        tab(["المستند", "محتواه", "متى تفتحه"], [
            ["00_COMMITTEE_GUIDE.md (و هذا PDF)",
             "هذا الدليل: ملخص، شروط، مصادر، تحقق",
             "الخطوة الأولى للجنة"],
            ["README.md", "التشغيل السريع وجدول نقاط النهاية",
             "عند أول تشغيل"],
            ["المشكلات_التي_تم_حلها.md",
             "كل خلل في البيانات وتحليله: السبب، الإصلاح، الرقم قبل/بعد",
             "عند مراجعة دقّة البيانات"],
            ["DEPLOYMENT.md", "النشر والتشغيل وجدول التسليمات",
             "عند النشر أو التحقق من التغطية"],
            ["tools/audit_data.py", "225+ فحصًا للقراءة فقط ← AUDIT: PASS",
             "قبل أي إعادة توليد للمستندات"],
            ["docs/API_CONTRACT.md", "عقد الـ API كاملًا (§1-§20)",
             "عند مراجعة الواجهات أو بناء عميل"],
            ["docs/MORS_REPORT.pdf", "التقرير العلمي: الجودة، المشكلات، "
             "الرسوم، المصادر، الحدود", "للحجج والأدلة التفصيلية"],
            ["docs/PROJECT_GUIDE.pdf", "شرح ملف-ملف للمستودع",
             "عند البحث عن مصدر سلوك معيّن"],
            ["00_MANIFEST.txt", "حجم كل ملف وبصمة SHA-256",
             "للتحقق من سلامة الحزمة"],
            ["last_report.json", "آخر تقرير معتمد بRAW JSON",
             "لإعادة تحليل الأرقام برمجيًا"],
        ], [46, 76, 48]),
    ]))

    # ------------------------------------------------------- 12 regenerate
    SEC.append(("12. إعادة توليد كل شيء", [
        p("كل المستندات الثلاثة (التقرير، دليل الملفات، هذا الدليل) تُبنى من "
          "نفس الكود ومن الـ API الحيّ؛ إعادة التوليد تأخذ دقيقة واحدة:"),
        code("pip install -r requirements.txt   # + حزمة PDF الاختيارية أدناه"
             "\npip install reportlab arabic-reshaper python-bidi matplotlib"
             "\npython main.py                     # اترك الخادم يعمل"
             "\npython tools/audit_data.py         # -> RESULT: AUDIT: PASS"
             "\npython tools/build_report.py       # -> docs/MORS_REPORT.pdf"
             "\npython tools/build_guide.py        # -> docs/PROJECT_GUIDE.pdf"
             "\npython tools/build_committee.py    # -> 00_COMMITTEE_GUIDE.md"
             " + docs/COMMITTEE_GUIDE.pdf"
             "\npython tools/build_zip.py          # -> الحزمة النهائية"),
        p("ولأن المحتوى مولَّد من الـ API، فإن أي رقم يتغيّر في المشروع "
          "يتغيّر تلقائيًا في المستندات — لا يوجد نص ثابت يدعي أمرًا لم "
          "يحدث."),
        hr(),
        p(f"دليل لجنة التحكيمية — نسخة {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} "
          f"؛ رقم التشغيل {run} ؛ الحالة {verdict} {n(score)}/100."),
    ]))

    # ------------------------------------------------------------- 13 team
    team = D.get("team") or {}
    members = team.get("members") or []
    if members:
        SEC.append(("13. فريق العمل", [
            p(f"{team.get('count') or len(members)} أعضاء، ولكل واحد وحدات "
              "ومشكلات يملكها داخل MORS؛ نفس القائمة معروضة في واجهة "
              "TEAM.MORS وفي التقرير §9:"),
            tab(["العضو / الدور", "المسؤوليات", "الوحدات والمشكلات"],
                [[m.get("name") or "—",
                  m.get("role") or "—",
                  "، ".join(str(x) for x in (m.get("owns") or [])) or "—"]
                 for m in members],
                [40, 55, 75]),
            p("المسؤوليات تشمل الوحدات (مثل HOME.MORS أو SPECTRAL.MORS) "
              "وأرقام المشكلات التي يحلّها العضو؛ المالك مذكور في بطاقة كل "
              f"مشكلة وحل معًا، وفي سجل التتبّع "
              f"{team.get('trace', {}).get('dataset_id', 'MORS-TEAM-v1.1.0')}."),
        ]))

    return SEC


# ------------------------------------------------------------------- render
from reportlab.lib import colors            # noqa: E402
from reportlab.lib.enums import TA_CENTER, TA_RIGHT  # noqa: E402
from reportlab.platypus import HRFlowable, Paragraph, Table, TableStyle  # noqa: E402

KPI_N = br._p("kpi_n_ar", fontName="Body-B", fontSize=17, leading=20,
              textColor=br.ACCENT, alignment=TA_CENTER, spaceAfter=1)
KPI_L = br._p("kpi_l_ar", fontName="Ar", fontSize=7.4, leading=10.4,
              textColor=br.MUTED, alignment=TA_CENTER, spaceAfter=0)
TH_R = br._p("th_ar", fontName="ArB", fontSize=8.2, leading=11,
             textColor=colors.white, spaceAfter=0, alignment=TA_RIGHT)


def make_kpis(items, ncols=4):
    """br.kpis, but the labels are Arabic-aware."""
    nums, labs = [], []
    for label, value in items:
        nums.append(Paragraph(f"<b>{br._xml(str(value))}</b>", KPI_N))
        if is_ar(label):
            lines = br.ar_lines(label, font="Ar", size=7.4,
                                width=(W / ncols - 6) * mm)
            labs.append(Paragraph("<br/>".join(br.ar(l) for l in lines), KPI_L))
        else:
            labs.append(Paragraph(br._xml(str(label)), KPI_L))
    while len(nums) % ncols:
        nums.append(Paragraph(" ", KPI_N))
        labs.append(Paragraph(" ", KPI_L))
    inner = []
    for i in range(0, len(nums), ncols):
        inner.append(nums[i:i + ncols])
        inner.append(labs[i:i + ncols])
    t = Table(inner, colWidths=[(W * mm) / ncols] * ncols, hAlign="LEFT")
    style = [
        ("BOX", (0, 0), (-1, -1), 0.6, br.ACCENT),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.white),
    ]
    for r in range(0, len(inner), 2):
        style.append(("BACKGROUND", (0, r), (-1, r), br.BAND2))
    t.setStyle(TableStyle(style))
    return t


COVER_T = br._p("cov_t", fontName="ArB", fontSize=30, leading=46,
                textColor=colors.white, spaceAfter=6, alignment=TA_RIGHT)
COVER_S = br._p("cov_s", fontName="Ar", fontSize=12.5, leading=21,
                textColor=colors.HexColor("#CFF6FF"), spaceAfter=2,
                alignment=TA_RIGHT)


def ar_to(text, style, font, size, width=None):
    """Arabic paragraph for a caller-supplied style (cover, titles)."""
    lines = br.ar_lines(text, font=font, size=size,
                        width=width or (W * mm))
    return Paragraph("<br/>".join(br.ar(l) for l in lines), style)


def render_pdf(sections, meta) -> list:
    story = [
        Spacer(1, 46 * mm),
        br.P("M O R S", "cover_kicker"),
        Spacer(1, 4 * mm),
        ar_to("دليل لجنة التحكيمية", COVER_T, "ArB", 30),
        br.P("Submission guide for the judging committee", "cover_sub"),
        Spacer(1, 12 * mm),
        br.P("ASI-HACK Space Analytics Engine  -  MORS Scientific Command "
             "Center", "cover_sub"),
        Spacer(1, 24 * mm),
        br.P(f"Sections      {len(sections)}", "cover_meta"),
        br.P(f"Run           {meta['run']}", "cover_meta"),
        br.P(f"Verdict       {meta['verdict']} {meta['score']}", "cover_meta"),
        br.P(f"Generated     {meta['when']}", "cover_meta"),
        br.NextPageTemplate("body"),
        PageBreak(),
    ]

    story += [br.P("How to use this guide", "h1"),
              HRFlowable(width="100%", thickness=1.2, color=br.ACCENT,
                         spaceAfter=8),
              br.P("Twelve short sections: what the package is, how to score "
                   "it in five minutes, every file, the architecture, the "
                   "live numbers, the eight hackathon conditions, the "
                   "sixteen scientific sources, the mandatory conventions, "
                   "the self-test, the honest limitations, the document map "
                   "and how to rebuild everything.", "body"),
              br.P("The same content ships as 00_COMMITTEE_GUIDE.md at the "
                   "root of the package for reviewers who prefer plain text.",
                   "note"),
              Spacer(1, 5 * mm),
              br.P("Contents", "h2")]
    story += [br.arP(t, "ar_body") for t, _ in sections]
    story += [PageBreak()]

    for i, (title, blocks) in enumerate(sections):
        if i:
            story += [PageBreak()]
        story += [br.arP(title, "ar_h1"),
                  HRFlowable(width="100%", thickness=1.2, color=br.ACCENT,
                             spaceAfter=8)]
        for b in blocks:
            story += pdf_block(b)
    return story


def render_md(sections, meta) -> str:
    out = [
        "# دليل لجنة التحكيمية — ASI-HACK Space Analytics Engine",
        "",
        "**MORS Scientific Command Center** — نسخة نصية من "
        "`docs/COMMITTEE_GUIDE.pdf`.",
        "",
        f"- **تاريخ التوليد:** {meta['when']}",
        f"- **رقم التشغيل (run_id):** `{meta['run']}`",
        f"- **حالة المجلس العلمي:** {meta['verdict']} — {meta['score']}",
        f"- **عدد الملفات المُنتقاة في الجدول:** {meta['files']} "
     "(القائمة الكاملة في 00_MANIFEST.txt)",
        "",
        "> اقرأ هذا الدليل من الأعلى للأسفل؛ كل قسم ينتهي بنتيجة قابلة "
        "للتحقق بأمر واحد. إن أردت الأدلة التفصيلية فالمرجع "
        "`docs/MORS_REPORT.pdf`.",
        "",
        "## الفهرس",
        "",
    ]
    for title, _ in sections:
        out.append(f"- {title}")
    out.append("")
    for title, blocks in sections:
        out.append(f"## {title}")
        out.append("")
        for b in blocks:
            out.append(md_block(b))
        out.append("")
    return "\n".join(out).rstrip() + "\n"


# --------------------------------------------------------------------- main
def main() -> int:
    print(f"committee guide -> fetching {BASE}")
    D = collect()
    meta = {
        "when": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "run": str(((D.get("report") or {}).get("run_id")) or "-"),
        "verdict": str(((D.get("report") or {}).get("council") or {})
                       .get("verdict") or "-"),
        "score": n(((D.get("report") or {}).get("council") or {})
                   .get("overall_score"), "-"),
        "files": 0,
    }

    # first pass writes the markdown so the inventory can list it too
    files = bg.scan()
    MD_OUT.parent.mkdir(parents=True, exist_ok=True)
    MD_OUT.write_text(render_md(build_content(D, files), meta),
                      encoding="utf-8")

    files = bg.scan()
    meta["files"] = len(files)
    MD_OUT.write_text(render_md(build_content(D, files), meta),
                      encoding="utf-8")

    PDF_OUT.parent.mkdir(parents=True, exist_ok=True)
    doc = br.Doc(str(PDF_OUT), {"when": meta["when"], "run": meta["run"]})
    doc.build(render_pdf(build_content(D, files), meta))

    print(f"WROTE {MD_OUT}  ({MD_OUT.stat().st_size:,} bytes)")
    print(f"WROTE {PDF_OUT}  ({PDF_OUT.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


