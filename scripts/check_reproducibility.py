"""Step 10: regenerate twice with the same seed and compare row counts + SHA-256 of every output file.
Also regenerates once with a different seed to show the checksums are actually seed-sensitive.

  python scripts/check_reproducibility.py --scale full --out reports/reproducibility_full.json
"""
import argparse, json, os, shutil, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from edu_synth import config as C, generate  # noqa: E402


def gen(scale, seed, d):
    a = generate.parser().parse_args(["--scale", scale, "--seed", str(seed), "--out", d])
    import contextlib, io
    with contextlib.redirect_stdout(io.StringIO()):
        return generate.run(a)["files"]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--scale", default="tiny"); p.add_argument("--seed", type=int, default=C.SEED)
    p.add_argument("--out", default="reports/reproducibility.json"); p.add_argument("--skip-other-seed", action="store_true")
    a = p.parse_args()
    tmp = tempfile.mkdtemp()
    try:
        runs = [gen(a.scale, a.seed, os.path.join(tmp, f"run{i}")) for i in (1, 2)]
        rep = {"scale": a.scale, "seed": a.seed, "files": {}, "identical": True}
        for f in runs[0]:
            r1, r2 = runs[0][f], runs[1][f]
            same = r1["rows"] == r2["rows"] and r1["sha256"] == r2["sha256"]
            rep["identical"] &= same
            rep["files"][f] = dict(rows_run1=r1["rows"], rows_run2=r2["rows"], sha256_run1=r1["sha256"], sha256_run2=r2["sha256"], match=same)
        if not a.skip_other_seed:
            other = gen(a.scale, a.seed + 1, os.path.join(tmp, "other"))
            rep["different_seed_changes_output"] = other["data/activity_events.csv"]["sha256"] != runs[0]["data/activity_events.csv"]["sha256"]
        os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
        json.dump(rep, open(a.out, "w"), indent=2)
        print("IDENTICAL" if rep["identical"] else "MISMATCH", "- files compared:", len(rep["files"]), "->", a.out)
        sys.exit(0 if rep["identical"] else 1)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
