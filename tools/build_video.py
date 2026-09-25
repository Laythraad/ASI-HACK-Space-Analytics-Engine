# Build the 2-minute English pitch video: TTS (System.Speech) + PIL frames + ffmpeg.
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageEnhance

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(r"C:\Users\sha\Desktop\📁 المشاريع (Projects)\New folder (6)")
FRAMES = ROOT / "presentation" / "frames"
OUT = ROOT / "presentation" / "MORS_Pitch_2min.mp4"
ENDCARD = FRAMES / "11_endcard.png"
TMP = Path(r"C:\Users\sha\AppData\Local\Temp\opencode\mors_video")
FFMPEG = Path(r"C:\Users\sha\AppData\Roaming\Python\Python312\site-packages\imageio_ffmpeg\binaries\ffmpeg-win-x86_64-v7.1.exe")

W, H, FPS = 1920, 1080, 30
URL = "laythraad.github.io/ASI-HACK-Space-Analytics-Engine"
VOICE = "Microsoft David Desktop"
RATE = 0

BG = (3, 7, 18)
PANEL = (15, 23, 42)
ACCENT = (56, 189, 248)
GREEN = (52, 211, 153)
WARN = (251, 191, 36)
TEXT = (226, 232, 240)
MUTED = (148, 163, 184)

F_TOP = ImageFont.truetype(r"C:\Windows\Fonts\segoeuib.ttf", 27)
F_URL = ImageFont.truetype(r"C:\Windows\Fonts\consola.ttf", 22)
F_CAP = ImageFont.truetype(r"C:\Windows\Fonts\segoeui.ttf", 33)
F_IDX = ImageFont.truetype(r"C:\Windows\Fonts\consolab.ttf", 27)
F_END_H = ImageFont.truetype(r"C:\Windows\Fonts\segoeuib.ttf", 96)
F_END_S = ImageFont.truetype(r"C:\Windows\Fonts\segoeui.ttf", 38)
F_END_C = ImageFont.truetype(r"C:\Windows\Fonts\segoeui.ttf", 30)
F_END_U = ImageFont.truetype(r"C:\Windows\Fonts\consola.ttf", 30)
F_END_M = ImageFont.truetype(r"C:\Windows\Fonts\consola.ttf", 24)

SEGS = [
    ("01_launcher.png",
     "MORS is a scientific space analytics engine. It audits space telemetry, "
     "detects anomalies, and verifies every claim before anyone trusts it."),
    ("10_dashboard.png",
     "It starts with truth. One thousand seven hundred eleven rows, eight "
     "thousand eight hundred forty cells, ninety-nine point eight percent "
     "complete, zero duplicates, certified by two hundred twenty-five automated "
     "checks with zero failures."),
    ("04_satellite.png",
     "Fifty satellites are tracked from low orbit to geostationary, with the "
     "physics printed on screen: altitude, velocity, inclination, and the "
     "spectral bands behind every index."),
    ("07_astronomy.png",
     "Astronomy runs on real signal: a light curve with a signal-to-noise ratio "
     "of twelve point five, one hundred twenty-five coronal mass ejections, "
     "seventeen solar flares, and thirty-two near-earth objects."),
    ("05_problems.png",
     "Every anomaly becomes a problem card with ten keys: symptom, root cause, "
     "evidence and fix. A claim without evidence is only an opinion."),
    ("06_solutions.png",
     "Priority is arithmetic, not opinion. Point four zero times evidence, "
     "plus point three five times impact, plus point two five times confidence, "
     "printed on the card itself."),
    ("08_ai.png",
     "Every AI answer carries five labelled tiers, from observed data to "
     "suggested action. When the model is unavailable we say so: local "
     "fallback, labelled, never disguised."),
    ("03_theme_mars.png",
     "Eighteen modules live in one dark glass interface: six planet themes, an "
     "accordion sidebar, and instant switching, built for judges to explore "
     "quickly."),
    ("09_team.png",
     "Four roles own the system end to end: data analysis, astronomy research, "
     "space systems, and pipeline architecture, led by Layth Ra'ad."),
    ("11_endcard.png",
     "Two hundred twenty-five checks, zero failures, one hundred percent "
     "traceability, and eight of eight challenge conditions met. Scan the code "
     "and verify it yourself. Thank you."),
]


# --------------------------------------------------------------------------- endcard
def build_endcard():
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    for i in range(H):
        a = int(18 * (1 - i / H))
        d.line([(0, i), (W, i)], fill=(a, a + 4, a + 12))

    d.text((140, 250), "MORS", font=F_END_H, fill=ACCENT)
    d.text((140, 370), "Scientific Space Analytics Engine", font=F_END_S, fill=TEXT)
    d.text((140, 430), "Audit · Detect · Verify — before you trust a model",
           font=F_END_C, fill=MUTED)

    chips = [("CERTIFIED 96/100", GREEN), ("225 checks · 0 failures", ACCENT),
             ("8/8 conditions", WARN)]
    x = 140
    for label, col in chips:
        w = int(d.textlength(label, font=F_END_U)) + 56
        d.rounded_rectangle([x, 530, x + w, 596], radius=10, outline=col, width=2)
        d.text((x + 28, 547), label, font=F_END_U, fill=col)
        x += w + 26

    d.text((140, 680), URL, font=F_END_U, fill=TEXT)
    d.text((140, 730), "open the site · explore the modules · re-run the audit",
           font=F_END_M, fill=MUTED)

    qr = Image.open(ROOT / "presentation" / "qr_live.png").convert("RGB")
    qr = qr.resize((340, 340), Image.NEAREST)
    d.rounded_rectangle([1400, 440, 1800, 880], radius=16, fill=PANEL, outline=ACCENT, width=2)
    im.paste(qr, (1450, 475))
    d.text((1466, 838), "SCAN → LIVE SITE", font=F_END_M, fill=ACCENT)

    d.rectangle([0, 1070, W, H], fill=PANEL)
    im.save(ENDCARD)
    return im.size


# --------------------------------------------------------------------------- tts
def tts():
    TMP.mkdir(parents=True, exist_ok=True)
    for i, (_, txt) in enumerate(SEGS, 1):
        (TMP / f"seg{i:02d}.txt").write_text(txt, encoding="utf-8")
    parts = ["Add-Type -AssemblyName System.Speech"]
    for i in range(1, len(SEGS) + 1):
        wav = str(TMP / f"seg{i:02d}.wav").replace("/", "\\")
        txt = str(TMP / f"seg{i:02d}.txt").replace("/", "\\")
        parts.append(
            "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer;"
            f"$s.SelectVoice('{VOICE}');$s.Rate={RATE};"
            f"$s.SetOutputToWaveFile('{wav}');"
            f"$t=[IO.File]::ReadAllText('{txt}');$s.Speak($t);$s.Dispose()"
        )
    r = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", ";".join(parts)],
        capture_output=True, text=True, timeout=900,
    )
    if r.returncode != 0:
        raise RuntimeError("tts failed: " + (r.stderr or "")[:800])
    print("tts: ok")


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


def trim(a, sr, pad=0.06):
    idx = np.nonzero(np.abs(a) > 0.012)[0]
    if len(idx) == 0:
        return a
    p = int(pad * sr)
    return a[max(0, idx[0] - p): min(len(a), idx[-1] + p)]


# --------------------------------------------------------------------------- timeline
def build_audio():
    clips = []
    for i in range(1, len(SEGS) + 1):
        a, sr = read_wav(TMP / f"seg{i:02d}.wav")
        clips.append((a, sr))
    target = max(sr for _, sr in clips)
    clips = [resample(a, sr, target) for a, sr in clips]
    clips = [trim(a, target) for a in clips]
    peak = max(float(np.max(np.abs(a))) for a in clips)
    if peak > 0:
        clips = [a * (0.95 / peak) for a in clips]

    speech = sum(len(a) for a in clips) / target
    gap = min(1.2, max(0.2, (117.0 - 1.5 - speech) / (len(clips) - 1)))
    lead, tail = 0.5, 1.2

    buf = [np.zeros(int(lead * target), dtype=np.float32)]
    windows, t = [], lead
    for i, a in enumerate(clips):
        windows.append((t, t + len(a) / target))
        buf.append(a)
        t += len(a) / target
        if i < len(clips) - 1:
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
        bounds.append(max(bounds[-1] + 1.0, windows[i][0]))
    bounds.append(total)
    return apath, target, bounds, total, speech


# --------------------------------------------------------------------------- render
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


def make_overlay(idx, caption):
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    d.rectangle([0, 0, W, 62], fill=(3, 7, 18, 232))
    d.text((46, 16), "MORS · SCIENTIFIC SPACE ANALYTICS ENGINE", font=F_TOP, fill=ACCENT + (255,))
    rt = f"ASI-HACK 2026 · {URL}"
    d.text((W - 46 - d.textlength(rt, font=F_URL), 21), rt, font=F_URL, fill=MUTED + (255,))

    lines = wrap(d, caption, F_CAP, 1600)
    lh = 46
    bar_h = 34 + lh * len(lines) + 30
    y0 = H - 14 - bar_h
    d.rounded_rectangle([46, y0, W - 46, H - 14], radius=16, fill=(3, 7, 18, 224),
                        outline=(56, 189, 248, 140), width=2)
    tag = f"{idx:02d}/10"
    d.text((86, y0 + 16), tag, font=F_IDX, fill=ACCENT + (255,))
    ty = y0 + (bar_h - lh * len(lines)) // 2 - 4
    for ln in lines:
        d.text((210, ty), ln, font=F_CAP, fill=TEXT + (255,))
        ty += lh
    return ov


def build_visuals():
    visuals = []
    for i, (name, _) in enumerate(SEGS, 1):
        p = FRAMES / name
        if not p.exists() and name == "11_endcard.png":
            build_endcard()
        im = Image.open(p).convert("RGB")
        if im.size != (W, H):
            im = im.resize((W, H), Image.LANCZOS)
        zoom = 1.045
        big = im.resize((int(W * zoom), int(H * zoom)), Image.LANCZOS)
        ov = make_overlay(i, SEGS[i - 1][1])
        visuals.append((big, ov, big.size[0] - W, big.size[1] - H))
    return visuals


def render(visuals, bounds, total, apath):
    cmd = [
        str(FFMPEG), "-y", "-hide_banner", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
        "-i", "pipe:0", "-i", str(apath),
        "-c:v", "libx264", "-preset", "slow", "-crf", "18",
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
        i = max(0, min(len(SEGS) - 1, next(
            (k for k in range(len(SEGS)) if bounds[k] <= t < bounds[k + 1]),
            len(SEGS) - 1)))
        big, ov, _mx, my = visuals[i]
        span = max(bounds[i + 1] - bounds[i], 0.001)
        u = min(1.0, max(0.0, (t - bounds[i]) / span))
        cx, cy = 0, int(my * u)
        frame = big.crop((cx, cy, cx + W, cy + H)).convert("RGBA")
        frame.alpha_composite(ov)
        frame = frame.convert("RGB")

        fi = 0.5 if i == 0 else 0.25
        fo = 0.7 if i == len(SEGS) - 1 else 0.25
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
    rc = proc.wait(timeout=600)
    if rc != 0:
        raise RuntimeError("ffmpeg failed: " + err[:1200])
    print("ffmpeg done rc=0")


def verify(total):
    r = subprocess.run([str(FFMPEG), "-hide_banner", "-i", str(OUT)],
                       capture_output=True, text=True, timeout=120)
    info = r.stderr
    dur = ""
    for ln in info.splitlines():
        if "Duration" in ln:
            dur = ln.strip()
            break
    size = OUT.stat().st_size
    print(dur)
    print(f"file={OUT.name} bytes={size} ({size / 1e6:.1f} MB) expected~{total:.1f}s")
    return size, dur


def main():
    print("endcard:", build_endcard())
    tts()
    apath, sr, bounds, total, speech = build_audio()
    print("bounds:", [round(b, 2) for b in bounds])
    visuals = build_visuals()
    render(visuals, bounds, total, apath)
    verify(total)


if __name__ == "__main__":
    main()
