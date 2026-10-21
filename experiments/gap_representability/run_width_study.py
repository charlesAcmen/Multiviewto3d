"""Frozen CPU width study with stage receipts and portable artifact hashes.

Only the renderer/evaluator read GT. This orchestrator imports no scientific
packages, so even missing dependencies get a readable failure receipt.
"""
import argparse
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

from run_receipts import sha256_file, text_sha256_file, utc_now, write_csv, write_inventory, write_json

SOURCES = ["run_width_study.py", "run_receipts.py", "render_synthetic.py", "rgb_frontend.py",
           "fit_image_evidence.py", "evaluate_local.py", "run_smoke.py", "requirements.lock.txt"]
PACKAGES = ["numpy", "scipy", "opencv-python-headless", "osqp", "scikit-image", "matplotlib", "psutil"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--shape", choices=["fork", "window"], default="window")
    parser.add_argument("--widths", type=float, nargs="+", default=[.24, .12, .06, .03])
    parser.add_argument("--seeds", type=int, nargs="+", default=[20261022])
    args = parser.parse_args()
    if any(not 0 < w < .4 for w in args.widths):
        parser.error("Widths must be between 0 and .4")
    if any(seed < 0 for seed in args.seeds):
        parser.error("Seeds must be nonnegative")
    if len(set(args.widths)) != len(args.widths) or len(set(args.seeds)) != len(args.seeds):
        parser.error("Duplicate widths/seeds would overwrite a case")
    out = args.output.resolve()
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        raise SystemExit("Choose fresh output directory")
    out.mkdir(parents=True, exist_ok=True)
    source = Path(__file__).resolve().parent
    child_env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    try:
        revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=source,
                                  capture_output=True, text=True, check=False).stdout.strip()
    except OSError:
        revision = None
    versions = {}
    for name in PACKAGES:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    receipt = dict(schema_version=2, status="running", git_head=revision,
                   started_utc=utc_now(), host=platform.node(), python=sys.version,
                   platform=platform.platform(), shape=args.shape, widths=args.widths,
                   seeds=args.seeds, image_size=512, view_policy="all_20_training_views",
                   source_sha256={name: sha256_file(source / name) for name in SOURCES},
                   source_text_sha256={name: text_sha256_file(source / name) for name in SOURCES},
                   installed_versions=versions, gpu_used=False, gpu_peak_bytes=None,
                   hypothesis="capacity/coverage failure-range study, not adaptive scheduling",
                   cases=[])

    def save():
        receipt["updated_utc"] = utc_now()
        write_json(out / "summary.json", receipt)
        write_csv(out / "cases.csv", [
            {key: value for key, value in row.items() if key != "stages"} for row in receipt["cases"]])

    save()
    missing = [name for name, version in versions.items() if version is None]
    if missing:
        receipt.update(status="dependency_failure", missing_packages=missing)
        save()
        write_inventory(out)
        raise SystemExit(f"Missing dependencies: {missing}; no experiment started. See {out / 'summary.json'}")
    metrics = []
    active_case = None
    active_row = None
    started = time.perf_counter()
    exit_code = 0
    try:
        for width in args.widths:
            for seed in args.seeds:
                case = out / f"{args.shape}-w{width}-s{seed}"
                case.mkdir()
                active_case = case
                row = dict(case=case.name, width=width, seed=seed, status="running",
                           elapsed_seconds=0., failed_stage=None, active_stage=None, stages=[])
                active_row = row
                receipt["cases"].append(row)
                save()
                start = time.perf_counter()
                stages = [
                    ("render_synthetic.py", ["--output", case / "data", "--shape", args.shape,
                                             "--gap-width", width, "--seed", seed]),
                    ("rgb_frontend.py", ["--data", case / "data", "--output", case / "evidence",
                                         "--evidence-only"]),
                    ("fit_image_evidence.py", ["--evidence", case / "evidence/evidence.npz",
                                               "--output", case / "fit", "--fields-only"]),
                    ("evaluate_local.py", ["--data", case / "data", "--evidence", case / "evidence",
                                           "--fit", case / "fit", "--output", case / "evaluation"]),
                ]
                for script, options in stages:
                    if row["status"] == "failed":
                        if script == "evaluate_local.py" and row["failed_stage"] != "render_synthetic.py":
                            options += ["--mask-only"]
                        else:
                            row["stages"].append(dict(script=script, status="skipped_after_failure"))
                            save()
                            continue
                    changed = [name for name, digest in receipt["source_sha256"].items()
                               if sha256_file(source / name) != digest]
                    if changed:
                        raise RuntimeError(f"Source changed during run: {changed}. Start a new run.")
                    command = [sys.executable, str(source / script), *map(str, options)]
                    stage = dict(script=script, status="running", started_utc=utc_now(), command=command)
                    row["stages"].append(stage)
                    row["active_stage"] = script
                    save()
                    stage_start = time.perf_counter()
                    with (case / "RUN_LOG.md").open("a", encoding="utf-8") as log:
                        log.write(f"\n### {script}\n\n```json\n{json.dumps(command)}\n```\n")
                        log.flush()
                        result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT,
                                                env=child_env, check=False)
                        log.write(f"\nExit code: {result.returncode}\n")
                    missing_evidence = (script == "rgb_frontend.py"
                                        and not (case / "evidence/evidence.npz").is_file())
                    failed = result.returncode != 0 or missing_evidence
                    stage.update(status="failed" if failed else "completed", exit_code=result.returncode,
                                 missing_evidence=missing_evidence,
                                 elapsed_seconds=time.perf_counter() - stage_start, ended_utc=utc_now())
                    print(f"{case.name}: {script} exit={result.returncode}", flush=True)
                    if failed:
                        row.update(status="failed", failed_stage=row["failed_stage"] or script)
                    row["active_stage"] = None
                    row["elapsed_seconds"] = time.perf_counter() - start
                    save()
                    write_inventory(case)
                    changed = [name for name, digest in receipt["source_sha256"].items()
                               if sha256_file(source / name) != digest]
                    if changed:
                        raise RuntimeError(f"Source changed during stage: {changed}. Preserve this run; do not reuse it.")
                if (case / "evaluation/summary.json").exists():
                    evaluation = json.loads((case / "evaluation/summary.json").read_text(encoding="utf-8"))
                    if row["status"] != "failed":
                        row["status"] = evaluation["fit_status"]
                    for metric in evaluation["metrics"]:
                        metrics.append(dict(case=case.name, shape=args.shape, width=width, seed=seed,
                                            nominal_front_mouth_pixels=evaluation["nominal_front_mouth_pixels"],
                                            **metric))
                    write_csv(out / "metrics.csv", metrics)
                elif row["status"] != "failed":
                    row.update(status="failed", failed_stage="missing_evaluation_summary")
                row["elapsed_seconds"] = time.perf_counter() - start
                save()
        receipt["status"] = ("completed" if all(c["status"] == "completed" for c in receipt["cases"])
                             else "completed_with_failures")
        exit_code = 0 if receipt["status"] == "completed" else 2
    except (KeyboardInterrupt, Exception) as error:
        interrupted = isinstance(error, KeyboardInterrupt)
        receipt.update(status="interrupted" if interrupted else "orchestration_failure",
                       error=f"{type(error).__name__}: {error}")
        if active_row is not None:
            active_row.update(status=receipt["status"], failed_stage=active_row["active_stage"] or "orchestrator")
            if active_row["stages"] and active_row["stages"][-1]["status"] == "running":
                active_row["stages"][-1].update(status=receipt["status"], error=receipt["error"])
        exit_code = 130 if interrupted else 2
        print(receipt["error"], file=sys.stderr)
    finally:
        receipt.update(ended_utc=utc_now(), elapsed_seconds=time.perf_counter() - started)
        save()
        if active_case is not None:
            write_inventory(active_case)
        write_inventory(out)
    print(f"{receipt['status']}: {out / 'summary.json'}", flush=True)
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
