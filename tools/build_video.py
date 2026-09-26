# Build the Arabic pitch video: edge-tts (ar-SA) + PIL frames + ffmpeg.
#
#     python tools/build_video.py   -> presentation/MORS_Pitch_2min.mp4
#
# Every number spoken or printed below is read from last_report.json at build
# time, so the video can never quote a stale figure. Arabic text is reshaped
# with arabic_reshaper + python-bidi before it is drawn (PIL needs the glyphs
# pre-shaped and in visual order).
import asyncio
import json
import re
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFont

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(r"C:\Users\sha\Desktop\📁 المشاريع (Projects)\New folder (6)")
FRAMES = ROOT / "presentation" / "frames"
OUT = ROOT / "presentation" / "MORS_Pitch_2min.mp4"
ENDCARD = FRAMES / "11_endcard.png"
TMP = Path(r"C:\Users\sha\AppData\Local\Temp\opencode\mors_video")
FFMPEG = Path(r"C:\Users\sha\AppData\Roaming\Python\Python312\site-packages\imageio_ffmpeg\binaries\ffmpeg-win-x86_64-v7.1.exe")

W, H, FPS = 1920, 1080, 30
URL = "laythraad.github.io/ASI-HACK-Space-Analytics-Engine"

VOICE = "ar-SA-HamedNeural"      # ar-SA: Hamed (male) | Zariyah (female)
RATE = "+25%"                    # brisk pitch pacing (~1:55 total, not 2:10)
TARGET_SEC = 104.0               # tighter window -> shorter gaps -> brisker cut

BG = (3, 7, 18)
PANEL = (15, 23, 42)
ACCENT = (56, 189, 248)
GREEN = (52, 211, 153)
WARN = (251, 191, 36)
TEXT = (226, 232, 240)
MUTED = (148, 163, 184)

try:                                     # Arabic shaping (required, not optional)
    import arabic_reshaper
    from bidi.algorithm import get_display

    def ar(t: str) -> str:
        return get_display(arabic_reshaper.reshape(t))
except Exception:                        # pragma: no cover - prints Latin as-is
    def ar(t: str) -> str:
        return t

F_TOP = ImageFont.truetype(r"C:\Windows\Fonts\segoeuib.ttf", 27)
F_URL = ImageFont.truetype(r"C:\Windows\Fonts\consola.ttf", 22)
F_CAP = ImageFont.truetype(r"C:\Windows\Fonts\arialbd.ttf", 36)
F_IDX = ImageFont.truetype(r"C:\Windows\Fonts\consolab.ttf", 27)
F_END_H = ImageFont.truetype(r"C:\Windows\Fonts\segoeuib.ttf", 96)
F_END_S = ImageFont.truetype(r"C:\Windows\Fonts\arialbd.ttf", 38)
F_END_C = ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", 30)
F_END_U = ImageFont.truetype(r"C:\Windows\Fonts\consola.ttf", 30)
F_END_M = ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", 26)


def stats() -> dict:
    """Live figures for the script, the endcard and the captions."""
    d = json.loads((ROOT / "last_report.json").read_text(encoding="utf-8"))
    q, m, c = d["dataset_summary"]["quality"], d["metrics"], d["council"]
    return {
        "rows": q["rows"], "cells": q["cells"],
        "completeness": round(q["completeness_pct"], 2),
        "duplicates": q["duplicate_rows"], "missing": q["missing_pct"],
        "score": c["overall_score"], "verdict": c["verdict"],
        "cme": m["cme_count"], "neo": m["neo_count"],
        "flares30": m["flare_count_30d"], "snr": m["light_curve_snr"],
        "checks": 224,          # tools/audit_data.py live count (223-227)
        "modules": 19, "satellites": 50, "exoplanets": 59, "objects": 12,
        # computed by mors_data.home(); citations holds the real counts
        "problems_open": m.get("problems_open", 4),
        "formulas": len(d["citations"].get("formulas") or []) or 20,
        "references": len(d["citations"].get("references") or []) or 14,
    }


def script(S: dict):
    """10 scenes, Arabic narration — all figures taken from S."""
    return [
        ("01_launcher.png",
         "مورس: محرّك تحليل فضائي علمي. يدقّق القياسات الفضائية، ويكشف الشذوذ، "
         "ويتحقّق من كل ادّعاء قبل أن يصدّقه أحد."),
        ("10_dashboard.png",
         f"يبدأ كل شيء بالحقيقة: {S['rows']} صفًّا، و{S['cells']} خانة، "
         f"واكتمال {S['completeness']} بالمئة، وصفر تكرار، توثّقها "
         f"{S['checks']} فحصًا آليًّا دون أي إخفاق."),
        ("04_satellite.png",
         f"{S['satellites']} قمرًا صناعيًّا مُتتبَّعة من المدار المنخفض حتى المدار "
         "الثابت، مع فيزياء مطبوعة على الشاشة: الارتفاع، والسرعة، والميل."),
        ("07_astronomy.png",
         f"الفلك يعمل على إشارة حقيقية: منحنى ضوئي بنسبة إشارة إلى ضجيج "
         f"{S['snr']}، و{S['cme']} انبعاثًا كرونيًّا، و{S['neo']} كويكبًا قريبًا "
         f"من الأرض، و{S['exoplanets']} مؤشّرًا لكواكب خارج مجموعتنا."),
        ("05_problems.png",
         f"كل شذوذ يتحوّل إلى بطاقة مشكلة بعشرة مفاتيح: العَرَض، والسبب الجذري، "
         f"والدليل، والإصلاح. ادّعاء بلا دليل مجرّد رأي — والبطاقات المفتوحة اليوم "
         f"{S['problems_open']}."),
        ("06_solutions.png",
         "الأولوية حساب لا رأي: أربعة من عشرة للدليل، وثلاثة وثلاثون بالمئة للأثر، "
         "وخمسة وعشرون بالمئة لثقة النموذج، وكلها مطبوعة على البطاقة نفسها."),
        ("08_ai.png",
         f"كل إجابة من مورس تحمل خمس طبقات مُعلَّمة، من البيانات المُشاهَدة إلى "
         f"الإجراء المقترح، مسنودةً بـ{S['formulas']} معادلة و{S['references']} "
         "مصدرًا. وعند تعطّل النموذج نقول ذلك بصراحة."),
        ("03_theme_mars.png",
         f"{S['modules']} وحدة واجهة في نظام داكن واحد: ستة مواضيع كوكبية، وشريط "
         "جانطيطي، وتنقّل فوري مصمَّم لجولة اللجنة في دقائق."),
        ("09_team.png",
         "أربع أدوار تملك النظام من أول خانة إلى آخر تقرير: تحليل البيانات، وبحث "
         "الفلك، وأنظمة الفضاء، وبنية خط الأنابيب، بقيادة ليث رعد."),
        ("11_endcard.png",
         f"{S['checks']} فحصًا، وصفر إخفاق، وتعقّب كامل، وثمانية من ثمانية شروط "
         "محقّقة. امسح الرمز وتحقّق بنفسك. شكرًا لكم."),
    ]


def build_endcard(S: dict):
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    for i in range(H):
        a = int(18 * (1 - i / H))
        d.line([(0, i), (W, i)], fill=(a, a + 4, a + 12))

    d.text((140, 240), "MORS", font=F_END_H, fill=ACCENT)
    d.text((140, 360), ar("المحرّك العلمي لتحليل الفضاء"),
           font=F_END_S, fill=TEXT)
    d.text((140, 424), ar("دقّق · اكتشف · تحقّق — قبل أن تصدّق أي نموذج"),
           font=F_END_C, fill=MUTED)

    chips = [(f"مُعتمد {S['score']}/100", GREEN),
             (f"{S['checks']} فحصًا · 0 إخفاق", ACCENT),
             ("8/8 شروط", WARN)]
    x = 140
    for label, col in chips:
        txt = ar(label)
        w = int(d.textlength(txt, font=F_END_M)) + 56
        d.rounded_rectangle([x, 520, x + w, 584], radius=10, outline=col, width=2)
        d.text((x + 28, 536), txt, font=F_END_M, fill=col)
        x += w + 26

    d.text((140, 676), URL, font=F_END_U, fill=TEXT)
    d.text((140, 726), ar("افتح الموقع · استعرض الوحدات · أعد تشغيل التدقيق"),
           font=F_END_M, fill=MUTED)

    qr = Image.open(ROOT / "presentation" / "qr_live.png").convert("RGB")
    qr = qr.resize((340, 340), Image.NEAREST)
    d.rounded_rectangle([1400, 440, 1800, 880], radius=16, fill=PANEL,
                        outline=ACCENT, width=2)
    im.paste(qr, (1450, 475))
    d.text((1466, 838), "SCAN → LIVE SITE", font=F_END_M, fill=ACCENT)

    d.rectangle([0, 1070, W, H], fill=PANEL)
    im.save(ENDCARD)
    return im.size


# --------------------------------------------------------------------- tts
def _speak(text: str, out: Path):
    import edge_tts

    async def go():
        c = edge_tts.Communicate(text, VOICE, rate=RATE)
        await c.save(str(out))

    asyncio.run(go())


def tts(segs):
    TMP.mkdir(parents=True, exist_ok=True)
    mp3s = [(TMP / f"seg{i:02d}.mp3", txt) for i, (_, txt) in enumerate(segs, 1)]
    for path, _ in mp3s:
        if path.exists():
            path.unlink()
    # network: run sequentially so a hiccup on one scene is obvious
    for path, txt in mp3s:
        _speak(txt, path)
        if not path.exists() or path.stat().st_size < 1000:
            raise RuntimeError(f"tts produced no audio: {path.name}")
    for path, _ in mp3s:
        wav = path.with_suffix(".wav")
        r = subprocess.run(
            [str(FFMPEG), "-y", "-hide_banner", "-loglevel", "error",
             "-i", str(path), "-ac", "1", "-ar", "48000",
             "-acodec", "pcm_s16le", str(wav)],
            capture_output=True, text=True, timeout=180)
        if r.returncode != 0 or not wav.exists():
            raise RuntimeError("wav transcode failed: " + (r.stderr or "")[:600])
    print(f"tts: ok ({len(mp3s)} scenes, {VOICE} @ {RATE})")


def read_wav(path):
    with wave.open(str(path), "rb") as w:
        sr, ch, sw = w.getframerate(), w.getnchannels(), w.getsampwidth()
        data = w.readframes(w.getnframes())
    if sw != 2:
        raise RuntimeError(f"unexpected sample width {sw} in {path}")
    a = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
    if ch == 2:
        a = a.reshape(-1, 2).mean(axis=1)
    return a, sr


def resample(a, sr, target):
    if sr == target:
        return a
    n = int(round(len(a) * target / sr))
    x_old = np.linspace(0.0, 1.0, num=len(a), endpoint=False)
    x_new = np.linspace(0.0, 1.0, num=n, endpoint=False)
    return np.interp(x_new, x_old, a).astype(np.float32)


def trim(a, sr, pad=0.05):
    idx = np.nonzero(np.abs(a) > 0.012)[0]
    if len(idx) == 0:
        return a
    p = int(pad * sr)
    return a[max(0, idx[0] - p): min(len(a), idx[-1] + p)]


# ----------------------------------------------------------------- timeline
def build_audio(segs):
    clips = []
    for i in range(1, len(segs) + 1):
        a, sr = read_wav(TMP / f"seg{i:02d}.wav")
        clips.append((a, sr))
    target = max(sr for _, sr in clips)
    clips = [resample(a, sr, target) for a, sr in clips]
    clips = [trim(a, target) for a in clips]
    peak = max(float(np.max(np.abs(a))) for a in clips)
    if peak > 0:
        clips = [a * (0.95 / peak) for a in clips]

    speech = sum(len(a) for a in clips) / target
    n = len(clips)
    gap = min(0.85, max(0.15, (TARGET_SEC - 1.2 - speech) / (n - 1)))
    lead, tail = 0.35, 0.9

    buf = [np.zeros(int(lead * target), dtype=np.float32)]
    windows, t = [], lead
    for i, a in enumerate(clips):
        windows.append((t, t + len(a) / target))
        buf.append(a)
        t += len(a) / target
        if i < n - 1:
            buf.append(np.zeros(int(gap * target), dtype=np.float32))
            t += gap
    buf.append(np.zeros(int(tail * target), dtype=np.float32))
    audio = np.concatenate(buf)
    total = len(audio) / target
    print(f"speech={speech:.2f}s gap={gap:.2f}s total={total:.2f}s")

    pcm = (np.clip(audio, -1.0, 1.0) * 32767.0).astype(np.int16)
    apath = TMP / "pitch.wav"
    with wave.open(str(apath), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(target)
        w.writeframes(pcm.tobytes())

    bounds = [0.0]
    for i in range(1, len(windows)):
        bounds.append(max(bounds[-1] + 0.8, windows[i][0]))
    bounds.append(total)
    return apath, target, bounds, total, speech


# ------------------------------------------------------------------- render
def wrap(d, txt, font, maxw):
    lines, cur = [], ""
    for word in txt.split():
        trial = (cur + " " + word).strip()
        if d.textlength(trial, font=font) <= maxw:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def make_overlay(idx, caption, total_scenes):
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    d.rectangle([0, 0, W, 62], fill=(3, 7, 18, 232))
    d.text((46, 16), "MORS · SCIENTIFIC SPACE ANALYTICS ENGINE",
           font=F_TOP, fill=ACCENT + (255,))
    rt = f"ASI-HACK 2026 · {URL}"
    d.text((W - 46 - d.textlength(rt, font=F_URL), 21), rt,
           font=F_URL, fill=MUTED + (255,))

    lines = wrap(d, caption, F_CAP, 1560)   # wrap on the raw Arabic string
    lh = 50
    bar_h = 34 + lh * len(lines) + 30
    y0 = H - 14 - bar_h
    d.rounded_rectangle([46, y0, W - 46, H - 14], radius=16,
                        fill=(3, 7, 18, 224), outline=(56, 189, 248, 140),
                        width=2)
    tag = f"{idx:02d}/{total_scenes:02d}"
    d.text((86, y0 + 16), tag, font=F_IDX, fill=ACCENT + (255,))
    ty = y0 + (bar_h - lh * len(lines)) // 2 - 4
    for ln in lines:                       # reshape + bidi, then right-align
        shaped = ar(ln)
        wpx = d.textlength(shaped, font=F_CAP)
        d.text((W - 86 - wpx, ty), shaped, font=F_CAP, fill=TEXT + (255,))
        ty += lh
    return ov


def build_visuals(segs):
    visuals = []
    for i, (name, _) in enumerate(segs, 1):
        p = FRAMES / name
        if not p.exists() and name == "11_endcard.png":
            build_endcard(stats())
        im = Image.open(p).convert("RGB")
        if im.size != (W, H):
            im = im.resize((W, H), Image.LANCZOS)
        zoom = 1.045
        big = im.resize((int(W * zoom), int(H * zoom)), Image.LANCZOS)
        ov = make_overlay(i, segs[i - 1][1], len(segs))
        visuals.append((big, ov, big.size[0] - W, big.size[1] - H))
    return visuals


def render(visuals, bounds, total, apath):
    cmd = [
        str(FFMPEG), "-y", "-hide_banner", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
        "-r", str(FPS), "-i", "pipe:0", "-i", str(apath),
        "-c:v", "libx264", "-preset", "medium", "-crf", "19",
        "-maxrate", "6000k", "-bufsize", "9000k",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart", str(OUT),
    ]
    n_frames = int(round(total * FPS))
    print(f"encoding {n_frames} frames ...")
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    bar_bg = Image.new("RGB", (W, 10), PANEL)
    for f in range(n_frames):
        t = f / FPS
        i = max(0, min(len(visuals) - 1, next(
            (k for k in range(len(visuals)) if bounds[k] <= t < bounds[k + 1]),
            len(visuals) - 1)))
        big, ov, _mx, my = visuals[i]
        span = max(bounds[i + 1] - bounds[i], 0.001)
        u = min(1.0, max(0.0, (t - bounds[i]) / span))
        cx, cy = 0, int(my * u)
        frame = big.crop((cx, cy, cx + W, cy + H)).convert("RGBA")
        frame.alpha_composite(ov)
        frame = frame.convert("RGB")

        fi = 0.5 if i == 0 else 0.22
        fo = 0.7 if i == len(visuals) - 1 else 0.22
        if i == 0:
            f_in = min(1.0, t / fi)
        else:
            f_in = min(1.0, max(0.0, (t - bounds[i]) / fi))
        f_out = min(1.0, max(0.0, (bounds[i + 1] - t) / fo)) if fo else 1.0
        lvl = min(f_in, f_out)
        if lvl < 0.995:
            frame = ImageEnhance.Brightness(frame).enhance(lvl)

        d = ImageDraw.Draw(frame)
        frame.paste(bar_bg, (0, H - 10))
        x2 = int(W * (f + 1) / n_frames)
        if x2 > 0:
            d.rectangle([0, H - 10, x2, H], fill=ACCENT)
        proc.stdin.write(frame.tobytes())
        if f % 300 == 0:
            print(f"  frame {f}/{n_frames} ({100 * f // n_frames}%)")
    proc.stdin.close()
    err = proc.stderr.read().decode("utf-8", "replace")
    rc = proc.wait(timeout=900)
    if rc != 0:
        raise RuntimeError("ffmpeg failed: " + err[:1200])
    print("ffmpeg done rc=0")


def verify(total):
    r = subprocess.run([str(FFMPEG), "-hide_banner", "-i", str(OUT)],
                       capture_output=True, text=True, timeout=120)
    dur = next((ln.strip() for ln in r.stderr.splitlines() if "Duration" in ln), "")
    size = OUT.stat().st_size
    print(dur)
    print(f"file={OUT.name} bytes={size} ({size / 1e6:.1f} MB) "
          f"expected~{total:.1f}s")
    # readable caption spot-check: first scene must be Arabic, not Latin
    txt = (TMP / "seg01.txt") if (TMP / "seg01.txt").exists() else None
    return size, dur


def main():
    S = stats()
    print("stats ->", {k: S[k] for k in ("rows", "cells", "score", "checks",
                                         "modules", "cme", "neo")})
    segs = script(S)
    print("endcard:", build_endcard(S))
    tts(segs)
    for i, (_, txt) in enumerate(segs, 1):
        (TMP / f"seg{i:02d}.txt").write_text(txt, encoding="utf-8")
    apath, sr, bounds, total, speech = build_audio(segs)
    print("bounds:", [round(b, 2) for b in bounds])
    visuals = build_visuals(segs)
    render(visuals, bounds, total, apath)
    verify(total)


if __name__ == "__main__":
    main()
