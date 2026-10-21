"""Read saved results and export a small handoff package; never run experiments.

Standard library only. Algorithm success is deliberately not inferred from
process exit codes, lower eta, or a single geometric metric.
"""
import argparse
import csv
import json
import math
import shutil
from pathlib import Path

from run_receipts import contained_path, sha256_file, text_sha256_file, utc_now, write_csv, write_inventory, write_json

METHODS = {"mask_raw", "mask_conservative", "nodes_8", "nodes_27", "nodes_125"}
SCORES = {"gap_occupied_fraction": -1, "solid_recall": 1,
          "near_wall_solid_recall": 1, "gap_path_fraction": 1}


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def read_csv(path):
    if not path.is_file():
        return []
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def dominance(a, b):
    """Descriptive, no significance claim; all four probes have to agree."""
    if any(number(row.get(key)) is None for row in (a, b) for key in SCORES):
        return "unavailable"
    delta = [(float(a[key]) - float(b[key])) * sign for key, sign in SCORES.items()]
    if all(abs(value) <= 1e-9 for value in delta):
        return "equal_on_recorded_probes"
    if all(value >= -1e-9 for value in delta) and any(value > 1e-9 for value in delta):
        return "candidate_dominates_on_recorded_probes"
    if all(value <= 1e-9 for value in delta) and any(value < -1e-9 for value in delta):
        return "baseline_dominates_on_recorded_probes"
    return "tradeoff"


def inventory_audit(run):
    inventory_path = run / "artifact_inventory.json"
    # Old/interrupted runs can lack a root inventory but have per-case receipts.
    manifests = [inventory_path] if inventory_path.is_file() else sorted(run.glob("*/artifact_inventory.json"))
    rows = []
    for manifest in manifests:
        for record in read_json(manifest)["files"]:
            path = contained_path(manifest.parent, record["path"])
            relative = path.relative_to(run).as_posix()
            state = ("missing" if not path.is_file() else
                     "verified" if sha256_file(path) == record["sha256"] else "hash_mismatch")
            if state == "hash_mismatch" and record.get("text_sha256"):
                if text_sha256_file(path) == record["text_sha256"]:
                    state = "text_equivalent"
            rows.append(dict(path=relative, role=record["role"], state=state,
                             expected_sha256=record["sha256"], expected_bytes=record["bytes"]))
    return rows, bool(manifests)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True,
                        help="Fresh small package directory, e.g. research/handoffs/<run-id>")
    parser.add_argument("--figure", action="append", default=[],
                        help="Run-relative PNG to include (repeat, max six); no automatic best-case selection")
    args = parser.parse_args()
    run, out = args.run.resolve(), args.output.resolve()
    if out.is_relative_to(run) or run.is_relative_to(out):
        parser.error("Package and run must be separate directory trees")
    if out.exists():
        parser.error("Choose a new package directory; previous evidence is never overwritten")
    if len(args.figure) > 6:
        parser.error("At most six selected figures; keep full artifacts on the run owner")
    summary = read_json(run / "summary.json")
    if "widths" not in summary or "seeds" not in summary or "cases" not in summary:
        parser.error("Expected a width-study summary, not an older E0/RGB run")
    if summary["status"] == "running":
        parser.error("Do not package an active run. An interrupted stale receipt needs manual inspection first.")
    selected = []
    for relative in args.figure:
        path = contained_path(run, relative)
        if not path.is_file() or path.suffix.lower() != ".png" or path.stat().st_size > 8 * 1024 * 1024:
            parser.error(f"Selected figure must be an existing PNG <=8 MiB: {relative}")
        selected.append(path)
    audit, has_inventory = inventory_audit(run)
    mismatches = [row["path"] for row in audit if row["state"] == "hash_mismatch"]
    missing_receipts = [row["path"] for row in audit
                        if row["state"] == "missing" and row["role"] == "receipt"]
    warnings = []
    if not has_inventory:
        warnings.append("No artifact hashes: historical/local availability is unverified.")
    if mismatches:
        warnings.append("Local files differ from the recorded run; inspect hash_mismatch entries.")
    if missing_receipts:
        warnings.append("Some receipts are missing; this package is incomplete.")
    if not has_inventory or mismatches or missing_receipts:
        integrity = "unverified_or_inconsistent"
    else:
        integrity = "available_receipts_verified"
    cases, comparisons, all_metrics = [], [], []
    for case in summary["cases"]:
        name = case["case"]
        directory = contained_path(run, name)
        metrics = read_csv(directory / "evaluation/metrics.csv")
        names = [row.get("method") for row in metrics]
        valid_scores = all(number(row.get(key)) is not None and 0 <= float(row[key]) <= 1
                           for row in metrics for key in SCORES)
        complete = (case["status"] == "completed" and len(names) == 5
                    and set(names) == METHODS and valid_scores)
        evaluation_path = directory / "evaluation/summary.json"
        quality = read_json(evaluation_path).get("evidence_quality", {}) if evaluation_path.is_file() else {}
        for row in metrics:
            all_metrics.append(dict(case=name, case_status=case["status"], **row))
        row_by_method = {row["method"]: row for row in metrics if row.get("method")}
        for candidate in ("nodes_27", "nodes_125"):
            for baseline in ("nodes_8", "mask_raw", "mask_conservative"):
                relation = (dominance(row_by_method[candidate], row_by_method[baseline])
                            if candidate in row_by_method and baseline in row_by_method else "unavailable")
                comparisons.append(dict(case=name, candidate=candidate, baseline=baseline,
                                        relation=relation, complete_case=complete))
        # Presence is recorded separately from hash integrity and execution status.
        cases.append(dict(case=name, recorded_status=case["status"], interface_complete=complete,
                          failed_stage=case.get("failed_stage"), methods=len(metrics),
                          surface_count=quality.get("surface_count"), free_count=quality.get("free_count"),
                          surface_gt_distance_p95=quality.get("surface_gt_distance_p95"),
                          free_gt_occupied_fraction=quality.get("free_gt_occupied_fraction"),
                          inside_gt_outside_fraction=quality.get("inside_gt_outside_fraction"),
                          gap_with_two_safe_mask_votes_fraction=quality.get("gap_with_two_safe_mask_votes_fraction"),
                          local_fields_present=(directory / "fit/fields.npz").is_file(),
                          local_evidence_present=(directory / "evidence/evidence.npz").is_file(),
                          local_figure_present=(directory / "evaluation/comparison.png").is_file()))
    planned = len(summary["widths"]) * len(summary["seeds"])
    unique_cases = len({case["case"] for case in cases}) == len(cases)
    complete_run = (summary["status"] == "completed" and len(cases) == planned and unique_cases
                    and all(case["interface_complete"] for case in cases))
    if not complete_run:
        warnings.append("Study interface is incomplete; retain every failed and not-started case.")
    if any(case["free_count"] == 0 for case in cases):
        warnings.append("Some cases have zero FREE evidence; they cannot test joint FREE/surface compatibility.")
    source_root = Path(__file__).resolve().parent
    source_check = {}
    for name, digest in summary.get("source_sha256", {}).items():
        path = contained_path(source_root, name)
        source_check[name] = "matches" if path.is_file() and sha256_file(path) == digest else "different_or_missing"
        normalized = summary.get("source_text_sha256", {}).get(name)
        if source_check[name] != "matches" and path.is_file() and normalized == text_sha256_file(path):
            source_check[name] = "text_equivalent"
    if any(state not in ("matches", "text_equivalent") for state in source_check.values()):
        warnings.append("Current source differs from run source; old results are not a test of current code.")

    # Include every small receipt, not just successful cases. Binaries stay local.
    out.mkdir(parents=True)
    copied = []
    for path in sorted(run.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in (".json", ".csv", ".md"):
            continue
        relative = path.relative_to(run)
        contained_path(run, relative)
        destination = out / "receipts" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
        copied.append(dict(source=relative.as_posix(), destination=destination.relative_to(out).as_posix(),
                           sha256=sha256_file(destination)))
    for path in selected:
        relative = path.relative_to(run)
        destination = out / "figures" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
        copied.append(dict(source=relative.as_posix(), destination=destination.relative_to(out).as_posix(),
                           sha256=sha256_file(destination)))
    report = dict(created_utc=utc_now(), run_id=run.name, run_status=summary["status"],
                  source_git_head=summary.get("git_head"), planned_cases=planned, recorded_cases=len(cases),
                  interface_complete=complete_run, integrity=integrity, warnings=warnings,
                  algorithm_feasibility="not_automatically_decided", cases=cases,
                  comparisons=comparisons, source_check=source_check, artifact_audit=audit,
                  package_files=copied, source_run_location=str(run),
                  limitations=["Synthetic development study with GT cameras/masks and fixed ROI",
                               "Finite field probes, not continuous mesh topology",
                               "Mask baselines query full masks; not equal supervision or runtime budget",
                               "No automatic selection, real-object or 12GB GPU validation"])
    write_json(out / "review.json", report)
    write_csv(out / "case_review.csv", cases)
    write_csv(out / "comparison_review.csv", comparisons)
    write_csv(out / "artifact_audit.csv", audit)
    text = [f"# Width study handoff: {run.name}", "",
            f"Recorded run status: `{summary['status']}`. Interface complete: `{complete_run}`.",
            f"Cases: {len(cases)}/{planned}. Receipt integrity: `{integrity}`.", "",
            "**This report reads saved results. It does not rerun experiments or certify algorithm feasibility.**", "",
            "Missing NPZ/RGB/OBJ after Git sync is expected. A verified receipt is not a local resumable run.", "",
            "## Warnings", "", *[f"- {warning}" for warning in warnings], "",
            "## Recorded metrics (all cases)", "",
            "| Case | Status | Method | Gap filled ↓ | Solid retained ↑ | Near-wall retained ↑ | Paths free ↑ |",
            "|---|---|---|---:|---:|---:|---:|"]
    for row in all_metrics:
        scores = [f"{float(row[key]):.6f}" if number(row.get(key)) is not None else "missing" for key in SCORES]
        text.append("| " + " | ".join([row["case"], row["case_status"], row["method"], *scores]) + " |")
    text += ["", "## Local availability at packaging time", "",
             "| Case | Fields NPZ | Evidence NPZ | Comparison image |",
             "|---|---|---|---|"]
    for case in cases:
        text.append(f"| {case['case']} | {case['local_fields_present']} | {case['local_evidence_present']} | {case['local_figure_present']} |")
    text += ["", "## Interpretation", "",
             "`comparison_review.csv` compares all four probes jointly. Equal/tradeoff/dominance is descriptive, not statistical evidence.",
             "If simple Mask carving matches or dominates, opening this hole is not a demonstrated method advantage.",
             "If a finer field improves all probes, that supports this local capacity comparison, not automatic allocation.",
             "Inspect evidence quality and every failure before attributing errors to representation.",
             "The run uses all input views for training, fixed ROI, GT cameras/Mask, and unequal sampling across Mask/LP methods.", "",
             "## Portable contents", "",
             "All JSON/CSV/Markdown receipts are under `receipts/`; chosen figures are under `figures/`.",
             "`review.json` records original relative paths, hashes and local availability at packaging time.",
             "`text_equivalent` permits only UTF-8 BOM/newline conversion by Git; binary artifacts require exact hashes.",
             "After transfer, re-run this reader with `--run <package>/receipts` and a fresh output to audit that machine.",
             "For missing binaries, request exact paths from the run owner or start a new run; do not merge/relabel runs.", ""]
    (out / "REVIEW.md").write_text("\n".join(text), encoding="utf-8")
    write_inventory(out)
    print(f"Saved receipt-only review/package: {out / 'REVIEW.md'}")
    raise SystemExit(0 if complete_run and integrity == "available_receipts_verified" else 2)


if __name__ == "__main__":
    main()
