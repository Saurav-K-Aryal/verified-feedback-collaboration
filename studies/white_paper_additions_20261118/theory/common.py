"""Local protocol freezing and provenance for this CPU-only study."""
from __future__ import annotations
import argparse
import hashlib
import importlib.metadata
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def write_json(path, obj):
    Path(path).write_text(json.dumps(obj, indent=2, allow_nan=False) + "\n")

def now():
    return datetime.now(timezone.utc).isoformat()

def setup(script, template):
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--protocol", type=Path, default=HERE / template)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--execute-frozen", action="store_true")
    args = parser.parse_args()
    if args.prepare_only and args.execute_frozen:
        parser.error("Choose preparation or execution, not both")
    out = args.out.resolve()
    files = [Path(script).resolve(), HERE / "common.py"]
    if args.execute_frozen:
        cfg = json.loads((out / "PROTOCOL.json").read_text())
        manifest = json.loads((out / "FREEZE.json").read_text())
        if digest(out / "PROTOCOL.json") != manifest["protocol_sha256"]:
            raise SystemExit("Frozen protocol changed")
        for path in files:
            if digest(path) != manifest["source_sha256"][path.name]:
                raise SystemExit("Source changed after protocol freeze")
    else:
        cfg = json.loads(args.protocol.read_text())
        if out.exists() and any(out.iterdir()):
            raise SystemExit("Use an empty output directory; no overwrite is permitted")
        out.mkdir(parents=True, exist_ok=True)
        cfg["frozen_utc"] = now()
        write_json(out / "PROTOCOL.json", cfg)
        source = out / "frozen_source"
        source.mkdir()
        for path in files:
            (source / path.name).write_bytes(path.read_bytes())
        write_json(out / "FREEZE.json", {
            "protocol_sha256": digest(out / "PROTOCOL.json"),
            "source_sha256": {p.name: digest(p) for p in files},
            "freeze_is_local_not_external_preregistration": True,
        })
    if args.prepare_only:
        print(f"Prepared {out}; no experiment executed")
        return None, out
    # Public reruns are explicitly requested by invoking this command.
    if (out / "RUN_STARTED.json").exists():
        raise SystemExit("This output has already started; choose a new frozen run")
    packages = {}
    for package in ["numpy", "scipy"]:
        try:
            packages[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            packages[package] = "not installed"
    hardware = {}
    if sys.platform == "darwin":
        for key in ["hw.model", "hw.memsize", "machdep.cpu.brand_string"]:
            result = subprocess.run(["sysctl", "-n", key], capture_output=True, text=True)
            hardware[key] = result.stdout.strip() or result.stderr.strip()
    write_json(out / "RUN_STARTED.json", {
        "started_utc": now(), "python": sys.version, "executable": sys.executable,
        "platform": platform.platform(), "hardware": hardware, "packages": packages,
        "argv": sys.argv, "protocol_sha256": digest(out / "PROTOCOL.json"),
        "execution_context": "portable public rerun; internal coordination guard removed",
        "models": "none; CPU mathematical study", "model_requests": 0,
    })
    return cfg, out

def report(out, title, prose, table, limits, record):
    protocol = (out / "PROTOCOL.json").read_text().strip()
    text = (f"# {title}\n\n## Paste ready text\n\n{prose}\n\n"
            f"## Table\n\n{table}\n\n## Limits and what was not established\n\n{limits}\n\n"
            f"## Run record\n\n```json\n{json.dumps(record, indent=2)}\n```\n\n"
            f"## Frozen protocol\n\n```json\n{protocol}\n```\n")
    (out / "RESULT.md").write_text(text)
