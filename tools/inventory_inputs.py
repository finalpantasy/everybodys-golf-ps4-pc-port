import argparse
import hashlib
import json
import subprocess
from pathlib import Path


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def role(name):
    lower = name.lower()
    if ".update." in lower:
        return "update"
    if ".v1.00-" in lower:
        return "base"
    return "dlc"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--orbis", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    orbis = args.orbis or root / "tools/orbis-0.5.0/orbis-cli-0.5.0-x86_64-pc-windows-msvc/orbis.exe"
    output = args.output or root / "analysis/input-inventory.json"
    records = []
    for path in sorted(root.glob("*.pkg")):
        print(f"Inspecting {path.name}", flush=True)
        result = subprocess.run(
            [str(orbis), "info", str(path), "--json"],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        records.append({
            "path": path.name,
            "role": role(path.name),
            "size": path.stat().st_size,
            "sha256": sha256(path),
            "orbis_info": json.loads(result.stdout),
        })
    document = {
        "schema_version": 1,
        "title_id": "CUSA04687",
        "package_count": len(records),
        "dlc_count": sum(record["role"] == "dlc" for record in records),
        "packages": records,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {output} with {len(records)} packages ({document['dlc_count']} DLC)")


if __name__ == "__main__":
    main()
