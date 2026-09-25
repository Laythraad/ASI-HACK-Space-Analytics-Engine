"""MORS source registry.

Two things live here:

1.  ``HACKATHON_SOURCES`` — the official ASI Hackathon source list
    (preparation / during-the-event / research) that the brief supplied,
    each one tagged with the *condition* it supports and with the exact
    file in this project that uses it.
2.  ``CONDITIONS`` — the eight "how do the sources help the team?" bullets
    from the brief, each mapped to concrete evidence inside this repo.

The payload is served at ``GET /api/mors/sources`` and is the backbone of
the SOURCES.MORS page, of section 15 of ``docs/MORS_REPORT.pdf`` and of
``docs/PROJECT_GUIDE.pdf``.

Nothing here is fetched at runtime — it is a curated, static registry, so
it always renders even fully offline.
"""
from __future__ import annotations

from typing import Any, Dict, List

__all__ = ["build", "CONDITIONS", "HACKATHON_SOURCES", "DATA_SOURCES"]

# ---------------------------------------------------------------------------
# The eight conditions from the brief (how the sources help the team)
# ---------------------------------------------------------------------------
CONDITIONS: List[Dict[str, Any]] = [
    {
        "key": "ai_basics",
        "n": 1,
        "name": "AI & Machine-Learning basics",
        "name_ar": "فهم أساسيات الذكاء الاصطناعي وتعلم الآلة",
        "helps_ar": ("تساعد المصادر العربية وGoogle ML Crash Course الفرق على "
                     "فهم المفاهيم الأساسية واختيار الأسلوب المناسب للمشكلة."),
        "sources": ["S-01", "S-02"],
        "used_in": [
            "agents/agent1_ingestion.py — StandardScaler + IsolationForest",
            "agents/agent2_council.py — five-expert scoring, verdict logic",
            "static/mors.html — 5-tier AI protocol panel",
        ],
        "evidence": ("The pipeline applies supervised-unsupervised fundamentals "
                     "(scaling, contamination-based anomaly detection, train-free "
                     "evaluation) and the council turns them into a scored "
                     "verdict instead of a raw number."),
        "status": "core",
    },
    {
        "key": "data_handling",
        "n": 2,
        "name": "Working with data",
        "name_ar": "التعامل مع البيانات",
        "helps_ar": ("توفر Earthdata NASA وWorldview NASA وموارد البيانات "
                     "ال أخرى أمثلة وبيانات حقيقية يمكن استخدامها عندما يحتاج "
                     "الحل إلى بيانات فضاء أو رصد الأرض."),
        "sources": ["S-03", "S-04", "S-05", "S-10", "S-11", "S-12"],
        "used_in": [
            "agents/agent1_ingestion.py — DONKI, NEOWS, Horizons, Kp",
            "agents/datasets.py — GIBS WMS VIIRS Black-Marble night lights",
            "agents/mors_data.py — APOD, Exoplanet Archive, CelesTrak",
        ],
        "evidence": ("Six live NASA/NOAA endpoints plus three reference CSVs; "
                     "every row keeps its source endpoint and fetch timestamp "
                     "in the traceability record."),
        "status": "core",
    },
    {
        "key": "analysis_modelling",
        "n": 3,
        "name": "Data analysis & model building",
        "name_ar": "تحليل البيانات وبناء النماذج",
        "helps_ar": ("يمكن استخدام أدوات مثل Google Colab وScikit-learn "
                     "لتجهيز البيانات، تحليلها، تدريب النماذج واختبارها بسرعة."),
        "sources": ["S-08", "S-09"],
        "used_in": [
            "agents/agent1_ingestion.py — cleaning log, quality audit",
            "agents/datasets.py — PCA reduction of the spectral matrix",
            "tools/build_report.py — report generation from live metrics",
        ],
        "evidence": ("Cell-level completeness/accuracy audit, PCA "
                     "(StandardScaler -> PCA) on real band matrices, and a "
                     "quality score that is recomputed on every run rather "
                     "than asserted."),
        "status": "core",
    },
    {
        "key": "computer_vision",
        "n": 4,
        "name": "Computer Vision",
        "name_ar": "الرؤية الحاسوبية",
        "helps_ar": ("إذا كان الحل يعتمد على الصور، يمكن استخدام Hugging Face "
                     "ومراجع Datasets وSatellite Deep Learning لتطبيق "
                     "Segmentation أو Detection أو Classification."),
        "sources": ["S-06", "S-13", "S-14"],
        "used_in": [
            "static/mors.html — ASTRONOMY.MORS image grid + FITS headers",
            "agents/mors_data.py images() — NASA APOD metadata + FITS cards",
            "agents/datasets.py — GIBS raster tiles for night lights",
        ],
        "evidence": ("The shipped build ingests image *metadata* (FITS header "
                     "cards, filters, exposure, WCS keywords) and raster night-"
                     "light tiles, and labels them Level 1. Pixel-level "
                     "segmentation/detection is the documented extension path, "
                     "not a claim."),
        "status": "extension",
    },
    {
        "key": "astronomical_data",
        "n": 5,
        "name": "Astronomical data",
        "name_ar": "البيانات الفلكية",
        "helps_ar": ("إذا كان التحدي يحتاج إلى بيانات فلكية، يمكن استخدام "
                     "Astropy وأدوات البيانات الفلكية المناسبة."),
        "sources": ["S-07"],
        "used_in": [
            "agents/agent1_ingestion.py — Astropy Time/SkyCoord transforms",
            "agents/mors_data.py — objects, FITS, photometry, light curves",
            "agents/mors_data.py — spectroscopy from NIST line lists",
        ],
        "evidence": ("ICRS/GCRS coordinate handling, FITS header parsing, "
                     "phase-folded light curves, synthetic spectra from NIST "
                     "laboratory wavelengths, and a curated Hipparcos/Gaia/RC3 "
                     "object catalogue."),
        "status": "core",
    },
    {
        "key": "generative_ai",
        "n": 6,
        "name": "AI / Generative-AI applications",
        "name_ar": "تطبيقات الذكاء الاصطناعي التوليدي",
        "helps_ar": ("يمكن لفريق استخدام المصادر كمرجع لفهم البيانات والمشكلة، "
                     "ثم اختيار الأدوات والنماذج المناسبة لبناء تطبيق أو نموذج "
                     "أولي يعتمد على AI Generative أو LLMs عند الحاجة."),
        "sources": ["S-01", "S-06", "S-08"],
        "used_in": [
            "agents/agent2_council.py — Gemini Council of 5",
            "agents/agent3_citations.py — Gemini citation enrichment",
            "agents/agent4_aimors.py — Ai.Mors conversational agent",
            "main.py — POST /api/mors/insight, POST /api/chat",
        ],
        "evidence": ("Three of four agents are LLM-backed with a deterministic "
                     "fallback, every AI answer is tier-labelled, and the "
                     "engine actually used is printed in the header pill."),
        "status": "core",
    },
    {
        "key": "predictive_automation",
        "n": 7,
        "name": "Predictive & automation systems",
        "name_ar": "الأنظمة التنبؤية والأتمتة",
        "helps_ar": ("يمكن استخدام نفس الموارد لفهم البيانات وبناء pipelines "
                     "أو نماذج تنبؤية وأتمتة أجزاء من الحل، حسب طبيعة "
                     "المشكلة."),
        "sources": ["S-03", "S-05", "S-09", "S-12"],
        "used_in": [
            "main.py — four-agent pipeline with stage log and auto-run",
            "agents/agent1_ingestion.py — Kp 3-sample moving average",
            "agents/mors_data.py — satellite pass windows, quality monitor",
            "START.bat — environment check, port recovery, service launch",
        ],
        "evidence": ("One command runs ingest -> clean -> council -> citations "
                     "-> UI; NOAA Kp is smoothed for trend reading, pass "
                     "windows are derived from orbital period, and the health "
                     "bar re-checks the whole frame each run."),
        "status": "core",
    },
    {
        "key": "inspiration_research",
        "n": 8,
        "name": "Inspiration & research",
        "name_ar": "الإلهام والبحث",
        "helps_ar": ("توفر FreeDSM وLightViz أمثلة على كيفية تحويل مشكلة "
                     "واقعية إلى حل تقني، ويمكن الاستفادة منهما للإلهام وليس "
                     "كحلول جاهزة."),
        "sources": ["S-15", "S-16"],
        "used_in": [
            "agents/datasets.py — night-light -> sky-brightness model",
            "PROJECTS.MORS — PRJ-002 Light-Pollution & Sky-Brightness Model",
            "problems P-002 / P-004 — calibration and tile-coverage findings",
        ],
        "evidence": ("The light-pollution module follows the LightViz pattern "
                     "(real imagery -> calibrated index -> human-readable "
                     "scale) and is explicitly declared a *calibrated model*, "
                     "not a photometric measurement."),
        "status": "core",
    },
]

# ---------------------------------------------------------------------------
# 1. The official ASI Hackathon source list
# ---------------------------------------------------------------------------
_H = "Preparation"          # قبل الهاكاثون
_D = "During"               # أثناء الهاكاثون
_R = "Research"             # بحث وإلهام

HACKATHON_SOURCES: List[Dict[str, Any]] = [
    {
        "id": "S-01", "no": 1, "phase": _H, "kind": "Course",
        "title": "Google Machine Learning Crash Course",
        "title_ar": "دورة Google المختصرة في تعلم الآلة",
        "url": "https://developers.google.com/machine-learning/crash-course",
        "level": "Beginner -> Intermediate", "category": "ai_basics",
        "goal_ar": "فهم أساسيات تعلم الآلة بطريقة عملية.",
        "learn_ar": ("Classification, Regression, Neural Networks, "
                     "Data Preparation, Model Evaluation."),
        "for_ar": "الشخص الذي يعرف أساسيات Python ويريد تأسيس نفسه في ML.",
        "when_ar": "كمرجع محدود أثناء الهاكاثون، وليس للتعلم من الصفر.",
        "used_in": ["agents/agent1_ingestion.py", "agents/agent2_council.py"],
    },
    {
        "id": "S-02", "no": 2, "phase": _H, "kind": "Video course",
        "title": "Machine Learning in Arabic (YouTube)",
        "title_ar": "تعلم الآلة بالعربي — يوتيوب",
        "url": None,
        "level": "Beginner", "category": "ai_basics",
        "goal_ar": "فهم تعلم الآلة باللغة العربية.",
        "learn_ar": "المفاهيم الأساسية قبل الانتقال إلى التطبيق.",
        "for_ar": "المبتدئين الذين يجدون المحتوى الإنجليزي صعباً.",
        "when_ar": "لا تحتاج مشاهدة السلسلة كاملة إذا كان وقتك محدوداً.",
        "used_in": ["static/mors.html — AI.MORS tier panel"],
    },
    {
        "id": "S-03", "no": 3, "phase": _H, "kind": "Training",
        "title": "NASA ARSET Training",
        "title_ar": "تدريب NASA ARSET عن بعد",
        "url": "https://arset.gsfc.nasa.gov/",
        "level": "Beginner -> Advanced", "category": "data_handling",
        "goal_ar": ("كيفية استخدام بيانات الاستشعار عن بعد وبيانات NASA "
                    "في مشكلات حقيقية."),
        "learn_ar": "Remote Sensing, Satellite Data, Earth Observation, تحليل البيانات.",
        "for_ar": "الفرق التي ستحتاج بيانات رصد الأرض أو الأقمار الصناعية.",
        "when_ar": "قبل الهاكاثون لفهم المجال، والرجوع إليه أثناء الهاكاثون.",
        "used_in": ["agents/datasets.py", "agents/mors_data.py"],
    },
    {
        "id": "S-04", "no": 4, "phase": _H, "kind": "Case study",
        "title": "Inside Look at How NASA Measures Air Pollution",
        "title_ar": "نظرة داخلية: كيف يقيس NASA التلوث الهوائي (ARSET)",
        "url": "https://arset.gsfc.nasa.gov/",
        "level": "Beginner", "category": "data_handling",
        "goal_ar": "مثال عملي على استخدام بيانات الأقمار لدراسة مشكلة بيئية.",
        "learn_ar": "كيف تستخدم بيانات NASA في مراقبة وتحليل التلوث.",
        "for_ar": "من يريد فهم العلاقة بين بيانات الأقمار والمشكلات الواقعية.",
        "when_ar": "قبل الهاكاثون كمثال ميداني.",
        "used_in": ["agents/datasets.py — light-pollution pipeline"],
    },
    {
        "id": "S-05", "no": 5, "phase": _H, "kind": "Course",
        "title": "Machine Learning on Satellite Imagery (UN SDG Learn)",
        "title_ar": "تعلم الآلة على صور الأقمار الصناعية",
        "url": None,
        "level": "Intermediate", "category": "predictive_automation",
        "goal_ar": "الربط بين تعلم الآلة وصور الأقمار الصناعية.",
        "learn_ar": "كيفية استخدام ML مع بيانات وصور الأقمار.",
        "for_ar": "من لديه أساسيات ML ويريد تطبيقها على رصد الأرض/الفضاء.",
        "when_ar": "قبل الهاكاثون أو كمرجع أثناءه.",
        "used_in": ["agents/datasets.py — GIBS raster ingestion"],
    },
    {
        "id": "S-06", "no": 6, "phase": _H, "kind": "Course",
        "title": "Hugging Face Computer Vision Course",
        "title_ar": "دورة Hugging Face في الرؤية الحاسوبية",
        "url": "https://huggingface.co/learn/computer-vision",
        "level": "Intermediate", "category": "computer_vision",
        "goal_ar": "تعلم استخدام الذكاء الاصطناعي في تحليل الصور.",
        "learn_ar": ("Image Classification, Object Detection, Segmentation, "
                     "Deep Learning Models."),
        "for_ar": "الفرق التي تفكر في حل يعتمد على الصور.",
        "when_ar": "قبل الهاكاثون أو كمرجع أثناءه.",
        "used_in": ["static/mors.html — image gallery", "future: pixel models"],
    },
    {
        "id": "S-07", "no": 7, "phase": _H, "kind": "Documentation",
        "title": "Astropy Documentation",
        "title_ar": "توثيق Astropy",
        "url": "https://docs.astropy.org/en/stable/",
        "level": "Intermediate", "category": "astronomical_data",
        "goal_ar": "التعامل مع البيانات الفلكية باستخدام Python.",
        "learn_ar": "FITS, coordinates, astronomical data.",
        "for_ar": "الفرق التي تعمل على بيانات الفيزياء الفلكية وليس فقط رصد الأرض.",
        "when_ar": "قبل أو أثناء الهاكاثون حسب طبيعة المشروع.",
        "used_in": ["agents/agent1_ingestion.py", "agents/mors_data.py"],
    },
    {
        "id": "S-08", "no": 8, "phase": _D, "kind": "Environment",
        "title": "Google Colab",
        "title_ar": "Google Colab — بيئة البرمجة",
        "url": "https://colab.research.google.com/",
        "level": "All levels", "category": "generative_ai",
        "goal_ar": "كتابة وتشغيل Python وML مباشرة من المتصفح.",
        "learn_ar": "لا تحتاج إلى إعداد بيئة Python كاملة على الجهاز.",
        "for_ar": "جميع الفرق التي تحتاج إلى برمجة.",
        "when_ar": "Analysis -> ML -> Visualization -> Prototyping.",
        "used_in": ["any notebook prototyping", "main.py runs locally"],
    },
    {
        "id": "S-09", "no": 9, "phase": _D, "kind": "Library",
        "title": "Scikit-learn Documentation",
        "title_ar": "توثيق Scikit-learn",
        "url": "https://scikit-learn.org/stable/",
        "level": "Intermediate", "category": "analysis_modelling",
        "goal_ar": "تنفيذ نماذج تعلم الآلة بسرعة.",
        "learn_ar": "Classification, Regression, Clustering, Preprocessing, Evaluation.",
        "for_ar": "أي فريق يستخدم ML على بيانات منظمة أو خصائص.",
        "when_ar": "ابحث عن الدالة أو الخوارزمية التي تحتاجها مباشرة.",
        "used_in": ["agents/agent1_ingestion.py — StandardScaler, IsolationForest"],
    },
    {
        "id": "S-10", "no": 10, "phase": _D, "kind": "Data platform",
        "title": "NASA Earthdata Search",
        "title_ar": "NASA Earthdata Search — منصة اكتشاف البيانات",
        "url": "https://search.earthdata.nasa.gov/",
        "level": "All levels", "category": "data_handling",
        "goal_ar": "البحث عن بيانات NASA المناسبة لمشروعك.",
        "learn_ar": "استخدامه عندما تحتاج Dataset حقيقي بدل Dataset تجريبي.",
        "for_ar": "الفرق التي تحتاج بيانات بيئية/أقمار/أرض.",
        "when_ar": "أثناء اختيار البيانات وأثناء تطوير المشروع.",
        "used_in": ["agents/agent1_ingestion.py", "agents/datasets.py"],
    },
    {
        "id": "S-11", "no": 11, "phase": _D, "kind": "Visualisation",
        "title": "NASA Worldview",
        "title_ar": "NASA Worldview — تصور بيانات الأقمار",
        "url": "https://worldview.earthdata.nasa.gov/",
        "level": "All levels", "category": "data_handling",
        "goal_ar": "استكشاف صور وبيانات الأقمار الصناعية بصرياً.",
        "learn_ar": "اختيار المناطق، مقارنة التواريخ، فهم نوع الصور المتاح.",
        "for_ar": "فرق رصد الأرض/الأقمار.",
        "when_ar": "أثناء البحث عن البيانات وتحديد فكرة المشروع.",
        "used_in": ["agents/datasets.py — GIBS layer selection"],
    },
    {
        "id": "S-12", "no": 12, "phase": _D, "kind": "Dataset",
        "title": "NASA Nighttime Lights",
        "title_ar": "بيانات الإضاءة الليلية من NASA",
        "url": "https://worldview.earthdata.nasa.gov/",
        "level": "Beginner", "category": "data_handling",
        "goal_ar": "الوصول إلى بيانات الإضاءة الليلية وتحليلها.",
        "learn_ar": "مفيدة في Light Pollution وUrbanization وHuman Activity.",
        "for_ar": "الفرق التي تختار مشكلة مرتبطة بالملاحظات الليلية.",
        "when_ar": "أثناء الهاكاثون إذا كانت مناسبة لمشكلتك.",
        "used_in": ["agents/datasets.py — VIIRS Black Marble tiles"],
    },
    {
        "id": "S-13", "no": 13, "phase": _D, "kind": "Dataset",
        "title": "Semantic Segmentation of Aerial Imagery (Kaggle)",
        "title_ar": "تجزئة دلالية لصور الأراضي — Kaggle",
        "url": None,
        "level": "Intermediate", "category": "computer_vision",
        "goal_ar": "تجربة الرؤية الحاسوبية على صور جوية/فضائية.",
        "learn_ar": "Computer Vision, Image Segmentation.",
        "for_ar": "الفرق التي تحتاج Dataset سريع لتجربة النموذج الأولي.",
        "when_ar": "أثناء الهاكاثون.",
        "used_in": ["future: segmentation prototype"],
    },
    {
        "id": "S-14", "no": 14, "phase": _D, "kind": "Technical reference",
        "title": "Satellite Image Deep Learning Techniques (GitHub)",
        "title_ar": "تقنيات التعلم العميق لصور الفضاء — GitHub",
        "url": None,
        "level": "Advanced", "category": "computer_vision",
        "goal_ar": "البحث عن تقنيات وأمثلة تعلم عميق لصور الفضاء.",
        "learn_ar": "Computer Vision, Classification, Detection, Segmentation.",
        "for_ar": "الفرق التي وصلت إلى مرحلة التنفيذ.",
        "when_ar": "استخدم البحث عندما تحتاج تقنية معينة، لا تقرأه كاملاً.",
        "used_in": ["future: detection / segmentation"],
    },
    {
        "id": "S-15", "no": 15, "phase": _R, "kind": "Research paper",
        "title": "FreeDSM (arXiv)",
        "title_ar": "FreeDSM — ورقة بحثية على arXiv",
        "url": None,
        "level": "Advanced", "category": "inspiration_research",
        "goal_ar": "مثال على مشروع يجمع بين إنترنت الأشياء والذكاء الاصطناعي.",
        "learn_ar": "كيف تحول مشكلة واقعية إلى نظام يعتمد على AI.",
        "for_ar": "الفرق المتقدمة التي تريد إلهاماً أو فكرة عن البنية.",
        "when_ar": "قبل أو أثناء الهاكاثون. لا يُنصح به كمصدر تعلم أساسي.",
        "used_in": ["PROJECTS.MORS — dossier architecture pattern"],
    },
    {
        "id": "S-16", "no": 16, "phase": _R, "kind": "Research paper",
        "title": "LightViz (arXiv)",
        "title_ar": "LightViz — ورقة بحثية على arXiv",
        "url": None,
        "level": "Advanced", "category": "inspiration_research",
        "goal_ar": ("مثال على استخدام التكنولوجيا لمراقبة وتحليل التلوث "
                    "الضوئي."),
        "learn_ar": "يربط بين البيانات والمراقبة والتحليل في مشكلة واقعية.",
        "for_ar": "الفرق التي تعمل على تلوث الضوء أو مشاريع مشابهة.",
        "when_ar": "قبل أو أثناء الهاكاثون.",
        "used_in": ["agents/datasets.py", "PRJ-002 Light-Pollution model"],
    },
]

# ---------------------------------------------------------------------------
# 2. Live data sources actually consumed by this build
# ---------------------------------------------------------------------------
DATA_SOURCES: List[Dict[str, Any]] = [
    {"id": "D-01", "name": "NASA DONKI (CME / FLR)", "kind": "REST API",
     "url": "https://api.nasa.gov/DONKI/CME", "via": "api",
     "used_in": "agent1_ingestion.fetch_donki",
     "gives": "159 CME records + solar flares",
     "category": "data_handling"},
    {"id": "D-02", "name": "NASA NEOWS", "kind": "REST API",
     "url": "https://api.nasa.gov/neo/rest/v1/feed", "via": "api",
     "used_in": "agent1_ingestion.fetch_neows",
     "gives": "36 near-Earth objects, size / speed / miss distance",
     "category": "data_handling"},
    {"id": "D-03", "name": "JPL Horizons", "kind": "REST API",
     "url": "https://ssd.jpl.nasa.gov/api/horizons.api", "via": "api",
     "used_in": "agent1_ingestion.fetch_horizons",
     "gives": "1442 heliocentric vectors (Astropy transforms)",
     "category": "astronomical_data"},
    {"id": "D-04", "name": "NASA GIBS WMS (VIIRS Black Marble)",
     "kind": "WMS raster", "via": "api",
     "url": "https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi",
     "used_in": "datasets.light_pollution",
     "gives": "night-light tiles -> sky-brightness model, 11 sites",
     "category": "data_handling"},
    {"id": "D-05", "name": "NOAA SWPC planetary K-index", "kind": "JSON feed",
     "via": "api",
     "url": "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json",
     "used_in": "datasets.kp_index",
     "gives": "Kp 0-9 series + 3-sample smoothing + flare join",
     "category": "predictive_automation"},
    {"id": "D-06", "name": "NASA APOD", "kind": "REST API",
     "url": "https://api.nasa.gov/planetary/apod", "via": "api",
     "used_in": "mors_data.images()",
     "gives": "8 images with FITS-style header cards",
     "category": "computer_vision"},
    {"id": "D-07", "name": "NASA Exoplanet Archive (TAP)", "kind": "TAP/SQL",
     "via": "api",
     "url": "https://exoplanetarchive.ipac.caltech.edu/TAP/sync",
     "used_in": "mors_data.exoplanets()",
     "gives": "60 confirmed planets + habitability proxy",
     "category": "astronomical_data"},
    {"id": "D-08", "name": "CelesTrak GP (NORAD 2LE)", "kind": "TLE feed",
     "url": "https://celestrak.org/NORAD/elements/gp.php", "via": "api",
     "used_in": "mors_data._sat_api()",
     "gives": "50 objects balanced LEO/MEO/GEO + pass windows",
     "category": "data_handling"},
    {"id": "D-09", "name": "NIST Atomic Spectra Database", "kind": "Reference",
     "url": "https://physics.nist.gov/asd", "via": "local_model",
     "used_in": "mors_data.spectroscopy()",
     "gives": "laboratory line list for synthetic spectra",
     "category": "astronomical_data"},
    {"id": "D-10", "name": "Hipparcos / Gaia / RC3 / Sharpless / JPL",
     "kind": "Catalogues", "url": None, "via": "local_model",
     "used_in": "mors_data.objects()",
     "gives": "12 curated objects with ICRS coordinates",
     "category": "astronomical_data"},
    {"id": "D-11", "name": "Google Gemini API", "kind": "LLM API",
     "url": "https://ai.google.dev/", "via": "ai_synthesis",
     "used_in": "agent2_council / agent3_citations / agent4_aimors",
     "gives": "Council of 5, citations, Ai.Mors answers (429 -> local)",
     "category": "generative_ai"},
    {"id": "D-12", "name": "Local reference CSVs (./data)", "kind": "CSV",
     "url": None, "via": "local_model",
     "used_in": "agent1_ingestion.ingest_local_docs",
     "gives": "light-pollution, spectral and metric reference tables",
     "category": "analysis_modelling"},
]


def build() -> Dict[str, Any]:
    from datetime import datetime, timezone
    from .mors_data import badge, trace

    phases: Dict[str, int] = {}
    levels: Dict[str, int] = {}
    kinds: Dict[str, int] = {}
    by_cat: Dict[str, int] = {}
    for s in HACKATHON_SOURCES:
        phases[s["phase"]] = phases.get(s["phase"], 0) + 1
        levels[s["level"]] = levels.get(s["level"], 0) + 1
        kinds[s["kind"]] = kinds.get(s["kind"], 0) + 1
        by_cat[s["category"]] = by_cat.get(s["category"], 0) + 1

    cond_rows = []
    for c in CONDITIONS:
        cond_rows.append({
            "n": c["n"], "key": c["key"], "name": c["name"],
            "name_ar": c["name_ar"], "helps_ar": c["helps_ar"],
            "status": c["status"],
            "n_sources": len(c["sources"]),
            "n_used_in": len(c["used_in"]),
            "sources": c["sources"],
            "used_in": c["used_in"],
            "evidence": c["evidence"],
        })

    t = trace("ASI Hackathon source registry + project data sources",
              "curated registry -> condition mapping -> project evidence",
              "static registry, no network calls",
              dataset_id="MORS-SOURCES-v1.0.0", via="local_model",
              endpoint="/api/mors/sources",
              note="Phase 1 sources are preparation, phase 2 are build "
                   "references, phase 3 are research inspiration only.")
    return {
        "count": len(HACKATHON_SOURCES),
        "hackathon": HACKATHON_SOURCES,
        "data_sources": DATA_SOURCES,
        "conditions": cond_rows,
        "aggregates": {
            "by_phase": phases,
            "by_level": levels,
            "by_kind": kinds,
            "by_category": by_cat,
            "total": len(HACKATHON_SOURCES),
            "live_data_sources": sum(1 for d in DATA_SOURCES
                                     if d.get("via") == "api"),
            "conditions_covered": sum(1 for c in CONDITIONS
                                      if c.get("sources") and
                                      c.get("used_in")),
            "conditions_core": sum(1 for c in CONDITIONS
                                   if c["status"] == "core"),
            "conditions_extension": sum(1 for c in CONDITIONS
                                        if c["status"] == "extension"),
            "conditions_total": len(CONDITIONS),
        },
        "disclaimer_ar": ("لا يطلب من الفرق استخدام جميع المصادر أو اتباع ترتيب "
                          "محدد؛ يُنصح باختيار المصادر التي تناسب طبيعة المشكلة "
                          "ونوع البيانات ومستوى الفريقتقنية الذكاء الاصطناعي "
                          "التي اختارها."),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "trace": t,
        "badge": badge(t),
    }
