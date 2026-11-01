"""CLI: python -m edu_synth.generate --scale full --seed 20261022 --out output/full"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shlex
import subprocess
import sys
import time

import numpy as np
import pandas as pd

from . import __version__, build, config as C, detect, export, metrics as Mx, schema, validate


def run(args) -> dict:
    sc = C.resolve_scale(args.scale, learners=args.learners, courses=args.courses, enrollments=args.enrollments, events=args.events)
    out = args.out; os.makedirs(out, exist_ok=True)
    t0 = time.time(); log = print
    log(f"[1/6] generating scale={sc} seed={args.seed}")
    res = build.build(sc, args.seed, log)
    tables = res["tables"]
    log("[2/6] exporting CSV/JSON/SQL")
    files = export.write_tables(tables, out)
    files.update(export.write_ground_truth(res["ground_truth"], res["latent"], res["expected_weekly"], out))
    export.write_sql(out, with_seed=args.sql_seed)
    del tables; res.pop('tables'); import gc; gc.collect()
    log("[3/6] validating exported files")
    t = export.load_tables(os.path.join(out, "data"))
    gt = res["ground_truth"]
    rep = validate.validate(t, gt)
    os.makedirs(os.path.join(out, "reports"), exist_ok=True)
    with open(os.path.join(out, "reports", "validation_summary.json"), "w") as f: json.dump(rep, f, indent=2, default=str)
    with open(os.path.join(out, "reports", "validation_summary.md"), "w") as f: f.write(validate.to_markdown(rep))
    log(f"      validation: {rep['overall']} ({rep['n_checks']} checks, {rep['n_failed']} failed)")
    for c in rep["checks"]:
        if c["status"] == "FAIL": log("      FAIL:", c["group"], c["check"], c["violations"], "expected", c["expected"])
    log("[4/6] metrics (dedup + local-day + fixed windows)")
    v = Mx.valid_events(t["activity_events"], t["enrollments"], t["cohorts"])
    weekly = Mx.weekly_metrics(v, t["enrollments"], t["cohorts"], t["course_outcomes"])
    comp = Mx.cohort_comparison(weekly, t["cohorts"], t["courses"], t["course_outcomes"])
    impact = Mx.anomaly_impact(t["activity_events"], t["enrollments"], t["cohorts"], weekly)
    md = os.path.join(out, "metrics"); os.makedirs(md, exist_ok=True)
    weekly.to_csv(os.path.join(md, "weekly_cohort_metrics.csv"), index=False)
    comp.to_csv(os.path.join(md, "cohort_comparison.csv"), index=False)
    impact.to_csv(os.path.join(md, "anomaly_impact.csv"), index=False)
    kpi = Mx.kpi_summary(weekly, comp, t["course_outcomes"], t["enrollments"])
    kpi["event_inflation_overall_pct"] = round(float((len(t["activity_events"]) / len(v) - 1) * 100), 3)
    exp = res["expected_weekly"]
    same = weekly.drop(columns=[]).equals(exp)
    kpi["pipeline_metrics_match_ground_truth_metrics"] = bool(same)
    kpi["weeks_with_active_count_error_if_naive"] = int((impact.active_learner_delta != 0).sum())
    with open(os.path.join(md, "kpi_summary.json"), "w") as f: json.dump(kpi, f, indent=2)
    with open(os.path.join(md, "metric_definitions.json"), "w") as f: json.dump(Mx.METRIC_DEFINITIONS, f, indent=2)
    log(f"      metrics reproduce ground-truth metrics exactly: {same}")
    log("[5/6] detector evaluation (detectors never see ground truth)")
    scores = detect.score(detect.detect(t), gt)
    with open(os.path.join(out, "reports", "detection_evaluation.json"), "w") as f: json.dump(scores, f, indent=2)
    for k, s in scores.items(): log(f"      {k}: P={s['precision']} R={s['recall']} (truth={s['truth']})")
    log("[6/6] docs + manifest")
    docs = os.path.join(out, "docs"); os.makedirs(docs, exist_ok=True)
    open(os.path.join(docs, "data_dictionary.md"), "w").write(schema.dictionary_markdown())
    pd.DataFrame([dict(table=tb, **{k: f[k] for k in ("name", "type", "required", "allowed", "unit", "unique", "rule")}) for tb, sp in schema.TABLES.items() for f in sp["fields"]]
                 ).to_csv(os.path.join(docs, "data_dictionary.csv"), index=False)
    open(os.path.join(docs, "er_diagram.mmd"), "w").write(schema.er_mermaid())
    try: commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
    except Exception: commit = None
    manifest = dict(generator_version=__version__, command="python -m edu_synth.generate " + " ".join(shlex.quote(a) for a in sys.argv[1:]),
                    seed=args.seed, scale=sc.__dict__, as_of_date=C.AS_OF_DATE, git_commit=commit,
                    environment=dict(python=platform.python_version(), numpy=np.__version__, pandas=pd.__version__),
                    injected_anomalies=res["injected"], validation=dict(overall=rep["overall"], failed=rep["n_failed"]),
                    runtime_seconds=round(time.time() - t0, 1), files=files)
    with open(os.path.join(out, "manifest.json"), "w") as f: json.dump(manifest, f, indent=2)
    src = dict(external_data_used=False, note="All data is synthetic and generated from code + seed. No external datasets were downloaded, "
               "so no license/attribution obligations apply.", sources=[], schema_inspiration=[
        dict(name="xAPI / IEEE 9274.1.1 statements", url="https://xapi.com/specification/", used_for="event verb/object modelling ideas only", data_retrieved=False),
        dict(name="IMS Caliper Analytics", url="https://www.imsglobal.org/activity/caliper", used_for="event naming ideas only", data_retrieved=False)],
        fields_for_external_records=["source_url", "dataset_version", "retrieval_date", "license", "attribution", "transformations", "fields_discarded"])
    with open(os.path.join(out, "source_manifest.json"), "w") as f: json.dump(src, f, indent=2)
    log(f"done in {time.time() - t0:.1f}s -> {out}")
    return manifest


def parser():
    p = argparse.ArgumentParser(description="Synthetic learning-analytics data generator")
    p.add_argument("--scale", choices=list(C.PRESETS), default="full")
    p.add_argument("--seed", type=int, default=C.SEED)
    p.add_argument("--out", default="output/full")
    p.add_argument("--learners", type=int); p.add_argument("--courses", type=int)
    p.add_argument("--enrollments", type=int); p.add_argument("--events", type=int)
    p.add_argument("--sql-seed", action="store_true", help="also write sql/seed.sql (INSERTs); recommended for tiny/starter only")
    return p


if __name__ == "__main__":
    m = run(parser().parse_args())
    sys.exit(0 if m["validation"]["overall"] == "PASS" else 1)
