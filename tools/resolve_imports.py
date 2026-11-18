import json
import re
from collections import defaultdict
from pathlib import Path


def main():
    root = Path(__file__).resolve().parent.parent
    link = json.loads((root / "work/game-1.17-prepared/link.json").read_text(encoding="utf-8"))
    mapping = defaultdict(set)
    nid_mapping = defaultdict(set)
    resogun_names = root / "external/resogun-recomp/src/import_names.inc"
    for nid, name in re.findall(r'\{"([^"]+)","([^"]+)"\}', resogun_names.read_text(encoding="utf-8")):
        mapping[nid].add(name)
        nid_mapping[nid.split("#", 1)[0]].add(name)
    lib_function = re.compile(
        r'LIB_FUNCTION\(\s*"([^"]+)"\s*,\s*"([^"]+)"\s*,\s*[^,]+,\s*"[^"]+"\s*,\s*([^\)]+)\)'
    )
    for path in (root / "external/driveclub-recomp/gpu/shadps4/core/libraries").rglob("*.cpp"):
        text = path.read_text(encoding="utf-8", errors="replace")
        for nid, library, name in lib_function.findall(text):
            key = f"{nid}#{library}"
            name = name.strip()
            mapping[key].add(name)
            nid_mapping[nid].add(name)
    records = []
    for name in link["unresolved_imports"]:
        candidates = sorted(mapping.get(name, set()))
        nid_candidates = sorted(nid_mapping.get(name.split("#", 1)[0], set()))
        status = "resolved" if len(candidates) == 1 else "ambiguous" if candidates or len(nid_candidates) > 1 else "unresolved"
        records.append({
            "import": name,
            "status": status,
            "candidates": candidates or nid_candidates,
        })
    document = {
        "schema_version": 1,
        "source": "work/game-1.17-prepared/link.json",
        "counts": {
            "total": len(records),
            "resolved": sum(r["status"] == "resolved" for r in records),
            "ambiguous": sum(r["status"] == "ambiguous" for r in records),
            "unresolved": sum(r["status"] == "unresolved" for r in records),
        },
        "imports": records,
    }
    output = root / "analysis/import-names.json"
    output.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(document["counts"])
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
