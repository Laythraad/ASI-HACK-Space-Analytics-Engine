"""
AGENT 4 — "Ai.Mors" Conversational Space Agent
===============================================
Restricted STRICTLY to the certified report produced by Agents 1-3
(council verdict + metrics + citations + traceability).

MANDATORY: every reply begins with  "أهلاً وسهلاً بكم في الفضاء"
Format: numbered steps (1-, 2-, 3-, ...) with equations, data points and
academic citations. Works even offline via a deterministic template engine.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("agent4")

ROOT = Path(__file__).resolve().parent.parent
PROMPT_PATH = ROOT / "prompts" / "aimors_prompt.txt"

GREETING = "أهلاً وسهلاً بكم في الفضاء"


class AiMorsAgent:
    """Agent 4: certified-data-only chat agent (Gemini API)."""

    def __init__(self, api_key: Optional[str], model: str = "gemini-3.1-pro-preview",
                 fallback_model: str = "gemini-flash-latest") -> None:
        self.api_key = api_key
        self.model = model
        self.fallback_model = fallback_model
        self.system_prompt = (
            PROMPT_PATH.read_text(encoding="utf-8") if PROMPT_PATH.exists() else ""
        )

    # ---------------------------------------------------------- data digest
    @staticmethod
    def _context(report: Dict[str, Any]) -> str:
        """Compact certified digest — the ONLY allowed source of truth."""
        council = report.get("council", {}) or {}
        cites = report.get("citations", {}) or {}
        dsu = report.get("dataset_summary", {}) or {}
        metrics = dsu.get("metrics") or report.get("metrics", {})
        sci = report.get("science") or dsu.get("science") or {}

        lp = sci.get("light_pollution") or {}
        kp = sci.get("kp_index") or {}
        sp = sci.get("spectral") or {}
        qt = sci.get("quantum") or {}
        sites = (lp.get("sites") or [])
        bell = (qt.get("states") or {}).get("bell") or {}

        digest = {
            "council_verdict": council.get("verdict"),
            "council_score": council.get("overall_score"),
            "council_summary": council.get("summary"),
            "council_experts": [
                {"name": e.get("name"), "role": e.get("role"),
                 "score": e.get("score")}
                for e in (council.get("experts") or [])],
            "metrics": metrics,
            "sources": [s.get("name") for s in dsu.get("sources", [])],
            "cleaning": (dsu.get("cleaning") or [])[:8],
            "formulas": [f.get("name") for f in (cites.get("formulas") or [])][:14],
            "traceability_ids": [t.get("id") for t in (cites.get("traceability") or [])][:14],
            "references": [r.get("url") for r in (cites.get("references") or [])][:10],
            "light_pollution": {
                "model": lp.get("model", {}),
                "sites": [{"name": s.get("name"),
                           "radiance_nw_cm2_sr": s.get("radiance_nw_cm2_sr"),
                           "nelm_mag": s.get("nelm_mag"),
                           "bortle_model": s.get("bortle_model")}
                          for s in sites[:11]],
            },
            "space_weather": {
                "kp_scale": (kp.get("scale") or {}),
                "kp_latest": (kp.get("kp") or [{}])[-1],
                "kp_max": max([p.get("kp") or 0 for p in (kp.get("kp") or [])],
                              default=None),
                "flares_last5": [{"t": f.get("t"), "class": f.get("class"),
                                  "peak_flux_w_m2": f.get("peak_flux_w_m2")}
                                 for f in (kp.get("flares") or [])[-5:]],
                "daily_last7": (kp.get("daily") or [])[-7:],
                "provenance": kp.get("source", {}),
            },
            "spectral": {
                "bands": sp.get("bands", []),
                "profiles": [{"land_cover": p.get("land_cover"),
                              "reflectance": p.get("reflectance"),
                              "ndvi": p.get("ndvi")}
                             for p in (sp.get("profiles") or [])],
                "processing": sp.get("processing", {}),
                "provenance": sp.get("provenance", {}),
            },
            "quantum": {
                "bell_entropy_ebit": bell.get("entanglement_entropy_ebit"),
                "bell_expectation": bell.get("expectation"),
                "verification": qt.get("verification", {}),
                "honesty": qt.get("honesty", ""),
                "qho_levels": (qt.get("qho_levels") or {}).get("levels", [])[:4],
            },
        }
        return json.dumps(digest, ensure_ascii=False, indent=1, default=str)

    # --------------------------------------------------------------- prompt
    def _build_contents(self, message: str, history: List[Dict[str, Any]],
                        report: Dict[str, Any]) -> List[Dict[str, Any]]:
        system_block = (
            f"{self.system_prompt}\n\n"
            "=== CERTIFIED DATA PAYLOAD (sole source of truth) ===\n"
            f"{self._context(report)}\n"
            "=== END PAYLOAD ===\n"
            "If the question is not answerable from this payload, say the certified "
            "dataset does not cover it; offer the nearest certified metric. "
            "NEVER invent numbers, DOIs or NASA results."
        )
        contents: List[Dict[str, Any]] = [{"role": "user", "parts": [system_block]}]
        for turn in (history or [])[-8:]:
            role = "model" if turn.get("role") in {"model", "assistant"} else "user"
            text = turn.get("parts") or turn.get("content") or ""
            if isinstance(text, list):
                text = " ".join(str(p.get("text", p) if isinstance(p, dict) else p)
                                for p in text)
            if str(text).strip():
                contents.append({"role": role, "parts": [str(text)]})
        contents.append({"role": "user", "parts": [message]})
        return contents

    # -------------------------------------------------------------- fallback
    def _offline_reply(self, message: str, report: Dict[str, Any]) -> str:
        """Deterministic grounded answer in the mandatory response format."""
        council = report.get("council", {}) or {}
        dsu = report.get("dataset_summary", {}) or {}
        metrics = dsu.get("metrics") or report.get("metrics", {}) or {}
        cites = report.get("citations", {}) or {}
        sci = report.get("science") or dsu.get("science") or {}
        lp = sci.get("light_pollution") or {}
        kp = sci.get("kp_index") or {}
        sp = sci.get("spectral") or {}
        qt = sci.get("quantum") or {}
        trace = (cites.get("traceability") or [{}])[0]
        refs = cites.get("references") or [{}]
        verdict = council.get("verdict", "—")
        score = council.get("overall_score", "—")

        bell = (qt.get("states") or {}).get("bell") or {}
        kp_last = (kp.get("kp") or [{}])[-1]
        pca = (sp.get("processing") or {}).get("explained_variance_ratio") or []

        steps = [
            f"1- السؤال المستلم: «{message[:150]}». الإجابة مبنية حصراً على التقرير "
            f"المعتمد من مجلس الخبراء الخمسة ({verdict} — {score}/100).",
            "2- المعادلات المرجعية: قانون كبلر $$T^2 = \\frac{a^3}{G M_\\odot}$$، "
            "ومعادلة سطوع سماء الليل $$\\mu = 17.836 - 2.5\\log_{10}(L)$$ ثم "
            "حدود الرؤية $$NELM = \\mu - 14.6$$، "
            "والإطار الكمّي $$\\langle O\\rangle = \\langle\\psi|O|\\psi\\rangle$$.",
            f"3- القيم المعتمدة: CME={metrics.get('cme_count', 'n/a')}، "
            f"NEO={metrics.get('neo_count', 'n/a')}، "
            f"أقرب مسافة={metrics.get('closest_au', 'n/a')} au "
            f"({metrics.get('closest_ld', 'n/a')} LD)، "
            f"Kp الأقصى={metrics.get('kp_max', 'n/a')} (آخر قراءة "
            f"{kp_last.get('kp', 'n/a')} عند {kp_last.get('t', 'n/a')})، "
            f"شذوذات={metrics.get('anomaly_count', 'n/a')}، "
            f"أصفى موقع NELM={metrics.get('darkest_site_nelm', 'n/a')} mag مقابل "
            f"أعتمه موقع={metrics.get('brightest_site_nelm', 'n/a')} mag، "
            f"إنتروبيا ارتباط بيل={bell.get('entanglement_entropy_ebit', 'n/a')} ebit، "
            f"إنفساح PCA={[round(v, 3) for v in pca]}.",
            (f"4- التتبع: {trace.get('id', 'TRC-???')} ← "
             f"{trace.get('endpoint', 'NASA API')} "
             f"({trace.get('timestamp', 'n/a')}). المرجع: "
             f"{refs[0].get('title', 'NASA API Documentation') if refs else 'NASA'} — "
             f"{refs[0].get('url', 'https://api.nasa.gov') if refs else 'https://api.nasa.gov'}. "
             f"ملحوظة: بيانات الضوء الليلي من {((lp.get('source') or {}).get('layer') or 'NASA GIBS')} "
             f"وحدات Kp/الشمس من {(kp.get('source') or {}).get('provider', 'NOAA/NASA')}; "
             f"النتائج الكمّية {qt.get('honesty', 'محاكاة كلاسيكية بدون معالج كمّي')[:120]}."),
        ]
        body = "\n".join(steps) + "\nالخلاصة: جميع القيم أعلاه مستخرجة من التقرير المُعتمد محلياً."
        return f"{GREETING}\n{body}"

    # ------------------------------------------------------------------ run
    def chat(self, message: str, history: Optional[List[Dict[str, Any]]],
             report: Dict[str, Any]) -> Dict[str, Any]:
        message = (message or "").strip()
        trace_ids = [t.get("id") for t in
                     ((report.get("citations", {}) or {}).get("traceability") or [])][:5]
        reply: str = ""
        engine = "deterministic_fallback"

        if not report:
            reply = (f"{GREETING}\n"
                     "1- لم يُشغَّل المخطط بعد، لذا لا يوجد تقرير معتمد.\n"
                     "2- زُر «تشغيل المخطط / Run Pipeline» أولاً لبناء قاعدة المعرفة "
                     "المعتمدة من مجلس الخبراء الخمسة.\n"
                     "3- بعد الاعتماد ستكون كل إجاباتي مربوطة بـ Traceability IDs "
                     "ومراجع NASA الرسمية.\n"
                     "الخلاصة: شغّل المخطط لتحصل على إجابات معتمدة علمياً.")
            return {"reply": reply, "greeting_ok": True, "trace": [],
                    "engine": engine,
                    "timestamp": datetime.now(timezone.utc).isoformat()}

        if self.api_key:
            import google.generativeai as genai

            chain = [self.model] + ([self.fallback_model]
                                    if self.fallback_model and
                                    self.fallback_model != self.model else [])
            for model_name in chain:
                try:
                    genai.configure(api_key=self.api_key)
                    model = genai.GenerativeModel(
                        model_name=model_name,
                        system_instruction=self.system_prompt,
                        generation_config={"temperature": 0.4,
                                           "max_output_tokens": 1200})
                    resp = model.generate_content(
                        self._build_contents(message, history or [], report))
                    text = (resp.text or "").strip()
                    if text:
                        reply = text
                        engine = f"gemini:{model_name}"
                        break
                except Exception as exc:  # noqa: BLE001
                    # CHAT IS LATENCY-SENSITIVE: no sleeps here. On a quota hit we
                    # fall through to the next model and finally to the grounded
                    # offline template, which answers instantly.
                    log.warning("Ai.Mors model %s failed (%s)",
                                model_name, str(exc)[:200])
                    continue
        else:
            reply = ""

        if not reply:
            reply = self._offline_reply(message, report)

        # HARD CONSTRAINT 1: enforce the mandatory greeting
        greeting_ok = reply.lstrip().startswith(GREETING)
        if not greeting_ok:
            reply = f"{GREETING}\n{reply.lstrip()}"
            greeting_ok = True

        return {
            "reply": reply,
            "greeting_ok": greeting_ok,
            "trace": trace_ids,
            "engine": engine,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
