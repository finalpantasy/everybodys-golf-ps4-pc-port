import argparse
import json
import os
from pathlib import Path


def files_under(root):
    return {
        str(path.relative_to(root)).replace("\\", "/"): path
        for path in root.rglob("*")
        if path.is_file()
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--update", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    base = args.base.resolve()
    update = args.update.resolve()
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        raise SystemExit(f"refusing non-empty output directory: {output}")
    base_files = files_under(base)
    update_files = files_under(update)
    records = []
    for relative in sorted(base_files.keys() | update_files.keys()):
        base_file = base_files.get(relative)
        update_file = update_files.get(relative)
        selected = update_file or base_file
        reason = "update" if update_file else "base-only"
        if update_file and base_file and update_file.stat().st_size == 0 and base_file.stat().st_size != 0:
            selected = base_file
            reason = "base-nonempty-fallback"
        target = output.joinpath(*relative.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        os.link(selected, target)
        records.append({
            "path": relative,
            "source": reason,
            "size": selected.stat().st_size,
        })
    manifest = {
        "schema_version": 1,
        "base": str(base),
        "update": str(update),
        "file_count": len(records),
        "base_nonempty_fallbacks": [r["path"] for r in records if r["source"] == "base-nonempty-fallback"],
        "files": records,
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "stage-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Linked {len(records)} files into {output}")
    print(f"Base non-empty fallbacks: {manifest['base_nonempty_fallbacks']}")


if __name__ == "__main__":
    main()
