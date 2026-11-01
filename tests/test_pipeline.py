import json, os, re, sys
import numpy as np, pandas as pd, pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from edu_synth import config as C, detect, export, generate, metrics as Mx, schema, validate  # noqa: E402


def _run(out, seed=C.SEED, scale="tiny"):
    a = generate.parser().parse_args(["--scale", scale, "--seed", str(seed), "--out", str(out)])
    import contextlib, io
    with contextlib.redirect_stdout(io.StringIO()):
        return generate.run(a)


@pytest.fixture(scope="module")
def ds(tmp_path_factory):
    out = tmp_path_factory.mktemp("tiny")
    man = _run(out)
    t = export.load_tables(os.path.join(out, "data"))
    gt = pd.read_csv(os.path.join(out, "ground_truth", "ground_truth.csv"), dtype=str, keep_default_na=False)
    return dict(out=str(out), t=t, gt=gt, man=man)


def test_volume_matches_requested_scale(ds):
    sc = C.PRESETS["tiny"]; t = ds["t"]
    assert (len(t["learners"]), len(t["courses"]), len(t["enrollments"]), len(t["activity_events"])) == (sc.learners, sc.courses, sc.enrollments, sc.events)


def test_full_scale_defaults_match_problem_statement():
    s = C.PRESETS["full"]
    assert (s.learners, s.courses, s.enrollments, s.events) == (20000, 500, 100000, 2_000_000)
    assert C.SEED == 20261022


def test_validation_suite_passes(ds):
    rep = json.load(open(os.path.join(ds["out"], "reports", "validation_summary.json")))
    assert rep["overall"] == "PASS" and rep["n_failed"] == 0 and rep["n_checks"] > 100


def test_id_conventions(ds):
    t = ds["t"]
    assert t["learners"].learner_id.str.match(r"^LRN-\d{6}$").all()
    assert t["courses"].course_id.str.match(r"^CRS-\d{6}$").all()
    assert (t["enrollments"].enrollment_id == "ENR-" + t["enrollments"].learner_id + "-" + t["enrollments"].course_id).all()
    assert t["activity_events"].event_id.str.match(r"^EVT-ENR-LRN-\d{6}-CRS-\d{6}-\d{6}$").all()
    assert t["assessments"].assessment_id.str.match(r"^ASM-2026-\d{6}$").all()
    assert t["learners"].learner_id.iloc[0] == "LRN-000001"


def test_pk_unique_and_fk_valid_except_labelled(ds):
    t, gt = ds["t"], ds["gt"]
    for name, df in t.items():
        assert df[schema.TABLES[name]["pk"]].is_unique, name
    for ct, cc, pt, pc, nullable, _ in schema.FKS:
        orphans = t[ct][cc].notna() & ~t[ct][cc].isin(set(t[pt][pc]))
        if (ct, cc) == ("activity_events", "enrollment_id"):
            expected = set(gt[gt.issue_type == "unenrolled_activity"].entity_id)
            assert set(t[ct].event_id[orphans]) == expected and len(expected) > 0
        else:
            assert orphans.sum() == 0, (ct, cc)


def test_ground_truth_is_separate_and_not_leaked(ds):
    forbidden = {"issue_type", "label_class", "ground_truth", "is_dormant", "diligence"}
    for name, df in ds["t"].items():
        assert not forbidden & set(df.columns), name
    assert os.path.exists(os.path.join(ds["out"], "ground_truth", "ground_truth.csv"))
    assert not any("ground_truth" in f for f in os.listdir(os.path.join(ds["out"], "data")))


def test_all_four_required_anomalies_labelled(ds):
    c = ds["gt"][ds["gt"].label_class == "injected_anomaly"].issue_type.value_counts()
    for k in ("duplicate_event", "unenrolled_activity", "completion_before_required_assessment", "timezone_day_shift"):
        assert c.get(k, 0) > 0, k


def test_dedup_removes_exactly_labelled_duplicates(ds):
    ev, gt = ds["t"]["activity_events"], ds["gt"]
    n_dup = (gt.issue_type == "duplicate_event").sum()
    assert ev.duplicated(C.DEDUP_KEY).sum() == n_dup
    v = Mx.valid_events(ev, ds["t"]["enrollments"], ds["t"]["cohorts"])
    n_unen = (gt.issue_type == "unenrolled_activity").sum()
    assert len(v) == len(ev) - n_dup - n_unen


def test_detectors_find_injected_anomalies_without_ground_truth(ds):
    scores = detect.score(detect.detect(ds["t"]), ds["gt"])
    for k, s in scores.items():
        assert s["recall"] >= 0.99 and s["precision"] >= 0.99, (k, s)


def test_duplicates_inflate_naive_engagement_and_dedup_fixes_it(ds):
    t = ds["t"]
    v = Mx.valid_events(t["activity_events"], t["enrollments"], t["cohorts"])
    weekly = Mx.weekly_metrics(v, t["enrollments"], t["cohorts"], t["course_outcomes"])
    imp = Mx.anomaly_impact(t["activity_events"], t["enrollments"], t["cohorts"], weekly)
    assert imp.naive_events.sum() > imp.valid_events.sum()


def test_timezone_shift_misassigns_weeks_when_reported_date_used(ds):
    t = ds["t"]
    v = Mx.valid_events(t["activity_events"], t["enrollments"], t["cohorts"])
    weekly = Mx.weekly_metrics(v, t["enrollments"], t["cohorts"], t["course_outcomes"])
    imp = Mx.anomaly_impact(t["activity_events"], t["enrollments"], t["cohorts"], weekly)
    assert (imp.active_learner_delta != 0).any()


def test_pipeline_metrics_equal_ground_truth_metrics(ds):
    t = ds["t"]
    v = Mx.valid_events(t["activity_events"], t["enrollments"], t["cohorts"])
    weekly = Mx.weekly_metrics(v, t["enrollments"], t["cohorts"], t["course_outcomes"])
    exp = pd.read_csv(os.path.join(ds["out"], "ground_truth", "expected_weekly_metrics.csv"))
    pd.testing.assert_frame_equal(weekly.reset_index(drop=True), exp.reset_index(drop=True), check_dtype=False, atol=1e-9)


def test_cohort_comparison_uses_identical_window(ds):
    c = pd.read_csv(os.path.join(ds["out"], "metrics", "cohort_comparison.csv"))
    assert (c.window_weeks == C.COMPARISON_WINDOW_WEEKS).all() and len(c) > 0
    w = pd.read_csv(os.path.join(ds["out"], "metrics", "weekly_cohort_metrics.csv"))
    ok = w[w.cohort_id.isin(c.cohort_id) & (w.week_index < C.COMPARISON_WINDOW_WEEKS)]
    assert (ok.groupby("cohort_id").size() == C.COMPARISON_WINDOW_WEEKS).all()
    assert ok.is_complete_week.all()


def test_completion_follows_rule_and_is_derived(ds):
    t = ds["t"]
    o = t["course_outcomes"].merge(t["completion_rules"], on="rule_id", suffixes=("", "_r"))
    need = np.ceil(o.min_required_content_pct * o.required_content_items_total / 100 - 1e-9)
    ok = (o.required_content_items_completed >= need) & (o.required_assessments_passed == o.required_assessments_total) & (o.weighted_score_pct + .011 >= o.min_weighted_score_pct)
    assert ((o.completion_status == "completed") == ok).all()
    assert (o.completion_status == "completed").any() and (o.completion_status != "completed").any()


def test_completion_anomaly_is_visible_as_history_vs_rule_mismatch(ds):
    t, gt = ds["t"], ds["gt"]
    bad = set(gt[gt.issue_type == "completion_before_required_assessment"].entity_id)
    enr = t["enrollments"].set_index("enrollment_id"); out = t["course_outcomes"].set_index("enrollment_id")
    status_mismatch = set(enr.index[(enr.current_status == "completed") != (out.completion_status.reindex(enr.index) == "completed")])
    assert status_mismatch <= bad and len(status_mismatch) > 0


def test_history_is_append_only_and_lifecycle_legal(ds):
    h = ds["t"]["enrollment_status_history"]
    assert h.groupby("enrollment_id").size().min() >= 1
    for _, g in h.groupby("enrollment_id"):
        prev = None
        for s in g.sort_values("history_id").to_status:
            assert s in C.LEGAL_TRANSITIONS[prev]; prev = s


def test_edge_case_coverage(ds):
    cov = json.load(open(os.path.join(ds["out"], "reports", "validation_summary.json")))["coverage"]
    assert cov["boundary"]["repeated_attempts"] > 0 and cov["failure_exception"]["abandoned_attempts"] > 0
    assert cov["failure_exception"]["inactive_learners"] > 0 and cov["event_mix"]["offline_sync"] > 0
    assert cov["event_mix"]["late_arriving_gt72h"] > 0 and cov["boundary"]["late_joiners"] > 0
    assert cov["boundary"]["two_rule_versions_courses"] > 0


def test_same_seed_reproducible_and_different_seed_differs(ds, tmp_path):
    m2 = _run(tmp_path / "again")
    for f, info in ds["man"]["files"].items():
        assert m2["files"][f]["sha256"] == info["sha256"], f
        assert m2["files"][f]["rows"] == info["rows"]
    m3 = _run(tmp_path / "other", seed=C.SEED + 1)
    assert m3["files"]["data/activity_events.csv"]["sha256"] != ds["man"]["files"]["data/activity_events.csv"]["sha256"]


def test_parameterised_scale_uses_same_generator(tmp_path):
    a = generate.parser().parse_args(["--scale", "tiny", "--learners", "120", "--courses", "8", "--enrollments", "500", "--events", "9000", "--out", str(tmp_path)])
    import contextlib, io
    with contextlib.redirect_stdout(io.StringIO()):
        m = generate.run(a)
    assert m["validation"]["overall"] == "PASS" and m["files"]["data/activity_events.csv"]["rows"] == 9000


def test_sql_schema_and_seed_load(ds, tmp_path):
    import sqlite3
    db = str(tmp_path / "x.sqlite")
    export.build_sqlite(os.path.join(ds["out"], "data"), db)
    con = sqlite3.connect(db)
    assert con.execute("select count(*) from activity_events").fetchone()[0] == len(ds["t"]["activity_events"])
    assert con.execute("select count(*) from activity_events e left join enrollments n using(enrollment_id) where n.enrollment_id is null").fetchone()[0] == (ds["gt"].issue_type == "unenrolled_activity").sum()
