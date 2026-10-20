"""Render a textured fork or closed window to RGB/masks/known cameras on CPU.

The analytic boxes are used ONLY here and in evaluation. Reconstruction reads
the image directory and cameras.npz, never GT depth, normals, or correspondences.
"""
import argparse
import json
import time
from pathlib import Path
import cv2
import numpy as np


def cameras(size):
    k = np.array([[size * 1.25, 0, (size - 1) / 2], [0, size * 1.25, (size - 1) / 2], [0, 0, 1.]])
    rotations, centers = [], []
    for height in (0.65, 1.15):
        for yaw in (-30, -15, 0, 15, 30, 150, 165, 180, 195, 210):
            angle = np.deg2rad(yaw)
            eye = np.array([0.5 + 2 * np.sin(angle), height, 0.5 + 2 * np.cos(angle)])
            forward = np.array([0.5, 0.5, 0.5]) - eye
            forward /= np.linalg.norm(forward)
            right = np.cross(forward, [0., 1., 0.])
            right /= np.linalg.norm(right)
            down = np.cross(forward, right)
            rotations.append(np.stack([right, down, forward]))
            centers.append(eye)
    r, c = np.stack(rotations), np.stack(centers)
    rt = np.concatenate([r, -np.einsum("nij,nj->ni", r, c)[:, :, None]], axis=2)
    return k, r, c, np.einsum("ij,njk->nik", k, rt)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--size", type=int, default=512)
    p.add_argument("--shape", choices=["fork", "window"], default="fork")
    p.add_argument("--gap-width", type=float, default=.24)
    p.add_argument("--seed", type=int, default=20261020)
    args = p.parse_args()
    if not 0 < args.gap_width < .4:
        p.error("--gap-width must be between 0 and .4 for the fixed local study ROI")
    out = args.output.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit("Choose fresh output directory")
    (out / "rgb").mkdir(parents=True)
    (out / "mask").mkdir()
    start = time.perf_counter()
    left, right = .5 - args.gap_width / 2, .5 + args.gap_width / 2
    boxes = np.array([[[.05, .1, .12], [left, .9, .88]],
                      [[right, .1, .12], [.95, .9, .88]],
                      [[.05, .1, .12], [.95, .28, .88]]])
    if args.shape == "window":
        boxes = np.concatenate([boxes, [[[.05, .72, .12], [.95, .9, .88]]]])
    k, rotations, centers, projections = cameras(args.size)
    np.savez(out / "cameras.npz", K=k, R=rotations, centers=centers, P=projections)
    (out / "ground_truth_only.json").write_text(json.dumps(
        {"boxes": boxes.tolist(), "shape": args.shape, "gap_width": args.gap_width}, indent=2))
    rng = np.random.default_rng(args.seed)
    textures = []
    for _ in range(6 * len(boxes)):
        fine = cv2.resize(rng.uniform(20, 240, (100, 100)).astype(np.float32), (512, 512), interpolation=cv2.INTER_CUBIC)
        coarse = cv2.resize(rng.uniform(20, 240, (22, 22)).astype(np.float32), (512, 512), interpolation=cv2.INTER_CUBIC)
        tex = np.clip(.7 * fine + .3 * coarse, 0, 255)
        tint = rng.uniform(.7, 1., (1, 1, 3))
        textures.append(np.clip(tex[:, :, None] * tint, 0, 255).astype(np.uint8))
    u, v = np.meshgrid(np.arange(args.size), np.arange(args.size))
    directions_cam = np.column_stack([(u.ravel() - k[0, 2]) / k[0, 0],
                                       (v.ravel() - k[1, 2]) / k[1, 1], np.ones(u.size)])
    for view, (r, eye) in enumerate(zip(rotations, centers)):
        directions = directions_cam @ r
        inv = np.divide(1, directions, out=np.full_like(directions, 1e12), where=np.abs(directions) > 1e-12)
        best = np.full(len(directions), np.inf)
        box_ids = np.full(len(directions), -1)
        faces = np.zeros(len(directions), dtype=int)
        for bi, (lo, hi) in enumerate(boxes):
            a, b = (lo - eye) * inv, (hi - eye) * inv
            entry, leave = np.minimum(a, b), np.maximum(a, b)
            near, far = entry.max(axis=1), leave.min(axis=1)
            good = (near <= far) & (near > 0) & (near < best)
            axis = entry.argmax(axis=1)
            positive = directions[np.arange(len(directions)), axis] < 0
            faces[good] = (axis * 2 + positive)[good]
            best[good], box_ids[good] = near[good], bi
        rgb = np.full((len(directions), 3), 245, np.uint8)
        valid = box_ids >= 0
        world = eye + directions[valid] * best[valid, None]
        valid_ids = np.flatnonzero(valid)
        for bi in range(len(boxes)):
            for face in range(6):
                subset = (box_ids[valid] == bi) & (faces[valid] == face)
                if not subset.any():
                    continue
                axis = face // 2
                tangents = [j for j in range(3) if j != axis]
                xy = world[subset][:, tangents] * 511
                color = np.concatenate([cv2.remap(textures[bi * 6 + face],
                                  xy[start:start+20000, 0].astype(np.float32)[:, None],
                                  xy[start:start+20000, 1].astype(np.float32)[:, None],
                                  cv2.INTER_LINEAR).reshape(-1, 3) for start in range(0, len(xy), 20000)])
                shade = [0.85, 0.95, 1.0][axis]
                rgb[valid_ids[subset]] = (color * shade).astype(np.uint8)
        cv2.imwrite(str(out / "rgb" / f"{view:03d}.png"), rgb.reshape(args.size, args.size, 3))
        cv2.imwrite(str(out / "mask" / f"{view:03d}.png"), valid.reshape(args.size, args.size).astype(np.uint8) * 255)
        print(f"Rendered view {view+1}/{len(centers)}", flush=True)
    (out / "manifest.json").write_text(json.dumps(dict(views=len(centers), resolution=args.size,
        elapsed_seconds=time.perf_counter()-start, coordinate_frame="fixed object [0,1]^3",
        input_assumptions="GT pinhole cameras and GT target masks; static textured opaque analytic object",
        no_depth_saved=True, shape=args.shape, gap_width=args.gap_width,
        random_seed=args.seed, cv2=cv2.__version__), indent=2))


if __name__ == "__main__":
    main()
