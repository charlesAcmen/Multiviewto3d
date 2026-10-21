"""Standard-library receipts; never import or execute the reconstruction stack."""
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def text_sha256_file(path):
    """Allow Git's BOM/newline conversion, but preserve all textual content."""
    text = Path(path).read_text(encoding="utf-8-sig")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_json(path, value):
    """Replace only this generated receipt atomically, not an earlier run."""
    path = Path(path)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False),
                         encoding="utf-8")
    temporary.replace(path)


def write_csv(path, rows):
    if not rows:
        return
    path = Path(path)
    temporary = path.with_name(path.name + ".tmp")
    columns = list(dict.fromkeys(key for row in rows for key in row))
    with temporary.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def contained_path(root, relative):
    root = Path(root).resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"Path escapes run directory: {relative}")
    return path


def artifact_role(relative):
    path = Path(relative)
    if path.suffix.lower() in (".json", ".csv", ".md"):
        return "receipt"
    if "data" in path.parts:
        return "input"
    if path.suffix.lower() in (".png", ".jpg", ".svg"):
        return "figure"
    if path.suffix.lower() in (".obj", ".ply"):
        return "mesh"
    return "intermediate"


def write_inventory(root):
    """Hash local artifacts; the receipt is not evidence of algorithm quality."""
    root = Path(root).resolve()
    files = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name == "artifact_inventory.json" or path.suffix == ".tmp":
            continue
        relative = path.relative_to(root).as_posix()
        contained_path(root, relative)
        record = dict(path=relative, bytes=path.stat().st_size,
                      sha256=sha256_file(path), role=artifact_role(relative))
        if path.suffix.lower() in (".json", ".csv", ".md", ".txt", ".py"):
            record["text_sha256"] = text_sha256_file(path)
        files.append(record)
    inventory = dict(schema_version=1, created_utc=utc_now(), files=files,
                     note="Missing binaries after Git sync are expected; verify before resuming.")
    write_json(root / "artifact_inventory.json", inventory)
    return inventory
