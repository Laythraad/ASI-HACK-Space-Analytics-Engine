# دليل لجنة التحكيمية — ASI-HACK Space Analytics Engine

**MORS Scientific Command Center** — نسخة نصية من `docs/COMMITTEE_GUIDE.pdf`.

- **تاريخ التوليد:** 2026-09-25 06:22 UTC
- **رقم التشغيل (run_id):** `run-20260925-061746-46a7`
- **حالة المجلس العلمي:** CERTIFIED — 96
- **عدد الملفات في الحزمة:** 35

> اقرأ هذا الدليل من الأعلى للأسفل؛ كل قسم ينتهي بنتيجة قابلة للتحقق بأمر واحد. إن أردت الأدلة التفصيلية فالمرجع `docs/MORS_REPORT.pdf`.

## الفهرس

- 1. نظرة عامة على الحزمة
- 2. كيف تقيّم المشروع خلال خمس دقائق
- 3. محتويات الحزمة — كل ملف وما يفعله
- 4. المعمارية: خط أنابيب الوكيلاء الأربعة
- 5. أرقام حيّة يمكن للجنة التحقق منها
- 6. الشروط الثمانية — كيف تخدم المصادر الفريق
- 7. المصادر العلمية الستة عشر
- 8. الاتفاقيات الإلزامية الخمسة
- 9. التحقق الذاتي — أثبتها بنفسك
- 10. حدود صادقة — ما لا ندّعي إنجازه
- 11. أين تجد كل مستند
- 12. إعادة توليد كل شيء
- 13. فريق العمل

## 1. نظرة عامة على الحزمة

هذه الحزمة هي التسليم الكامل لمشروع ASI-HACK Space Analytics Engine: محرك تحليل فضائي بأربعة وكلاء ذكاء اصطناعي، فوق واجهة قيادة علمية اسمها MORS Scientific Command Center. المشروع يحوّل بيانات فضاء حقيقية (NASA / NOAA / CelesTrak / NASA Exoplanet Archive) إلى مؤشرات جودة، ومشكلات مرتّبة بمعادلة أولوية، وحلول قابلة للتنفيذ، مع تتبّع كامل (traceability) يربط كل رقم بمصدره وطريقة المعالجة (method) ولحظة التحديث.

الحزمة قائمة بذاتها (self-contained): تُفكّ وتُشغّل بأمر واحد، ولا تحتاج أي خطوة بناء أو تجميع (no build step). كل مستند في الحزمة مولّد من الكود نفسه، لذلك لا يمكن أن يتعارض مع ما هو مكتوب فيه.

- **ملفات الحزمة** — 35
- **أسطر بايثون وHTML** — 16,530
- **وحدات MORS** — 19
- **مصادر علمية** — 16
- **جودة البيانات** — 99.81/100
- **صفوف معالَجة** — 1,711
- **نتيجة المجلس العلمي** — CERTIFIED 96/100
- **حالة الاختبار** — SELFTEST: PASS

#### ما الذي يحققه المشروع في شروط الهاكاثون

الشروط الثمانية مغطاة 8 من 8: منها 7 شروط أساسية منفَّذة بالكامل، وشرط واحد (الرؤية الحاسوبية) مغطى بثلاث مصادر على مستوى البيانات الفيزيائية (بطاقات FITS والصفائح الليلية) ومُسجَّل بوضوح كامتداد موثّق لا كادّعاء مُنجز — التفصيل في القسم 6 أدناه.


## 2. كيف تقيّم المشروع خلال خمس دقائق

الترتيب المقترح للجنة التحكيمية؛ كل خطوة تنتهي بنتيجة ملموسة يمكن التحقق منها فورًا.

| # | الإجراء | النتيجة المتوقعة |
|---|---|---|
| 1 | فكّ ضغط الحزمة ثم شغّل START.bat (أو python main.py) | خادم Flask يعمل على http://127.0.0.1:5000 |
| 2 | افتح http://127.0.0.1:5000/mors | واجهة MORS: شريط صحة البيانات + 18 وحدة في الشريط الجانبي |
| 3 | اضغط زر تشغيل الخط أنابيب (POST /api/pipeline/run) | تقرير معتمد 96/100 من خمسة خبراء (CERTIFIED) |
| 4 | افتح http://127.0.0.1:5000/mors#/sources | SOURCES.MORS: 16 مصدرًا علميًا + الشروط الثمانية |
| 5 | شغّل python main.py --selftest | سطر أخير: SELFTEST : PASS بعد نحو 75 ثانية |
| 6 | اقرأ 00_COMMITTEE_GUIDE.md ثم docs/COMMITTEE_GUIDE.pdf | هذا الدليل؛ ثم docs/MORS_REPORT.pdf للأدلة التفصيلية |
| 7 | طابق 00_MANIFEST.txt مع الملفات المستخرجة | حجم كل ملف + بصمة SHA-256 تطابق ما سُلّم |

#### ملاحظة عن مفاتيح API

المشروع يعمل من دون مفاتيح بالوضع المحلي الاحتياطي (local_model)، لكن .env يحوي مفتاح NASA ومتغيرات نماذج Gemini. إن لم تتوفر حصيلة (quota) مجانية، تنتقل الوكيلاء تلقائيًا إلى المحرك الاحتياطي الحتمي ويسجَّل هذا التحويل في council.engine وفي مشكلة P-001 — أي أن المشروع لا يتوقف ولا يختلق نتيجة بديلة.


## 3. محتويات الحزمة — كل ملف وما يفعله

القائمة بترتيب القراءة المقدَّم: المستندات المُصدَّرة أولًا، ثم نقطة الدخول، ثم الوكيلون، ثم الواجهات، ثم أدوات التوليد، ثم المستندات.

| الملف | الحجم | الدور |
|---|---|---|
| 00_COMMITTEE_GUIDE.md | 26.6 KB | Submission guide for the judging committee (Markdown) |
| 00_MANIFEST.txt | 6.0 KB | Package manifest (size + SHA-256 per file) |
| main.py | 30.3 KB | Flask orchestrator, HTTP API and CLI entry point |
| START.bat | 4.5 KB | Windows launcher with environment checks |
| requirements.txt | 469 B | Python dependency list |
| README.md | 9.5 KB | Front door: how to run, what it does, what it does not do |
| المشكلات_التي_تم_حلها.md | 23.2 KB | Problems solved — data & analysis defect log (Arabic) |
| DEPLOYMENT.md | 15.5 KB | Operations and deliverables manual |
| .env | 1.5 KB | Secrets — never committed |
| .gitignore | 164 B | Keeps secrets and runtime artifacts out of the repository |
| last_report.json | 82.1 KB | Persisted copy of the most recent pipeline report |
| agents/__init__.py | 341 B | Package façade for the four agents |
| agents/agent1_ingestion.py | 37.8 KB | Agent 1 — Ingest & Clean |
| agents/agent2_council.py | 15.3 KB | Agent 2 — Council of Five |
| agents/agent3_citations.py | 15.8 KB | Agent 3 — Citations & traceability |
| agents/agent4_aimors.py | 12.7 KB | Agent 4 — Ai.Mors conversational agent |
| agents/datasets.py | 32.4 KB | Dataset builders for the science widgets |
| agents/mors_data.py | 105.6 KB | MORS data layer — the 17 science modules |
| agents/sources_data.py | 28.8 KB | Scientific source registry and hackathon condition map |
| static/index.html | 44.2 KB | Legacy ASI-HACK dashboard (single file, no build step) |
| static/mors.html | 169.6 KB | MORS Scientific Command Center SPA |
| tools/audit_data.py | 48.3 KB | Read-only data & analysis audit (225+ checks) |
| tools/build_report.py | 83.9 KB | Generates docs/MORS_REPORT.pdf |
| tools/build_guide.py | 47.3 KB | Generates this document (docs/PROJECT_GUIDE.pdf) |
| tools/build_committee.py | 40.6 KB | Generates 00_COMMITTEE_GUIDE.md and docs/COMMITTEE_GUIDE.pdf |
| tools/build_zip.py | 4.0 KB | Portable packager — writes the submitted archive |
| prompts/council_prompt.txt | 4.9 KB | System prompt for Agent 2 (Council of Five) |
| prompts/aimors_prompt.txt | 4.8 KB | System prompt for Agent 4 (Ai.Mors) |
| data/light_pollution_reference.csv | 657 B | Reference night-light / sky-brightness table |
| data/reference_metrics.csv | 652 B | Reference metrics for the quality audit |
| data/spectral_reference.csv | 406 B | Laboratory emission-line list |
| docs/API_CONTRACT.md | 21.4 KB | Machine-readable-ish API contract |
| docs/MORS_REPORT.pdf | 549.6 KB | Generated platform report (43 pages) |
| docs/PROJECT_GUIDE.pdf | 182.2 KB | This document |
| docs/COMMITTEE_GUIDE.pdf | 142.8 KB | Submission guide for the judging committee (PDF) |

الإجمالي 35 ملفًا بحجم 1794 كيلوبايت (قبل الضغط).


## 4. المعمارية: خط أنابيب الوكيلاء الأربعة

كل طبقة مسؤولة عن سؤال واحد فقط، ويمرّ الملف بينها عبر سجل تتبّع مشترك؛ هذا ما يجعل الرقم القابل للتدقيق ممكنًا.

| الطبقة | الملف | السؤال الذي تجيب عنه |
|---|---|---|
| Agent 1 — Ingestion | agents/agent1_ingestion.py | ما البيانات؟ جمعها، تنظيفها، فحص جودتها، ورصد الشواذ |
| Agent 2 — Council | agents/agent2_council.py | هل يمكن الوثوق بها؟ خمسة خبراء مستقلون يمنحون نتيجة مُسبَّقة |
| Agent 3 — Citations | agents/agent3_citations.py | ما مصدر كل رقم؟ معادلات ومراجع وسجل تتبّع لكل ادعاء |
| Agent 4 — Ai.Mors | agents/agent4_aimors.py | كيف نشرحها للناس؟ واجهة محادثة عربية بخمسة مستويات علمية |
| Data layer | agents/mors_data.py | كيف نقدّمها كوحدات؟ 17 وحدة على ترتيب الاكتساب: API ثم AI ثم محلي |
| Science datasets | agents/datasets.py | ما الجداول المرجعية؟ التلوث الضوئي، الطيف، Kp، المقاييس |
| Source registry | agents/sources_data.py | ما المصادر العلمية وكيف تخدم الفريق؟ 16 مصدرًا + الشروط الثمانية |
| HTTP surface | main.py | كيف يصل المستخدم؟ Flask + /mors + /api/* + /api/chat |
| Front end | static/mors.html, static/index.html | ماذا يرى المختبر؟ SPA واحدة بلا إطار عمل ولا خطوة بناء |
| Document builders | tools/*.py | ماذا يحصل الحاكم؟ ثلاثة PDF تُولَّد من الـ API نفسه |

#### أصل البيانات (acquisition policy)

كل وحدة تمرّ على ثلاث مصادر بالترتيب نفسه: نداء API حقيقي → استدلال نموذج ذكاء اصطناعي → نموذج محلي حتمي، والمصدر الذي استُخدم فعلًا مكتوب في trace.via. لا تُعرض أبدًا رقم من غير أن يُذكر أي من هذه الطرق تم استخدامه.


## 5. أرقام حيّة يمكن للجنة التحقق منها

كل رقم في هذا القسم يأتي من استجابة API مباشرة وقت توليد الدليل؛ يمكن إعادة قراءتها بأمر واحد كما في القسم 9.

- **الجودة** — 99.81/100
- **الصفوف** — 1,711
- **الأقمار** — 50
- **المشكلات** — 5
- **الوحدات** — 19
- **المصادر** — 16
- **النتيجة** — 96/100
- **القرار** — CERTIFIED

| المؤشر | القيمة | النقطة (endpoint) |
|---|---|---|
| جودة البيانات | 99.81/100 | /api/mors/datahealth |
| الصفوف المعالَجة | 1,711 | /api/mors/datahealth |
| المصادر الحية | 8 | /api/mors/datahealth |
| الخلايا الناقصة | 0.192% | /api/mors/datahealth |
| الصفوف المكرّرة | 0% | /api/mors/datahealth |
| الاكتمال | 99.808% | /api/mors/datahealth |
| الدقة | 99.81% | /api/mors/datahealth |
| الشواذ المكتشفة | 167 (9.76%) | /api/mors/datahealth |
| قرار المجلس العلمي | CERTIFIED — 96/100 (محرك local_fallback) | /api/report |
| الأقمار الصناعية | 50 (LEO 24 / MEO 12 / GEO 14) | /api/mors/satellite |
| وحدات MORS | 19 | /api/mors |
| الكواكب خارج المجموعة الشمسية | 59 | /api/mors/exoplanets |
| أجرام قريبة من الأرض | 12 | /api/mors/objects |
| انبعاثات كروونية مسجّلة | 125 | /api/data/space-weather |
| انفجارات شمسية (30 يومًا) | 12 | /api/data/kp-index |
| أقصى مؤشر Kp | 4.33 من 9 | /api/data/kp-index |
| ال NEO المراقَب | 32 | /api/data/neo |
| أقرب اقتراب (يوم قمري) | 26.227 LD | /api/data/horizons |
| علاقة إنتروبيا كمّية (بيل) | 1 ebit | /api/data/quantum |
| مشكلات مفتوحة (مرتّبة) | 5 | /api/mors/problems |

#### سياق التقرير

رقم التشغيل الحالي run-20260925-061746-46a7 بتاريخ 2026-09-25T06:19:10.118819+00:00؛ خمسة خبراء (Dr. Orbit، Dr. Helios، Dr. Quantel، Dr. Terra، Dr. Vigil) يمنحون درجات مستقلة تُطابق وتُجمَّع، والنتيجة المجمّعة هي المعروضة أعلاه.


## 6. الشروط الثمانية — كيف تخدم المصادر الفريق

> لا يطلب من الفرق استخدام جميع المصادر أو اتباع ترتيب محدد؛ يُنصح باختيار المصادر التي تناسب طبيعة المشكلة ونوع البيانات ومستوى الفريقتقنية الذكاء الاصطناعي التي اختارها.

| الشرط | الحالة | المصادر | المعنى بالعربية | الأدلة في المستودع |
|---|---|---|---|---|
| 1. AI & Machine-Learning basics | مُنجز | S-01, S-02 | فهم أساسيات الذكاء الاصطناعي وتعلم الآلة | agents/agent1_ingestion.py — StandardScaler + IsolationForest; agents/agent2_council.py — five-expert scori... |
| 2. Working with data | مُنجز | S-03, S-04, S-05, S-10, S-11, S-12 | التعامل مع البيانات | agents/agent1_ingestion.py — DONKI, NEOWS, Horizons, Kp; agents/datasets.py — GIBS WMS VIIRS Black-Marble n... |
| 3. Data analysis & model building | مُنجز | S-08, S-09 | تحليل البيانات وبناء النماذج | agents/agent1_ingestion.py — cleaning log, quality audit; agents/datasets.py — PCA reduction of the spectra... |
| 4. Computer Vision | امتداد موثّق | S-06, S-13, S-14 | الرؤية الحاسوبية | static/mors.html — ASTRONOMY.MORS image grid + FITS headers; agents/mors_data.py images() — NASA APOD metad... |
| 5. Astronomical data | مُنجز | S-07 | البيانات الفلكية | agents/agent1_ingestion.py — Astropy Time/SkyCoord transforms; agents/mors_data.py — objects, FITS, photome... |
| 6. AI / Generative-AI applications | مُنجز | S-01, S-06, S-08 | تطبيقات الذكاء الاصطناعي التوليدي | agents/agent2_council.py — Gemini Council of 5; agents/agent3_citations.py — Gemini citation enrichment |
| 7. Predictive & automation systems | مُنجز | S-03, S-05, S-09, S-12 | الأنظمة التنبؤية والأتمتة | main.py — four-agent pipeline with stage log and auto-run; agents/agent1_ingestion.py — Kp 3-sample moving ... |
| 8. Inspiration & research | مُنجز | S-15, S-16 | الإلهام والبحث | agents/datasets.py — night-light -> sky-brightness model; PROJECTS.MORS — PRJ-002 Light-Pollution & Sky-Bri... |

الحالة «مُنجز» تعني أن هناك كودًا عاملًا في المستودع يحقّق الشرط؛ «امتداد موثّق» تعني أن المسار مُعرَّف ومفهوم السبب لم يُنفَّذ بعد وهو مسجّل في التقرير كمشكلة/امتداد — وهو ما يتوافق مع نص التعريف أعلاه الذي لا يلزم بترتيب استخدام المصادر.


## 7. المصادر العلمية الستة عشر

المصادر موزّعة على ثلاث مراحل: تحضير (Preparation)، أثناء الفرقعة (During)، وبحث وتأمل (Research). التوزيع: {"During": 7, "Preparation": 7, "Research": 2}.

| # | المصدر | المرحلة | المستوى | أين يُستخدم في المشروع |
|---|---|---|---|---|
| 1 | Google Machine Learning Crash Course | Preparation | Beginner -> Intermediate | agents/agent1_ingestion.py, agents/agent2_council.py |
| 2 | Machine Learning in Arabic (YouTube) | Preparation | Beginner | static/mors.html — AI.MORS tier panel |
| 3 | NASA ARSET Training | Preparation | Beginner -> Advanced | agents/datasets.py, agents/mors_data.py |
| 4 | Inside Look at How NASA Measures Air Pollution | Preparation | Beginner | agents/datasets.py — light-pollution pipeline |
| 5 | Machine Learning on Satellite Imagery (UN SDG Learn) | Preparation | Intermediate | agents/datasets.py — GIBS raster ingestion |
| 6 | Hugging Face Computer Vision Course | Preparation | Intermediate | static/mors.html — image gallery, future: pixel models |
| 7 | Astropy Documentation | Preparation | Intermediate | agents/agent1_ingestion.py, agents/mors_data.py |
| 8 | Google Colab | During | All levels | any notebook prototyping, main.py runs locally |
| 9 | Scikit-learn Documentation | During | Intermediate | agents/agent1_ingestion.py — StandardScaler, IsolationForest |
| 10 | NASA Earthdata Search | During | All levels | agents/agent1_ingestion.py, agents/datasets.py |
| 11 | NASA Worldview | During | All levels | agents/datasets.py — GIBS layer selection |
| 12 | NASA Nighttime Lights | During | Beginner | agents/datasets.py — VIIRS Black Marble tiles |
| 13 | Semantic Segmentation of Aerial Imagery (Kaggle) | During | Intermediate | future: segmentation prototype |
| 14 | Satellite Image Deep Learning Techniques (GitHub) | During | Advanced | future: detection / segmentation |
| 15 | FreeDSM (arXiv) | Research | Advanced | PROJECTS.MORS — dossier architecture pattern |
| 16 | LightViz (arXiv) | Research | Advanced | agents/datasets.py, PRJ-002 Light-Pollution model |

#### مصادر البيانات الفعلية التي يستدعيها المشروع

| الرمز | المصدر | طريقة الوصول | أين يُستدعى |
|---|---|---|---|
| D-01 | NASA DONKI (CME / FLR) | api | agent1_ingestion.fetch_donki |
| D-02 | NASA NEOWS | api | agent1_ingestion.fetch_neows |
| D-03 | JPL Horizons | api | agent1_ingestion.fetch_horizons |
| D-04 | NASA GIBS WMS (VIIRS Black Marble) | api | datasets.light_pollution |
| D-05 | NOAA SWPC planetary K-index | api | datasets.kp_index |
| D-06 | NASA APOD | api | mors_data.images() |
| D-07 | NASA Exoplanet Archive (TAP) | api | mors_data.exoplanets() |
| D-08 | CelesTrak GP (NORAD 2LE) | api | mors_data._sat_api() |
| D-09 | NIST Atomic Spectra Database | local_model | mors_data.spectroscopy() |
| D-10 | Hipparcos / Gaia / RC3 / Sharpless / JPL | local_model | mors_data.objects() |
| D-11 | Google Gemini API | ai_synthesis | agent2_council / agent3_citations / agent4_aimors |
| D-12 | Local reference CSVs (./data) | local_model | agent1_ingestion.ingest_local_docs |


## 8. الاتفاقيات الإلزامية الخمسة

هذه الاتفاقيات المطلوبة في التعريف، ويظهر تنفيذها في كل شاشة وكل تقرير:

- مخطط بطاقة المشكلة بعشرة مفاتيح إلزامية: problem_id, title, severity, category, component, symptom, root_cause, fix, evidence, priority — والمفاتيح الممنوعة (description, solution, notes, status, details) غير موجودة في أي بطاقة.
- معادلة الأولوية مشتقّة رقميًا: priority_score = 0.40×evidence + 0.35×impact + 0.25×confidence، وتصنيف High عند 75 فأكثر، Medium عند 50 فأكثر، وإلا Low. لا يُمنَح تصنيف يدويًا.
- شارة التتبّع [Source | Dataset Version | Processing Pipeline | Method | Last Updated | Operator | Timestamp] تظهر بجانب كل رسم وتحت كل وحدة.
- بروتوكول الذكاء الاصطناعي بخمسة مستويات: Observed Data / Calculated Metric / AI Interpretation / Hypothesis / Suggested Action — والنموذج لا يدّعي قياسًا قط أبدًا.
- سياسة الاكتساب الثلاثية: api ثم ai_synthesis ثم local_model، ومصدر الاستخدام مسجّل في trace.via.

```
priority_score = 0.40*evidence + 0.35*impact + 0.25*confidence
High >= 75   Medium >= 50   otherwise Low
```

علاوة على ذلك: لغة الواجهة عربية وإنجليزية، وضع ليلي/نهاري وشُعاعات كوكبية (Earth/Mars/Jupiter/Saturn/Neptune/Moon) تغيّر اللون فقط دون تغيير التخطيط، ولا يوجد نيون أو فوضى بصرية.


## 9. التحقق الذاتي — أثبتها بنفسك

بعد فكّ الضغط، تكفي هذه الأوامر للتأكدة من أن الحزمة سليمة وتعمل كما هو مُعلن:

```
python main.py --selftest
# ======================================================
#   verdict         : CERTIFIED
#   score           : 96/100
#   Ai.Mors greeting: 'أهلاً وسهلاً بكم في الفضاء' (ok=True)
#   SELFTEST        : PASS
```

ثم تحقق من الواجهات ونقاط النهاية:

```
python main.py                # ثم افتح http://127.0.0.1:5000/mors
curl http://127.0.0.1:5000/api/health
curl http://127.0.0.1:5000/api/mors
curl http://127.0.0.1:5000/api/mors/sources
curl http://127.0.0.1:5000/api/mors/datahealth
```

وبخصوص سلامة الملفات نفسها، قارن 00_MANIFEST.txt بالمستخرج؛ البصمة SHA-256 لكل ملف موجودة هناك.


## 10. حدود صادقة — ما لا ندّعي إنجازه

اللجنة تُكافأ على الشفافية لا على الكمال؛ هذه قائمة مفتوحة تُحدَّث تلقائيًا مع كل تشغيل للخط أنابيب وتصنَّف بالأولوية نفسها المستخدمة في الواجهة:

| الرمز | المشكلة | الأولوية | الثقة |
|---|---|---|---|
| P-001 | Council verification running in local fallback | High | 96% |
| P-006 | Multi-spectral profiles are reference spectra, not imagery | High | 98% |
| P-003 | Anomaly count is methodologically forced, not discovered | High | 97% |
| P-005 | Kp index window much shorter than the flare window | Medium | 93% |
| P-008 | Light-curve SNR leaves limited photometric headroom | Medium | 86% |

- P-001: تحقّق المجلس العلمي يعمل بالمحرك الاحتياطي المحلي عند نفاد حصيلة Gemini المجانية؛ الأرقام نفسها تبقى قابلة للتكرار لكنها غير مُتقاطعة من نموذج لغوي.
- P-006: الملفات متعددة الطيف مبنية على طيفات مرجعية لا مشاهد مُصنَّفة فعليًا — والمصدر مذكور صراحةً.
- P-003: عدد الشواذ (167) مشتقّ من معامل تلوث ثابت 0.1 لا من عتبة إحصائية مستنتجة — ولهذا هو معلَّم في التقرير.


## 11. أين تجد كل مستند

| المستند | محتواه | متى تفتحه |
|---|---|---|
| 00_COMMITTEE_GUIDE.md (و هذا PDF) | هذا الدليل: ملخص، شروط، مصادر، تحقق | الخطوة الأولى للجنة |
| README.md | التشغيل السريع وجدول نقاط النهاية | عند أول تشغيل |
| المشكلات_التي_تم_حلها.md | كل خلل في البيانات وتحليله: السبب، الإصلاح، الرقم قبل/بعد | عند مراجعة دقّة البيانات |
| DEPLOYMENT.md | النشر والتشغيل وجدول التسليمات | عند النشر أو التحقق من التغطية |
| tools/audit_data.py | 225+ فحصًا للقراءة فقط ← AUDIT: PASS | قبل أي إعادة توليد للمستندات |
| docs/API_CONTRACT.md | عقد الـ API كاملًا (§1-§20) | عند مراجعة الواجهات أو بناء عميل |
| docs/MORS_REPORT.pdf | التقرير العلمي: الجودة، المشكلات، الرسوم، المصادر، الحدود | للحجج والأدلة التفصيلية |
| docs/PROJECT_GUIDE.pdf | شرح ملف-ملف للمستودع | عند البحث عن مصدر سلوك معيّن |
| 00_MANIFEST.txt | حجم كل ملف وبصمة SHA-256 | للتحقق من سلامة الحزمة |
| last_report.json | آخر تقرير معتمد بRAW JSON | لإعادة تحليل الأرقام برمجيًا |


## 12. إعادة توليد كل شيء

كل المستندات الثلاثة (التقرير، دليل الملفات، هذا الدليل) تُبنى من نفس الكود ومن الـ API الحيّ؛ إعادة التوليد تأخذ دقيقة واحدة:

```
pip install -r requirements.txt   # + حزمة PDF الاختيارية أدناه
pip install reportlab arabic-reshaper python-bidi matplotlib
python main.py                     # اترك الخادم يعمل
python tools/audit_data.py         # -> RESULT: AUDIT: PASS
python tools/build_report.py       # -> docs/MORS_REPORT.pdf
python tools/build_guide.py        # -> docs/PROJECT_GUIDE.pdf
python tools/build_committee.py    # -> 00_COMMITTEE_GUIDE.md + docs/COMMITTEE_GUIDE.pdf
python tools/build_zip.py          # -> الحزمة النهائية
```

ولأن المحتوى مولَّد من الـ API، فإن أي رقم يتغيّر في المشروع يتغيّر تلقائيًا في المستندات — لا يوجد نص ثابت يدعي أمرًا لم يحدث.

---

دليل لجنة التحكيمية — نسخة 2026-09-25 06:22 UTC ؛ رقم التشغيل run-20260925-061746-46a7 ؛ الحالة CERTIFIED 96/100.


## 13. فريق العمل

4 أعضاء، ولكل واحد وحدات ومشكلات يملكها داخل MORS؛ نفس القائمة معروضة في واجهة TEAM.MORS وفي التقرير §9:

| العضو / الدور | المسؤوليات | الوحدات والمشكلات |
|---|---|---|
| ليث رعد | Team leadership · system architecture · pipeline integration · review | MORS architecture، HOME.MORS، PROJECTS.MORS، TEAM.MORS، P-007 |
| Data Analyst | Data cleaning · EDA · statistics · data quality · anomalies | DATA.MORS، PROBLEMS.MORS، SOLUTIONS.MORS، P-002، P-003، P-004 |
| Astronomy Researcher | Photometry · spectroscopy · FITS · light curves · sources | ASTRONOMY.MORS، SOURCES.MORS، P-005، P-006، P-008 |
| Space Systems & AI Engineer | Orbits · telemetry · AI model integration · quantum simulation | AI.MORS، SATELLITE.MORS، QUANTUM.MORS، P-001 |

المسؤوليات تشمل الوحدات (مثل HOME.MORS أو SPECTRAL.MORS) وأرقام المشكلات التي يحلّها العضو؛ المالك مذكور في بطاقة كل مشكلة وحل معًا، وفي سجل التتبّع MORS-TEAM-v1.1.0.
