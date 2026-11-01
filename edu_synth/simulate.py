"""Step 2b: transactional layer - enrollments, learner trajectories, attempts, activity events (vectorised).

Everything below is driven by explicit behavioural rules (diligence -> dropout hazard, pacing, release gating,
aptitude -> scores, retries). Outcomes are NOT drawn here; they are derived later (derive.py) from these records.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as C
from .masters import TZ

ASOF_DAY = int(np.datetime64(C.AS_OF_DATE, "D").astype(np.int64))
ASOF_END_S = (ASOF_DAY + 1) * 86400 - 1
ET = {n: i for i, n in enumerate(C.EVENT_TYPES)}
TY = {"video": 0, "reading": 1, "discussion": 2, "quiz": 3, "assignment": 4, "final_exam": 5}
HOUR_W = np.array([0, .2, .1, .1, .1, .3, 1, 2, 3, 3, 2.5, 2.5, 3, 2.5, 2.5, 3, 3, 3.5, 4, 5, 6, 6, 4, 0], float)
HOUR_P = HOUR_W / HOUR_W.sum()
STD_OFF = np.array([t[3] for t in TZ])


def days(series) -> np.ndarray:
    return pd.to_datetime(pd.Series(series)).to_numpy().astype("datetime64[D]").astype(np.int64)


def tz_offsets(t_s: np.ndarray, tz_idx: np.ndarray) -> np.ndarray:
    """Exact UTC offset (minutes, DST-aware) of each event's learner timezone at event time."""
    out = np.zeros(len(t_s), dtype=np.int32)
    ts = t_s.astype("datetime64[s]")
    for k, (name, *_rest) in enumerate(TZ):
        m = tz_idx == k
        if not m.any():
            continue
        utc = pd.DatetimeIndex(ts[m]).tz_localize("UTC")
        loc = utc.tz_convert(name).tz_localize(None)
        out[m] = ((loc.to_numpy() - ts[m]) // np.timedelta64(1, "m")).astype(np.int32)
    return out


def make_enrollments(sc, seed, learners, latent, tzi, cat):
    r = C.rng(seed, "enrollments")
    courses, cohorts = cat["courses"], cat["cohorts"]
    nL, nC = len(learners), len(courses)
    pop = cat["popularity"]
    elig = np.nonzero(pop > 0)[0]
    cw = pop[elig] / pop[elig].sum()
    lw = latent.enroll_weight.to_numpy() / latent.enroll_weight.sum()
    want = min(sc.enrollments, nL * len(elig))
    got = pd.DataFrame({"li": [], "ci": []}, dtype="int64")
    tries = 0
    while len(got) < want:
        m = int((want - len(got)) * 1.4) + 64
        li = r.choice(nL, m, p=lw if tries < 4 else None)
        ci = r.choice(elig, m, p=cw if tries < 4 else None)
        got = pd.concat([got, pd.DataFrame({"li": li, "ci": ci})]).drop_duplicates().reset_index(drop=True)
        tries += 1
    pairs = got.iloc[:want].sort_values(["li", "ci"]).reset_index(drop=True)
    li, ci = pairs.li.to_numpy(), pairs.ci.to_numpy()
    n = len(pairs)

    # cohort lookup (cohorts are stored grouped by course, ascending start)
    c_course = cohorts.course_id.str[4:].astype(int).to_numpy() - 1
    c_first = np.full(nC, -1); c_n = np.zeros(nC, int)
    for k, c in enumerate(c_course):
        if c_first[c] < 0: c_first[c] = k
        c_n[c] += 1
    c_start = days(cohorts.start_date)
    coh = c_first[ci] + np.floor(r.random(n) * c_n[ci]).astype(int)
    signup = days(learners.signup_date)[li]
    lead = np.minimum(np.floor(r.exponential(8, n)).astype(int), 40)
    late = r.random(n) < .08
    late_off = r.integers(1, 11, n)

    def enr_day(cc):
        s = c_start[cc]
        return np.where(late, s + late_off, s - lead)
    d = enr_day(coh)
    bad = d < signup + 1
    coh = np.where(bad, c_first[ci] + c_n[ci] - 1, coh)       # latest cohort always starts after any signup
    d = np.maximum(enr_day(coh), signup + 1)
    enr_s = d * 86400 + r.integers(0, 86400, n)
    mode_il = (cohorts.delivery_mode.to_numpy()[coh] == "instructor_led")
    lvl = courses.level.map({l: i for i, l in enumerate(C.LEVELS)}).to_numpy()[ci]
    dil = np.clip(latent.diligence.to_numpy()[li] + r.normal(0, .08, n) + .06 * mode_il - .04 * lvl, .02, .98)
    apt = np.clip(r.normal(.74 + .22 * (dil - .5) - .03 * lvl, .08), .3, .97)
    df = pd.DataFrame({"li": li, "ci": ci, "coh": coh, "enr_s": enr_s, "dil": dil, "apt": apt, "lvl": lvl,
                       "source": r.choice(C.ENR_SOURCES, n, p=[.70, .20, .10]),
                       "dormant": latent.dormant.to_numpy()[li]})
    df["learner_id"] = learners.learner_id.to_numpy()[li]
    df["course_id"] = courses.course_id.to_numpy()[ci]
    df["cohort_id"] = cohorts.cohort_id.to_numpy()[coh]
    df["enrollment_id"] = [C.enr(a, b) for a, b in zip(df.learner_id, df.course_id)]
    df["start_day"] = c_start[coh]
    df["end_day"] = days(cohorts.end_date)[coh]
    df["access_day"] = days(cohorts.access_end_date)[coh]
    df["tz"] = tzi[li]
    return df


def simulate(enr: pd.DataFrame, cat: dict, sc: C.Scale, seed: int, n_baseline_events: int):
    r = C.rng(seed, "events")
    E, nC = len(enr), len(cat["courses"])
    content, asms = cat["content_items"], cat["assessments"]

    # ---- item (leaf) arrays, ordered by course then course_order
    items = content[content.content_type != "module"].reset_index(drop=True)
    i_course = items.course_id.str[4:].astype(int).to_numpy() - 1
    n_items = np.bincount(i_course, minlength=nC)
    item_off = np.cumsum(n_items) - n_items
    ity = items.content_type.map(TY).to_numpy()
    i_est = items.est_minutes.to_numpy()
    i_rel = items.release_offset_days.to_numpy()
    cid2item = {c: k for k, c in enumerate(items.content_id)}
    a_item = np.array([cid2item[c] for c in asms.content_id])
    item_asm = np.full(len(items), -1); item_asm[a_item] = np.arange(len(asms))
    a_ty = asms.assessment_type.map({"quiz": 0, "assignment": 1, "final_exam": 2}).to_numpy()
    a_max = asms.max_score.to_numpy(); a_pass = asms.pass_score.to_numpy()
    a_maxatt = asms.max_attempts.to_numpy(); a_due = asms.due_offset_days.to_numpy()
    disc_item = np.full(nC, -1)
    for k in np.nonzero(ity == 2)[0][::-1]:
        disc_item[i_course[k]] = k

    ec, el = enr.ci.to_numpy(), enr.li.to_numpy()
    dil, apt = enr.dil.to_numpy(), enr.apt.to_numpy()
    start_s = enr.start_day.to_numpy() * 86400
    bound = np.minimum(enr.access_day.to_numpy() * 86400, ASOF_END_S)
    enr_s = enr.enr_s.to_numpy()
    std_off = STD_OFF[enr.tz.to_numpy()]

    # ---- (enrollment x item) pairs
    cnt_e = n_items[ec]; tot = int(cnt_e.sum())
    pe = np.repeat(np.arange(E), cnt_e)
    soff = np.cumsum(cnt_e) - cnt_e
    pit = item_off[ec][pe] + (np.arange(tot) - soff[pe])
    ty = ity[pit]
    perf = (ty != 2) | (r.random(tot) < .35)                    # optional discussions mostly skipped
    cs = np.cumsum(perf)
    rank = cs - np.where(soff > 0, cs[np.maximum(soff - 1, 0)], 0)[pe]
    n_perf = np.bincount(pe, weights=perf, minlength=E).astype(int)
    hazard = np.clip(0.085 - 0.082 * dil + 0.006 * enr.lvl.to_numpy(), .002, .15)   # per-item chance to disengage
    k_stop = r.geometric(hazard) - 1
    k_stop = np.where(enr.dormant.to_numpy(), 0, k_stop)
    disengaged = k_stop < n_perf
    selected = perf & (rank <= k_stop[pe])

    gap = r.exponential((1.6 / (0.35 + dil))[pe]) * perf
    cg = np.cumsum(gap)
    cgg = cg - np.where(soff > 0, cg[np.maximum(soff - 1, 0)], 0)[pe]
    late_join = np.maximum(enr_s // 86400 - enr.start_day.to_numpy(), 0)
    lag = r.exponential(1.5, E) + late_join
    td = np.maximum(lag[pe] + cgg, i_rel[pit] + r.uniform(0, 2.5, tot))
    BIG = 1e4
    td = np.maximum.accumulate(td + pe * BIG) - pe * BIG          # monotone within enrollment
    hr = r.choice(24, tot, p=HOUR_P) + r.random(tot)
    t = start_s[pe] + np.floor(td).astype(np.int64) * 86400 + np.round(hr * 3600).astype(np.int64) - std_off[pe] * 60
    t = np.maximum(t, enr_s[pe] + r.integers(60, 21600, tot))
    act = selected & (t < bound[pe])

    # ---- learning events
    pcomp = np.clip(.94 + .05 * dil, 0, .99)
    ev_e, ev_item, ev_type, ev_t, ev_att, ev_dur = [], [], [], [], [], []

    def add(e, item, typ, tt, att=None, dur=None):
        ev_e.append(e); ev_item.append(item); ev_type.append(np.full(len(e), typ) if np.isscalar(typ) else typ)
        ev_t.append(tt); ev_att.append(np.full(len(e), -1) if att is None else att)
        ev_dur.append(np.full(len(e), -1) if dur is None else dur)

    for tcode, first, comp in ((0, "video_play", "video_complete"), (1, "content_view", "content_complete"), (2, "discussion_post", None)):
        p = np.nonzero(act & (ty == tcode))[0]
        if not comp:
            add(pe[p], pit[p], ET[first], t[p])
            continue
        lo, hi = (.8, 1.4) if tcode == 0 else (.5, 1.6)
        dsec = (i_est[pit[p]] * 60 * r.uniform(lo, hi, len(p))).astype(np.int64)
        ok = (r.random(len(p)) < pcomp[pe[p]]) & (t[p] + dsec < bound[pe[p]])
        if tcode == 0:      # video: play always logged, complete only if watched through
            add(pe[p], pit[p], ET[first], t[p])
            add(pe[p][ok], pit[p][ok], ET[comp], (t[p] + dsec)[ok], dur=dsec[ok])
        else:               # reading: opened-only (content_view) OR finished (content_complete)
            add(pe[p][~ok], pit[p][~ok], ET[first], t[p][~ok])
            add(pe[p][ok], pit[p][ok], ET[comp], (t[p] + dsec)[ok], dur=dsec[ok])

    # ---- attempts (repeat until pass / max attempts / learner gives up)
    ap = np.nonzero(act & (ty >= 3))[0]
    cur_p, cur_s, no = ap, t[ap], 1
    rows = []
    ab_p = np.array([.03, .02, .05])
    while len(cur_p):
        e = pe[cur_p]; ai = item_asm[pit[cur_p]]; aty = a_ty[ai]
        ab = r.random(len(cur_p)) < ab_p[aty]
        pct = np.clip(r.normal(apt[e] + .05 * (no - 1), .12), 0, 1)
        score = np.round(pct * a_max[ai] * 2) / 2
        dur = np.where(aty == 0, r.integers(300, 1200, len(cur_p)),
                       np.where(aty == 1, r.integers(1800, 3 * 86400, len(cur_p)), r.integers(1800, 5400, len(cur_p))))
        sub = cur_s + dur
        keep = np.where(ab, cur_s < bound[e], sub < bound[e])
        rows.append(pd.DataFrame({"e": e[keep], "ai": ai[keep], "attempt_no": no, "start": cur_s[keep],
                                  "sub": np.where(ab, -1, sub)[keep], "score": np.where(ab, np.nan, score)[keep],
                                  "abandoned": ab[keep]}))
        passed = ~ab & (score >= a_pass[ai])
        retry = keep & ~passed & (no < a_maxatt[ai]) & (r.random(len(cur_p)) < (.55 + .4 * dil[e]))
        gd = np.where(aty == 0, r.integers(1, 4, len(cur_p)), np.where(aty == 1, r.integers(2, 7, len(cur_p)), r.integers(2, 11, len(cur_p))))
        nxt = np.where(ab, cur_s + 1800, sub) + gd * 86400
        cur_p, cur_s, no = cur_p[retry], nxt[retry], no + 1
    att = pd.concat(rows, ignore_index=True)
    att = att.sort_values(["e", "start", "ai"], kind="stable").reset_index(drop=True)
    att["max_score"] = a_max[att.ai]
    att["pass_score"] = a_pass[att.ai]
    att["due_s"] = (enr.start_day.to_numpy()[att.e] + a_due[att.ai] + 1) * 86400
    sub_mask = ~att.abandoned.to_numpy()
    att["is_late"] = sub_mask & (att["sub"].to_numpy() >= att.due_s.to_numpy())
    att["passed"] = sub_mask & (att.score.to_numpy() >= att.pass_score.to_numpy())
    aid = np.arange(len(att))
    add(att.e.to_numpy(), a_item[att.ai.to_numpy()], ET["assessment_start"], att.start.to_numpy(), att=aid)
    sm = np.nonzero(sub_mask)[0]
    add(att.e.to_numpy()[sm], a_item[att.ai.to_numpy()][sm], ET["assessment_submit"], att["sub"].to_numpy()[sm], att=aid[sm],
        dur=(att["sub"].to_numpy() - att.start.to_numpy())[sm])

    core = [np.concatenate(x) for x in (ev_e, ev_item, ev_type, ev_t, ev_att, ev_dur)]
    n_core = len(core[0])
    R = n_baseline_events - n_core
    if R < 0:
        raise ValueError(f"core behavioural events ({n_core}) exceed baseline target ({n_baseline_events}); "
                         "increase --events or lower dropout/activity assumptions")

    # ---- filler events (sessions, revisits, downloads, posts) allocated by engagement; exact total via largest remainder
    first = np.full(E, np.iinfo(np.int64).max); last = np.zeros(E, np.int64)
    np.minimum.at(first, core[0], core[3]); np.maximum.at(last, core[0], core[3])
    ncore_e = np.bincount(core[0], minlength=E)
    w = (ncore_e > 0) * np.sqrt(ncore_e) * (.5 + dil)
    raw = R * w / w.sum()
    base_n = np.floor(raw).astype(np.int64)
    rem = R - int(base_n.sum())
    order = np.lexsort((np.arange(E), -(raw - base_n)))
    base_n[order[:rem]] += 1
    xe = np.repeat(np.arange(E), base_n)
    fl, ll = first[xe], last[xe]
    dl0 = (fl + std_off[xe] * 60) // 86400; dl1 = (ll + std_off[xe] * 60) // 86400
    dday = dl0 + np.floor(r.random(R) * (dl1 - dl0 + 1)).astype(np.int64)
    xt = dday * 86400 + np.round((r.choice(24, R, p=HOUR_P) + r.random(R)) * 3600).astype(np.int64) - std_off[xe] * 60
    badw = (xt < fl) | (xt > ll)
    xt = np.where(badw, fl + np.floor(r.random(R) * (ll - fl + 1)).astype(np.int64), xt)
    lp = np.nonzero(act & (ty <= 1))[0]
    lp_cnt = np.bincount(pe[lp], minlength=E); lp_off = np.cumsum(lp_cnt) - lp_cnt
    u = r.random(R)
    revisit_pair = lp[np.minimum(lp_off[xe] + np.floor(r.random(R) * np.maximum(lp_cnt[xe], 1)).astype(np.int64), len(lp) - 1)]
    has_lp = lp_cnt[xe] > 0
    xitem = np.full(R, -1); xtype = np.full(R, ET["session_start"]); xdur = np.full(R, -1)
    m_rev = has_lp & (u >= .50) & (u < .85)
    xitem[m_rev] = pit[revisit_pair[m_rev]]
    xtype[m_rev] = np.where(ity[xitem[m_rev]] == 0, ET["video_play"], ET["content_view"])
    m_dl = has_lp & (u >= .85) & (u < .95)
    xitem[m_dl] = pit[revisit_pair[m_dl]]; xtype[m_dl] = ET["resource_download"]
    dcourse = disc_item[ec[xe]]
    m_ds = (u >= .95) & (dcourse >= 0)
    xitem[m_ds] = dcourse[m_ds]; xtype[m_ds] = ET["discussion_post"]
    m_ss = xtype == ET["session_start"]
    xdur[m_ss] = np.clip(r.lognormal(np.log(900), .7, int(m_ss.sum())), 60, 7200).astype(np.int64)

    ev = pd.DataFrame({"e": np.concatenate([core[0], xe]), "item": np.concatenate([core[1], xitem]),
                       "tcode": np.concatenate([core[2], xtype]), "t": np.concatenate([core[3], xt]),
                       "att": np.concatenate([core[4], np.full(R, -1)]), "dur": np.concatenate([core[5], xdur])})
    ev = ev.sort_values(["e", "t", "tcode", "att", "item"], kind="stable").reset_index(drop=True)
    st = np.searchsorted(ev.e.to_numpy(), np.arange(E))
    ev["seq"] = np.arange(len(ev)) - st[ev.e.to_numpy()] + 1
    ev["tz"] = enr.tz.to_numpy()[ev.e.to_numpy()]
    ev["off"] = tz_offsets(ev.t.to_numpy(), ev.tz.to_numpy())
    ev["ldate"] = (ev.t.to_numpy() + ev.off.to_numpy().astype(np.int64) * 60) // 86400
    assert (ev.t.to_numpy() <= ASOF_END_S).all()
    enr = enr.copy()
    enr["disengaged"] = disengaged
    return dict(events=ev, attempts=att, items=items, a_item=a_item, disengaged=disengaged, enr=enr,
                stats=dict(core_events=int(n_core), filler_events=int(R), pairs=int(tot)))
