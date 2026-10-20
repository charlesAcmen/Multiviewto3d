"""Check whether the capacity diagnosis requires the additional inside probes."""
import argparse
import json
import shutil
from pathlib import Path
from run_smoke import evidence, solve, csv_write


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path(__file__).parent / "results" / "constraint_ablation_v1")
    out = parser.parse_args().output.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit("Choose a fresh output directory")
    out.mkdir(parents=True, exist_ok=True)
    e = evidence("gap", 42, center=0.5, width=0.24)
    rows = []
    for normals, inside in [(False, False), (True, False), (False, True), (True, True)]:
        for margin in (0, 0.01, 0.04):
            f2, f3 = [solve(e, n, free_margin=margin, with_normals=normals, with_inside=inside) for n in (2, 3)]
            rows.append(dict(normals=normals, inside_probes=inside, free_margin=margin,
                             coarse_eta=f2["eta"], fine_eta=f3["eta"]))
    csv_write(out / "ablation.csv", rows)
    no_support = [r for r in rows if not r["normals"] and not r["inside_probes"]]
    assert no_support[0]["coarse_eta"] < 1e-6  # zero margin admits zero field
    assert no_support[-1]["coarse_eta"] > 0.1 and no_support[-1]["fine_eta"] < 1e-6
    for name in ("run_smoke.py", "run_constraint_ablation.py"):
        shutil.copyfile(Path(__file__).with_name(name), out / (name + ".snapshot"))
    (out / "README.md").write_text(
        "# Constraint ablation (Oracle)\n\n"
        "With exact surfaces and a positive FREE margin, coarse/fine diagnosis survives without interior probes. "
        "With no normals, no inside probes and zero FREE margin, the zero field makes both levels feasible. "
        "This is a constraint nondegeneracy check, not a reconstructed mesh or RGB evaluation.\n", encoding="utf-8")
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
