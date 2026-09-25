"""Build the submission zip and 00_MANIFEST.txt (size + SHA-256 per file).

Usage:
    python main.py                 # leave a server running (docs must be fresh)
    python tools/build_zip.py      # -> ASI-HACK-Space-Analytics-Engine.zip
"""
from __future__ import annotations

import hashlib
import io
import os
import sys
import zipfile
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "ASI-HACK-Space-Analytics-Engine.zip")
MANIFEST = os.path.join(ROOT, "00_MANIFEST.txt")

INCLUDE = [
    "00_COMMITTEE_GUIDE.md",
    "00_MANIFEST.txt",
    "main.py",
    "START.bat",
    "README.md",
    "المشكلات_التي_تم_حلها.md",
    "DEPLOYMENT.md",
    "requirements.txt",
    ".env",
    ".gitignore",
    "last_report.json",
    "agents/__init__.py",
    "agents/agent1_ingestion.py",
    "agents/agent2_council.py",
    "agents/agent3_citations.py",
    "agents/agent4_aimors.py",
    "agents/datasets.py",
    "agents/mors_data.py",
    "agents/sources_data.py",
    "prompts/aimors_prompt.txt",
    "prompts/council_prompt.txt",
    "prompts/aimors_analyst_prompt.txt",
    "prompts/uiux_command_center_prompt.txt",
    "prompts/uiux_visualization_prompt.txt",
    "prompts/cyber_mors_prompt.txt",
    "prompts/report_generator_prompt.txt",
    "prompts/deep_audit_prompt.txt",
    "static/index.html",
    "static/mors.html",
    "tools/audit_data.py",
    "tools/build_report.py",
    "tools/build_guide.py",
    "tools/build_committee.py",
    "tools/build_zip.py",
    "docs/API_CONTRACT.md",
    "docs/MORS_REPORT.pdf",
    "docs/PROJECT_GUIDE.pdf",
    "docs/COMMITTEE_GUIDE.pdf",
    "data/reference_metrics.csv",
    "data/light_pollution_reference.csv",
    "data/spectral_reference.csv",
]

# roles come from the curated registry that also drives docs/PROJECT_GUIDE.pdf
sys.path.insert(0, os.path.join(ROOT, "tools"))
try:
    import build_guide as bg
    ROLES = {k: v.get("role", "") for k, v in bg.FILES.items()}
except Exception:  # pragma: no cover - registry is optional for packing
    ROLES = {}

PACKED = [f for f in INCLUDE if f != "00_MANIFEST.txt"]
missing = [f for f in INCLUDE
           if f != "00_MANIFEST.txt"
           and not os.path.isfile(os.path.join(ROOT, f))]
if missing:
    print("MISSING:", missing)
    raise SystemExit(1)


def digest(path: str) -> str:
    h = hashlib.sha256()
    with io.open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


rows = []
for rel in PACKED:
    p = os.path.join(ROOT, rel)
    rows.append((digest(p), os.path.getsize(p), rel, ROLES.get(rel, "")))

stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
lines = [
    "ASI-HACK Space Analytics Engine - package manifest",
    "MORS Scientific Command Center",
    "",
    f"generated : {stamp}",
    f"files     : {len(rows)}",
    f"raw bytes : {sum(r[1] for r in rows)}",
    "",
    "Verify with:  Get-FileHash -Algorithm SHA256 <file>",
    "Columns: SHA-256 | bytes | path | role",
    "-" * 100,
]
for sha, size, rel, role in rows:
    lines.append(f"{sha}  {size:>9}  {rel:<42}  {role}")
lines.append("-" * 100)
lines.append(f"This manifest itself: {os.path.basename(MANIFEST)} "
             "(its own digest is the one you compute after extracting).")
lines.append("")
io.open(MANIFEST, "w", encoding="utf-8", newline="\r\n").write("\n".join(lines))

if os.path.exists(OUT):
    os.remove(OUT)

total = 0
with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
    for rel in INCLUDE:
        p = os.path.join(ROOT, rel)
        info = zipfile.ZipInfo(rel.replace("\\", "/"),
                               date_time=(2026, 9, 25, 2, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o644 << 16
        data = io.open(p, "rb").read()
        z.writestr(info, data)
        total += len(data)
        print("%8d  %s" % (len(data), rel))

print("entries=%d  raw=%d  zip=%d" % (len(INCLUDE), total,
                                      os.path.getsize(OUT)))
