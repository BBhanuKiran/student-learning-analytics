"""Step 2a: parent/master tables - learners, instructors, courses, cohorts, content, assessments, rules."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from . import config as C

# (IANA tz, country, probability, standard UTC offset minutes used only for local-hour -> UTC conversion)
TZ = [("Asia/Kolkata", "IN", .34, 330), ("America/New_York", "US", .11, -300), ("America/Chicago", "US", .04, -360),
      ("America/Los_Angeles", "US", .07, -480), ("Europe/London", "GB", .08, 0), ("Europe/Berlin", "DE", .07, 60),
      ("Asia/Singapore", "SG", .05, 480), ("Australia/Sydney", "AU", .05, 600), ("America/Sao_Paulo", "BR", .05, -180),
      ("Africa/Lagos", "NG", .04, 60), ("Asia/Tokyo", "JP", .03, 540), ("Asia/Dubai", "AE", .03, 240),
      ("Etc/UTC", "ZZ", .04, 0)]
CATEGORIES = ["Data Science", "Software Engineering", "Business Analytics", "Digital Marketing", "Finance",
              "Healthcare Informatics", "Design", "Project Management", "Languages", "Cybersecurity"]
TOPICS = ["Foundations", "Essentials", "Applied Methods", "Case Studies", "Practitioner Lab", "Fundamentals",
          "Strategy", "Tools and Workflows", "Capstone Prep", "Deep Dive"]


def make_learners(sc: C.Scale, seed: int):
    r = C.rng(seed, "learners")
    n = sc.learners
    p = np.array([t[2] for t in TZ]); p = p / p.sum()
    tzi = r.choice(len(TZ), n, p=p)
    dormant = r.random(n) < 0.07                       # latent: never produces any activity
    closed = dormant & (r.random(n) < 0.43)            # ~3% of all accounts are closed
    df = pd.DataFrame({
        "learner_id": [C.lrn(i) for i in range(1, n + 1)],
        "signup_date": (pd.Timestamp("2025-09-01") + pd.to_timedelta(r.integers(0, 227, n), unit="D")).strftime("%Y-%m-%d"),
        "country_code": [TZ[i][1] for i in tzi],
        "timezone": [TZ[i][0] for i in tzi],
        "preferred_device": r.choice(C.DEVICES, n, p=[.50, .20, .30]),
        "age_band": r.choice(C.AGE_BANDS, n, p=[.30, .40, .20, .10]),
        "signup_channel": r.choice(C.SIGNUP_CHANNELS, n, p=[.45, .20, .20, .15]),
        "account_status": np.where(closed, "closed", "active"),
    })
    latent = pd.DataFrame({"learner_id": df.learner_id, "diligence": np.round(r.beta(2.2, 2.0, n), 4),
                           "dormant": dormant, "enroll_weight": r.lognormal(0, .8, n)})
    return df, latent, tzi


def make_catalog(sc: C.Scale, seed: int):
    """Courses, cohorts, content hierarchy, assessments, completion rules (all deterministic)."""
    r = C.rng(seed, "catalog")
    nC = sc.courses
    n_ins = max(5, nC // 5)
    instructors = pd.DataFrame({
        "instructor_id": [C.ins(i) for i in range(1, n_ins + 1)],
        "department": [CATEGORIES[i % 10] for i in range(n_ins)],
        "joined_date": (pd.Timestamp("2018-01-01") + pd.to_timedelta(r.integers(0, 2900, n_ins), unit="D")).strftime("%Y-%m-%d"),
    })
    dur = r.choice([6, 8, 10], nC, p=[.30, .45, .25])
    level = r.choice(C.LEVELS, nC, p=[.40, .38, .22])
    cat = r.integers(0, 10, nC)
    courses = pd.DataFrame({
        "course_id": [C.crs(i) for i in range(1, nC + 1)],
        "title": [f"{CATEGORIES[cat[i]]}: {TOPICS[i % 10]} {i + 1}" for i in range(nC)],
        "category": [CATEGORIES[k] for k in cat],
        "level": level,
        "language": r.choice(["en", "hi", "es", "pt"], nC, p=[.70, .12, .12, .06]),
        "duration_weeks": dur,
        "instructor_id": [C.ins(int(k) + 1) for k in r.integers(0, n_ins, nC)],
        "course_status": "published",
        "created_date": (pd.Timestamp("2025-01-01") + pd.to_timedelta(r.integers(0, 365, nC), unit="D")).strftime("%Y-%m-%d"),
    })
    n_draft = max(1, round(0.03 * nC)) if nC >= 10 else 0
    draft_idx = set(r.choice(nC, n_draft, replace=False).tolist()) if n_draft else set()
    for i in draft_idx:
        courses.loc[i, "course_status"] = "draft"
    popularity = r.lognormal(0, .9, nC)
    for i in draft_idx:
        popularity[i] = 0.0

    # ---- cohorts: Mondays only, >=1 cohort starting on/after 2026-04-27 so every learner can find a valid cohort
    mondays = pd.date_range("2026-01-05", "2026-09-14", freq="7D")
    last_lo = int(np.searchsorted(mondays, pd.Timestamp("2026-04-27")))
    coh_rows, k = [], 0
    for i in range(nC):
        if i in draft_idx:
            continue
        ncoh = int(r.choice([2, 3], p=[.6, .4]))
        first = int(r.integers(0, last_lo - 1))
        last = int(r.integers(last_lo, len(mondays)))
        picks = {first, last}
        while len(picks) < ncoh:
            picks.add(int(r.integers(first, last + 1)))
        for mi in sorted(picks):
            k += 1
            s = mondays[mi]; e = s + pd.Timedelta(days=int(dur[i]) * 7 - 1)
            acc = e + pd.Timedelta(days=C.GRACE_DAYS)
            iso = s.isocalendar()
            coh_rows.append(dict(cohort_id=C.coh(k), course_id=C.crs(i + 1), cohort_code=f"{C.crs(i + 1)}-{iso.year}W{iso.week:02d}",
                                 start_date=s.strftime("%Y-%m-%d"), end_date=e.strftime("%Y-%m-%d"),
                                 access_end_date=acc.strftime("%Y-%m-%d"),
                                 delivery_mode=str(r.choice(C.DELIVERY_MODES)), capacity=int(r.integers(40, 401)),
                                 cohort_status="closed" if acc < pd.Timestamp(C.AS_OF_DATE) else "running"))
    cohorts = pd.DataFrame(coh_rows)
    # archived: only courses whose every cohort is closed (25% of eligible)
    if len(cohorts):
        allclosed = cohorts.groupby("course_id").cohort_status.apply(lambda s: (s == "closed").all())
        for cid in allclosed[allclosed].index:
            if r.random() < .25:
                courses.loc[courses.course_id == cid, "course_status"] = "archived"
                popularity[int(cid[4:]) - 1] *= 0.5

    # ---- content hierarchy + assessments
    content, asms, cn, an = [], [], 0, 0
    for i in range(nC):
        cid = C.crs(i + 1); d = int(dur[i]); M = d // 2; status = "draft" if i in draft_idx else "published"
        order = 0
        asm_leaves = []     # (content_idx_in_list, type, module)
        for m in range(M):
            rel = int(m * d * 7 / M)
            cn += 1; order += 1; parent = C.cnt(cn)
            content.append(dict(content_id=parent, course_id=cid, parent_content_id=None, content_type="module",
                                title=f"Module {m + 1}", hierarchy_level=1, sequence_no=m + 1, course_order=order,
                                week_number=rel // 7 + 1, release_offset_days=rel, is_required=False, est_minutes=5,
                                content_status=status))
            leaves = [("video", True), ("reading", True)]
            if r.random() < .5:
                leaves.append(("discussion", False))
            leaves.append(("quiz", bool(r.random() < .5)))
            if m == M // 2 and r.random() < .6:
                leaves.append(("assignment", bool(r.random() < .5)))
            if m == M - 1:
                leaves.append(("final_exam", True))
            for s, (ty, req) in enumerate(leaves, 1):
                cn += 1; order += 1
                est = {"video": int(r.integers(8, 26)), "reading": int(r.integers(5, 16)), "discussion": 10,
                       "quiz": int(r.integers(10, 21)), "assignment": 120, "final_exam": 60}[ty]
                content.append(dict(content_id=C.cnt(cn), course_id=cid, parent_content_id=parent, content_type=ty,
                                    title=f"{ty.replace('_', ' ').title()} {m + 1}.{s}", hierarchy_level=2, sequence_no=s,
                                    course_order=order, week_number=rel // 7 + 1, release_offset_days=rel,
                                    is_required=req, est_minutes=est, content_status=status))
                if ty in C.ASSESSMENT_TYPES:
                    asm_leaves.append((len(content) - 1, ty, rel))
        # weights: exam 40, assignment 20 (if any), quizzes share the rest, integer split, sum == 100
        quizzes = [x for x in asm_leaves if x[1] == "quiz"]
        has_asg = any(x[1] == "assignment" for x in asm_leaves)
        rest = 100 - 40 - (20 if has_asg else 0)
        base, rem = divmod(rest, len(quizzes))
        qw = [base + (1 if j < rem else 0) for j in range(len(quizzes))]
        qi = 0
        for (ci_, ty, rel) in asm_leaves:
            an += 1
            if ty == "quiz":
                w = qw[qi]; qi += 1; mx, pp, ma, tl = 20, .60, 3, 20; due = min(rel + 10, d * 7 - 1)
            elif ty == "assignment":
                w, mx, pp, ma, tl = 20, 50, .60, 2, None; due = min(rel + 14, d * 7 - 1)
            else:
                w, mx, pp, ma, tl = 40, 100, .65, 2, 90; due = d * 7 - 1
            ci = content[ci_]
            asms.append(dict(assessment_id=C.asm(an), course_id=cid, content_id=ci["content_id"], assessment_type=ty,
                             title=ci["title"], max_score=mx, pass_score=math.ceil(mx * pp), weight_pct=w,
                             is_required=ci["is_required"], max_attempts=ma, time_limit_min=tl,
                             available_offset_days=ci["release_offset_days"], due_offset_days=due,
                             assessment_status=status))
    content = pd.DataFrame(content)
    assessments = pd.DataFrame(asms)
    assessments["time_limit_min"] = assessments["time_limit_min"].astype("Int64")

    # ---- completion rules (versioned + effective dated)
    rules, rn = [], 0
    for i in range(nC):
        cid = C.crs(i + 1)
        mc = int(r.choice([80, 90, 100], p=[.4, .4, .2])); mw = int(r.choice([60, 65, 70], p=[.4, .4, .2]))
        two = (i not in draft_idx) and r.random() < .25
        rn += 1
        rules.append(dict(rule_id=C.crl(rn), course_id=cid, rule_version=1, effective_from="2026-01-01",
                          effective_to="2026-04-30" if two else None, min_required_content_pct=mc,
                          min_weighted_score_pct=mw, grace_days_after_end=C.GRACE_DAYS,
                          rule_status="superseded" if two else "active"))
        if two:
            rn += 1
            rules.append(dict(rule_id=C.crl(rn), course_id=cid, rule_version=2, effective_from="2026-05-01",
                              effective_to=None, min_required_content_pct=min(100, mc + 10),
                              min_weighted_score_pct=mw + 5, grace_days_after_end=C.GRACE_DAYS, rule_status="active"))
    rules = pd.DataFrame(rules)
    return dict(instructors=instructors, courses=courses, cohorts=cohorts, content_items=content,
                assessments=assessments, completion_rules=rules, popularity=popularity)
