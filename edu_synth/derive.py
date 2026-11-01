"""Step 6: derived values. CourseOutcome + EnrollmentStatusHistory are computed FROM source records
(events, attempts, CompletionRule) - never drawn independently."""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as C
from .simulate import ASOF_DAY, ASOF_END_S, days

INF = np.iinfo(np.int64).max


def derive(sim: dict, cat: dict, seed: int):
    r = C.rng(seed, "derive")
    enr, ev, att, items = sim["enr"], sim["events"], sim["attempts"], sim["items"]
    asms, rules, courses = cat["assessments"], cat["completion_rules"], cat["courses"]
    E, nC = len(enr), len(courses)
    ec = enr.ci.to_numpy()

    # ---- effective CompletionRule per enrolment (effective-dated, resolved by cohort start_date)
    rules = rules.assign(ci=rules.course_id.str[4:].astype(int) - 1, frm=days(rules.effective_from))
    v1 = rules[rules.rule_version == 1].set_index("ci").sort_index()
    v2 = rules[rules.rule_version == 2].set_index("ci")
    use2 = np.zeros(E, bool)
    if len(v2):
        v2f = np.full(nC, INF); v2f[v2.index.to_numpy()] = v2.frm.to_numpy()
        use2 = enr.start_day.to_numpy() >= v2f[ec]
    def pick(col):
        a = v1[col].reindex(range(nC)).to_numpy()
        if len(v2):
            b = v2[col].reindex(range(nC)).to_numpy()
            a = np.where(np.isnan(b.astype(float)) if b.dtype.kind == "f" else False, a, a)  # placeholder keeps dtype
            return np.where(use2, np.where(pd.isna(b[ec]), a[ec], b[ec]), a[ec])
        return a[ec]
    rule_id = pick("rule_id")
    min_c = pick("min_required_content_pct").astype(float)
    min_w = pick("min_weighted_score_pct").astype(float)

    # ---- required content (video/reading) per course
    i_course = items.course_id.str[4:].astype(int).to_numpy() - 1
    is_learn = items.content_type.isin(["video", "reading"]).to_numpy() & items.is_required.to_numpy()
    req_total = np.bincount(i_course[is_learn], minlength=nC)[ec]
    a_course = asms.course_id.str[4:].astype(int).to_numpy() - 1
    a_req = asms.is_required.to_numpy()
    a_w = asms.weight_pct.to_numpy()
    areq_total = np.bincount(a_course[a_req], minlength=nC)[ec]

    # ---- content condition: time the k-th distinct required item completion occurred
    cc = ev[ev.tcode.isin([C.EVENT_TYPES.index(x) for x in C.COMPLETION_EVENT_TYPES])][["e", "item", "t"]]
    cc = cc.groupby(["e", "item"], as_index=False).t.min().sort_values(["e", "t"], kind="stable")
    cc["rk"] = cc.groupby("e").cumcount() + 1
    done = np.bincount(cc.e.to_numpy(), minlength=E)
    need = np.ceil(min_c * req_total / 100 - 1e-9).astype(int)
    hit = cc[cc.rk.to_numpy() == need[cc.e.to_numpy()]]
    content_at = np.full(E, INF); content_at[hit.e.to_numpy()] = hit.t.to_numpy()

    # ---- assessment conditions
    sub = att[~att.abandoned].copy()
    sub["pct"] = sub.score / sub.max_score * 100
    sub = sub.sort_values(["e", "sub"], kind="stable")
    g = sub.groupby(["e", "ai"]).pct
    sub["run_best"] = g.cummax()
    sub["prev_best"] = sub.groupby(["e", "ai"]).run_best.shift(1).fillna(0.0)
    sub["inc"] = a_w[sub.ai.to_numpy()] * (sub.run_best - sub.prev_best)
    sub["cum"] = sub.groupby("e").inc.cumsum() / 100.0            # weights sum to 100 => percent
    wscore = np.zeros(E); last_cum = sub.groupby("e").cum.last()
    wscore[last_cum.index.to_numpy()] = last_cum.to_numpy()
    ok = sub[sub.cum.to_numpy() >= min_w[sub.e.to_numpy()] - 1e-9]
    w_at = np.full(E, INF); fw = ok.groupby("e")["sub"].min(); w_at[fw.index.to_numpy()] = fw.to_numpy()
    pas = sub[sub.passed.to_numpy() & a_req[sub.ai.to_numpy()]]
    fp = pas.groupby(["e", "ai"], as_index=False)["sub"].min()
    gp = fp.groupby("e")["sub"].agg(["count", "max"])
    req_passed = np.zeros(E, int); req_pass_at = np.full(E, INF)
    req_passed[gp.index.to_numpy()] = gp["count"].to_numpy()
    full = gp[gp["count"].to_numpy() == areq_total[gp.index.to_numpy()]]
    req_pass_at[full.index.to_numpy()] = full["max"].to_numpy()

    completed = (content_at < INF) & (req_pass_at < INF) & (w_at < INF)
    completed_at = np.where(completed, np.maximum(np.maximum(content_at, req_pass_at), w_at), INF)

    # ---- activity facts from valid events
    ee = ev.e.to_numpy()
    n_ev = np.bincount(ee, minlength=E)
    first = np.full(E, INF); last = np.zeros(E, np.int64)
    np.minimum.at(first, ee, ev.t.to_numpy()); np.maximum.at(last, ee, ev.t.to_numpy())
    has_ev = n_ev > 0
    sd = enr.start_day.to_numpy()
    ud = ev[["e", "ldate"]].drop_duplicates()
    active_days = np.bincount(ud.e.to_numpy(), minlength=E)
    uw = pd.DataFrame({"e": ud.e.to_numpy(), "w": (ud.ldate.to_numpy() - sd[ud.e.to_numpy()]) // 7}).drop_duplicates()
    active_weeks = np.bincount(uw.e.to_numpy(), minlength=E)
    dur_w = courses.duration_weeks.to_numpy()[ec]
    weeks_el = np.maximum(1, np.minimum(dur_w, np.ceil((ASOF_DAY - sd + 1) / 7)))
    frac = active_weeks / weeks_el
    band = np.where(~has_ev, "inactive", np.where(frac < .34, "low", np.where(frac < .67, "medium", "high")))

    # ---- lifecycle (explicit state-change records)
    expiry = enr.access_day.to_numpy() * 86400
    dis = sim["disengaged"]
    explicit = r.random(E) < .35
    drop_t = np.where(has_ev, last + np.where(explicit, (r.uniform(.5, 14, E) * 86400).astype(np.int64), 21 * 86400),
                      enr.enr_s.to_numpy() + (r.uniform(1, 30, E) * 86400).astype(np.int64))
    never_drop = ~has_ev & (r.random(E) < .25)
    will_drop = np.where(has_ev, dis, never_drop) & ~completed
    term_t = np.where(will_drop, drop_t, expiry)
    term_s = np.where(will_drop & (drop_t < expiry), "dropped", "expired")
    term_t = np.where(term_s == "dropped", term_t, expiry)
    reason = np.where(term_s == "expired", "access_window_closed",
                      np.where(has_ev & ~explicit, "inactivity_21d", "learner_request"))
    by = np.where(term_s == "expired", "system", np.where(reason == "inactivity_21d", "system", "learner"))
    term_s = np.where(completed, "completed", term_s)
    term_t = np.where(completed, completed_at, term_t)
    reason = np.where(completed, "completion_rule_met", reason)
    by = np.where(completed, "system", by)
    has_term = term_t <= ASOF_END_S

    status = np.where(completed, "completed", np.where(has_term, term_s, "x"))
    outcome_status = np.where(completed, "completed", np.where(has_term, "not_completed", "in_progress"))

    # learner-local date of completion
    from .simulate import tz_offsets
    cmp_ok = completed
    off = np.zeros(E, np.int64)
    off[cmp_ok] = tz_offsets(completed_at[cmp_ok], enr.tz.to_numpy()[cmp_ok])
    cdate = (np.where(cmp_ok, completed_at, 0) + off * 60) // 86400

    out = pd.DataFrame({
        "e": np.arange(E), "rule_id": rule_id, "req_total": req_total, "req_done": np.minimum(done, req_total),
        "areq_total": areq_total, "req_passed": req_passed, "wscore": wscore,
        "total_attempts": np.bincount(att.e.to_numpy(), minlength=E), "n_ev": n_ev, "active_days": active_days,
        "active_weeks": active_weeks, "first": np.where(has_ev, first, 0), "last": last, "has_ev": has_ev,
        "completed": completed, "completed_at": np.where(completed, completed_at, 0), "cdate": cdate,
        "band": band, "outcome_status": outcome_status,
        "content_at": content_at, "req_pass_at": req_pass_at, "w_at": w_at,
        "min_c": min_c, "min_w": min_w})

    # ---- history rows (append-only)
    src_by = enr.source.map({"self_enrol": "learner", "employer_assigned": "admin", "admin_import": "system"}).to_numpy()
    H = []
    allE = np.arange(E)
    H.append(pd.DataFrame({"e": allE, "order": 0, "from": None, "to": "enrolled", "t": enr.enr_s.to_numpy(), "by": src_by, "reason": "enrollment_created"}))
    m = has_ev
    H.append(pd.DataFrame({"e": allE[m], "order": 1, "from": "enrolled", "to": "active", "t": first[m], "by": "system", "reason": "first_activity"}))
    m = has_term
    H.append(pd.DataFrame({"e": allE[m], "order": 2, "from": np.where(has_ev[m], "active", "enrolled"), "to": term_s[m],
                           "t": term_t[m], "by": by[m], "reason": reason[m]}))
    hist = pd.concat(H, ignore_index=True)
    return out, hist
