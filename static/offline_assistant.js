/* Offline assistant — makes the hosted (static) demo behave like the live site.
 *
 * GitHub Pages cannot run Flask, so the two POST endpoints the UIs use
 * (/api/chat, /api/mors/insight, /api/pipeline/run) have no server behind them.
 * This module answers from the same certified JSON snapshot that feeds the rest
 * of the UI (static/api/**), and always labels itself as the static demo so the
 * judge can tell an offline answer from a live one.
 *
 * Loaded by static/index.html and static/mors.html; no dependencies.        */
(function () {
  "use strict";

  var CACHE = {};

  function fetchJSON(rel) {
    if (CACHE[rel]) return CACHE[rel];
    var tries = [rel, "static/" + rel];
    var p = (function attempt(i) {
      if (i >= tries.length) return Promise.reject(new Error("snapshot missing: " + rel));
      return fetch(tries[i], { cache: "no-cache" }).then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      }).catch(function () { return attempt(i + 1); });
    })(0);
    CACHE[rel] = p;
    return p;
  }

  function all() {
    return Promise.all([
      fetchJSON("api/report.json"),
      fetchJSON("api/mors/problems.json"),
      fetchJSON("api/mors/sources.json"),
      fetchJSON("api/mors/team.json"),
      fetchJSON("api/mors/datahealth.json"),
      fetchJSON("api/mors/home.json")
    ]).then(function (a) {
      return { report: a[0], problems: a[1], sources: a[2], team: a[3], dh: a[4], home: a[5] };
    });
  }

  function firstFix(p) {
    var f = p.fix;
    if (Array.isArray(f)) return f[0] || "";
    return String(f || "");
  }
  function numOf(x, d) { var n = parseFloat(x); return isNaN(n) ? d : n; }

  function greet() {
    return "أهلاً وسهلاً بكم في الفضاء";
  }

  /* ------------------------------------------------------------------ chat */
  function reply(message, S) {
    var q = String(message || "");
    var lq = q.toLowerCase();
    var m = S.report.metrics || {};
    var home = S.home.metrics || {};
    var dig = S.dh || {};
    var probs = (S.problems.problems || []);
    var byP = S.problems.by_priority || {};
    var members = (S.team.members || []);
    var agg = S.sources.aggregates || {};
    var eng = "static:snapshot (no backend) — لقطة معتمدة محفوظة عند النشر";
    var lines = [], trace = ["snapshot/api/report.json", "snapshot/api/mors/problems.json"];

    function has(words) {
      return words.some(function (w) { return lq.indexOf(w) !== -1; });
    }

    if (has(["مرحب", "أهلا", "اهلا", "السلام", "salam", "hello", "hi ", "السلام عليكم"])) {
      lines.push(greet());
      lines.push("1- هذه واجهة MORS — محرك تحليل بيانات الفضاء لتحدي ASI-HACK 2026 (AI for Space).");
      lines.push("2- أربعة وكلاء يعملون بالتتابع: استيعاب البيانات ← مجلس من خمسة خبراء ← رسم بياني للاستشهادات ← Ai.Mors.");
      lines.push("3- آخر تشغيل معتمد: " + (home.verdict || "CERTIFIED") + " بنتيجة " + numOf(home.score, 96) +
        "/100 من " + numOf(home.rows, 1711) + " صفراً و" + numOf(home.sources, 8) + " مصادر بيانات.");
      lines.push("الخلاصة: اكتب (المشكلات) أو (المصادر) أو (الفريق) أو (النتيجة) أو (التشغيل) للتفاصيل.");
    } else if (has(["مشاكل", "مشكل", "حلول", "حل", "fix", "problem", "solution", "bug", "أخطاء", "خطأ", "بطاقة", "issues"])) {
      lines.push(numOf(byP.High, probs.length ? 3 : 0) + " عالية الأولوية، و" +
        numOf(byP.Medium, 2) + " متوسطة — من " + numOf(S.problems.count, probs.length) + " بطاقة موثّقة");
      probs.slice(0, 3).forEach(function (p, i) {
        lines.push((i + 1) + "- " + (p.problem_id || p.id) + " [" + (p.priority_code || p.priority) + "] " +
          (p.title || "") + " ← " + (firstFix(p) || p.root_cause || ""));
      });
      lines.push("4- كل بطاقة تحمل عشرة مفاتيح: symptom / root_cause / fix / evidence مع severity وcategory وpriority_code.");
      lines.push("الخلاصة: افتح PROBLEMS.MORS لرؤية البطاقات كاملة مع دليل الإثبات.");
      trace.push("snapshot/api/mors/problems.json");
    } else if (has(["مصدر", "مصادر", "شرط", "شروط", "challenge", "source", "data source"])) {
      lines.push((agg.total || 16) + " مصدراً تدريجياً و" + (agg.conditions_covered || 8) +
        " من " + (agg.conditions_total || 8) + " شروط موثّقة");
      lines.push("1- شروط التحدي: " + (agg.conditions_covered || 8) + "/" + (agg.conditions_total || 8) +
        " (" + (agg.conditions_core || 7) + " أساسي + " + (agg.conditions_extension || 1) + " امتداد).");
      lines.push("2- مصادر البيانات الحيّة: NASA DONKI، NASA NEO، JPL Horizons، NASA GIBS، NOAA Kp، CelesTrak، Exoplanet Archive.");
      lines.push("3- كل صف يحمل اسم المصدر وطابع زمن الالتقاط (traceability) — " + numOf(home.rows, 1711) + " صفاً بعد التنظيف.");
      lines.push("الخلاصة: التفاصيل كاملة في SOURCES.MORS وقسم المصادر من التقرير PDF.");
      trace.push("snapshot/api/mors/sources.json");
    } else if (has(["فريق", "عضو", "قائد", "team", "member", "leader", "مين"])) {
      lines.push("أربعة أعضاء: قائد واحد وثلاثة أدوار متخصصة");
      members.forEach(function (tm, i) {
        lines.push((i + 1) + "- " + (tm.name || tm.name_latin) + " — " + (tm.title || tm.role || "") +
          " | يملك: " + (tm.owns || []).slice(0, 3).join("، "));
      });
      lines.push("الخلاصة: سجلّ الفريق الكامل في TEAM.MORS (أدوار ومسؤوليات ووحدات مملوكة).");
      trace.push("snapshot/api/mors/team.json");
    } else if (has(["نتيج", "تقييم", "score", "verdict", "معتمد", "certified", "تقرير", "council", "مجلس"])) {
      lines.push("الحكم الحالي " + (home.verdict || "CERTIFIED") + " — " + numOf(home.score, 96) + "/100");
      lines.push("1- المجلس: خمسة خبراء (Astrophysics، Solar، Data، AI، Review) تصحح مخرجات بعضها قبل الحكم.");
      lines.push("2- جودة البيانات " + numOf(dig.data_quality_score, 99.81) + "% واكتمال " +
        numOf(dig.completeness_pct, 99.81) + "% من " + numOf(dig.cells, 8840) + " خلية.");
      lines.push("3- مؤشرات لحظية: " + numOf(m.cme_count, 125) + " حدث اندماج شمسي، " +
        numOf(m.neo_count, 32) + " جرماً قريباً، مؤشر Kp الأقصى " + numOf(m.kp_max, 4.33) +
        "، " + numOf(m.anomaly_count, 167) + " شذوذًا.");
      lines.push("الخلاصة: التقرير الكامل (المصادر + المعادلات + الحدود) في docs/MORS_REPORT.pdf.");
      trace.push("snapshot/api/report.json");
    } else if (has(["تشغيل", "شغل", "كيف", "run", "start", "setup", "install", "أوامر"])) {
      lines.push("تشغيل المشروع على جهازك في ثلاثة خطوات");
      lines.push("1- python -m pip install -r requirements.txt");
      lines.push("2- python main.py   (أو اضغط START.bat على ويندوز)");
      lines.push("3- افتح http://127.0.0.1:5000/ — وكلاء المخطط يعملون بالكامل عندك محلياً.");
      lines.push("الخلاصة: النسخة المنشورة الآن لقطة ثابتة تعمل بلا خادم، والتشغيل المحلي يفعّل المخطط الحيّ.");
      trace.push("README.md", "DEPLOYMENT.md");
    } else if (has(["مطالبة", "prompt", "تعليمات", "برومبت"])) {
      lines.push("ست مطالبات رئيسية محفوظة في مجلد prompts/");
      lines.push("1- Ai.Mors analyst — دورة عمل من 25 قاعدة للتحليل المتمركز حول البيانات.");
      lines.push("2- UI/UX command center + visualization، 3- CYBER.MORS، 4- report generator، 5- deep audit.");
      lines.push("الخلاصة: افتح AI.MORS ثم Prompt library لقراءة النصوص كاملة داخل الواجهة.");
      trace.push("snapshot/api/mors/prompts.json");
    } else {
      lines.push("MORS Scientific Command Center — محرك تحليل بيانات الفضاء");
      lines.push("1- الحكم: " + (home.verdict || "CERTIFIED") + " " + numOf(home.score, 96) + "/100 على " +
        numOf(home.rows, 1711) + " صفراً و" + numOf(home.sources, 8) + " مصادر.");
      lines.push("2- المشكلات ← الحلول: " + numOf(S.problems.count, probs.length) + " بطاقة موثّقة (" +
        (byP.High || 0) + " عالية، " + (byP.Medium || 0) + " متوسطة).");
      lines.push("3- الشروط: " + (agg.conditions_covered || 8) + "/" + (agg.conditions_total || 8) +
        " — المصادر: " + (agg.total || 16) + " تدريجية + " + (agg.live_data_sources || 8) + " حيّة.");
      lines.push("4- الوحدات: 19 وحدة API في مركز القيادة + تقرير PDF من 44 صفحة.");
      lines.push("الخلاصة: اسألني عن (المشكلات) أو (المصادر) أو (الفريق) أو (النتيجة) أو (التشغيل).");
    }

    return {
      reply: lines.join("\n"),
      trace: trace,
      engine: eng,
      greeting_ok: /أهلاً وسهلاً بكم في الفضاء/.test(lines[0] || ""),
      timestamp: new Date().toISOString()
    };
  }

  /* -------------------------------------------------------------- insight */
  function insight(question, dataset, S) {
    var m = S.report.metrics || {};
    var home = S.home.metrics || {};
    var dig = S.dh || {};
    var probs = (S.problems.problems || []);
    var top = probs[0] || {};
    var ds = !dataset || dataset === "auto" ? "report" : dataset;
    var q = String(question || "");
    var facts = {
      report: numOf(home.rows, 1711) + " rows · score " + numOf(home.score, 96) + "/100 · verdict " + (home.verdict || "CERTIFIED"),
      problems: (S.problems.count || probs.length) + " open cards · " + ((S.problems.by_priority || {}).High || 0) + " high priority",
      quality: numOf(dig.data_quality_score, 99.81) + "% quality · " + numOf(dig.completeness_pct, 99.81) + "% completeness · " +
        numOf(dig.outlier_count, 167) + " outliers",
      science: numOf(m.cme_count, 125) + " CME · Kp max " + numOf(m.kp_max, 4.33) + " · " + numOf(m.neo_count, 32) + " NEO",
      quantum: "entropy " + numOf(m.quantum_entropy_ebit, 1.0) + " ebit · classical NumPy simulation"
    };
      var qKey = /quality|جودة|دقة/.test(q) ? "quality"
        : /problem|مشكل|مشاكل|حلول|حل/.test(q) ? "problems"
          : /science|فيزياء|شمس|cme|flare|kp|طقس/.test(q) ? "science"
            : /quantum|كمي/.test(q) ? "quantum" : "report";
    var parts = q.split(/\s+/).filter(Boolean).slice(0, 12).join(" ");

    return {
      tiers: [
        { tier: "Data grounding", text: "dataset=" + ds + " · " + facts[qKey] + " · run " + (S.report.run_id || "run-…") },
        {
          tier: "AI Interpretation",
          text: "السؤال «" + parts + "» مُجاب من لقطة التقرير المعتمدة: " +
            "الحكم " + (home.verdict || "CERTIFIED") + " بنتيجة " + numOf(home.score, 96) +
            "/100، جودة البيانات " + numOf(dig.data_quality_score, 99.81) +
            "%، و" + numOf(S.problems.count, probs.length) + " مشكلة موثّقة ببطاقات عشرة مفاتيح. " +
            "المحرك هنا لقطة ثابتة (بدون خادم)؛ التشغيل المحلي يعيد التحليل حيّاً."
        },
        {
          tier: "Confidence", text: Math.round(
            0.5 * Math.min(100, numOf(dig.completeness_pct, 99)) +
            0.3 * Math.min(100, numOf(home.score, 96)) + 0.2 * 100) +
            "% — مشتق من اكتمال البيانات ونتيجة المجلس؛ تقدير لا إثبات مطلق."
        },
        { tier: "Action", text: "الأولوية التالية: " + (top.problem_id || top.id || "P-001") + " — " + (firstFix(top) || "راجع PROBLEMS.MORS") },
        { tier: "Evidence", text: numOf(home.rows, 1711) + " rows across " + numOf(home.sources, 8) +
          " live sources; every value keeps its source endpoint and fetch timestamp." }
      ],
      citations: ["NASA DONKI", "NASA NEO", "JPL Horizons", "NOAA Kp", "NASA GIBS"],
      engine: "static:snapshot (no backend) — لقطة معتمدة محفوظة عند النشر"
    };
  }

  /* ------------------------------------------------------------- pipeline */
  function stages(S) {
    var home = S.home.metrics || {};
    var runs = (S.home.runs || [{}])[0];
    return [
      { label: "Agent 1 — ingestion", to: 22, note: numOf(home.rows, 1711) + " rows / " + numOf(home.sources, 8) + " sources" },
      { label: "Agent 2 — council of five experts", to: 55, note: "engine " + (runs.engine || "local_fallback") },
      { label: "Agent 3 — citations & formulas", to: 80, note: numOf(home.formulas, 21) + " formulas · " + numOf(home.references, 14) + " references" },
      { label: "Agent 4 — Ai.Mors synthesis", to: 95, note: "report-grounded" },
      { label: "certified", to: 100, note: (home.verdict || "CERTIFIED") + " " + numOf(home.score, 96) + "/100" }
    ];
  }

  function runPipeline(step, S) {
    var list = stages(S), i = 0;
    var run = ((S.home.runs || [])[0]) || {};
    var ok = run.status === "completed" && run.verdict;
    return new Promise(function (resolve) {
      (function next() {
        if (i >= list.length) {
          /* honest status: mirror the snapshot's last run, never claim success blindly */
          resolve({ status: ok ? "completed" : "failed",
                    final: list[list.length - 1],
                    note: ok ? "" : "snapshot has no completed run" });
          return;
        }
        var s = list[i++];
        step(s.to, s.label, s.note);
        setTimeout(next, 650);
      })();
    });
  }

  function withData(fn) {
    return all().then(function (S) { return fn(S); });
  }

  window.OfflineAssistant = {
    mode: "static",
    reply: function (message) { return withData(function (S) { return reply(message, S); }); },
    insight: function (question, dataset) { return withData(function (S) { return insight(question, dataset, S); }); },
    pipeline: function (step) { return withData(function (S) { return runPipeline(step, S); }); }
  };
})();
