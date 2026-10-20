"""Finite-constraint Oracle experiment; NOT an RGB reconstruction benchmark.

Run from any directory. Writes raw evidence/results before figures. All grids
are genuine 3D trilinear grids; axis-aligned manufactured surfaces deliberately
make the capacity failure understandable. The mesh demo supplies an exact outer
scaffold to every method. No GPU training or end-to-end VRAM claim is made.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import platform
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import scipy
from scipy import sparse
from scipy.optimize import linprog, minimize, LinearConstraint
from skimage.measure import marching_cubes
import psutil

VALUE_UNIT = 0.02
NORMAL_UNIT = 0.25
SURFACE_EPS = 0.002
FREE_MARGIN = 0.04
INSIDE_MARGIN = 0.08
NORMAL_MIN = 0.5
FEASIBLE_ETA = 1e-6


def grid_points(n):
    return np.stack(np.meshgrid(*([np.linspace(0, 1, n)] * 3), indexing="ij"), -1).reshape(-1, 3)


def basis(points, n, normals=None):
    """Sparse interpolation, or a directional derivative, in [0,1]^3."""
    points = np.asarray(points, dtype=float).reshape(-1, 3)
    if np.any(points < -1e-10) or np.any(points > 1 + 1e-10):
        raise ValueError("Point outside local grid")
    u = points * (n - 1)
    base = np.clip(np.floor(u).astype(int), 0, n - 2)
    frac = u - base
    rows, cols, values = [], [], []
    for bit in itertools.product((0, 1), repeat=3):
        bit = np.asarray(bit)
        factors = np.where(bit, frac, 1 - frac)
        if normals is None:
            w = factors.prod(axis=1)
        else:
            w = np.zeros(len(points))
            for axis in range(3):
                others = [a for a in range(3) if a != axis]
                w += normals[:, axis] * (2 * bit[axis] - 1) * (n - 1) * factors[:, others].prod(axis=1)
        idx = base + bit
        rows.append(np.arange(len(points)))
        cols.append((idx[:, 0] * n + idx[:, 1]) * n + idx[:, 2])
        values.append(w)
    return sparse.coo_matrix((np.concatenate(values), (np.concatenate(rows), np.concatenate(cols))),
                             shape=(len(points), n ** 3)).tocsr()


def evidence(kind, seed, *, center=None, width=None, axis=0, phase="train"):
    """Manufactured oriented surfaces, FREE samples, and interior probes.

    Interior probes are derived from exact normals at offset 0.1. They are
    additional Oracle supervision, NOT input permitted silently in RGB tests.
    """
    rng = np.random.default_rng(seed + (10000 if phase != "train" else 0))
    center = float(center if center is not None else rng.uniform(0.46, 0.54))
    width = float(width if width is not None else rng.uniform(0.18, 0.32))
    yz = rng.uniform(0.15, 0.85, (12, 2))

    def points(x):
        p = np.empty((len(yz), 3))
        p[:, axis] = x
        p[:, [a for a in range(3) if a != axis]] = yz
        return p

    direction = np.eye(3)[axis]
    if kind in ("gap", "unresolved_gap"):
        left, right = center - width / 2, center + width / 2
        s = np.concatenate([points(left), points(right)])
        normals = np.concatenate([np.tile(direction, (len(yz), 1)), np.tile(-direction, (len(yz), 1))])
        free = points(center)
        inside = np.concatenate([points(left - 0.1), points(right + 0.1)])
    else:
        s = points(center)
        normals = np.tile(direction, (len(yz), 1))
        free = points(center + 0.15)
        inside = points(center - 0.15)
        if kind == "contradiction":
            # Identical locations demand a surface AND strictly positive air.
            free = np.concatenate([free, s.copy()])
    return dict(kind=kind, seed=seed, axis=axis, center=center, width=width,
                surface=s, normals=normals, free=free, inside=inside)


def constraints(e, n, free_margin=FREE_MARGIN, surface_eps=SURFACE_EPS, with_normals=True, with_inside=True):
    af, ass, ai = (basis(e[k], n) for k in ("free", "surface", "inside"))
    pieces = [-af, ass, -ass]
    rhs = [np.full(af.shape[0], -free_margin), np.full(ass.shape[0], surface_eps),
           np.full(ass.shape[0], surface_eps)]
    units = [np.full(len(b), VALUE_UNIT) for b in rhs]
    if with_inside:
        pieces.append(ai)
        rhs.append(np.full(ai.shape[0], -INSIDE_MARGIN))
        units.append(np.full(ai.shape[0], VALUE_UNIT))
    if with_normals:
        an = basis(e["surface"], n, e["normals"])
        pieces.append(-an)
        rhs.append(np.full(an.shape[0], -NORMAL_MIN))
        units.append(np.full(an.shape[0], NORMAL_UNIT))
    return sparse.vstack(pieces, format="csr"), np.concatenate(rhs), np.concatenate(units)


def solve(e, n, *, tie_break=False, **kwargs):
    """min eta subject to A z <= b + eta*u, with FREE signed node bounds."""
    t0 = time.perf_counter()
    a, b, units = constraints(e, n, **kwargs)
    aa = sparse.hstack([a, -units[:, None]], format="csr")
    c = np.r_[np.zeros(n ** 3), 1.0]
    result = linprog(c, A_ub=aa, b_ub=b,
                     bounds=[(-2.0, 2.0)] * (n ** 3) + [(0, None)], method="highs")
    if not result.success:
        raise RuntimeError(result.message)
    z, eta = result.x[:-1], float(result.x[-1])
    if tie_break:
        # Among minimax-optimal fields, choose the L1 nearest to the same
        # filled initial field. This removes arbitrary solver vertex choices.
        count = n ** 3
        eye = sparse.eye(count, format="csr")
        zero = sparse.csr_matrix((a.shape[0], count))
        mat = sparse.vstack([sparse.hstack([a, zero]), sparse.hstack([eye, -eye]),
                             sparse.hstack([-eye, -eye])], format="csr")
        ref = np.full(count, -0.12)
        r = linprog(np.r_[np.zeros(count), np.ones(count)], A_ub=mat,
                    b_ub=np.r_[b + (eta + 1e-8) * units, ref, -ref],
                    bounds=[(-2, 2)] * count + [(0, None)] * count, method="highs")
        if not r.success:
            raise RuntimeError(r.message)
        z = r.x[:count]
    violation = float(np.maximum((a @ z - b) / units, 0).max())
    if violation > eta + 2e-5:
        raise AssertionError("Returned field violates certified slack")
    return dict(z=z, eta=eta, verified_eta=violation, seconds=time.perf_counter() - t0,
                nodes=n ** 3, n=n, constraints=a.shape[0])


def decide(coarse, fine):
    if coarse <= FEASIBLE_ETA:
        return "reoptimize"
    if fine <= FEASIBLE_ETA:
        return "refine_candidate"
    return "defer_or_expand"  # Never infer that the observations are wrong.


def stabilize(e, fit):
    """Minimum grid Dirichlet energy at the SAME optimal slack.

    A conventional convex quadratic regularizer, not a novelty claim. It picks
    a less oscillatory initializer among feasible nodes, without adding GT.
    """
    n = fit["n"]
    ids = np.arange(n ** 3).reshape((n,) * 3)
    pairs = []
    for axis in range(3):
        lo, hi = [slice(None)] * 3, [slice(None)] * 3
        lo[axis], hi[axis] = slice(None, -1), slice(1, None)
        pairs.append((ids[tuple(lo)].ravel(), ids[tuple(hi)].ravel()))
    i, j = [np.concatenate([p[k] for p in pairs]) for k in range(2)]
    d = sparse.coo_matrix((np.r_[np.ones(len(i)), -np.ones(len(i))],
                         (np.r_[np.arange(len(i)), np.arange(len(i))], np.r_[i, j])),
                         shape=(len(i), n ** 3)).tocsr()
    q = (d.T @ d).toarray() + 1e-6 * np.eye(n ** 3)
    a, b, u = constraints(e, n)
    t0 = time.perf_counter()
    r = minimize(lambda z: 0.5 * z @ q @ z, fit["z"], jac=lambda z: q @ z,
                 constraints=LinearConstraint(a.toarray(), -np.inf, b + (fit["eta"] + 1e-8) * u),
                 bounds=[(-2, 2)] * (n ** 3), method="SLSQP",
                 options={"ftol": 1e-11, "maxiter": 500})
    if not r.success:
        raise RuntimeError("Stabilization failed: " + r.message)
    eta_actual = float(np.maximum((a @ r.x - b) / u, 0).max())
    if eta_actual > fit["eta"] + 2e-5:
        raise AssertionError("Stabilization changed allowed minimax slack")
    return {**fit, "z": r.x, "stabilize_seconds": time.perf_counter() - t0,
            "verified_eta": eta_actual}


def evaluate(points, fit, chunk=20000):
    return np.concatenate([basis(points[i:i + chunk], fit["n"]) @ fit["z"]
                           for i in range(0, len(points), chunk)])


def box_field(p, center, half):
    q = np.abs(p - np.asarray(center)) - np.asarray(half)
    return np.linalg.norm(np.maximum(q, 0), axis=-1) + np.minimum(q.max(axis=-1), 0)


def object_field(p, local_values):
    # Exact shared outer context and lower connecting bar: visualization fixture.
    outer = box_field(p, [0.5, 0.5, 0.5], [0.45, 0.4, 0.38])
    bar = box_field(p, [0.5, 0.19, 0.5], [0.45, 0.09, 0.38])
    return np.maximum(outer, np.minimum(local_values, bar))


def write_obj(path, vertices, faces):
    with path.open("w", encoding="ascii") as f:
        f.write("# Oracle local field + known outer scaffold; normalized units\n")
        for v in vertices:
            f.write("v %.8f %.8f %.8f\n" % tuple(v))
        for face in faces + 1:
            f.write("f %d %d %d\n" % tuple(face))


def csv_write(path, rows):
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def tests():
    rng = np.random.default_rng(190)
    p = rng.uniform(0.01, 0.99, (100, 3))
    for n in (2, 3, 5):
        a = basis(p, n)
        assert np.allclose(a.sum(axis=1), 1)
        assert a.min() >= -1e-12
        # Exact reproduction of a trilinear polynomial including xyz.
        fn = lambda x: x[:, 0] * x[:, 1] * x[:, 2] + 2 * x[:, 0] - x[:, 2] + 0.3
        assert np.allclose(a @ fn(grid_points(n)), fn(p))
        normal = np.tile([1, 0, 0], (len(p), 1))
        assert np.allclose(basis(p, n, normal) @ fn(grid_points(n)), 2 + p[:, 1] * p[:, 2])
    # Coarse coefficients must prolong exactly into the fine nested space.
    z = rng.uniform(-1, 1, 8)
    assert np.allclose(basis(p, 2) @ z, basis(p, 3) @ (basis(grid_points(3), 2) @ z))
    plane = solve(evidence("plane", 0), 2)
    gap = evidence("gap", 0, center=0.5, width=0.24)
    g2, g3 = solve(gap, 2), solve(gap, 3)
    c2, c3 = (solve(evidence("contradiction", 0), n) for n in (2, 3))
    assert plane["eta"] < 1e-6
    assert g2["eta"] > 0.1 and g3["eta"] < 1e-6
    assert c2["eta"] > 0.1 and c3["eta"] > 0.1
    # Failing two levels is not a certificate of wrong observations.
    small = evidence("unresolved_gap", 0, center=0.25, width=0.1)
    s2, s3, s5 = [solve(small, n)["eta"] for n in (2, 3, 5)]
    assert s2 > 0.1 and s3 > 0.1 and s5 < 1e-6
    return dict(partition_of_unity=True, trilinear_exactness=True, derivative=True,
                nested_prolongation=True, known_branch_cases=True,
                unresolved_gap_eta=[s2, s3, s5])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path(__file__).parent / "results" / "smoke_v1")
    parser.add_argument("--seeds", type=int, default=12)
    args = parser.parse_args()
    out = args.output.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit("Output directory is not empty; choose a new --output to preserve evidence")
    out.mkdir(parents=True, exist_ok=True)
    start = time.perf_counter()
    def checkpoint(s):
        with (out / "RUN_LOG.md").open("a", encoding="utf-8") as f:
            f.write(f"- {time.perf_counter() - start:.2f}s: {s}\n")
        print(s, flush=True)

    checkpoint("Started CPU-only manufactured Oracle experiment; no images or GPU training.")
    test_result = tests()
    (out / "tests.json").write_text(json.dumps(test_result, indent=2), encoding="utf-8")
    checkpoint("Interpolation, LP residual, nesting, and branch regression checks passed.")
    raw, rows, stability_rows = [], [], []
    examples = {}
    for seed in range(args.seeds):
        for kind in ("plane", "gap", "contradiction", "unresolved_gap"):
            kw = dict(center=0.25, width=0.1) if kind == "unresolved_gap" else {}
            e = evidence(kind, seed, axis=seed % 3, **kw)
            raw.append({k: v.tolist() if isinstance(v, np.ndarray) else v for k, v in e.items()})
            fits = [solve(e, n) for n in (2, 3, 5)]
            # This 'held-out' set only resamples the SAME analytic surfaces.
            # It is not independent views or independent object generalization.
            held = evidence(kind, seed, center=e["center"], width=e["width"], axis=seed % 3, phase="held")
            ah, bh, uh = constraints(held, 3)
            hold_eta = float(np.maximum((ah @ fits[1]["z"] - bh) / uh, 0).max())
            stable = stabilize(e, fits[1])
            stable_hold_eta = float(np.maximum((ah @ stable["z"] - bh) / uh, 0).max())
            stability_rows.append(dict(kind=kind, seed=seed, raw_resampled_eta=hold_eta,
                                       stabilized_resampled_eta=stable_hold_eta,
                                       stabilization_seconds=stable["stabilize_seconds"]))
            row = dict(kind=kind, seed=seed, axis=seed % 3, center=e["center"], width=e["width"],
                       coarse_eta=fits[0]["eta"], fine_eta=fits[1]["eta"], third_eta=fits[2]["eta"],
                       action=decide(fits[0]["eta"], fits[1]["eta"]),
                       resampled_fine_eta=hold_eta, seconds=sum(f["seconds"] for f in fits))
            rows.append(row)
            examples.setdefault(kind, (e, fits))
            # Persist after each solved case, before visualization or summaries.
            csv_write(out / "diagnostics.csv", rows)
            csv_write(out / "stability.csv", stability_rows)
    (out / "evidence.json").write_text(json.dumps(raw, indent=2), encoding="utf-8")
    checkpoint(f"Saved {len(rows)} diagnostic cases and their explicit Oracle evidence.")

    # Sensitivity within the full Oracle setup (inside probes remain active).
    sensitivity = []
    e = evidence("gap", 42, center=0.5, width=0.24)
    for margin in (0, 0.01, 0.04):
        for eps in (0.002, 0.03, 0.08):
            for normals in (False, True):
                f2, f3 = [solve(e, n, free_margin=margin, surface_eps=eps, with_normals=normals) for n in (2, 3)]
                sensitivity.append(dict(free_margin=margin, surface_eps=eps, normals=normals,
                                        coarse_eta=f2["eta"], fine_eta=f3["eta"]))
    csv_write(out / "sensitivity.csv", sensitivity)

    # Controlled scheduler stress test. Same evidence/node increment per patch.
    # Initial residual deliberately includes underoptimized planes and conflict.
    patches = []
    for idx, kind in enumerate(["plane", "gap", "contradiction"] * 4):
        epatch = evidence(kind, idx, axis=idx % 3)
        f2, f3 = [solve(epatch, n) for n in (2, 3)]
        a, b, u = constraints(epatch, 2)
        initial = np.full(8, -0.6 if kind == "plane" else -0.12)
        residual = float(np.maximum((a @ initial - b) / u, 0).max())
        gain = f2["eta"] - f3["eta"] if f3["eta"] <= FEASIBLE_ETA else 0.0
        patches.append(dict(index=idx, kind=kind, initial_residual=residual, gain=gain,
                            seconds=f2["seconds"] + f3["seconds"]))
    selectors = {"initial_residual": np.argsort([-p["initial_residual"] for p in patches])[:4],
                 "uniform_stride": np.arange(0, 12, 3),
                 "representability": np.argsort([-p["gain"] for p in patches])[:4]}
    budget = []
    for policy, indices in selectors.items():
        budget.append(dict(policy=policy, seed=-1, selected=" ".join(map(str, indices)),
                           useful_gap_refinements=sum(patches[i]["kind"] == "gap" for i in indices),
                           total_refinements=4, total_nodes=12 * 8 + 4 * (27 - 8)))
    for seed in range(100):
        indices = np.random.default_rng(seed).choice(12, 4, replace=False)
        budget.append(dict(policy="random", seed=seed, selected=" ".join(map(str, indices)),
                           useful_gap_refinements=sum(patches[i]["kind"] == "gap" for i in indices),
                           total_refinements=4, total_nodes=172))
    csv_write(out / "scheduler.csv", budget)
    (out / "scheduler_patches.json").write_text(json.dumps(patches, indent=2), encoding="utf-8")
    checkpoint("Saved tolerance ablations and a manufactured scheduling stress test (not a scene benchmark).")

    e = evidence("gap", 42, center=0.5, width=0.24)
    fits = {"coarse": solve(e, 2, tie_break=True), "refined": solve(e, 3, tie_break=True)}
    fits["stabilized"] = stabilize(e, fits["refined"])
    np.savez(out / "demo_fields.npz", **{k: f["z"] for k, f in fits.items()})
    resolution = 81
    pts = grid_points(resolution)
    gt_local = 0.12 - np.abs(pts[:, 0] - 0.5)
    local = {"ground_truth": gt_local, **{k: evaluate(pts, fit) for k, fit in fits.items()},
             "air_only": np.full(len(pts), 0.04)}
    meshes, geom = {}, []
    # Evaluation points are independent of training, in restricted gap/solid ROIs.
    rng = np.random.default_rng(20261020)
    ep = rng.uniform([0.05, 0.32, 0.15], [0.95, 0.85, 0.85], (100000, 3))
    gap_mask = (ep[:, 0] > 0.39) & (ep[:, 0] < 0.61)
    solid_mask = (ep[:, 0] < 0.36) | (ep[:, 0] > 0.64)
    for name, values in local.items():
        field = object_field(pts, values).reshape((resolution,) * 3)
        verts, faces, _, _ = marching_cubes(field, level=0, spacing=(1 / (resolution - 1),) * 3)
        write_obj(out / f"{name}.obj", verts, faces)
        meshes[name] = (verts, faces)
        if name == "ground_truth":
            elocal = 0.12 - np.abs(ep[:, 0] - 0.5)
        elif name == "air_only":
            elocal = np.full(len(ep), 0.04)
        else:
            elocal = evaluate(ep, fits[name])
        occupied = object_field(ep, elocal) <= 0
        geom.append(dict(method=name, gap_occupied_fraction=float(occupied[gap_mask].mean()),
                         solid_probe_recall=float(occupied[solid_mask].mean()),
                         vertices=len(verts), faces=len(faces), extraction_resolution=resolution,
                         learned_nodes=fits[name]["nodes"] if name in fits else 0))
    csv_write(out / "geometry.csv", geom)
    checkpoint(f"Exported {len(meshes)} explicit OBJ meshes with the shared known scaffold; saved ROI metrics.")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    fig = plt.figure(figsize=(16, 4.8))
    for i, (name, (vertices, faces)) in enumerate(meshes.items(), 1):
        ax = fig.add_subplot(1, len(meshes), i, projection="3d")
        # Display y as height and z as depth; front view keeps the slit visible.
        shown = vertices[:, [0, 2, 1]]
        poly = Poly3DCollection(shown[faces], linewidths=0, alpha=1, shade=True,
                               facecolors={"ground_truth": "#9aa7b1", "coarse": "#de885c",
                                           "refined": "#84b4ae", "stabilized": "#319681", "air_only": "#be8299"}[name])
        ax.add_collection3d(poly)
        ax.set(xlim=(0, 1), ylim=(0, 1), zlim=(0, 1), title=name.replace("_", " "))
        ax.set_box_aspect((1, 1, 1))
        ax.view_init(elev=12, azim=-80)
        ax.set_axis_off()
    fig.suptitle("Oracle local mechanism only: exact oriented surfaces + shared known outer scaffold", fontsize=12)
    fig.text(0.5, 0.03, "Coarse: 8 nodes | Both refined fields: 27 nodes | Air-only deletes the prongs", ha="center")
    fig.tight_layout(rect=(0, 0.05, 1, 0.93))
    fig.savefig(out / "mesh_comparison.png", dpi=180)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    kinds = ["plane", "gap", "contradiction", "unresolved_gap"]
    for n, key in enumerate(["coarse_eta", "fine_eta", "third_eta"]):
        means = [np.mean([r[key] for r in rows if r["kind"] == k]) for k in kinds]
        axes[0].bar(np.arange(4) + (n - 1) * 0.24, means, 0.24, label=["8 nodes", "27 nodes", "125 nodes"][n])
    axes[0].set_xticks(np.arange(4), ["Plane", "Gap", "Conflict", "Finer gap"])
    axes[0].set_ylabel("Minimum normalized violation eta (lower is better)")
    axes[0].set_title("Controlled cases; resampling is not real-view validation")
    axes[0].legend()
    x = np.linspace(0, 1, 500)
    pp = np.column_stack([x, np.full_like(x, 0.6), np.full_like(x, 0.5)])
    axes[1].plot(x, 0.12 - np.abs(x - 0.5), "k--", label="GT local field")
    for name, fit in fits.items():
        axes[1].plot(x, evaluate(pp, fit), label=name)
    axes[1].axhline(0, color="gray", linewidth=0.8)
    axes[1].axvspan(0.38, 0.62, color="#50a99b", alpha=0.12)
    axes[1].set(xlabel="Normalized x", ylabel="Field value (outside > 0)", title="Same observations, changed representation")
    axes[1].legend()
    fig.tight_layout()
    fig.savefig(out / "diagnostics.png", dpi=180)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 4))
    for key, label, marker in [("raw_resampled_eta", "Arbitrary LP optimum", "x"),
                               ("stabilized_resampled_eta", "Same slack + minimum grid energy", "o")]:
        for i, kind in enumerate(kinds):
            ys = [r[key] for r in stability_rows if r["kind"] == kind]
            ax.scatter(np.full(len(ys), i) + np.linspace(-0.13, 0.13, len(ys)), ys,
                       marker=marker, label=label if i == 0 else None, alpha=0.65)
    ax.set_xticks(np.arange(4), ["Plane", "Gap", "Conflict", "Finer gap"])
    ax.set(ylabel="Violation on resampled analytic surfaces", title="Feasibility is a diagnostic, not a final reconstruction")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out / "stability.png", dpi=180)
    plt.close(fig)

    try:
        gpu = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total,memory.used", "--format=csv"],
                             capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        gpu = "unavailable"
    memory = psutil.Process().memory_info()
    report = dict(evidence_level="CPU manufactured Oracle mechanism experiment; not RGB reconstruction",
                  diagnostic_cases=len(rows), seeds=args.seeds, total_seconds=time.perf_counter() - start,
                  python=sys.version, platform=platform.platform(), numpy=np.__version__, scipy=scipy.__version__,
                  process_rss_bytes=memory.rss, peak_working_set_bytes=getattr(memory, "peak_wset", None),
                  gpu_snapshot_NOT_peak=gpu, gpu_used_by_experiment=False,
                  torch_allocated=None, torch_reserved=None, geometry=geom,
                  source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  limitations=["Exact surfaces/normals and inward probes are Oracle supervision",
                               "No fixed patch boundary or global learned field in the diagnostic LP",
                               "Same analytic planes resampled; not independent test objects/views",
                               "Two-level failure cannot distinguish noise from insufficient fine resolution",
                               "Finite linear feasibility is not a signed-distance or topology certificate",
                               "Scheduler layout/initialization are constructed; no practical advantage proven",
                               "Mesh outer envelope and base are known analytic fixtures",
                               "Whole small CPU volume used for MC; not streaming GPU extraction"])
    (out / "summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    checkpoint("Finished; raw metrics, OBJ meshes, figures, environment, and limitations saved.")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
