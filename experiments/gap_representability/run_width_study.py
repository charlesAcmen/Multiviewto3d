"""Replay a frozen RGB/mask pipeline on a new shape/width sweep, on CPU.

Each stage is a separate process. Only the renderer/evaluator receive shape
metadata; the frontend and fitter never receive GT boxes. Do not overwrite runs.
"""
import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

from run_smoke import csv_write


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--shape", choices=["fork", "window"], default="window")
    parser.add_argument("--widths", type=float, nargs="+", default=[.24, .12, .06, .03])
    parser.add_argument("--seeds", type=int, nargs="+", default=[20261022])
    args = parser.parse_args()
    if any(not 0 < w < .4 for w in args.widths):
        parser.error("Widths must be between 0 and .4")
    if len(set(args.widths)) != len(args.widths) or len(set(args.seeds)) != len(args.seeds):
        parser.error("Duplicate widths/seeds would overwrite a case")
    out = args.output.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit("Choose fresh output directory")
    out.mkdir(parents=True)
    source = Path(__file__).resolve().parent
    child_env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=source,
                              capture_output=True, text=True, check=False).stdout.strip()
    sources = ["run_width_study.py", "render_synthetic.py", "rgb_frontend.py",
               "fit_image_evidence.py", "evaluate_local.py", "run_smoke.py", "requirements.lock.txt"]
    receipt = dict(status="running", git_head=revision, python=sys.version,
                   platform=platform.platform(), shape=args.shape, widths=args.widths,
                   seeds=args.seeds, image_size=512, view_policy="all_20_training_views",
                   source_sha256={name: hashlib.sha256((source / name).read_bytes()).hexdigest()
                                  for name in sources},
                   installed_versions={name: importlib.metadata.version(name) for name in
                                       ["numpy", "scipy", "opencv-python-headless", "osqp",
                                        "scikit-image", "matplotlib"]},
                   gpu_used=False, gpu_peak_bytes=None,
                   hypothesis="capacity/coverage failure-range study, not adaptive scheduling",
                   cases=[])
    def save():
        (out / "summary.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    save()
    metrics = []
    for width in args.widths:
        for seed in args.seeds:
            case = out / f"{args.shape}-w{width}-s{seed}"
            case.mkdir()
            row = dict(case=case.name, width=width, seed=seed, status="running",
                       elapsed_seconds=0., failed_stage=None)
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
                        continue
                command = [sys.executable, str(source / script), *map(str, options)]
                with (case / "RUN_LOG.md").open("a", encoding="utf-8") as log:
                    log.write(f"\n### {script}\n\n```json\n{json.dumps(command)}\n```\n")
                    log.flush()
                    result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT,
                                            env=child_env, check=False)
                print(f"{case.name}: {script} exit={result.returncode}", flush=True)
                missing_evidence = script == "rgb_frontend.py" and not (case / "evidence/evidence.npz").exists()
                if result.returncode != 0 or missing_evidence:
                    row.update(status="failed", failed_stage=row["failed_stage"] or script)
            if (case / "evaluation/summary.json").exists():
                evaluation = json.loads((case / "evaluation/summary.json").read_text())
                if row["status"] != "failed":
                    row["status"] = evaluation["fit_status"]
                for metric in evaluation["metrics"]:
                    metrics.append(dict(case=case.name, shape=args.shape, width=width, seed=seed,
                                        nominal_front_mouth_pixels=evaluation["nominal_front_mouth_pixels"],
                                        **metric))
                csv_write(out / "metrics.csv", metrics)
            row["elapsed_seconds"] = time.perf_counter() - start
            csv_write(out / "cases.csv", receipt["cases"])
            save()
    receipt["status"] = ("completed" if all(c["status"] == "completed" for c in receipt["cases"])
                         else "completed_with_failures")
    save()
    print(f"{receipt['status']}: {out / 'summary.json'}", flush=True)
    if receipt["status"] != "completed":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
