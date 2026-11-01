# Learning-analytics synthetic data generator

End-to-end synthetic dataset + analytics pipeline for **course participation, content use, assessment progress and completion across learner cohorts**.
One deterministic generator (fixed seed `20261022`) produces master data, transactions/events, derived outcomes, labelled anomalies, a separate ground truth, validation, metrics and reproducibility evidence.

| | full (default for the brief) | starter | tiny (tests) |
|---|---:|---:|---:|
| learners | 20,000 | 1,000 | 200 |
| courses | 500 | 25 | 10 |
| enrollments | 100,000 | 5,000 | 1,000 |
| activity events (incl. injected rows) | 2,000,000 | 100,000 | 20,000 |

Any count can be overridden (`--learners --courses --enrollments --events`); presets and overrides use the **same** code path.

## Quick start
```bash
pip install -r requirements.txt                 # numpy, pandas, pyarrow, pytest (Python 3.10+)
python -m pytest -q tests                        # 20 tests, ~10 s
python -m edu_synth.generate --scale tiny    --out output/tiny    --sql-seed    # seconds
python -m edu_synth.generate --scale starter --out output/starter --sql-seed    # ~10 s
python -m edu_synth.generate --scale full    --seed 20261022 --out output/full  # ~3 min, ~2.5 GB RAM peak, ~0.6 GB on disk
python scripts/check_reproducibility.py --scale full --skip-other-seed --out reports/reproducibility_full.json   # step 10
```
`make test | tiny | starter | full | repro-tiny | repro-full` wrap the same commands. The generator exits non-zero if validation fails.

## What is produced (`<out>/`)
| path | content |
|---|---|
| `data/*.csv` | 12 tables: learners, instructors, courses, cohorts, enrollments, enrollment_status_history, content_items, assessments, attempts, completion_rules, activity_events, course_outcomes |
| `json/*.json` | same tables as JSON (only tables <= 25k rows) |
| `sql/schema.sql`, `sql/seed.sql` | DDL with PK/FK; INSERT seed (with `--sql-seed`; use tiny/starter). `edu_synth.export.build_sqlite()` loads any scale into SQLite |
| `ground_truth/ground_truth.csv` | every injected anomaly / expected edge case with `issue_type`, `label_class`, `entity_id`, `expected_decision`, `detail` (**never an input**) |
| `ground_truth/expected_weekly_metrics.csv` | the metrics a *correct* pipeline must reproduce; `latent_learner_traits.csv` = hidden generator traits |
| `metrics/` | `weekly_cohort_metrics.csv`, `cohort_comparison.csv`, `anomaly_impact.csv`, `kpi_summary.json`, `metric_definitions.json` |
| `reports/` | `validation_summary.{json,md}` (146 checks + coverage), `detection_evaluation.json` (precision/recall of detectors) |
| `docs/` | `data_dictionary.{md,csv}` (type, required, allowed values, unit, uniqueness, validation rule for every field), `er_diagram.mmd` |
| `manifest.json`, `source_manifest.json` | command, seed, scale, versions, git commit, row counts + SHA-256 of every file; provenance |

Committed evidence from the full run is in [`reports/full_run/`](reports/full_run) and a ready-to-use sample in [`sample_data/tiny/`](sample_data/tiny).

## Design at a glance
* **IDs** (deterministic, zero-padded, immutable): `LRN-000001`, `CRS-000001`, `ENR-<learner-id>-<course-id>`, `EVT-<enrollment-id>-000001`, `ASM-2026-000001`; supporting `COH-`, `CNT-`, `CRL-`, `ATT-`, `INS-`, `ESH-<enrollment-id>-NN`, `OUT-<enrollment-id>`.
* **Relationships**: Learner N:M Course through the `Enrollment` bridge (scoped to a `Cohort`); Course 1:N Cohort / ContentItem / Assessment / CompletionRule (versioned, effective-dated); ContentItem self-hierarchy (module -> leaf) and 1:0..1 Assessment; Enrollment 1:N ActivityEvent / Attempt / StatusHistory and 1:1 CourseOutcome; Attempt 1:0..2 ActivityEvent. Full FK list with cardinality in `docs/data_dictionary.md`, ER diagram in `docs/er_diagram.mmd`.
* **State history is never overwritten**: `enrollment_status_history` is an append-only log; `Enrollment.current_status` is its latest row. Duplicate/late/offline events and repeated attempts are separate rows.
* **Outcomes are derived, not drawn**: completion = effective `CompletionRule` applied to deduplicated events + attempts (content %, all required assessments passed, weighted score %). Behaviour (dropout hazard, pace, aptitude, retries) is a documented model - see [`docs/generation_logic.md`](docs/generation_logic.md).
* **Metrics have explicit definitions** (`docs/metric_definitions.md`): valid event = deduplicated + enrolled + inside the access window; day/week from `event_time_utc + client_tz_offset_min` (never `reported_activity_date`); cohort-relative weeks; cohort comparisons use an identical 8-week window over complete weeks only.

## Required edge cases (all injected as *labelled* rows)
| issue_type | full-run count | detected from inputs only (precision / recall) | effect if ignored |
|---|---:|---|---|
| `duplicate_event` | 40,000 | 1.0 / 1.0 (same `client_event_key`) | +2.46% events overall; inflates events per active learner |
| `unenrolled_activity` | 8,000 | 1.0 / 1.0 (enrollment_id has no Enrollment) | counted as engagement from non-participants |
| `completion_before_required_assessment` | 1,200 | 1.0 / 1.0 (history `completed` vs attempts/rule) | premature completions in funnel |
| `timezone_day_shift` | 9,760 | 1.0 / 1.0 (reported date != local date) | 1,099 cohort-weeks with wrong weekly-active count |

Also covered: inactive learners (3,084 with no activity), mobile/offline sync (~195k events), late arrivals > 72 h (19,199), repeated attempts (61,570 retries), abandoned/failed/late attempts, late joiners, pre-start enrolment, draft/archived courses, two completion-rule versions, dropped / expired / in-progress enrolments. The validator reconciles each violation set **exactly** with the ground truth (e.g. the orphan-FK event ids must equal the `unenrolled_activity` label set).

## Validation (step 8) and acceptance
`edu_synth/validate.py` re-reads the exported CSVs and runs 146 checks: schema vs dictionary, primary-key uniqueness, ID formats, foreign keys (incl. optional ones), enums, required fields, date ordering (cohort windows, enrolment vs signup, event vs enrolment/ingest, attempt order, rule effective ranges), arithmetic reconciliation (weights = 100, percent/pass flags, attempt numbering, outcome counts and weighted score recomputed independently from events/attempts), completion-rule conformance, lifecycle legality, duplicates, and ground-truth hygiene (no label columns in inputs). Result for the full run: **PASS, 0 failed** (`reports/full_run/validation_summary.md`).

Acceptance criteria from the brief:
* *Metrics have explicit definitions* - `docs/metric_definitions.md`.
* *Event deduplication works* - dedup removes exactly the labelled duplicates; pipeline metrics equal `expected_weekly_metrics.csv` (`pipeline_metrics_match_ground_truth_metrics: true`).
* *Course completion follows rules* - checked per outcome against the rule effective at cohort start.
* *Cohort comparisons use consistent windows* - fixed 8 cohort-relative weeks, complete weeks only (test `test_cohort_comparison_uses_identical_window`).

## Reproducibility (step 10)
Same seed -> byte-identical output. `scripts/check_reproducibility.py` regenerates twice and compares row counts and SHA-256 of every file (result committed in `reports/reproducibility_full.json`; tiny also checks that a different seed changes the checksums). Randomness comes from named `numpy.random.SeedSequence` streams; library versions are recorded in `manifest.json` (checksums are guaranteed for identical numpy/pandas versions).

## Realism snapshot (full run)
Completion 29.9% (in progress 6.7%, not completed 63.5%); 11% of enrolments inactive; weekly active rate averages 51.7% over the first 8 weeks and decays steeply (week-8/week-1 retention median 0.12); instructor-led cohorts complete more (33.5% vs 29.9%) and beginner courses more than advanced (39% vs 22%); 15.5% of attempts are retries; ~10% of events arrive via offline sync; evening-peaked usage across 13 time zones.

## Lawful provenance
No external data is used - everything is synthetic from code + seed; no personal data. `source_manifest.json` records this and lists only schema-inspiration references (xAPI, IMS Caliper; nothing downloaded) with the fields to fill (URL, version, retrieval date, license, attribution, transformations, discarded fields) if external data were ever added.

## Assumptions / limitations
* One enrollment per learner per course (by the `ENR-<learner>-<course>` convention); re-enrolment would need a new cohort-scoped ID scheme.
* Unenrolled activity uses a phantom `enrollment_id`, so `activity_events.enrollment_id` is a *logical* FK with labelled violations (declared in DDL; load with `PRAGMA foreign_keys=OFF`).
* `event_id` sequence reflects insertion order per enrolment; appended duplicate rows are not chronological.
* Behavioural parameters are plausible, not calibrated to a real platform.

## Repository layout
```
edu_synth/  config.py schema.py masters.py simulate.py derive.py build.py metrics.py detect.py validate.py export.py generate.py timeutil.py
tests/      test_pipeline.py (20 tests)       scripts/  check_reproducibility.py
docs/       generation_logic.md metric_definitions.md       reports/  evidence from the full run
sample_data/tiny/  small committed sample (CSV, JSON, SQL, ground truth, metrics)
```
