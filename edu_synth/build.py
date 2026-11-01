"""Orchestrates generation: masters -> transactions -> derived -> labelled anomaly injection -> ground truth."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from . import config as C, masters, simulate as S, derive as D, metrics as Mx, schema
from .timeutil import iso_date, iso_ts

INF = D.INF
ASOF_END = S.ASOF_END_S


def _hash_keys(ids) -> np.ndarray:
    h = pd.util.hash_pandas_object(pd.Series(ids, dtype=object), index=False).to_numpy()
    return np.char.add("CK-", np.char.mod("%016x", h)).astype(object)


def build(sc: C.Scale, seed: int = C.SEED, log=print) -> dict:
    n_dup = round(C.DUP_RATE * sc.events); n_unen = round(C.UNENROLLED_RATE * sc.events)
    n_base = sc.events - n_dup - n_unen
    learners, latent, tzi = masters.make_learners(sc, seed)
    cat = masters.make_catalog(sc, seed)
    enr = S.make_enrollments(sc, seed, learners, latent, tzi, cat)
    log(f"  masters: {len(learners)} learners, {len(cat['courses'])} courses, {len(cat['cohorts'])} cohorts, "
        f"{len(cat['content_items'])} content items, {len(enr)} enrollments")
    sim = S.simulate(enr, cat, sc, seed, n_base)
    enr = sim["enr"]; ev, att, items = sim["events"], sim["attempts"], sim["items"]
    log(f"  simulated: {len(ev)} baseline events ({sim['stats']['core_events']} behavioural + {sim['stats']['filler_events']} filler), {len(att)} attempts")
    out, hist = D.derive(sim, cat, seed)
    E = len(enr)
    r = C.rng(seed, "inject")
    gt = []   # ground-truth rows (dicts of column->value) appended per issue

    # ------------------------------------------------------------------ anomaly: completion before required assessment
    candA = np.nonzero((out.content_at.to_numpy() < INF) & (out.req_pass_at.to_numpy() == INF) & ~out.completed.to_numpy())[0]
    candB = np.nonzero(out.completed.to_numpy() & (out.content_at.to_numpy() + 3600 < out.req_pass_at.to_numpy()) &
                       (out.req_pass_at.to_numpy() < INF))[0]
    want = max(1, int(np.ceil(C.COMPLETION_ANOM_RATE * E / 2)))
    pickA = np.sort(r.choice(candA, min(want, len(candA)), replace=False)) if len(candA) else np.array([], int)
    pickB = np.sort(r.choice(candB, min(want, len(candB)), replace=False)) if len(candB) else np.array([], int)
    hist["hist_t"] = hist["t"]
    comp_anom = {}
    for e in pickA:
        hist = hist[~((hist.e == e) & (hist.order == 2))]
        hist = pd.concat([hist, pd.DataFrame([{"e": e, "order": 2, "from": "active", "to": "completed", "t": int(out.content_at[e]),
                                                "by": "system", "reason": "completion_rule_met"}])], ignore_index=True)
        comp_anom[e] = ("required_assessment_not_passed", int(out.content_at[e]))
    if len(pickB):
        m = hist.e.isin(pickB) & (hist.order == 2)
        hist.loc[m, "t"] = hist.loc[m, "e"].map(lambda e: int(out.content_at[e]))
        for e in pickB:
            comp_anom[e] = ("required_assessment_passed_after_completion", int(out.content_at[e]))
    hist = hist.sort_values(["e", "order"], kind="stable").reset_index(drop=True)
    assert (hist.groupby("e").t.diff().fillna(0) >= 0).all()

    # ------------------------------------------------------------------ id arrays
    enr_ids = enr.enrollment_id.to_numpy(); lrn_ids = enr.learner_id.to_numpy(); crs_ids = enr.course_id.to_numpy()
    item_ids = items.content_id.to_numpy(); att_ids = np.array([C.att(i + 1) for i in range(len(att))], dtype=object)
    asm_ids = cat["assessments"].assessment_id.to_numpy()

    # ------------------------------------------------------------------ events: stay numeric until the final step (memory)
    e = ev.e.to_numpy(); nB = len(ev); li_e = enr.li.to_numpy(); ci_e = enr.ci.to_numpy()
    pref = learners.preferred_device.map({d: i for i, d in enumerate(C.DEVICES)}).to_numpy()[li_e][e]
    sw = r.random(nB) < .15
    dev = np.where(sw, r.integers(0, 3, nB), pref)
    offline = (dev != 0) & (r.random(nB) < .18)
    delay = np.where(offline, np.clip(r.lognormal(np.log(50400), 1.3, nB), 600, 20 * 86400), r.integers(1, 31, nB)).astype(np.int64)
    tB = ev.t.to_numpy(); ingB = np.minimum(tB + delay, ASOF_END)
    ldB = ev.ldate.to_numpy(); udate = tB // 86400
    repB = ldB.copy()

    # ---- inject: timezone day shift (rows not used as duplicate sources)
    n_tz = round(C.TZ_RATE * nB)
    sdays = enr.start_day.to_numpy()[e]
    diff = ldB != udate
    wdiff = diff & (((ldB - sdays) // 7) != ((udate - sdays) // 7))
    dup_w = np.where(offline, 3.0, 1.0); dup_w = dup_w / dup_w.sum()
    dup_idx = np.sort(r.choice(nB, min(n_dup, nB), replace=False, p=dup_w)) if n_dup else np.array([], int)
    is_dup_src = np.zeros(nB, bool); is_dup_src[dup_idx] = True
    p1 = np.nonzero(wdiff & ~is_dup_src)[0]; p2 = np.nonzero(diff & ~wdiff & ~is_dup_src)[0]
    k2 = min(len(p2), n_tz - min(len(p1), int(round(.6 * n_tz)))); k1 = min(len(p1), n_tz - k2)
    tz_idx = np.sort(np.concatenate([r.choice(p1, k1, replace=False) if k1 else [], r.choice(p2, k2, replace=False) if k2 else []]).astype(int))
    repB[tz_idx] = udate[tz_idx]

    # ---- inject: duplicates (retry / double submit): same client_event_key, new event_id, later ingest
    mx = np.bincount(e, weights=None, minlength=E)
    mx = np.zeros(E, int); np.maximum.at(mx, e, ev.seq.to_numpy())
    d_e = e[dup_idx]
    order_d = np.argsort(d_e, kind="stable")
    d_rank = np.empty(len(dup_idx), int)
    srt = d_e[order_d]; first_of = np.searchsorted(srt, srt)
    d_rank[order_d] = np.arange(len(srt)) - first_of + 1
    d_seq = mx[d_e] + d_rank
    dd = np.where(offline[dup_idx], r.integers(60, 6 * 3600, len(dup_idx)), r.integers(1, 600, len(dup_idx)))
    d_ing = np.minimum(ingB[dup_idx] + dd, ASOF_END)

    # ---- inject: activity from unenrolled learner/course pairs (phantom enrollment ids)
    crs_n = len(cat["courses"]); active_l = np.nonzero(~latent.dormant.to_numpy())[0]
    elig_c = np.nonzero(cat["popularity"] > 0)[0]
    have = set((li_e * crs_n + ci_e).tolist())
    P = max(1, n_unen // 3); ph = []
    while len(ph) < P:
        l_, c_ = int(r.choice(active_l)), int(r.choice(elig_c))
        if l_ * crs_n + c_ not in have:
            have.add(l_ * crs_n + c_); ph.append((l_, c_))
    per = np.full(P, n_unen // P); per[: n_unen - per.sum()] += 1
    coh = cat["cohorts"]; coh_c = coh.course_id.str[4:].astype(int).to_numpy() - 1
    cs, cacc = S.days(coh.start_date), S.days(coh.access_end_date)
    i_course = items.course_id.str[4:].astype(int).to_numpy() - 1
    ity_ = items.content_type.to_numpy()
    learn_items = {c: np.nonzero((i_course == c) & np.isin(ity_, ["video", "reading"]))[0] for c in {c for _, c in ph}}
    PX = {k: [] for k in ("e", "item", "tcode", "t", "tz", "seq", "dev")}
    ph_enr_ids = []
    for pi, ((l_, c_), m_) in enumerate(zip(ph, per)):
        cids = np.nonzero(coh_c == c_)[0]; k = int(r.choice(cids))
        lo = cs[k] * 86400; hi = min(cacc[k] * 86400, ASOF_END) - 1
        ph_enr_ids.append(C.enr(learners.learner_id.iat[l_], cat["courses"].course_id.iat[c_]))
        for j in range(1, int(m_) + 1):
            it = int(r.choice(learn_items[c_])); sess = r.random() < .3
            day = int(r.integers(lo // 86400, hi // 86400)); hr = float(r.choice(24, p=S.HOUR_P) + r.random())
            tt = min(max(day * 86400 + int(hr * 3600) - int(S.STD_OFF[tzi[l_]]) * 60, lo), hi)
            PX["e"].append(E + pi); PX["item"].append(-1 if sess else it)
            PX["tcode"].append(S.ET["session_start"] if sess else (S.ET["video_play"] if ity_[it] == "video" else S.ET["content_view"]))
            PX["t"].append(tt); PX["tz"].append(int(tzi[l_])); PX["seq"].append(j)
            PX["dev"].append(C.DEVICES.index(learners.preferred_device.iat[l_]))
    PX = {k: np.array(v, dtype=np.int64) for k, v in PX.items()}
    nU = len(PX["e"])
    pho = S.tz_offsets(PX["t"], PX["tz"]); phl = (PX["t"] + pho.astype(np.int64) * 60) // 86400
    phi = PX["t"] + r.integers(1, 31, nU)
    ph_li = np.array([p[0] for p in ph]); ph_ci = np.array([p[1] for p in ph])
    enr_ext = np.concatenate([enr_ids, np.array(ph_enr_ids, dtype=object)])
    li_ext = np.concatenate([li_e, ph_li]); ci_ext = np.concatenate([ci_e, ph_ci])

    ND = len(dup_idx); N = nB + ND + nU
    assert N == sc.events, (N, sc.events)
    cat_ = lambda *xs: np.concatenate(xs)
    X = dict(
        e=cat_(e, d_e, PX["e"]), seq=cat_(ev.seq.to_numpy(), d_seq, PX["seq"]),
        item=cat_(ev.item.to_numpy(), ev.item.to_numpy()[dup_idx], PX["item"]),
        att=cat_(ev.att.to_numpy(), ev.att.to_numpy()[dup_idx], np.full(nU, -1)),
        tcode=cat_(ev.tcode.to_numpy(), ev.tcode.to_numpy()[dup_idx], PX["tcode"]),
        t=cat_(tB, tB[dup_idx], PX["t"]), ing=cat_(ingB, d_ing, phi),
        off=cat_(ev.off.to_numpy(), ev.off.to_numpy()[dup_idx], pho), rep=cat_(repB, repB[dup_idx], phl),
        dev=cat_(dev, dev[dup_idx], PX["dev"]), offline=cat_(offline, offline[dup_idx], np.zeros(nU, bool)),
        dur=cat_(ev.dur.to_numpy(), ev.dur.to_numpy()[dup_idx], np.full(nU, -1)),
        inj=cat_(np.zeros(nB, bool), np.ones(ND, bool), np.ones(nU, bool)),
        ld=cat_(ldB, ldB[dup_idx], phl))
    del ev
    eid = np.array([C.evt(enr_ext[a], int(b)) for a, b in zip(X["e"], X["seq"])], dtype=object)
    keyid = eid.copy(); keyid[nB:nB + ND] = eid[dup_idx]
    ckey = _hash_keys(keyid); del keyid

    for i in tz_idx:
        gt.append(dict(issue_type="timezone_day_shift", label_class="injected_anomaly", entity_type="ActivityEvent",
                       entity_id=eid[i], related_entity_id=enr_ext[X["e"][i]],
                       expected_decision="assign day/week from event_time_utc + client_tz_offset_min, not reported_activity_date",
                       detail=json.dumps({"expected_local_date": str(np.datetime64(int(ldB[i]), 'D')),
                                          "reported_date": str(np.datetime64(int(udate[i]), 'D')), "week_misassigned": bool(wdiff[i])})))
    for j, i in enumerate(dup_idx):
        gt.append(dict(issue_type="duplicate_event", label_class="injected_anomaly", entity_type="ActivityEvent", entity_id=eid[nB + j],
                       related_entity_id=eid[i], expected_decision="drop: keep earliest-ingested row per client_event_key",
                       detail=json.dumps({"duplicate_of": eid[i]})))
    for i in range(nB + ND, N):
        a_ = X["e"][i]
        gt.append(dict(issue_type="unenrolled_activity", label_class="injected_anomaly", entity_type="ActivityEvent", entity_id=eid[i],
                       related_entity_id=enr_ext[a_], expected_decision="exclude from engagement metrics; route to support review (learner has no enrollment in this course)",
                       detail=json.dumps({"learner_id": learners.learner_id.iat[li_ext[a_]], "course_id": cat["courses"].course_id.iat[ci_ext[a_]]})))
    lag_h = (X["ing"] - X["t"]) / 3600
    for i in np.nonzero((lag_h > C.LATE_ARRIVAL_HOURS) & ~X["inj"])[0]:
        gt.append(dict(issue_type="late_arriving_event", label_class="expected_edge_case", entity_type="ActivityEvent", entity_id=eid[i],
                       related_entity_id=enr_ext[X["e"][i]], expected_decision="keep; bucket by event_time_utc (not ingestion time)",
                       detail=json.dumps({"ingest_lag_hours": round(float(lag_h[i]), 1)})))

    rank_e = np.empty(len(enr_ext), int); rank_e[np.argsort(enr_ext, kind="stable")] = np.arange(len(enr_ext))
    o = np.lexsort((X["seq"], rank_e[X["e"]]))
    X = {k: v[o] for k, v in X.items()}; eid, ckey = eid[o], ckey[o]
    ie, ic = X["item"], X["att"]
    C_ = lambda codes, cats: pd.Categorical.from_codes(codes, categories=list(cats))
    events = pd.DataFrame({
        "event_id": eid, "enrollment_id": C_(X["e"], enr_ext), "learner_id": C_(li_ext[X["e"]], learners.learner_id),
        "course_id": C_(ci_ext[X["e"]], cat["courses"].course_id),
        "content_id": C_(ie, item_ids), "attempt_id": pd.Categorical(np.where(ic >= 0, att_ids[np.maximum(ic, 0)], None)),
        "event_type": C_(X["tcode"], C.EVENT_TYPES), "event_time_utc": iso_ts(X["t"]), "ingested_at_utc": iso_ts(X["ing"]),
        "client_tz_offset_min": X["off"].astype(int), "reported_activity_date": iso_date(X["rep"]),
        "device_type": C_(X["dev"], C.DEVICES), "source": C_(X["offline"].astype(int), C.SOURCES),
        "duration_sec": pd.array(X["dur"], dtype="Int64"), "client_event_key": ckey})
    events["duration_sec"] = events.duration_sec.mask(events.duration_sec == -1, pd.NA)
    inj = X["inj"]; del X, eid, ckey

    # ------------------------------------------------------------------ remaining tables
    hist["hid"] = hist.groupby("e").cumcount() + 1
    history = pd.DataFrame({"history_id": [f"ESH-{enr_ids[a]}-{b:02d}" for a, b in zip(hist.e, hist.hid)],
                            "enrollment_id": enr_ids[hist.e.to_numpy()], "from_status": hist["from"].where(hist["from"].notna(), None),
                            "to_status": hist.to, "changed_at": iso_ts(hist.t.to_numpy()), "changed_by": hist.by, "reason_code": hist.reason})
    lastrow = hist.groupby("e").tail(1).set_index("e").reindex(range(E))
    enrollments = pd.DataFrame({"enrollment_id": enr_ids, "learner_id": lrn_ids, "course_id": crs_ids, "cohort_id": enr.cohort_id.to_numpy(),
                                "enrolled_at": iso_ts(enr.enr_s.to_numpy()), "enrollment_source": enr.source.to_numpy(),
                                "current_status": lastrow.to.to_numpy(), "status_updated_at": iso_ts(lastrow.t.to_numpy())})

    for e_, (variant, ht) in comp_anom.items():
        gt.append(dict(issue_type="completion_before_required_assessment", label_class="injected_anomaly", entity_type="Enrollment", entity_id=enr_ids[e_],
                       related_entity_id=f"OUT-{enr_ids[e_]}", expected_decision="reject premature 'completed'; completion must follow CompletionRule (all required assessments passed)",
                       detail=json.dumps({"variant": variant, "recorded_completed_at": str(np.datetime64(ht, 's')) + "Z",
                                          "required_assessments_total": int(out.areq_total[e_]), "required_assessments_passed_final": int(out.req_passed[e_]),
                                          "rule_derived_status": str(out.outcome_status[e_])})))

    a = att
    sm = ~a.abandoned.to_numpy()
    attempts = pd.DataFrame({
        "attempt_id": att_ids, "enrollment_id": enr_ids[a.e.to_numpy()], "assessment_id": asm_ids[a.ai.to_numpy()],
        "attempt_no": a.attempt_no.to_numpy(), "started_at": iso_ts(a.start.to_numpy()),
        "submitted_at": iso_ts(np.where(sm, a["sub"].to_numpy(), 0), sm), "score": a.score.to_numpy(), "max_score": a.max_score.to_numpy(),
        "percent_score": np.round(a.score.to_numpy() / a.max_score.to_numpy() * 100, 2),
        "passed": pd.array(np.where(sm, a.passed.to_numpy(), None), dtype="boolean"), "is_late": a.is_late.to_numpy(),
        "attempt_status": np.where(sm, "submitted", "abandoned"),
        "duration_sec": pd.array(np.where(sm, a["sub"].to_numpy() - a.start.to_numpy(), -1), dtype="Int64")})
    attempts["duration_sec"] = attempts.duration_sec.mask(attempts.duration_sec == -1, pd.NA)

    ccode = out.completed.to_numpy()
    outcomes = pd.DataFrame({
        "outcome_id": ["OUT-" + x for x in enr_ids], "enrollment_id": enr_ids, "learner_id": lrn_ids, "course_id": crs_ids,
        "cohort_id": enr.cohort_id.to_numpy(), "rule_id": out.rule_id.to_numpy(), "evaluated_at": iso_ts(np.full(E, ASOF_END)),
        "required_content_items_total": out.req_total.to_numpy(), "required_content_items_completed": out.req_done.to_numpy(),
        "content_completion_pct": np.round(out.req_done.to_numpy() / out.req_total.to_numpy() * 100, 2),
        "required_assessments_total": out.areq_total.to_numpy(), "required_assessments_passed": out.req_passed.to_numpy(),
        "weighted_score_pct": np.round(out.wscore.to_numpy(), 2), "total_attempts": out.total_attempts.to_numpy(),
        "valid_event_count": out.n_ev.to_numpy(), "active_days": out.active_days.to_numpy(), "active_weeks": out.active_weeks.to_numpy(),
        "first_activity_at": iso_ts(out["first"].to_numpy(), out.has_ev.to_numpy()), "last_activity_at": iso_ts(out["last"].to_numpy(), out.has_ev.to_numpy()),
        "completion_status": out.outcome_status.to_numpy(), "completed_at": iso_ts(out.completed_at.to_numpy(), ccode),
        "completed_date_local": iso_date(out.cdate.to_numpy(), ccode),
        "days_to_complete": np.where(ccode, np.round((out.completed_at.to_numpy() - enr.enr_s.to_numpy()) / 86400, 2), np.nan),
        "engagement_band": out.band.to_numpy()})

    # inactive learners (zero valid activity anywhere) - expected edge case
    ev_per_learner = events[~inj].learner_id.value_counts()
    ev_per_learner = ev_per_learner[ev_per_learner > 0]
    enr_per_learner = enrollments.learner_id.value_counts()
    for lid in learners.learner_id[~learners.learner_id.isin(ev_per_learner.index)]:
        gt.append(dict(issue_type="inactive_learner", label_class="expected_edge_case", entity_type="Learner", entity_id=lid, related_entity_id="",
                       expected_decision="exclude from active-learner numerators; keep in enrolled denominators",
                       detail=json.dumps({"enrollments": int(enr_per_learner.get(lid, 0))})))

    gtdf = pd.DataFrame(gt)
    gtdf = gtdf.sort_values(["issue_type", "entity_id"], kind="mergesort").reset_index(drop=True)
    gtdf.insert(0, "gt_id", [f"GT-{i + 1:06d}" for i in range(len(gtdf))])
    gtdf = gtdf[schema.GROUND_TRUTH_COLUMNS]

    tables = dict(learners=learners, instructors=cat["instructors"], courses=cat["courses"], cohorts=cat["cohorts"],
                  enrollments=enrollments, enrollment_status_history=history, content_items=cat["content_items"],
                  assessments=cat["assessments"], attempts=attempts, completion_rules=cat["completion_rules"],
                  activity_events=events, course_outcomes=outcomes)

    # expected (clean) weekly metrics = same metric code on rows that are NOT injected
    clean = events[~inj]
    v = Mx.valid_events(clean, enrollments, tables["cohorts"])
    expected = Mx.weekly_metrics(v, enrollments, tables["cohorts"], outcomes)
    latent_out = latent.rename(columns={"dormant": "is_dormant"})
    return dict(tables=tables, ground_truth=gtdf, expected_weekly=expected, latent=latent_out, sim_stats=sim["stats"],
                injected=dict(duplicates=int(ND), unenrolled=int(nU), tz_shift=int(len(tz_idx)),
                              completion_before_assessment=int(len(comp_anom)), baseline_events=int(nB)))
