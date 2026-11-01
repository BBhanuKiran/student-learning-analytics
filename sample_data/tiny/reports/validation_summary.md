# Validation summary - PASS

146 checks, 0 failed. `violations` is the number of offending rows found; `expected` is the number of *labelled* violations (ground truth).

| group | check | violations | expected | status |
|---|---|---:|---:|---|
| schema | learners: columns match data dictionary | 0 | 0 | PASS |
| primary_key | learners.learner_id unique & non-null | 0 | 0 | PASS |
| id_format | learners.learner_id matches ^LRN-\d{6}$ | 0 | 0 | PASS |
| schema | instructors: columns match data dictionary | 0 | 0 | PASS |
| primary_key | instructors.instructor_id unique & non-null | 0 | 0 | PASS |
| id_format | instructors.instructor_id matches ^INS-\d{4}$ | 0 | 0 | PASS |
| schema | courses: columns match data dictionary | 0 | 0 | PASS |
| primary_key | courses.course_id unique & non-null | 0 | 0 | PASS |
| id_format | courses.course_id matches ^CRS-\d{6}$ | 0 | 0 | PASS |
| schema | cohorts: columns match data dictionary | 0 | 0 | PASS |
| primary_key | cohorts.cohort_id unique & non-null | 0 | 0 | PASS |
| id_format | cohorts.cohort_id matches ^COH-\d{6}$ | 0 | 0 | PASS |
| schema | enrollments: columns match data dictionary | 0 | 0 | PASS |
| primary_key | enrollments.enrollment_id unique & non-null | 0 | 0 | PASS |
| id_format | enrollments.enrollment_id matches ^ENR-LRN-\d{6}-CRS-\d{6}$ | 0 | 0 | PASS |
| schema | enrollment_status_history: columns match data dictionary | 0 | 0 | PASS |
| primary_key | enrollment_status_history.history_id unique & non-null | 0 | 0 | PASS |
| id_format | enrollment_status_history.history_id matches ^ESH-ENR-LRN-\d{6}-CRS-\d{6}-\d{2}$ | 0 | 0 | PASS |
| schema | content_items: columns match data dictionary | 0 | 0 | PASS |
| primary_key | content_items.content_id unique & non-null | 0 | 0 | PASS |
| id_format | content_items.content_id matches ^CNT-\d{7}$ | 0 | 0 | PASS |
| schema | assessments: columns match data dictionary | 0 | 0 | PASS |
| primary_key | assessments.assessment_id unique & non-null | 0 | 0 | PASS |
| id_format | assessments.assessment_id matches ^ASM-2026-\d{6}$ | 0 | 0 | PASS |
| schema | attempts: columns match data dictionary | 0 | 0 | PASS |
| primary_key | attempts.attempt_id unique & non-null | 0 | 0 | PASS |
| id_format | attempts.attempt_id matches ^ATT-\d{8}$ | 0 | 0 | PASS |
| schema | completion_rules: columns match data dictionary | 0 | 0 | PASS |
| primary_key | completion_rules.rule_id unique & non-null | 0 | 0 | PASS |
| id_format | completion_rules.rule_id matches ^CRL-\d{6}$ | 0 | 0 | PASS |
| schema | activity_events: columns match data dictionary | 0 | 0 | PASS |
| primary_key | activity_events.event_id unique & non-null | 0 | 0 | PASS |
| id_format | activity_events.event_id matches ^EVT-ENR-LRN-\d{6}-CRS-\d{6}-\d{6}$ | 0 | 0 | PASS |
| schema | course_outcomes: columns match data dictionary | 0 | 0 | PASS |
| primary_key | course_outcomes.outcome_id unique & non-null | 0 | 0 | PASS |
| id_format | course_outcomes.outcome_id matches ^OUT-ENR-LRN-\d{6}-CRS-\d{6}$ | 0 | 0 | PASS |
| id_format | enrollment_id == 'ENR-'+learner_id+'-'+course_id | 0 | 0 | PASS |
| id_format | event_id prefix == EVT-+enrollment_id | 0 | 0 | PASS |
| id_format | history_id prefix / outcome_id == OUT-+enrollment_id | 0 | 0 | PASS |
| foreign_key | courses.instructor_id -> instructors.instructor_id | 0 | 0 | PASS |
| foreign_key | cohorts.course_id -> courses.course_id | 0 | 0 | PASS |
| foreign_key | enrollments.learner_id -> learners.learner_id | 0 | 0 | PASS |
| foreign_key | enrollments.course_id -> courses.course_id | 0 | 0 | PASS |
| foreign_key | enrollments.cohort_id -> cohorts.cohort_id | 0 | 0 | PASS |
| foreign_key | enrollment_status_history.enrollment_id -> enrollments.enrollment_id | 0 | 0 | PASS |
| foreign_key | content_items.course_id -> courses.course_id | 0 | 0 | PASS |
| foreign_key | content_items.parent_content_id -> content_items.content_id | 0 | 0 | PASS |
| foreign_key | assessments.course_id -> courses.course_id | 0 | 0 | PASS |
| foreign_key | assessments.content_id -> content_items.content_id | 0 | 0 | PASS |
| foreign_key | attempts.enrollment_id -> enrollments.enrollment_id | 0 | 0 | PASS |
| foreign_key | attempts.assessment_id -> assessments.assessment_id | 0 | 0 | PASS |
| foreign_key | completion_rules.course_id -> courses.course_id | 0 | 0 | PASS |
| foreign_key | activity_events orphan event_ids == labelled unenrolled_activity set | 0 | 0 | PASS |
| foreign_key | activity_events.enrollment_id -> enrollments.enrollment_id | 80 | 80 | PASS |
| foreign_key | activity_events.learner_id -> learners.learner_id | 0 | 0 | PASS |
| foreign_key | activity_events.course_id -> courses.course_id | 0 | 0 | PASS |
| foreign_key | activity_events.content_id -> content_items.content_id | 0 | 0 | PASS |
| foreign_key | activity_events.attempt_id -> attempts.attempt_id | 0 | 0 | PASS |
| foreign_key | course_outcomes.enrollment_id -> enrollments.enrollment_id | 0 | 0 | PASS |
| foreign_key | course_outcomes.learner_id -> learners.learner_id | 0 | 0 | PASS |
| foreign_key | course_outcomes.course_id -> courses.course_id | 0 | 0 | PASS |
| foreign_key | course_outcomes.cohort_id -> cohorts.cohort_id | 0 | 0 | PASS |
| foreign_key | course_outcomes.rule_id -> completion_rules.rule_id | 0 | 0 | PASS |
| foreign_key | enrollment.course_id == cohort.course_id | 0 | 0 | PASS |
| foreign_key | assessment.course_id == content_item.course_id | 0 | 0 | PASS |
| foreign_key | attempt.assessment.course == attempt.enrollment.course | 0 | 0 | PASS |
| foreign_key | child content parent is a module of the same course | 0 | 0 | PASS |
| cardinality | enrollment unique per (learner, course) | 0 | 0 | PASS |
| cardinality | outcome 1:1 with enrollment | 0 | 0 | PASS |
| cardinality | assessment 1:1 with assessment content item | 0 | 0 | PASS |
| cardinality | no enrollment/cohort for draft courses | 0 | 0 | PASS |
| enum | learners.preferred_device in allowed set | 0 | 0 | PASS |
| enum | learners.age_band in allowed set | 0 | 0 | PASS |
| enum | learners.signup_channel in allowed set | 0 | 0 | PASS |
| enum | learners.account_status in allowed set | 0 | 0 | PASS |
| enum | courses.level in allowed set | 0 | 0 | PASS |
| enum | courses.course_status in allowed set | 0 | 0 | PASS |
| enum | cohorts.delivery_mode in allowed set | 0 | 0 | PASS |
| enum | cohorts.cohort_status in allowed set | 0 | 0 | PASS |
| enum | enrollments.enrollment_source in allowed set | 0 | 0 | PASS |
| enum | enrollments.current_status in allowed set | 0 | 0 | PASS |
| enum | enrollment_status_history.to_status in allowed set | 0 | 0 | PASS |
| enum | enrollment_status_history.changed_by in allowed set | 0 | 0 | PASS |
| enum | content_items.content_type in allowed set | 0 | 0 | PASS |
| enum | content_items.content_status in allowed set | 0 | 0 | PASS |
| enum | assessments.assessment_type in allowed set | 0 | 0 | PASS |
| enum | assessments.assessment_status in allowed set | 0 | 0 | PASS |
| enum | attempts.attempt_status in allowed set | 0 | 0 | PASS |
| enum | completion_rules.rule_status in allowed set | 0 | 0 | PASS |
| enum | activity_events.event_type in allowed set | 0 | 0 | PASS |
| enum | activity_events.device_type in allowed set | 0 | 0 | PASS |
| enum | activity_events.source in allowed set | 0 | 0 | PASS |
| enum | course_outcomes.completion_status in allowed set | 0 | 0 | PASS |
| enum | course_outcomes.engagement_band in allowed set | 0 | 0 | PASS |
| enum | history.from_status null only on first row | 0 | 0 | PASS |
| enum | content module only at level 1 | 0 | 0 | PASS |
| enum | required fields non-null | 0 | 0 | PASS |
| date_order | cohort start < end < access_end; end = start+dur*7-1; access = end+14 | 0 | 0 | PASS |
| date_order | cohort start is Monday | 0 | 0 | PASS |
| date_order | cohort_status consistent with as_of | 0 | 0 | PASS |
| date_order | enrolled_at >= learner.signup_date + 1 day | 0 | 0 | PASS |
| date_order | enrolled_at <= cohort start + 10 days | 0 | 0 | PASS |
| date_order | history changed_at non-decreasing per enrollment and <= as_of | 0 | 0 | PASS |
| date_order | ingested_at_utc >= event_time_utc and <= as_of end | 0 | 0 | PASS |
| date_order | attempt submitted_at >= started_at | 0 | 0 | PASS |
| date_order | attempt started_at > enrolled_at | 0 | 0 | PASS |
| date_order | completion rule versions are contiguous, last is open-ended | 0 | 0 | PASS |
| date_order | valid events occur after enrolled_at | 0 | 0 | PASS |
| date_order | valid events inside [cohort start, access_end] (local date) | 0 | 0 | PASS |
| duplicates | event_id unique | 0 | 0 | PASS |
| duplicates | extra rows sharing client_event_key == labelled duplicate_event | 0 | 0 | PASS |
| duplicates | dedup removes exactly the labelled duplicates (kept rows = total - labelled) | 0 | 0 | PASS |
| duplicates | removed rows are exactly the labelled duplicate event_ids | 0 | 0 | PASS |
| duplicates | client_event_key never shared across different enrollments | 0 | 0 | PASS |
| anomaly_reconciliation | reported_activity_date != local date  <=>  labelled timezone_day_shift | 0 | 0 | PASS |
| arithmetic | assessment weights per course sum to 100 | 0 | 0 | PASS |
| arithmetic | pass_score = ceil(max*pass_pct) within (0, max] | 0 | 0 | PASS |
| arithmetic | percent_score = round(score/max*100, 2) | 0 | 0 | PASS |
| arithmetic | attempt.passed == score >= pass_score | 0 | 0 | PASS |
| arithmetic | attempt.max_score == assessment.max_score | 0 | 0 | PASS |
| arithmetic | abandoned attempts have no score/submission; submitted have both | 0 | 0 | PASS |
| arithmetic | duration_sec = submitted_at - started_at | 0 | 0 | PASS |
| arithmetic | attempt_no contiguous 1..n per (enrollment, assessment) | 0 | 0 | PASS |
| arithmetic | attempts per (enrollment, assessment) <= max_attempts | 0 | 0 | PASS |
| arithmetic | is_late == submitted after due date end | 0 | 0 | PASS |
| arithmetic | assessment_start events == attempts; assessment_submit events == submitted attempts | 0 | 0 | PASS |
| arithmetic | outcome.total_attempts == attempts rows | 0 | 0 | PASS |
| arithmetic | outcome.valid_event_count == deduped enrolled events | 0 | 0 | PASS |
| arithmetic | outcome.required_content_items_completed == distinct completion events | 0 | 0 | PASS |
| arithmetic | outcome.required_content_items_total == required video/reading items | 0 | 0 | PASS |
| arithmetic | content_completion_pct = completed/total*100 | 0 | 0 | PASS |
| arithmetic | weighted_score_pct = sum(weight*best_percent)/100 | 0 | 0 | PASS |
| arithmetic | required_assessments_passed recomputed | 0 | 0 | PASS |
| arithmetic | required_assessments_total == required assessments of course | 0 | 0 | PASS |
| completion_rules | outcome.rule_id is effective at cohort start_date and belongs to the course | 0 | 0 | PASS |
| completion_rules | completion_status=='completed' <=> all three rule thresholds satisfied | 0 | 0 | PASS |
| completion_rules | completed_at/date/days_to_complete present iff completed | 0 | 0 | PASS |
| lifecycle | every history transition is legal and from_status == previous to_status | 0 | 0 | PASS |
| lifecycle | no transition after a terminal state | 0 | 0 | PASS |
| lifecycle | every enrollment starts with 'enrolled' at enrolled_at | 0 | 0 | PASS |
| lifecycle | enrollment.current_status/status_updated_at == latest history row | 0 | 0 | PASS |
| lifecycle | 'active' transition time == first valid event time | 0 | 0 | PASS |
| lifecycle | terminal statuses only after as_of-valid times | 0 | 0 | PASS |
| anomaly_reconciliation | history-vs-rule completion mismatches == labelled completion_before_required_assessment | 0 | 0 | PASS |
| ground_truth | no ground-truth/latent column leaks into input tables | 0 | 0 | PASS |
| ground_truth | every ground-truth entity_id exists in the input data | 0 | 0 | PASS |

## Coverage

```json
{
  "normal_paths": {
    "completed": 307,
    "in_progress": 34,
    "not_completed": 659
  },
  "enrollment_status": {
    "dropped": 394,
    "completed": 313,
    "expired": 259,
    "enrolled": 17,
    "active": 17
  },
  "boundary": {
    "repeated_attempts": 615,
    "attempts_at_max": 234,
    "late_submissions": 347,
    "late_joiners": 82,
    "pre_start_enrollments": 805,
    "two_rule_versions_courses": 1,
    "courses_without_cohorts": 1
  },
  "failure_exception": {
    "abandoned_attempts": 127,
    "failed_attempts": 773,
    "dropped": 394,
    "expired": 259,
    "inactive_learners": 22,
    "learners_with_zero_enrollments": 1
  },
  "event_mix": {
    "offline_sync": 2166,
    "late_arriving_gt72h": 203,
    "by_type": {
      "assessment_start": 3936,
      "assessment_submit": 3802,
      "video_play": 3464,
      "video_complete": 2700,
      "content_complete": 2568,
      "session_start": 1947,
      "content_view": 678,
      "discussion_post": 526,
      "resource_download": 379
    },
    "by_device": {
      "web": 8311,
      "android": 6914,
      "ios": 4775
    }
  },
  "injected_anomalies": {
    "duplicate_event": 400,
    "unenrolled_activity": 80,
    "completion_before_required_assessment": 12,
    "timezone_day_shift": 98
  }
}
```
