"""Validate local research artifacts and record static source hashes; no training."""
from pathlib import Path
import datetime, hashlib, json, re

root = Path(__file__).resolve().parents[1]
names = ["2026-10-19_mesh_research_audit.md", "2026-10-19_PROGRESS_HANDOFF.md",
         "2026-10-19_followup_findings.md", "2026-10-19_12gb_validation_plan.md"]
errors = []
for name in names:
    data = (root / name).read_text(encoding="utf-8")
    if "\ufffd" in data:
        errors.append(f"Replacement character in {name}")
    if "\ue200" in data:
        errors.append(f"Internal web citation token in {name}")
    if sum(line.startswith("```") for line in data.splitlines()) % 2:
        errors.append(f"Unbalanced code fence in {name}")
    for target in re.findall(r"\]\((\./[^)]+)\)", data):
        if not (root / target).exists():
            errors.append(f"Missing local link: {name}: {target}")
    print(f"{name}: {len(data.splitlines())} lines, {len(data)} characters")

main = (root / names[0]).read_text(encoding="utf-8")
required = ["Dyn-HOR", "BundleSDF", "In-Hand", "HOLD", "DG-Mesh", "DynaSurfGS",
            "ObjectCarver", "DebSDF", "GPU-SDF", "NeAT", "NeuS2", "Neuralangelo", "MILo"]
assert all(name in main for name in required)
assert 1024**3 * 3 * 4 / 2**30 == 12
assert 512**3 * 16 / 2**30 == 2

sources = []
for path in sorted((root / "evidence" / "code").glob("*")):
    if path.is_file():
        raw = path.read_bytes()
        sources.append({"path": path.relative_to(root).as_posix(), "bytes": len(raw),
                        "sha256": hashlib.sha256(raw).hexdigest()})
for name in ["uapose.pdf", "manifoldneus.pdf"]:
    path = root / "evidence" / name
    raw = path.read_bytes()
    sources.append({"path": path.relative_to(root).as_posix(), "bytes": len(raw),
                    "sha256": hashlib.sha256(raw).hexdigest()})
manifest = {"verified_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "purpose": "Static evidence identity; not a benchmark or upstream commit claim",
            "sources": sources, "document_check_errors": errors}
(root / "evidence" / "static_evidence_hashes.json").write_text(
    json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
print(json.dumps({"sources_hashed": len(sources), "document_check_errors": errors}, ensure_ascii=False))
if errors:
    raise SystemExit(1)
