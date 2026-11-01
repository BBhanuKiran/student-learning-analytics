"""Step 8/Acceptance: metric definitions + implementation (dedup, enrolment validity, local-day weeks, fixed windows)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as C

METRIC_DEFINITIONS = {
    "valid_event": "An ActivityEvent that (1) is the earliest-ingested row for its client_event_key (deduplication), "
                   "(2) belongs to an existing enrollment_id (foreign key valid) and (3) has a learner-local date inside "
                   "[cohort.start_date, cohort.access_end_date].",
    "local_date": "date(event_time_utc + client_tz_offset_min minutes). reported_activity_date is NOT used (known to be wrong for some rows).",
    "cohort_week_index": "floor((local_date - cohort.start_date) / 7 days). Week 0 starts on the cohort's start Monday. "
                         "All cohort comparisons use cohort-relative weeks, never calendar weeks.",
    "enrolled_to_date": "Enrollments of the cohort whose enrolled_at date is <= last day of the week (late joiners count from the week they join).",
    "weekly_active_learners": "Distinct learner_id with >= 1 valid_event whose cohort_week_index = w.",
    "weekly_active_rate": "weekly_active_learners / enrolled_to_date.",
    "events_per_active_learner": "valid_events / weekly_active_learners (this is the metric duplicate events inflate).",
    "content_completions": "Distinct (enrollment, content) pairs whose FIRST completion event (video_complete | content_complete) falls in week w.",
    "assessment_submissions": "valid assessment_submit events in week w (every submission, including repeated attempts).",
    "cumulative_completion_rate": "Enrollments with CourseOutcome.completion_status = completed and completed_date_local in a week <= w, divided by enrolled_to_date. "
                                  "Completion follows the CompletionRule effective at cohort start (content %, all required assessments passed, weighted score %).",
    "is_complete_week": "True when the week's last day <= as_of date; incomplete weeks are excluded from comparisons.",
    "cohort_comparison_window": f"First {C.COMPARISON_WINDOW_WEEKS} cohort weeks (weeks 0-{C.COMPARISON_WINDOW_WEEKS - 1}); only cohorts with all of them complete are compared. "
                                "Every cohort therefore has an identical-length window regardless of calendar start or course length.",
    "completion_rate_at_access_end": "completed / enrollments for cohorts whose access window has closed; compare only within the same duration_weeks.",
}


def to_dt(s):
    if pd.api.types.is_datetime64_any_dtype(s):
        return s
    return pd.to_datetime(s, format="%Y-%m-%dT%H:%M:%SZ")


def look(s: pd.Series, mapping: pd.Series) -> pd.Series:
    """Memory-friendly dict-style lookup that works on categorical (large) and plain columns."""
    if isinstance(s.dtype, pd.CategoricalDtype):
        idx = pd.Index(mapping.reindex(s.cat.categories).to_numpy())
        return pd.Series(idx.take(s.cat.codes.to_numpy(), allow_fill=True), index=s.index)
    return s.map(mapping)


def valid_events(events: pd.DataFrame, enrollments: pd.DataFrame, cohorts: pd.DataFrame) -> pd.DataFrame:
    order = pd.DataFrame({"event_id": events.event_id, "k": events[C.DEDUP_KEY], "_ing": to_dt(events.ingested_at_utc)})
    order = order.sort_values(["_ing", "event_id"], kind="mergesort")          # earliest ingest wins; id breaks ties
    keep = order.index[~order.duplicated("k", keep="first")]
    del order
    ev = events.loc[keep, ["event_id", "enrollment_id", "learner_id", "content_id", "event_type", "client_tz_offset_min"]].copy()
    ev["_t"] = to_dt(events.event_time_utc.loc[keep])
    coh_of = look(ev.enrollment_id, enrollments.set_index("enrollment_id").cohort_id)
    ev = ev[coh_of.notna().to_numpy()].copy()                                    # FK validity
    ev["cohort_id"] = pd.Categorical(coh_of[coh_of.notna()].to_numpy())
    ev["local_date"] = (ev._t + pd.to_timedelta(ev.client_tz_offset_min.astype("int64"), unit="m")).dt.floor("D")
    c = cohorts.set_index("cohort_id")
    start = look(ev.cohort_id, pd.to_datetime(c.start_date)); acc = look(ev.cohort_id, pd.to_datetime(c.access_end_date))
    ok = ((ev.local_date >= start) & (ev.local_date <= acc)).to_numpy()
    ev = ev[ok].copy(); start = start[ok]
    ev["week_idx"] = (ev.local_date - start).dt.days // 7
    return ev.drop(columns=["client_tz_offset_min"])


def _grid(cohorts: pd.DataFrame, as_of: str) -> pd.DataFrame:
    c = cohorts[["cohort_id", "course_id", "start_date", "access_end_date"]].copy()
    c["start"] = pd.to_datetime(c.start_date); c["acc"] = pd.to_datetime(c.access_end_date)
    c["nw"] = ((c.acc - c.start).dt.days + 1 + 6) // 7
    g = c.loc[c.index.repeat(c.nw)].reset_index(drop=True)
    g["week_index"] = g.groupby("cohort_id").cumcount()
    g["week_start"] = g.start + pd.to_timedelta(g.week_index * 7, unit="D")
    return g


def weekly_metrics(ev: pd.DataFrame, enrollments: pd.DataFrame, cohorts: pd.DataFrame, outcomes: pd.DataFrame,
                   as_of: str = C.AS_OF_DATE) -> pd.DataFrame:
    asof = pd.Timestamp(as_of)
    g = _grid(cohorts, as_of)
    st = g.drop_duplicates("cohort_id").set_index("cohort_id").start
    en = enrollments[["cohort_id", "enrolled_at"]].copy()
    en["ed"] = to_dt(en.enrolled_at).dt.floor("D")
    en["week_index"] = np.maximum((en.ed - en.cohort_id.map(st)).dt.days // 7, 0)
    n_en = en.groupby(["cohort_id", "week_index"]).size().rename("new_enrolled").reset_index()
    g = g.merge(n_en, how="left", on=["cohort_id", "week_index"]).fillna({"new_enrolled": 0})
    g["enrolled_to_date"] = g.groupby("cohort_id").new_enrolled.cumsum().astype(int)

    act = ev.groupby(["cohort_id", "week_idx"]).agg(weekly_active_learners=("learner_id", "nunique"), valid_events=("event_id", "size"))
    act.index.names = ["cohort_id", "week_index"]
    g = g.merge(act.reset_index(), how="left", on=["cohort_id", "week_index"])
    cc = ev[ev.event_type.isin(C.COMPLETION_EVENT_TYPES)].sort_values("_t", kind="mergesort").drop_duplicates(["enrollment_id", "content_id"])
    ccn = cc.groupby(["cohort_id", "week_idx"]).size().rename("content_completions"); ccn.index.names = ["cohort_id", "week_index"]
    asn = ev[ev.event_type == "assessment_submit"].groupby(["cohort_id", "week_idx"]).size().rename("assessment_submissions"); asn.index.names = ["cohort_id", "week_index"]
    g = g.merge(ccn.reset_index(), how="left", on=["cohort_id", "week_index"]).merge(asn.reset_index(), how="left", on=["cohort_id", "week_index"])
    done = outcomes[outcomes.completion_status == "completed"].copy()
    done["w"] = ((pd.to_datetime(done.completed_date_local) - done.cohort_id.map(st)).dt.days // 7)
    dn = done.groupby(["cohort_id", "w"]).size().rename("new_completions").reset_index().rename(columns={"w": "week_index"})
    g = g.merge(dn, how="left", on=["cohort_id", "week_index"])
    for col in ["weekly_active_learners", "valid_events", "content_completions", "assessment_submissions", "new_completions"]:
        g[col] = g[col].fillna(0).astype(int)
    g["cumulative_completions"] = g.groupby("cohort_id").new_completions.cumsum()
    g = g[g.week_start <= asof].copy()
    g["is_complete_week"] = (g.week_start + pd.Timedelta(days=6)) <= asof
    g["weekly_active_rate"] = (g.weekly_active_learners / g.enrolled_to_date.replace(0, np.nan)).round(4)
    g["events_per_active_learner"] = (g.valid_events / g.weekly_active_learners.replace(0, np.nan)).round(3)
    g["cumulative_completion_rate"] = (g.cumulative_completions / g.enrolled_to_date.replace(0, np.nan)).round(4)
    g["week_start_date"] = g.week_start.dt.strftime("%Y-%m-%d")
    cols = ["cohort_id", "course_id", "week_index", "week_start_date", "is_complete_week", "enrolled_to_date",
            "weekly_active_learners", "weekly_active_rate", "valid_events", "events_per_active_learner",
            "content_completions", "assessment_submissions", "cumulative_completions", "cumulative_completion_rate"]
    return g[cols].sort_values(["cohort_id", "week_index"]).reset_index(drop=True)


def naive_weekly(events, enrollments, cohorts) -> pd.DataFrame:
    """What a pipeline WITHOUT dedup/FK checks and trusting reported_activity_date would publish."""
    c = cohorts.set_index("cohort_id"); start = pd.to_datetime(c.start_date)
    ev = events[["enrollment_id", "learner_id", "reported_activity_date"]].copy()   # already slim
    ev["cohort_id"] = pd.Categorical(look(ev.enrollment_id, enrollments.set_index("enrollment_id").cohort_id).to_numpy())
    ev = ev[ev.cohort_id.notna()]
    ev["week_index"] = (pd.to_datetime(ev.reported_activity_date) - look(ev.cohort_id, start)).dt.days // 7
    out = ev.groupby(["cohort_id", "week_index"]).agg(naive_active_learners=("learner_id", "nunique"), naive_events=("learner_id", "size")).reset_index()
    return out


def anomaly_impact(events, enrollments, cohorts, weekly: pd.DataFrame) -> pd.DataFrame:
    nv = naive_weekly(events, enrollments, cohorts)
    m = weekly.merge(nv, how="left", on=["cohort_id", "week_index"]).fillna({"naive_active_learners": 0, "naive_events": 0})
    m["event_inflation_pct"] = ((m.naive_events / m.valid_events.replace(0, np.nan) - 1) * 100).round(2)
    m["active_learner_delta"] = (m.naive_active_learners - m.weekly_active_learners).astype(int)
    return m[["cohort_id", "week_index", "valid_events", "naive_events", "event_inflation_pct",
              "weekly_active_learners", "naive_active_learners", "active_learner_delta"]]


def cohort_comparison(weekly, cohorts, courses, outcomes, W: int = C.COMPARISON_WINDOW_WEEKS) -> pd.DataFrame:
    ok = weekly[(weekly.week_index == W - 1) & weekly.is_complete_week].cohort_id
    w = weekly[weekly.cohort_id.isin(ok) & (weekly.week_index < W)]
    def at(k): return w[w.week_index == k].set_index("cohort_id").weekly_active_rate
    agg = w.groupby("cohort_id").agg(avg_weekly_active_rate=("weekly_active_rate", "mean"),
                                    avg_events_per_active_learner=("events_per_active_learner", "mean"),
                                    content_completions=("content_completions", "sum"),
                                    assessment_submissions=("assessment_submissions", "sum"),
                                    enrolled_by_window_end=("enrolled_to_date", "max"))
    agg["active_rate_week1"] = at(0); agg["active_rate_week4"] = at(3); agg["active_rate_week8"] = at(W - 1)
    agg["retention_week8_vs_week1"] = (agg.active_rate_week8 / agg.active_rate_week1.replace(0, np.nan)).round(4)
    oc = outcomes.groupby("cohort_id").agg(n_enrollments=("outcome_id", "size"),
                                           n_completed=("completion_status", lambda s: int((s == "completed").sum())))
    agg = agg.join(oc)
    ch = cohorts.set_index("cohort_id")
    cr = courses.set_index("course_id")
    agg["course_id"] = ch.course_id; agg["start_date"] = ch.start_date; agg["delivery_mode"] = ch.delivery_mode
    agg["cohort_status"] = ch.cohort_status; agg["duration_weeks"] = ch.course_id.map(cr.duration_weeks); agg["level"] = ch.course_id.map(cr.level)
    agg["completion_rate_at_access_end"] = np.where(agg.cohort_status == "closed", (agg.n_completed / agg.n_enrollments).round(4), np.nan)
    agg["window_weeks"] = W
    for c_ in ["avg_weekly_active_rate", "avg_events_per_active_learner"]:
        agg[c_] = agg[c_].round(4)
    return agg.reset_index()


def kpi_summary(weekly, comparison, outcomes, enrollments) -> dict:
    d = {"enrollments": int(len(enrollments)),
         "completion_rate_all": round(float((outcomes.completion_status == "completed").mean()), 4),
         "outcome_status_share": {k: round(v, 4) for k, v in outcomes.completion_status.value_counts(normalize=True).items()},
         "engagement_band_share": {k: round(v, 4) for k, v in outcomes.engagement_band.value_counts(normalize=True).items()},
         "cohorts_in_comparison": int(len(comparison)), "window_weeks": C.COMPARISON_WINDOW_WEEKS}
    if len(comparison):
        d["mean_avg_weekly_active_rate"] = round(float(comparison.avg_weekly_active_rate.mean()), 4)
        d["by_delivery_mode"] = {k: round(float(v), 4) for k, v in comparison.groupby("delivery_mode").avg_weekly_active_rate.mean().items()}
        closed = comparison.dropna(subset=["completion_rate_at_access_end"])
        d["mean_completion_rate_closed_cohorts"] = round(float(closed.completion_rate_at_access_end.mean()), 4) if len(closed) else None
    return d
