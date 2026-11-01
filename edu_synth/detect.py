"""Consumer-side anomaly detectors. Use ONLY input tables (never ground truth); scored afterwards against ground truth."""
from __future__ import annotations

import pandas as pd

from . import metrics as Mx


def detect(t: dict) -> dict:
    ev, enr, hist, att, asm = t["activity_events"], t["enrollments"], t["enrollment_status_history"], t["attempts"], t["assessments"]
    srt = ev[["event_id", "client_event_key", "ingested_at_utc"]].sort_values(["ingested_at_utc", "event_id"], kind="mergesort")
    dup = set(srt[srt.duplicated("client_event_key", keep="first")].event_id)
    unen = set(ev.event_id[~ev.enrollment_id.isin(enr.enrollment_id)])
    local = (Mx.to_dt(ev.event_time_utc) + pd.to_timedelta(ev.client_tz_offset_min.astype("int64"), unit="m")).dt.floor("D")
    tz = set(ev.event_id[(local != pd.to_datetime(ev.reported_activity_date)).to_numpy()])
    # completion recorded before every required assessment had been passed
    comp = hist[hist.to_status == "completed"][["enrollment_id", "changed_at"]]
    req = asm[asm.is_required][["assessment_id", "course_id"]]
    need = comp.assign(course_id=comp.enrollment_id.map(dict(zip(enr.enrollment_id, enr.course_id)))).merge(
        req.groupby("course_id").size().rename("req_total").reset_index(), on="course_id", how="left").fillna({"req_total": 0})
    ok = att[(att.passed == True) & att.assessment_id.isin(req.assessment_id)][["enrollment_id", "assessment_id", "submitted_at"]]  # noqa: E712
    ok = ok.merge(comp, on="enrollment_id")
    ok = ok[ok.submitted_at <= ok.changed_at]
    have = ok.groupby("enrollment_id").assessment_id.nunique()
    need["passed_by_completion"] = need.enrollment_id.map(have).fillna(0).astype(int)
    comp_bad = set(need.enrollment_id[need.passed_by_completion < need.req_total])
    return {"duplicate_event": dup, "unenrolled_activity": unen, "timezone_day_shift": tz,
            "completion_before_required_assessment": comp_bad}


def score(detected: dict, gt: pd.DataFrame) -> dict:
    rep = {}
    for it, det in detected.items():
        truth = set(gt[(gt.issue_type == it) & (gt.label_class == "injected_anomaly")].entity_id)
        tp = len(det & truth); fp = len(det - truth); fn = len(truth - det)
        p = tp / (tp + fp) if tp + fp else 1.0; r_ = tp / (tp + fn) if tp + fn else 1.0
        rep[it] = dict(truth=len(truth), detected=len(det), true_positive=tp, false_positive=fp, false_negative=fn,
                       precision=round(p, 4), recall=round(r_, 4), f1=round(2 * p * r_ / (p + r_), 4) if p + r_ else 0.0)
    return rep
