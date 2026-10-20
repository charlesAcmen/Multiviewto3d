"""RGB SIFT + calibrated triangulation + mask FREE points, with no GT geometry.

This is a controlled image-interface smoke test, not complete MVS or SfM. Pose
and masks are given. A shared manually specified ROI isolates the two gap walls.
"""
import argparse
import itertools
import json
import time
from pathlib import Path
import cv2
import numpy as np
from scipy.spatial import cKDTree
from run_smoke import solve, stabilize, evaluate, object_field, grid_points, write_obj, csv_write
from skimage.measure import marching_cubes


def project(p, projection):
    h = np.column_stack([p, np.ones(len(p))]) @ projection.T
    return h[:, :2] / h[:, 2, None], h[:, 2]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--view-stride", type=int, default=1)
    parser.add_argument("--view-offset", type=int, default=0)
    parser.add_argument("--evidence-only", action="store_true")
    args = parser.parse_args()
    out = args.output.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit("Choose fresh output directory")
    out.mkdir(parents=True)
    start = time.perf_counter()
    log = out / "RUN_LOG.md"
    def report(s):
        print(s, flush=True)
        with log.open("a", encoding="utf-8") as f:
            f.write(f"- {time.perf_counter()-start:.2f}s: {s}\n")
    data = args.data.resolve()
    cameras = np.load(data / "cameras.npz")
    ps, centers = cameras["P"], cameras["centers"]
    images = [cv2.imread(str(f)) for f in sorted((data / "rgb").glob("*.png"))]
    masks = [cv2.imread(str(f), 0) for f in sorted((data / "mask").glob("*.png"))]
    view_ids = list(range(args.view_offset, len(images), args.view_stride))
    images, masks = [images[i] for i in view_ids], [masks[i] for i in view_ids]
    ps, centers = ps[view_ids], centers[view_ids]
    (out / "input_manifest.json").write_text(json.dumps(dict(view_ids=view_ids, data=str(data),
        inputs=["rgb/*.png", "mask/*.png", "cameras.npz"], no_ground_truth_geometry_read=True), indent=2))
    size = images[0].shape[0]
    sift = cv2.SIFT_create(nfeatures=4000, contrastThreshold=0.025, edgeThreshold=12)
    features = [sift.detectAndCompute(cv2.cvtColor(im, cv2.COLOR_BGR2GRAY), cv2.erode(mask, np.ones((5, 5), np.uint8)))
                for im, mask in zip(images, masks)]
    report(f"Extracted SIFT from {len(images)} RGB images, total features {sum(len(f[0]) for f in features)}.")
    points, origins, pair_ids, errors, matches_records = [], [], [], [], []
    matcher = cv2.BFMatcher(cv2.NORM_L2)
    pairs = []
    for i, j in itertools.combinations(range(len(images)), 2):
        baseline = np.linalg.norm(centers[i] - centers[j])
        if .20 < baseline < 1.1:
            pairs.append((i, j))
    for i, j in pairs:
        kp1, d1 = features[i]
        kp2, d2 = features[j]
        if d1 is None or d2 is None:
            continue
        forward, reverse = matcher.knnMatch(d1, d2, k=2), matcher.knnMatch(d2, d1, k=2)
        backward = {m.queryIdx: m.trainIdx for m, n in reverse if m.distance < .7 * n.distance}
        good = [m for m, n in forward if m.distance < .7 * n.distance and backward.get(m.trainIdx) == m.queryIdx]
        if not good:
            continue
        uv1 = np.array([kp1[m.queryIdx].pt for m in good], dtype=np.float64)
        uv2 = np.array([kp2[m.trainIdx].pt for m in good], dtype=np.float64)
        h = cv2.triangulatePoints(ps[i], ps[j], uv1.T, uv2.T).T
        p = h[:, :3] / h[:, 3, None]
        pr1, z1 = project(p, ps[i]); pr2, z2 = project(p, ps[j])
        reproj = np.maximum(np.linalg.norm(pr1 - uv1, axis=1), np.linalg.norm(pr2 - uv2, axis=1))
        dcam1, dcam2 = p - centers[i], p - centers[j]
        cosine = np.einsum("ij,ij->i", dcam1, dcam2) / (np.linalg.norm(dcam1, axis=1) * np.linalg.norm(dcam2, axis=1))
        keep = (reproj < .7) & (z1 > 0) & (z2 > 0) & (cosine < np.cos(np.deg2rad(3))) & (p.min(axis=1) > 0) & (p.max(axis=1) < 1)
        points.extend(p[keep]); origins.extend(np.tile((centers[i] + centers[j]) / 2, (keep.sum(), 1)))
        pair_ids.extend(np.tile([i, j], (keep.sum(), 1))); errors.extend(reproj[keep])
        matches_records.append(dict(view_i=i, view_j=j, ratio_mutual=len(good), accepted=int(keep.sum())))
    p = np.asarray(points)
    origin = np.asarray(origins)
    if len(p) < 30:
        raise RuntimeError(f"Insufficient RGB matches ({len(p)}). Preserve evidence and inspect texture/coverage.")
    np.savez(out / "triangulated.npz", xyz=p, camera_origins=origin, view_pairs=pair_ids, reprojection_px=errors)
    csv_write(out / "matching.csv", matches_records)
    report(f"Triangulated {len(p)} RGB matches; no GT depth/normals/correspondences read.")
    # Spatial thinning does not query GT. Orient PCA normals toward observations.
    _, unique = np.unique(np.floor(p / .008).astype(int), axis=0, return_index=True)
    p, origin = p[unique], origin[unique]
    tree = cKDTree(p)
    surface, normals, confidence, selected_indices = [], [], [], []
    for idx, point in enumerate(p):
        # Shared manually fixed gap-wall ROI, independent of GT point validity.
        if not (.28 < point[0] < .72 and .34 < point[1] < .84 and .17 < point[2] < .83):
            continue
        neighbors = tree.query_ball_point(point, .07)
        if len(neighbors) < 7:
            continue
        q = p[neighbors]
        cov = np.cov((q - q.mean(axis=0)).T)
        vals, vecs = np.linalg.eigh(cov)
        if vals[1] < 1e-6 or vals[0] / vals[1] > .08:
            continue
        normal = vecs[:, 0]
        if np.dot(normal, origin[idx] - point) < 0:
            normal *= -1
        surface.append(point); normals.append(normal); confidence.append(1-vals[0]/vals[1]); selected_indices.append(idx)
    surface, normals = np.asarray(surface), np.asarray(normals)
    if len(surface) < 12:
        report(f"Only {len(surface)} reliable ROI surface points; frontend not sufficient yet.")
        (out / "failure.json").write_text(json.dumps(dict(stage="roi_normals", reliable_points=len(surface), matched=len(p))))
        return
    # Candidate FREE points are classified ONLY by the input masks/projections.
    rng = np.random.default_rng(12345)
    candidates = rng.uniform([.3, .34, .17], [.7, .84, .83], (5000, 3))
    free_votes = np.zeros(len(candidates), int)
    first_support = np.full(len(candidates), -1)
    for view, (mask, projection) in enumerate(zip(masks, ps)):
        bg = cv2.erode(255 - mask, np.ones((5, 5), np.uint8))
        uv, z = project(candidates, projection)
        pix = np.rint(uv).astype(int)
        valid = (z > 0) & (pix.min(axis=1) >= 0) & (pix.max(axis=1) < size)
        voted = np.zeros(len(candidates), bool)
        voted[valid] = bg[pix[valid, 1], pix[valid, 0]] > 0
        first_support[voted & (first_support < 0)] = view
        free_votes += voted
    chosen = np.flatnonzero(free_votes >= 2)
    chosen = chosen[rng.permutation(len(chosen))[:250]]
    free = candidates[chosen]
    # Near-surface inside probes are inferred from estimated normals. This is a
    # local thickness assumption, NOT ground-truth interior labels.
    take = rng.permutation(len(surface))[:160]
    surface, normals = surface[take], normals[take]
    inside = surface - .06 * normals
    e = dict(surface=surface, normals=normals, free=free, inside=inside)
    np.savez(out / "evidence.npz", **e, free_support_count=free_votes[chosen], free_first_view=first_support[chosen],
             surface_tri_indices=unique[np.asarray(selected_indices)[take]])
    report(f"Built image-derived evidence: {len(surface)} surface normals, {len(free)} FREE points, {len(inside)} inferred inward probes.")
    if args.evidence_only:
        (out / "summary.json").write_text(json.dumps(dict(status="evidence_complete", view_ids=view_ids,
            triangulated_matches=len(points), unique_points=len(p), surface_count=len(surface),
            free_count=len(free), elapsed_seconds=time.perf_counter()-start), indent=2))
        return
    fits = {f"nodes_{n**3}": solve(e, n) for n in (2, 3, 5)}
    rows = []
    for name, fit in fits.items():
        # LP is only the diagnostic; stable fit remains constrained by its slack.
        csv_write(out / "lp_before_fit.csv", [dict(method=k, eta=v["eta"], nodes=v["nodes"]) for k,v in fits.items()])
        stable = stabilize(e, fit)
        fits[name] = stable
        rows.append(dict(method=name, nodes=fit["nodes"], minimum_violation=fit["eta"],
                         lp_seconds=fit["seconds"], fit_seconds=stable["stabilize_seconds"]))
    csv_write(out / "diagnostics.csv", rows)
    np.savez(out / "fields.npz", **{k: f["z"] for k, f in fits.items()})
    # Analytic outside scaffold is still a display fixture, not reconstructed.
    pts = grid_points(81)
    for name, fit in fits.items():
        values = object_field(pts, evaluate(pts, fit)).reshape((81, 81, 81))
        v, faces, _, _ = marching_cubes(values, level=0, spacing=(1/80,) * 3)
        write_obj(out / f"{name}_shared_scaffold.obj", v, faces)
    summary = dict(status="completed", elapsed_seconds=time.perf_counter()-start, views=len(images),
                   triangulated_matches=len(points), unique_points=len(p), surface_count=len(surface),
                   free_count=len(free), diagnostics=rows, cv2=cv2.__version__,
                   assumptions=["GT poses and masks; no estimated-pose or SAM claim", "Manually fixed shared local ROI",
                                "PCA normals and inward probes inferred from RGB matches", "No GT geometry read by frontend",
                                "Known external scaffold used only for local OBJ display", "No independent scene/test-view acceptance yet"])
    (out / "summary.json").write_text(json.dumps(summary, indent=2))
    report("Saved image evidence, LP diagnostics and scaffolded local meshes.")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
