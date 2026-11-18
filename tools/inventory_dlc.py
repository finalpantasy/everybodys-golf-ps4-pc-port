import json
import subprocess
from pathlib import Path


def main():
    root = Path(__file__).resolve().parent.parent
    orbis = root / "tools/orbis-0.5.0/orbis-cli-0.5.0-x86_64-pc-windows-msvc/orbis.exe"
    inventory = json.loads((root / "analysis/input-inventory.json").read_text(encoding="utf-8"))
    records = []
    for package in inventory["packages"]:
        if package["role"] != "dlc":
            continue
        path = root / package["path"]
        result = subprocess.run(
            [str(orbis), "list", str(path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        lines = result.stdout.splitlines()
        filesystem_files = [line for line in lines if line.startswith("filesystem file")]
        filesystem_dirs = [line for line in lines if line.startswith("filesystem directory")]
        records.append({
            "path": package["path"],
            "content_id": package["orbis_info"]["application"].get("content_id"),
            "title": package["orbis_info"]["application"].get("title"),
            "filesystem_available": "filesystem unavailable:" not in result.stdout,
            "filesystem_file_count": len(filesystem_files),
            "filesystem_directory_count": len(filesystem_dirs),
            "filesystem_files": filesystem_files,
            "exit_code": result.returncode,
            "diagnostics": result.stdout.split("warning: ")[1:],
        })
    document = {
        "schema_version": 1,
        "dlc_count": len(records),
        "packages_with_filesystem_files": sum(r["filesystem_file_count"] > 0 for r in records),
        "packages": records,
    }
    output = root / "analysis/dlc-content-inventory.json"
    output.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"DLC packages: {len(records)}")
    print(f"Packages containing filesystem files: {document['packages_with_filesystem_files']}")
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
