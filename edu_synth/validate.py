"""Step 8: validation on the EXPORTED files (re-read from disk). Ground truth is used only to reconcile expected violations."""
from __future__ import annotations

import math
import re

import numpy as np
import pandas as pd

from . import config as C, schema
from . import metrics as Mx

ENUMS = {
    "learners": dict(preferred_device=C.DEVICES, age_band=C.AGE_BANDS, signup_channel=C.SIGNUP_CHANNELS, account_status=C.ACCOUNT_STATUS),
    "courses": dict(level=C.LEVELS, course_status=C.COURSE_STATUS),
    "cohorts": dict(delivery_mode=C.DELIVERY_MODES, cohort_status=C.COHORT_STATUS),
    "enrollments": dict(enrollment_source=C.ENR_SOURCES, current_status=C.ENR_STATUSES),
    "enrollment_status_history": dict(to_status=C.ENR_STATUSES, changed_by=C.HISTORY_ACTORS),
    "content_items": dict(content_type=C.CONTENT_TYPES, content_status=C.CONTENT_STATUS),
    "assessments": dict(assessment_type=C.ASSESSMENT_TYPES, assessment_status=C.ASSESSMENT_STATUS),
    "attempts": dict(attempt_status=C.ATTEMPT_STATUS),
    "completion_rules": dict(rule_status=C.RULE_STATUS),
    "activity_events": dict(event_type=C.EVENT_TYPES, device_type=C.DEVICES, source=C.SOURCES),
    "course_outcomes": dict(completion_status=C.OUTCOME_STATUS, engagement_band=C.ENGAGEMENT_BANDS),
}
ID_RE = {"learners": r"^LRN-\d{6}$", "instructors": r"^INS-\d{4}$", "courses": r"^CRS-\d{6}$", "cohorts": r"^COH-\d{6}$",
         "content_items": r"^CNT-\d{7}$", "assessments": r"^ASM-2026-\d{6}$", "attempts": r"^ATT-\d{8}$",
         "completion_rules": r"^CRL-\d{6}$", "enrollments": r"^ENR-LRN-\d{6}-CRS-\d{6}$",
         "activity_events": r"^EVT-ENR-LRN-\d{6}-CRS-\d{6}-\d{6}$", "enrollment_status_history": r"^ESH-ENR-LRN-\d{6}-CRS-\d{6}-\d{2}$",
         "course_outcomes": r"^OUT-ENR-LRN-\d{6}-CRS-\d{6}$"}


class Report:
    def __init__(self): self.checks = []
    def add(self, group, name, bad, expected=0, detail=""):
        self.checks.append(dict(group=group, check=name, violations=int(bad), expected=int(expected),
                                status="PASS" if int(bad) == int(expected) else "FAIL", detail=detail))


def validate(t: dict, gt: pd.DataFrame, as_of: str = C.AS_OF_DATE) -> dict:
    R = Report(); asof = pd.Timestamp(as_of)
    dt = Mx.to_dt
    ev, enr, coh, crs, hist = t["activity_events"], t["enrollments"], t["cohorts"], t["courses"], t["enrollment_status_history"]
    att, asm, ci, rules, out, lrn = t["attempts"], t["assessments"], t["content_items"], t["completion_rules"], t["course_outcomes"], t["learners"]
    gtinj = gt[gt.label_class == "injected_anomaly"]
    gset = lambda it: set(gtinj[gtinj.issue_type == it].entity_id)

    # 1. schema + PK + id formats
    for name, df in t.items():
        R.add("schema", f"{name}: columns match data dictionary", int(list(df.columns) != schema.columns(name)))
        pk = schema.TABLES[name]["pk"]
        R.add("primary_key", f"{name}.{pk} unique & non-null", int(df[pk].duplicated().sum() + df[pk].isna().sum()))
        R.add("id_format", f"{name}.{pk} matches {ID_RE.get(name, 'n/a')}", int((~df[pk].astype(str).str.match(ID_RE[name])).sum()) if name in ID_RE else 0)
    R.add("id_format", "enrollment_id == 'ENR-'+learner_id+'-'+course_id", int((enr.enrollment_id != "ENR-" + enr.learner_id + "-" + enr.course_id).sum()))
    R.add("id_format", "event_id prefix == EVT-+enrollment_id", int((ev.event_id.str.rsplit("-", n=1).str[0] != "EVT-" + ev.enrollment_id.astype(str)).sum()))
    R.add("id_format", "history_id prefix / outcome_id == OUT-+enrollment_id", int((out.outcome_id != "OUT-" + out.enrollment_id).sum()))

    # 2. foreign keys
    for (ct, cc, pt, pc, nullable, card) in schema.FKS:
        child = t[ct][cc]; parent = set(t[pt][pc])
        bad = child.notna() & ~child.isin(parent)
        if not nullable:
            bad = bad | child.isna()
        exp = 0
        if (ct, cc) == ("activity_events", "enrollment_id"):
            exp = len(gset("unenrolled_activity"))
            R.add("foreign_key", "activity_events orphan event_ids == labelled unenrolled_activity set", int(set(ev.event_id[bad]) != gset("unenrolled_activity")))
        R.add("foreign_key", f"{ct}.{cc} -> {pt}.{pc}", int(bad.sum()), exp, card)
    R.add("foreign_key", "enrollment.course_id == cohort.course_id", int((enr.course_id != enr.cohort_id.map(dict(zip(coh.cohort_id, coh.course_id)))).sum()))
    R.add("foreign_key", "assessment.course_id == content_item.course_id", int((asm.course_id != asm.content_id.map(dict(zip(ci.content_id, ci.course_id)))).sum()))
    R.add("foreign_key", "attempt.assessment.course == attempt.enrollment.course",
          int((att.assessment_id.map(dict(zip(asm.assessment_id, asm.course_id))) != att.enrollment_id.map(dict(zip(enr.enrollment_id, enr.course_id)))).sum()))
    R.add("foreign_key", "child content parent is a module of the same course", int((ci[ci.parent_content_id.notna()].parent_content_id.map(dict(zip(ci.content_id, ci.course_id))) != ci[ci.parent_content_id.notna()].course_id).sum()))
    R.add("cardinality", "enrollment unique per (learner, course)", int(enr.duplicated(["learner_id", "course_id"]).sum()))
    R.add("cardinality", "outcome 1:1 with enrollment", int(len(set(enr.enrollment_id) ^ set(out.enrollment_id))))
    R.add("cardinality", "assessment 1:1 with assessment content item", int(asm.content_id.duplicated().sum()))
    R.add("cardinality", "no enrollment/cohort for draft courses", int(crs[crs.course_status == "draft"].course_id.isin(set(coh.course_id) | set(enr.course_id)).sum()))

    # 3. enums / nulls
    for tb, cols in ENUMS.items():
        for c, allowed in cols.items():
            R.add("enum", f"{tb}.{c} in allowed set", int((~t[tb][c].isin(allowed)).sum()))
    R.add("enum", "history.from_status null only on first row", int(((hist.from_status.isna()) != (hist.history_id.str.endswith("-01"))).sum()))
    R.add("enum", "content module only at level 1", int(((ci.content_type == "module") != (ci.hierarchy_level == 1)).sum()))
    R.add("enum", "required fields non-null", sum(int(t[tb][f["name"]].isna().sum()) for tb, sp in schema.TABLES.items() for f in sp["fields"] if f["required"]))

    # 4. date ordering
    s, e_, a_ = pd.to_datetime(coh.start_date), pd.to_datetime(coh.end_date), pd.to_datetime(coh.access_end_date)
    dur = coh.course_id.map(dict(zip(crs.course_id, crs.duration_weeks)))
    R.add("date_order", "cohort start < end < access_end; end = start+dur*7-1; access = end+14", int((~((s < e_) & (e_ < a_) & ((e_ - s).dt.days + 1 == dur * 7) & ((a_ - e_).dt.days == C.GRACE_DAYS))).sum()))
    R.add("date_order", "cohort start is Monday", int((s.dt.dayofweek != 0).sum()))
    R.add("date_order", "cohort_status consistent with as_of", int(((a_ < asof) != (coh.cohort_status == "closed")).sum()))
    en_t = dt(enr.enrolled_at)
    R.add("date_order", "enrolled_at >= learner.signup_date + 1 day", int((en_t.dt.floor("D") < pd.to_datetime(enr.learner_id.map(dict(zip(lrn.learner_id, lrn.signup_date))), format="%Y-%m-%d") + pd.Timedelta(days=1)).sum()))
    cs = pd.to_datetime(enr.cohort_id.map(dict(zip(coh.cohort_id, coh.start_date))))
    R.add("date_order", "enrolled_at <= cohort start + 10 days", int((en_t.dt.floor("D") > cs + pd.Timedelta(days=10)).sum()))
    ht = dt(hist.changed_at)
    R.add("date_order", "history changed_at non-decreasing per enrollment and <= as_of", int((hist.assign(_t=ht).groupby("enrollment_id")._t.diff() < pd.Timedelta(0)).sum() + (ht > asof + pd.Timedelta(days=1)).sum()))
    R.add("date_order", "ingested_at_utc >= event_time_utc and <= as_of end", int((dt(ev.ingested_at_utc) < dt(ev.event_time_utc)).sum() + (dt(ev.ingested_at_utc) > asof + pd.Timedelta(days=1)).sum()))
    st_, sb_ = dt(att.started_at), dt(att.submitted_at)
    R.add("date_order", "attempt submitted_at >= started_at", int((sb_ < st_).sum()))
    R.add("date_order", "attempt started_at > enrolled_at", int((st_ <= att.enrollment_id.map(dict(zip(enr.enrollment_id, en_t)))).sum()))
    # rule versions contiguous + non overlapping
    bad_r = 0
    for _, g in rules.sort_values(["course_id", "rule_version"]).groupby("course_id"):
        if len(g) == 2:
            bad_r += int(pd.Timestamp(g.effective_to.iat[0]) + pd.Timedelta(days=1) != pd.Timestamp(g.effective_from.iat[1]))
        bad_r += int(g.effective_to.iloc[-1] is not None and not pd.isna(g.effective_to.iloc[-1]))
    R.add("date_order", "completion rule versions are contiguous, last is open-ended", bad_r)

    # 5/6. valid events (dedup + enrolled), duplicates, timezone labels - slim, mask-based (2M rows)
    t_ev = dt(ev.event_time_utc); ing = dt(ev.ingested_at_utc)
    order = pd.DataFrame({"event_id": ev.event_id, "k": ev[C.DEDUP_KEY], "_ing": ing}).sort_values(["_ing", "event_id"], kind="mergesort")
    dup_ids = set(order.event_id[order.duplicated("k", keep="first")])
    keep_mask = ~ev.event_id.isin(dup_ids).to_numpy()
    n_valid = int(keep_mask.sum()); del order
    enrolled = ev.enrollment_id.isin(set(enr.enrollment_id)).to_numpy()
    vm = keep_mask & enrolled
    ven = ev.loc[vm, ["event_id", "enrollment_id", "event_type", "content_id", "attempt_id"]].assign(_t=t_ev[vm].to_numpy())
    en_series = pd.Series(en_t.to_numpy(), index=enr.enrollment_id)
    R.add("date_order", "valid events occur after enrolled_at", int((ven._t.to_numpy() <= Mx.look(ven.enrollment_id, en_series).to_numpy()).sum()))
    ev_coh = Mx.look(ven.enrollment_id, enr.set_index("enrollment_id").cohort_id)
    cstart = Mx.look(ev_coh.astype("category"), pd.to_datetime(coh.set_index("cohort_id").start_date)); cacc = Mx.look(ev_coh.astype("category"), pd.to_datetime(coh.set_index("cohort_id").access_end_date))
    loc_all = (t_ev + pd.to_timedelta(ev.client_tz_offset_min.astype("int64"), unit="m")).dt.floor("D")
    loc_v = loc_all[vm]
    R.add("date_order", "valid events inside [cohort start, access_end] (local date)", int(((loc_v.to_numpy() < cstart.to_numpy()) | (loc_v.to_numpy() > cacc.to_numpy())).sum()))
    R.add("duplicates", "event_id unique", int(ev.event_id.duplicated().sum()))
    R.add("duplicates", "extra rows sharing client_event_key == labelled duplicate_event", int(len(dup_ids) != len(gset("duplicate_event"))))
    R.add("duplicates", "dedup removes exactly the labelled duplicates (kept rows = total - labelled)", int(n_valid != len(ev) - len(gset("duplicate_event"))))
    R.add("duplicates", "removed rows are exactly the labelled duplicate event_ids", int(dup_ids != gset("duplicate_event")))
    R.add("duplicates", "client_event_key never shared across different enrollments", int(ev.groupby(C.DEDUP_KEY).enrollment_id.nunique().gt(1).sum()))
    bad_tz = loc_all.to_numpy() != pd.to_datetime(ev.reported_activity_date).to_numpy()
    R.add("anomaly_reconciliation", "reported_activity_date != local date  <=>  labelled timezone_day_shift", int(set(ev.event_id[bad_tz]) != gset("timezone_day_shift")))
    del t_ev, ing, loc_all, loc_v

    # 7. arithmetic reconciliation
    aw = asm.groupby("course_id").weight_pct.sum()
    R.add("arithmetic", "assessment weights per course sum to 100", int((aw != 100).sum()))
    R.add("arithmetic", "pass_score = ceil(max*pass_pct) within (0, max]", int(((asm.pass_score <= 0) | (asm.pass_score > asm.max_score)).sum()))
    sub = att[att.attempt_status == "submitted"]
    R.add("arithmetic", "percent_score = round(score/max*100, 2)", int((np.abs(sub.percent_score - (sub.score / sub.max_score * 100).round(2)) > 1e-6).sum()))
    ps = sub.assessment_id.map(dict(zip(asm.assessment_id, asm.pass_score)))
    R.add("arithmetic", "attempt.passed == score >= pass_score", int((sub.passed != (sub.score >= ps)).sum()))
    R.add("arithmetic", "attempt.max_score == assessment.max_score", int((att.max_score != att.assessment_id.map(dict(zip(asm.assessment_id, asm.max_score)))).sum()))
    R.add("arithmetic", "abandoned attempts have no score/submission; submitted have both", int(((att.attempt_status == "abandoned") != att.score.isna()).sum() + (att.score.isna() != att.submitted_at.isna()).sum()))
    R.add("arithmetic", "duration_sec = submitted_at - started_at", int((sub.duration_sec != (dt(sub.submitted_at) - dt(sub.started_at)).dt.total_seconds()).sum()))
    g = att.groupby(["enrollment_id", "assessment_id"]).attempt_no.agg(["max", "count", "nunique"])
    R.add("arithmetic", "attempt_no contiguous 1..n per (enrollment, assessment)", int(((g["max"] != g["count"]) | (g["nunique"] != g["count"])).sum()))
    mxa = g.reset_index().assessment_id.map(dict(zip(asm.assessment_id, asm.max_attempts)))
    R.add("arithmetic", "attempts per (enrollment, assessment) <= max_attempts", int((g["max"].to_numpy() > mxa.to_numpy()).sum()))
    late = (dt(sub.submitted_at) >= (pd.to_datetime(sub.enrollment_id.map(dict(zip(enr.enrollment_id, cs)))) + pd.to_timedelta(sub.assessment_id.map(dict(zip(asm.assessment_id, asm.due_offset_days))) + 1, unit="D")))
    R.add("arithmetic", "is_late == submitted after due date end", int((sub.is_late != late).sum()))
    # events <-> attempts
    estart = ven[ven.event_type == "assessment_start"]; esub = ven[ven.event_type == "assessment_submit"]
    R.add("arithmetic", "assessment_start events == attempts; assessment_submit events == submitted attempts",
          int(set(estart.attempt_id) != set(att.attempt_id)) + int(set(esub.attempt_id) != set(sub.attempt_id)))
    # outcomes recomputed independently
    o = out.set_index("enrollment_id")
    R.add("arithmetic", "outcome.total_attempts == attempts rows", int((o.total_attempts != att.groupby("enrollment_id").size().reindex(o.index).fillna(0)).sum()))
    R.add("arithmetic", "outcome.valid_event_count == deduped enrolled events", int((o.valid_event_count != ven.groupby("enrollment_id").size().reindex(o.index).fillna(0)).sum()))
    cc = ven[ven.event_type.isin(C.COMPLETION_EVENT_TYPES)].drop_duplicates(["enrollment_id", "content_id"]).groupby("enrollment_id").size().reindex(o.index).fillna(0)
    R.add("arithmetic", "outcome.required_content_items_completed == distinct completion events", int((o.required_content_items_completed != cc).sum()))
    rq = ci[ci.is_required & ci.content_type.isin(["video", "reading"])].groupby("course_id").size()
    R.add("arithmetic", "outcome.required_content_items_total == required video/reading items", int((o.required_content_items_total != o.course_id.map(rq)).sum()))
    R.add("arithmetic", "content_completion_pct = completed/total*100", int((np.abs(o.content_completion_pct - (o.required_content_items_completed / o.required_content_items_total * 100).round(2)) > 1e-6).sum()))
    best = sub.assign(pct=sub.score / sub.max_score * 100).groupby(["enrollment_id", "assessment_id"]).pct.max().reset_index()
    best["w"] = best.assessment_id.map(dict(zip(asm.assessment_id, asm.weight_pct)))
    ws = (best.pct * best.w / 100).groupby(best.enrollment_id).sum().reindex(o.index).fillna(0)
    R.add("arithmetic", "weighted_score_pct = sum(weight*best_percent)/100", int((np.abs(o.weighted_score_pct - ws.round(2)) > 0.011).sum()))
    reqa = asm[asm.is_required]
    pa = sub[sub.passed.fillna(False) & sub.assessment_id.isin(reqa.assessment_id)].drop_duplicates(["enrollment_id", "assessment_id"]).groupby("enrollment_id").size().reindex(o.index).fillna(0)
    R.add("arithmetic", "required_assessments_passed recomputed", int((o.required_assessments_passed != pa).sum()))
    R.add("arithmetic", "required_assessments_total == required assessments of course", int((o.required_assessments_total != o.course_id.map(reqa.groupby("course_id").size())).sum()))

    # 8. completion follows CompletionRule (rule effective at cohort start)
    rr = rules.assign(frm=pd.to_datetime(rules.effective_from), to=pd.to_datetime(rules.effective_to).fillna(pd.Timestamp("2100-01-01")))
    oo = out.assign(start=pd.to_datetime(out.cohort_id.map(dict(zip(coh.cohort_id, coh.start_date))))).merge(rr, on="rule_id", suffixes=("", "_r"))
    R.add("completion_rules", "outcome.rule_id is effective at cohort start_date and belongs to the course",
          int(((oo.start < oo.frm) | (oo.start > oo.to) | (oo.course_id != oo.course_id_r)).sum()) + int(len(out) - len(oo)))
    need = np.ceil(oo.min_required_content_pct * oo.required_content_items_total / 100 - 1e-9)
    exp_done = (oo.required_content_items_completed >= need) & (oo.required_assessments_passed == oo.required_assessments_total) & (oo.weighted_score_pct + 0.011 >= oo.min_weighted_score_pct)
    R.add("completion_rules", "completion_status=='completed' <=> all three rule thresholds satisfied", int((exp_done != (oo.completion_status == "completed")).sum()))
    R.add("completion_rules", "completed_at/date/days_to_complete present iff completed", int(((out.completion_status == "completed") != out.completed_at.notna()).sum() + (out.completed_at.notna() != out.days_to_complete.notna()).sum()))

    # 9. lifecycle
    h = hist.assign(_t=ht).sort_values(["enrollment_id", "history_id"], kind="mergesort")
    h["prev"] = h.groupby("enrollment_id").to_status.shift(1)
    nn = lambda x: None if pd.isna(x) else x
    bad_tr = sum(1 for p_, n_, f_ in zip(h.prev, h.to_status, h.from_status)
                 if n_ not in C.LEGAL_TRANSITIONS.get(nn(p_), set()) or nn(p_) != nn(f_))
    R.add("lifecycle", "every history transition is legal and from_status == previous to_status", bad_tr)
    R.add("lifecycle", "no transition after a terminal state", int(h.prev.isin(list(C.TERMINAL)).sum()))
    R.add("lifecycle", "every enrollment starts with 'enrolled' at enrolled_at", int(((h.groupby("enrollment_id").to_status.first() != "enrolled") | (h.groupby("enrollment_id")._t.first().to_numpy() != en_t.set_axis(enr.enrollment_id).reindex(h.groupby("enrollment_id").to_status.first().index).to_numpy())).sum()))
    last = h.groupby("enrollment_id").tail(1).set_index("enrollment_id").reindex(enr.enrollment_id)
    R.add("lifecycle", "enrollment.current_status/status_updated_at == latest history row", int((last.to_status.to_numpy() != enr.current_status.to_numpy()).sum() + (last.changed_at.to_numpy() != enr.status_updated_at.to_numpy()).sum()))
    first_act = ven.groupby("enrollment_id")._t.min()
    act_rows = h[h.to_status == "active"].set_index("enrollment_id")._t
    R.add("lifecycle", "'active' transition time == first valid event time", int((act_rows.reindex(first_act.index).to_numpy() != first_act.to_numpy()).sum()) if False else int((act_rows != first_act.reindex(act_rows.index)).sum()))
    R.add("lifecycle", "terminal statuses only after as_of-valid times", int((ht > asof + pd.Timedelta(days=1)).sum()))
    mism_status = set(enr.enrollment_id[(enr.current_status == "completed") != (o.completion_status.reindex(enr.enrollment_id).to_numpy() == "completed")])
    comp_t = h[h.to_status == "completed"].set_index("enrollment_id")._t
    out_t = dt(out.completed_at).set_axis(out.enrollment_id)
    mism_time = set(comp_t.index[(comp_t != out_t.reindex(comp_t.index)) & out_t.reindex(comp_t.index).notna()])
    R.add("anomaly_reconciliation", "history-vs-rule completion mismatches == labelled completion_before_required_assessment",
          int((mism_status | mism_time) != gset("completion_before_required_assessment")))

    # 10. label hygiene
    forbidden = {"issue_type", "ground_truth", "label_class", "is_dormant", "diligence", "dormant"}
    R.add("ground_truth", "no ground-truth/latent column leaks into input tables", sum(len(forbidden & set(df.columns)) for df in t.values()))
    R.add("ground_truth", "every ground-truth entity_id exists in the input data", int(
        (~gtinj[gtinj.entity_type == "ActivityEvent"].entity_id.isin(ev.event_id)).sum() + (~gtinj[gtinj.entity_type == "Enrollment"].entity_id.isin(enr.enrollment_id)).sum()))

    # coverage report
    inact = set(gt[gt.issue_type == "inactive_learner"].entity_id)
    coverage = {
        "normal_paths": dict(completed=int((out.completion_status == "completed").sum()), in_progress=int((out.completion_status == "in_progress").sum()),
                             not_completed=int((out.completion_status == "not_completed").sum())),
        "enrollment_status": enr.current_status.value_counts().to_dict(),
        "boundary": dict(repeated_attempts=int((att.attempt_no > 1).sum()), attempts_at_max=int((g["max"].to_numpy() >= mxa.to_numpy()).sum()),
                         late_submissions=int(att.is_late.sum()), late_joiners=int((en_t.dt.floor("D") > cs).sum()),
                         pre_start_enrollments=int((en_t.dt.floor("D") < cs).sum()), two_rule_versions_courses=int(rules.course_id.duplicated().sum()),
                         courses_without_cohorts=int((~crs.course_id.isin(coh.course_id)).sum())),
        "failure_exception": dict(abandoned_attempts=int((att.attempt_status == "abandoned").sum()), failed_attempts=int((sub.passed == False).sum()),  # noqa: E712
                                  dropped=int((enr.current_status == "dropped").sum()), expired=int((enr.current_status == "expired").sum()),
                                  inactive_learners=len(inact), learners_with_zero_enrollments=int((~lrn.learner_id.isin(enr.learner_id)).sum())),
        "event_mix": dict(offline_sync=int((ev.source == "offline_sync").sum()), late_arriving_gt72h=int((gt.issue_type == "late_arriving_event").sum()),
                          by_type=ev.event_type.value_counts().to_dict(), by_device=ev.device_type.value_counts().to_dict()),
        "injected_anomalies": {k: len(gset(k)) for k in C.ISSUE_TYPES if k not in ("inactive_learner", "late_arriving_event")},
    }
    failed = [c for c in R.checks if c["status"] == "FAIL"]
    return dict(overall="PASS" if not failed else "FAIL", n_checks=len(R.checks), n_failed=len(failed), checks=R.checks, coverage=coverage)


def to_markdown(rep: dict) -> str:
    out = [f"# Validation summary - {rep['overall']}", "", f"{rep['n_checks']} checks, {rep['n_failed']} failed. "
           "`violations` is the number of offending rows found; `expected` is the number of *labelled* violations (ground truth).", "",
           "| group | check | violations | expected | status |", "|---|---|---:|---:|---|"]
    for c in rep["checks"]:
        out.append(f"| {c['group']} | {c['check']} | {c['violations']} | {c['expected']} | {c['status']} |")
    out += ["", "## Coverage", "", "```json", __import__("json").dumps(rep["coverage"], indent=2, default=str), "```", ""]
    return "\n".join(out)
