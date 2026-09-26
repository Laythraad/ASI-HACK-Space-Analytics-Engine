#!/usr/bin/env python3
"""Dump every read-only API endpoint into static/api/*.json.

The dump is what the static demo on GitHub Pages serves when no backend is
reachable: both frontends fall back to these files automatically.

Usage:
    python main.py                       # leave the server running
    python tools/build_static_api.py      # -> static/api/**/*.json

Files written (relative to static/):
    api/health.json        GET /api/health
    api/report.json        GET /api/report
    api/mors.json          GET /api/mors
    api/mors/<name>.json   GET /api/mors/<name>
    api/data/<name>.json   GET /api/data/<name>
    api/_meta.json         manifest of the snapshot
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "static"
BASE = os.getenv("MORS_BASE", "http://127.0.0.1:5000").rstrip("/")

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # pragma: no cover
    pass

DATA_ENDPOINTS = [
    "space-weather", "neo", "horizons", "neo-matrix",
    "light-pollution", "kp-index", "spectral", "quantum",
]
EXTRA_MORS = ["prompts"]


def get(path: str, timeout: int = 300):
    with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def write(rel: str, payload) -> int:
    dest = OUT / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    dest.write_text(text, encoding="utf-8")
    return len(text.encode("utf-8"))


def main() -> int:
    written, failed = [], []
    print(f"snapshot -> {BASE}")

    # 1) health / report / module index
    for rel, path in (("api/health.json", "/api/health"),
                      ("api/report.json", "/api/report"),
                      ("api/mors.json", "/api/mors")):
        try:
            written.append((rel, write(rel, get(path))))
            print(f"  ok   {rel}")
        except Exception as exc:  # noqa: BLE001
            failed.append((path, str(exc)[:120]))
            print(f"  FAIL {path}: {exc}")

    # 2) every MORS module
    names: list[str] = []
    try:
        names = list((get("/api/mors") or {}).get("modules") or [])
    except Exception:  # noqa: BLE001
        pass
    for extra in EXTRA_MORS:
        if extra not in names:
            names.append(extra)
    for name in names:
        rel = f"api/mors/{name}.json"
        try:
            written.append((rel, write(rel, get(f"/api/mors/{name}"))))
            print(f"  ok   {rel}")
        except Exception as exc:  # noqa: BLE001
            failed.append((f"/api/mors/{name}", str(exc)[:120]))
            print(f"  FAIL /api/mors/{name}: {exc}")

    # 3) science data endpoints
    for name in DATA_ENDPOINTS:
        rel = f"api/data/{name}.json"
        try:
            written.append((rel, write(rel, get(f"/api/data/{name}"))))
            print(f"  ok   {rel}")
        except Exception as exc:  # noqa: BLE001
            failed.append((f"/api/data/{name}", str(exc)[:120]))
            print(f"  FAIL /api/data/{name}: {exc}")

    # 4) prune: a module removed from the registry must not linger in the
    #    snapshot, otherwise the static demo keeps serving a dead payload.
    #    ONLY safe when every endpoint answered — a transient fetch failure
    #    must never delete a good snapshot.
    pruned = []
    if not failed:
        keep = {r for r, _ in written} | {"api/_meta.json"}
        for p in sorted((OUT / "api").rglob("*.json")):
            rel = p.relative_to(OUT).as_posix()
            if rel not in keep:
                p.unlink()
                pruned.append(rel)
                print(f"  del  {rel}")
    elif written:
        print("  skip prune (snapshot incomplete — kept existing files)")

    meta = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "base": BASE,
        "files": sorted(r for r, _ in written),
        "failed": failed,
        "pruned": pruned,
        "note": "Read-only JSON snapshot served by the frontends when no "
                "backend is reachable (static hosting). POST endpoints "
                "(/api/chat, /api/mors/insight, /api/pipeline/run) are not "
                "part of the snapshot and stay disabled.",
    }
    write("api/_meta.json", meta)
    total = sum(n for _, n in written)
    print(f"\nWROTE {len(written)} files, {total:,} bytes -> {OUT}"
          + (f" (pruned {len(pruned)} stale)" if pruned else ""))
    if failed:
        print(f"incomplete snapshot: {len(failed)} endpoint(s) failed")
        return 1
    print("SNAPSHOT: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
