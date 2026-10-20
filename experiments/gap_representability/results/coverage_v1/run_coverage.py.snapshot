"""Coverage ablation after smoke_v2's visibly distorted notch.

Full-support data are EXTRA ORACLE evidence and are shared by the coarse/fine
pair. They are not test observations and do not establish real-view success.
"""
import argparse
import hashlib
import json
import shutil
import time
from pathlib import Path

import numpy as np
import psutil
from skimage.measure import marching_cubes
from run_smoke import (evidence, solve, stabilize, evaluate, grid_points,
                       object_field, write_obj, csv_write, constraints)


def full_support():
    e = evidence("gap", 42, center=0.5, width=0.24)
    yz = np.stack(np.meshgrid(np.linspace(0, 1, 5), np.linspace(0, 1, 5), indexing="ij"), -1).reshape(-1, 2)
    p = lambda x: np.column_stack([np.full(len(yz), x), yz])
    e["surface"] = np.concatenate([p(0.38), p(0.62)])
    e["normals"] = np.concatenate([np.tile([1, 0, 0], (len(yz), 1)), np.tile([-1, 0, 0], (len(yz), 1))])
    e["free"] = p(0.5)
    e["inside"] = np.concatenate([p(0.28), p(0.72)])
    return e


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path(__file__).parent / "results" / "coverage_v1")
    args = parser.parse_args()
    out = args.output.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit("Choose a fresh output directory")
    out.mkdir(parents=True, exist_ok=True)
    start = time.perf_counter()
    log = out / "RUN_LOG.md"
    log.write_text("# Coverage ablation (Oracle only)\n\n", encoding="utf-8")
    sources = {}
    for name in ("run_smoke.py", "run_coverage.py"):
        src = Path(__file__).with_name(name)
        shutil.copyfile(src, out / (name + ".snapshot"))
        sources[name] = hashlib.sha256(src.read_bytes()).hexdigest()
    sparse_e = evidence("gap", 42, center=0.5, width=0.24)
    dense_e = full_support()
    fits = {}
    for label, e in (("sparse", sparse_e), ("full", dense_e)):
        (out / f"{label}_evidence.json").write_text(json.dumps({k: v.tolist() if isinstance(v, np.ndarray) else v
                                                               for k, v in e.items()}, indent=2), encoding="utf-8")
        for n in (2, 3):
            fits[f"{label}_{n}"] = stabilize(e, solve(e, n))
            with log.open("a", encoding="utf-8") as f:
                f.write(f"- Solved {label}, {n**3} nodes, eta={fits[f'{label}_{n}']['eta']:.6g}.\n")
    rng = np.random.default_rng(1234)
    # Assess only the observed inner patch separately from its extrapolation.
    sample = rng.uniform([0.05, 0.32, 0.15], [0.95, 0.85, 0.85], (150000, 3))
    gap = (sample[:, 0] > 0.39) & (sample[:, 0] < 0.61)
    body = (sample[:, 0] < 0.36) | (sample[:, 0] > 0.64)
    # Fixed x=0.5, 41 z locations; each y line must be free from notch bottom
    # to outside top. This is a finite straight-path proxy, not topology proof.
    yline = np.linspace(0.32, 0.93, 151)
    zline = np.linspace(0.15, 0.85, 41)
    yy, zz = np.meshgrid(yline, zline, indexing="ij")
    line_points = np.column_stack([np.full(yy.size, 0.5), yy.ravel(), zz.ravel()])
    rows, meshes = [], {}
    pts = grid_points(81)
    for name in ["ground_truth", *fits]:
        fit = fits.get(name)
        field_at = (lambda p: 0.12 - np.abs(p[:, 0] - 0.5)) if fit is None else (lambda p: evaluate(p, fit))
        occupancy = object_field(sample, field_at(sample)) <= 0
        paths = object_field(line_points, field_at(line_points)).reshape(len(yline), len(zline)) > 0
        field = object_field(pts, field_at(pts)).reshape((81,) * 3)
        v, f, _, _ = marching_cubes(field, level=0, spacing=(1/80,) * 3)
        meshes[name] = v, f
        write_obj(out / f"{name}.obj", v, f)
        row = dict(method=name, nodes=0 if fit is None else fit["nodes"],
                   eta=None if fit is None else fit["eta"],
                   gap_occupied_fraction=float(occupancy[gap].mean()),
                   solid_probe_recall=float(occupancy[body].mean()),
                   notch_straight_path_fraction=float(paths.all(axis=0).mean()),
                   notch_path_count=len(zline), vertices=len(v), faces=len(f))
        rows.append(row)
        csv_write(out / "metrics.csv", rows)
    # A fair coarse-vs-fine comparison only within each support condition.
    held = evidence("gap", 42, center=0.5, width=0.24, phase="held")
    a, b, u = constraints(held, 3)
    verification = {k: float(np.maximum((a @ fits[k]["z"] - b) / u, 0).max()) for k in ["sparse_3", "full_3"]}
    assert fits["full_2"]["eta"] > 1 and fits["full_3"]["eta"] < 1e-6
    assert rows[-1]["gap_occupied_fraction"] < 0.01
    assert rows[-1]["solid_probe_recall"] > 0.99
    assert rows[-1]["notch_straight_path_fraction"] == 1
    np.savez(out / "fields.npz", **{k: f["z"] for k, f in fits.items()})
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    names = ["ground_truth", "full_2", "sparse_3", "full_3"]
    titles = ["Ground truth", "Full support: 8 nodes", "Sparse support: 27 nodes", "Full support: 27 nodes"]
    colors = ["#9aa7b1", "#d58257", "#bdad76", "#319681"]
    fig = plt.figure(figsize=(13, 4.8))
    for i, (name, title, color) in enumerate(zip(names, titles, colors), 1):
        v, f = meshes[name]
        ax = fig.add_subplot(1, 4, i, projection="3d")
        shown = v[:, [0, 2, 1]]
        ax.add_collection3d(Poly3DCollection(shown[f], linewidths=0, shade=True, facecolors=color))
        ax.set(xlim=(0, 1), ylim=(0, 1), zlim=(0, 1), title=title)
        ax.set_box_aspect((1, 1, 1))
        ax.view_init(elev=12, azim=-80)
        ax.set_axis_off()
    fig.suptitle("Both capacity AND observation coverage matter (synthetic Oracle evidence)")
    fig.text(0.5, 0.04, "Full-support coarse/fine share the same evidence. Sparse/full comparison changes supervision.", ha="center")
    fig.tight_layout(rect=(0, 0.05, 1, 0.92))
    fig.savefig(out / "coverage_comparison.png", dpi=180)
    plt.close(fig)
    memory = psutil.Process().memory_info()
    summary = dict(status="completed", elapsed_seconds=time.perf_counter()-start,
                   peak_working_set_bytes=getattr(memory, "peak_wset", None),
                   gpu_used=False, source_sha256=sources, resampled_violation=verification,
                   sparse_surface_points=len(sparse_e["surface"]), full_surface_points=len(dense_e["surface"]),
                   limitations=["Extra full-window Oracle observations; not a proposed automatic data source",
                                "No RGB, estimated pose, SAM, MVS, or GPU reconstruction",
                                "Known outer scaffold and base shared across arms",
                                "Straight-path samples and volume probes are not continuous topology certificates"],
                   metrics=rows)
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    with log.open("a", encoding="utf-8") as f:
        f.write("- Saved both support conditions, finite straight-path metrics, meshes, plots and exact source snapshots.\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
