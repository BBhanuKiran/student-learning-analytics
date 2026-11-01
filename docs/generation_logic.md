# Generation logic and documented business rules

All behaviour below is implemented in `edu_synth/` and driven by one seed (`20261022`). Every random stream is
named (`rng(seed, "events")`, `"catalog"`, `"enrollments"` ...) so changing one part never reshuffles another.

## 1. Order of generation (parents before children)
1. `masters.make_learners` - Learner (+ latent traits kept **out** of the input tables).
2. `masters.make_catalog` - Instructor, Course, Cohort, ContentItem hierarchy, Assessment, CompletionRule.
3. `simulate.make_enrollments` - Enrollment (bridge) with valid learner/course/cohort parents.
4. `simulate.simulate` - learner trajectories -> Attempt rows and ActivityEvent rows (valid parent IDs only).
5. `derive.derive` - CourseOutcome + EnrollmentStatusHistory **computed from** events, attempts and CompletionRule.
6. `build.build` - labelled anomaly injection, ground truth, expected (clean) metrics.

## 2. Master data rules
* Course duration 6/8/10 weeks -> 3/4/5 modules. Each module: video + reading (required), optional discussion,
  quiz (50% required). Middle module may have an assignment; last module has a required final exam.
* Assessment weights are integers summing to exactly 100 per course (exam 40, assignment 20 if present, quizzes share the rest).
* Cohorts start on Mondays 2026-01-05..2026-09-14; every course has 2-3 cohorts, at least one starting on/after 2026-04-27 so any learner can find a valid cohort. End = start + weeks*7 - 1; access window = end + 14 days. Draft courses have no cohort/enrollment; archived courses have only closed cohorts.
* CompletionRule v1 effective from 2026-01-01; 25% of courses get a stricter v2 effective 2026-05-01 (contiguous, no overlap). The rule applied to an enrollment is the one effective on its **cohort start date**.

## 3. Behavioural model (events / attempts)
* Each learner has a latent diligence (Beta). Enrollment diligence adds noise, +0.06 for instructor-led cohorts, -0.04 per level step.
* Per-item disengagement hazard `h = 0.085 - 0.082*diligence + 0.006*level` (geometric stop); dormant learners (7%) never act.
* Pace: exponential gaps (mean `1.6/(0.35+diligence)` days) gated by module release dates; local hour-of-day drawn from an evening-peaked distribution and converted with the learner's IANA timezone (exact DST offset stored per event).
* Video: `video_play` then `video_complete` (p = .94+.05*diligence). Reading: `content_complete`, or only `content_view` if not finished.
* Assessments: score ~ N(aptitude + 0.05*(attempt-1), 0.12) of max; abandon 2-5%; retry after failure with p = .55+.4*diligence up to `max_attempts`; `is_late` if submitted after the due day.
* Filler events (session_start, revisits, downloads, posts) are allocated so the baseline hits the exact target total (largest-remainder), weighted by engagement.
* Mobile devices queue 18% of events offline; ingestion lag is log-normal (median 14 h, up to 20 days). Lag > 72 h is labelled `late_arriving_event` (legitimate; bucket by event time).

## 4. Derived values (never drawn independently)
* **Content condition**: distinct required video/reading items with a completion event >= `ceil(min_required_content_pct * total / 100)`.
* **Assessment condition**: every required assessment has a passing attempt.
* **Score condition**: `sum(weight_i * best_percent_i) / sum(weight_i) >= min_weighted_score_pct` (best attempt per assessment, unattempted = 0).
* `completed` iff all three hold; `completed_at` = latest of the three first-satisfied times (all are monotone in time).
* Lifecycle log: `enrolled` -> `active` (first valid event) -> `completed` (rule met) | `dropped` (learner request, or 21 days of inactivity) | `expired` (access window closed). History rows are appended, never updated; `Enrollment.current_status` = latest row.
* Weekly/cohort metrics: see `docs/metric_definitions.md`.

## 5. Injected anomalies (always labelled, never silently corrupting other rows)
| issue_type | how injected | rate | expected handling |
|---|---|---|---|
| `duplicate_event` | extra row copying an event (same `client_event_key`, new `event_id`, later ingest; 3x more likely for offline-sync rows) | 2% of total events | keep earliest-ingested row per key |
| `unenrolled_activity` | events for a real learner/course pair with **no** enrollment (phantom `ENR-...` id, valid learner/course/content) | 0.4% of total events | exclude from engagement; route to support |
| `completion_before_required_assessment` | history says `completed` (A) while required assessment never passed, or (B) at the time content finished, before the last required pass | 1.2% of enrollments | reject premature completion; follow CompletionRule |
| `timezone_day_shift` | `reported_activity_date` uses the UTC date instead of the learner-local date (60% chosen so the **cohort week** changes) | 0.5% of baseline events | derive day from `event_time_utc + client_tz_offset_min` |

Expected edge cases (labelled `expected_edge_case`, not errors): `inactive_learner` (no valid event anywhere) and `late_arriving_event`.
