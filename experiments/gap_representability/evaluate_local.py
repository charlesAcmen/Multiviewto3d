"""Evaluate saved fields and mask baselines locally; GT is read ONLY here.

No analytic scaffold is added to predictions. Output meshes are clipped, open
local candidates, not complete or observation-certified object meshes.
"""
import argparse
import json
import time
from pathlib import Path

import cv2
import numpy as np
from skimage.measure import marching_cubes
from rgb_frontend import project
from run_smoke import box_field, csv_write, evaluate, grid_points

ROI_LO = np.array([.28, .34, .17])
ROI_HI = np.array([.72, .84, .83])


def mask_votes(points, backgrounds, projections):
    """Out-of-frame projections abstain; background votes certify FREE only."""
    votes = np.zeros(len(points), dtype=int)
    for start in range(0, len(points), 20000):
        chunk = points[start:start + 20000]
        for bg, projection in zip(backgrounds, projections):
            uv, depth = project(chunk, projection)
            pixels = np.rint(uv).astype(int)
            height, width = bg.shape
            valid = ((depth > 0) & (pixels[:, 0] >= 0) & (pixels[:, 0] < width)
                     & (pixels[:, 1] >= 0) & (pixels[:, 1] < height))
            indices = np.flatnonzero(valid)
            votes[start + indices] += bg[pixels[valid, 1], pixels[valid, 0]] > 0
    return votes


def fraction(values):
    return float(np.mean(values)) if len(values) else None


def main():
    parser = argparse.ArgumentParser()
    for name in ("data", "evidence", "fit", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--mask-only", action="store_true",
                        help="Keep mask baselines even when RGB evidence or fitting failed.")
    args = parser.parse_args()
    out = args.output.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit("Choose fresh output directory")
    out.mkdir(parents=True)
    gt = json.loads((args.data / "ground_truth_only.json").read_text())
    boxes = np.asarray(gt["boxes"])

    def truth(points):
        return np.min([box_field(points, (lo + hi) / 2, (hi - lo) / 2)
                       for lo, hi in boxes], axis=0)

    # Use exactly the frontend's selected views, not extra evaluator-only views.
    cameras = np.load(args.data / "cameras.npz")
    source_path = args.evidence / "input_manifest.json"
    source = (json.loads(source_path.read_text()) if source_path.exists()
              else {"view_ids": list(range(len(cameras["P"])))})
    if not args.mask_only and not source_path.exists():
        raise FileNotFoundError("RGB comparison requires the frontend input_manifest.json")
    projections = cameras["P"][source["view_ids"]]
    masks = [cv2.imread(str(args.data / "mask" / f"{v:03d}.png"), 0)
             for v in source["view_ids"]]
    if not masks or any(mask is None for mask in masks):
        raise ValueError("Missing or unreadable selected Mask; baseline comparison cannot proceed")
    raw_backgrounds = [255 - mask for mask in masks]
    safe_backgrounds = [cv2.erode(bg, np.ones((5, 5), np.uint8))
                        for bg in raw_backgrounds]
    quality = {"rgb_evidence_available": (args.evidence / "evidence.npz").exists()}
    if quality["rgb_evidence_available"]:
        evidence = np.load(args.evidence / "evidence.npz")
        quality.update(
            surface_count=len(evidence["surface"]), free_count=len(evidence["free"]),
            surface_gt_distance_p95=float(np.quantile(np.abs(truth(evidence["surface"])), .95)),
            free_gt_occupied_fraction=fraction(truth(evidence["free"]) <= 0),
            inside_gt_outside_fraction=fraction(truth(evidence["inside"]) > 0))

    rng = np.random.default_rng(20261022)
    probes = rng.uniform(ROI_LO, ROI_HI, (60000, 3))
    distance = truth(probes)
    # A small GT evaluation guard excludes ambiguous voxel/surface boundary points.
    gap, solid = distance > .002, distance < -.002
    near_wall = solid & (distance > -.01)
    quality["gap_with_two_safe_mask_votes_fraction"] = fraction(
        mask_votes(probes[gap], safe_backgrounds, projections) >= 2)
    csv_write(out / "evidence_quality.csv", [quality])
    x, y = np.meshgrid(.5 + gt["gap_width"] * np.linspace(-.35, .35, 7),
                       np.linspace(.36, .68, 11), indexing="ij")
    paths = np.stack([np.broadcast_to(x[..., None], (*x.shape, 151)),
                      np.broadcast_to(y[..., None], (*y.shape, 151)),
                      np.broadcast_to(np.linspace(.17, .83, 151), (*x.shape, 151))], -1)
    resolution = 81
    mesh_points = ROI_LO + grid_points(resolution) * (ROI_HI - ROI_LO)
    truth_grid = truth(mesh_points).reshape((resolution,) * 3)

    fields = {} if args.mask_only else np.load(args.fit / "fields.npz")
    fit_summary = ({"diagnostics": [], "status": "mask_only_after_rgb_failure"} if args.mask_only
                   else json.loads((args.fit / "summary.json").read_text()))
    diagnostics = {f"nodes_{r['nodes']}": r for r in fit_summary["diagnostics"]}
    methods = {
        "mask_raw": lambda p: mask_votes(p, raw_backgrounds, projections) - .5,
        "mask_conservative": lambda p: mask_votes(p, safe_backgrounds, projections) - 1.5,
    }
    for name in fields:
        z = fields[name]
        fit = dict(z=z, n=round(len(z) ** (1 / 3)))
        methods[name] = lambda p, fit=fit: evaluate(p, fit)
    rows, display = [], {"GT evaluation only": truth_grid}
    for name, field in methods.items():
        start = time.perf_counter()
        occupied = field(probes) <= 0
        path_free = field(paths.reshape(-1, 3)).reshape(*x.shape, 151) > 0
        volume = field(mesh_points).reshape((resolution,) * 3)
        display[name] = volume
        row = dict(method=name, nodes=diagnostics.get(name, {}).get("nodes"),
                   training_eta=diagnostics.get(name, {}).get("eta"),
                   gap_occupied_fraction=fraction(occupied[gap]),
                   solid_recall=fraction(occupied[solid]),
                   near_wall_solid_recall=fraction(occupied[near_wall]),
                   gap_path_fraction=float(path_free.all(axis=-1).mean()),
                   paths_tested=x.size, mesh_status="no_zero_crossing", mesh_faces=0,
                   evaluation_seconds=0.)
        if volume.min() < 0 < volume.max():
            vertices, faces, _, _ = marching_cubes(
                volume, 0, spacing=tuple((ROI_HI - ROI_LO) / (resolution - 1)))
            with (out / f"{name}_local_open.obj").open("w", encoding="ascii") as file:
                file.write("# Local candidate; open ROI boundary; NO GT scaffold; unknown areas not certified\n")
                np.savetxt(file, vertices + ROI_LO, fmt="v %.8f %.8f %.8f")
                np.savetxt(file, faces + 1, fmt="f %d %d %d")
            row.update(mesh_status="local_open_candidate", mesh_faces=len(faces))
        row["evaluation_seconds"] = time.perf_counter() - start
        rows.append(row)
        csv_write(out / "metrics.csv", rows)

    # Nominal projected mouth width at the yaw=0 front view, not a resolution claim.
    mouth = np.array([[.5 - gt["gap_width"] / 2, .5, .88],
                      [.5 + gt["gap_width"] / 2, .5, .88]])
    uv, _ = project(mouth, cameras["P"][2])
    summary = dict(status="completed", shape=gt["shape"], gap_width=gt["gap_width"],
                   nominal_front_mouth_pixels=float(np.linalg.norm(uv[1] - uv[0])),
                   fit_status=fit_summary["status"], view_ids=source["view_ids"],
                   evidence_quality=quality, metrics=rows,
                   evaluation_seed=20261022, roi=[ROI_LO.tolist(), ROI_HI.tolist()],
                   probe_count=len(probes), gap_probe_count=int(gap.sum()),
                   solid_probe_count=int(solid.sum()), near_wall_probe_count=int(near_wall.sum()),
                   mesh_grid=resolution, known_scaffold=False, gpu_used=False,
                   gpu_peak_bytes=None, heldout_views=False,
                   limitations=["Same primitive family as development fork, not real-scene generalization",
                                "GT cameras/masks, fixed ROI, PCA normals and inward-offset assumption",
                                "Uncarved mask volume is a candidate upper hull, not observed solid",
                                "Field/finite-path metrics, not mesh topology proof or Chamfer",
                                "All input views used for fitting; GT queried only for evaluation",
                                "No equal-budget scheduling comparison or GPU measurement"])
    (out / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False), encoding="utf-8")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 3, figsize=(11, 7), squeeze=False)
    extent = [ROI_LO[0], ROI_HI[0], ROI_LO[1], ROI_HI[1]]
    for ax, (name, volume) in zip(axes.flat, display.items()):
        ax.imshow((volume[:, :, resolution // 2] <= 0).T, origin="lower",
                  extent=extent, cmap="Greys", vmin=0, vmax=1, interpolation="nearest")
        ax.contour(np.linspace(ROI_LO[0], ROI_HI[0], resolution),
                   np.linspace(ROI_LO[1], ROI_HI[1], resolution),
                   truth_grid[:, :, resolution // 2].T, levels=[0], colors="red", linewidths=.8)
        ax.set(title=name, xlabel="x", ylabel="y")
    for ax in list(axes.flat)[len(display):]:
        ax.set_axis_off()
    fig.suptitle(f"{gt['shape']}, gap={gt['gap_width']}: z=0.5 slice; red = GT boundary")
    fig.tight_layout()
    fig.savefig(out / "comparison.png", dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    main()
