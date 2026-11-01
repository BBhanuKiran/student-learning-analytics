# Data dictionary

Generated from `edu_synth/schema.py` (the same definitions drive validation and DDL).

Timestamps are ISO-8601 UTC (`YYYY-MM-DDTHH:MM:SSZ`), dates are `YYYY-MM-DD`, booleans are `true`/`false`, null = empty cell.

## learners  (Learner)

Registered person taking courses. No personal data (synthetic, de-identified).

**Primary key:** `learner_id`

| field | type | required | allowed values / format | unit | unique | validation rule |
|---|---|---|---|---|---|---|
| `learner_id` | string | yes | LRN-###### |  | yes | regex ^LRN-\d{6}$; immutable |
| `signup_date` | date | yes | 2025-09-01..2026-04-15 | date | no | <= first enrolment date - 1 day |
| `country_code` | string | yes | ISO-3166 alpha-2 (ZZ = unknown/UTC) |  | no | consistent with timezone |
| `timezone` | string | yes | IANA tz name |  | no | valid IANA zone; drives local-date derivation |
| `preferred_device` | enum | yes | {web, ios, android} |  | no | enum |
| `age_band` | enum | yes | {18-24, 25-34, 35-44, 45+} |  | no | enum |
| `signup_channel` | enum | yes | {organic, employer, university, referral} |  | no | enum |
| `account_status` | enum | yes | {active, closed} |  | no | closed accounts have no activity |

## instructors  (Instructor (supporting))

Course owner/teacher (actor).

**Primary key:** `instructor_id`

| field | type | required | allowed values / format | unit | unique | validation rule |
|---|---|---|---|---|---|---|
| `instructor_id` | string | yes | INS-#### |  | yes | regex ^INS-\d{4}$ |
| `department` | string | yes | free text (10 categories) |  | no |  |
| `joined_date` | date | yes | 2018-01-01..2025-12-31 | date | no |  |

## courses  (Course)

Course master. Content hierarchy lives in content_items.

**Primary key:** `course_id`

**Foreign keys:** `instructor_id` -> `instructors.instructor_id`

| field | type | required | allowed values / format | unit | unique | validation rule |
|---|---|---|---|---|---|---|
| `course_id` | string | yes | CRS-###### |  | yes | regex ^CRS-\d{6}$ |
| `title` | string | yes |  |  | yes | non-empty |
| `category` | string | yes | 10 categories |  | no |  |
| `level` | enum | yes | {beginner, intermediate, advanced} |  | no | enum |
| `language` | string | yes | en|hi|es|pt |  | no |  |
| `duration_weeks` | int | yes | 6|8|10 | weeks | no | = cohort (end_date-start_date+1)/7 |
| `instructor_id` | string | yes | FK instructors |  | no | must exist |
| `course_status` | enum | yes | {draft, published, archived} |  | no | draft => no cohorts/enrolments; archived => all cohorts closed |
| `created_date` | date | yes | 2025-01-01..2025-12-31 | date | no | before first cohort start |

## cohorts  (Cohort)

Scheduled run of a course; comparison unit for analytics.

**Primary key:** `cohort_id`

**Foreign keys:** `course_id` -> `courses.course_id`

| field | type | required | allowed values / format | unit | unique | validation rule |
|---|---|---|---|---|---|---|
| `cohort_id` | string | yes | COH-###### |  | yes | regex ^COH-\d{6}$ |
| `course_id` | string | yes | FK courses |  | no | must exist, course not draft |
| `cohort_code` | string | yes | <course_id>-<YYYY>W<ww> |  | yes | unique |
| `start_date` | date | yes | Mondays 2026-01-05..2026-09-14 | date | no | start_date <= end_date < access_end_date |
| `end_date` | date | yes |  | date | no | = start_date + duration_weeks*7 - 1 |
| `access_end_date` | date | yes |  | date | no | = end_date + grace_days (14); events after it are invalid |
| `delivery_mode` | enum | yes | {instructor_led, self_paced} |  | no | enum |
| `capacity` | int | yes | 40..400 | learners | no | >= 1 |
| `cohort_status` | enum | yes | {running, closed} |  | no | closed iff access_end_date < as_of date |

## enrollments  (Enrollment (bridge Learner<->Course, scoped to Cohort))

N:M bridge between Learner and Course; current state is the latest row of enrollment_status_history.

**Primary key:** `enrollment_id`

**Foreign keys:** `learner_id` -> `learners.learner_id`; `course_id` -> `courses.course_id`; `cohort_id` -> `cohorts.cohort_id`

| field | type | required | allowed values / format | unit | unique | validation rule |
|---|---|---|---|---|---|---|
| `enrollment_id` | string | yes | ENR-<learner_id>-<course_id> |  | yes | = 'ENR-'+learner_id+'-'+course_id; one per learner/course |
| `learner_id` | string | yes | FK learners |  | no | must exist |
| `course_id` | string | yes | FK courses |  | no | must exist; = cohort.course_id |
| `cohort_id` | string | yes | FK cohorts |  | no | must exist |
| `enrolled_at` | timestamp | yes | ISO-8601 UTC | UTC | no | >= signup_date+1d; <= cohort start+10d |
| `enrollment_source` | enum | yes | {self_enrol, employer_assigned, admin_import} |  | no | enum |
| `current_status` | enum | yes | {enrolled, active, completed, dropped, expired} |  | no | = to_status of latest history row |
| `status_updated_at` | timestamp | yes | ISO-8601 UTC | UTC | no | = changed_at of latest history row |

## enrollment_status_history  (EnrollmentStatusHistory (event log of lifecycle))

Append-only lifecycle log; never overwritten.

**Primary key:** `history_id`

**Foreign keys:** `enrollment_id` -> `enrollments.enrollment_id`

| field | type | required | allowed values / format | unit | unique | validation rule |
|---|---|---|---|---|---|---|
| `history_id` | string | yes | ESH-<enrollment_id>-NN |  | yes | NN = 1-based sequence per enrollment |
| `enrollment_id` | string | yes | FK enrollments |  | no | must exist |
| `from_status` | enum | no | {enrolled, active, completed, dropped, expired} or null |  | no | null only for first row |
| `to_status` | enum | yes | {enrolled, active, completed, dropped, expired} |  | no | transition must be in LEGAL_TRANSITIONS |
| `changed_at` | timestamp | yes | ISO-8601 UTC | UTC | no | non-decreasing per enrollment; <= as_of |
| `changed_by` | enum | yes | {learner, system, admin} |  | no | enum |
| `reason_code` | string | yes | enrollment_created|first_activity|completion_rule_met|learner_request|inactivity_21d|access_window_closed |  | no |  |

## content_items  (ContentItem)

Course content hierarchy: module (level 1) -> leaf items (level 2).

**Primary key:** `content_id`

**Foreign keys:** `course_id` -> `courses.course_id`; `parent_content_id` -> `content_items.content_id` (optional)

| field | type | required | allowed values / format | unit | unique | validation rule |
|---|---|---|---|---|---|---|
| `content_id` | string | yes | CNT-####### |  | yes | regex ^CNT-\d{7}$ |
| `course_id` | string | yes | FK courses |  | no | must exist |
| `parent_content_id` | string | no | FK content_items (self) or null |  | no | null iff hierarchy_level=1; parent must be same course |
| `content_type` | enum | yes | {module, video, reading, discussion, quiz, assignment, final_exam} |  | no | module only at level 1 |
| `title` | string | yes |  |  | no |  |
| `hierarchy_level` | int | yes | 1|2 |  | no |  |
| `sequence_no` | int | yes | >=1 |  | no | order within parent |
| `course_order` | int | yes | >=1 |  | no | global order within course; unique per course |
| `week_number` | int | yes | 1..duration_weeks | week | no | = release_offset_days//7+1 |
| `release_offset_days` | int | yes | >=0 | days after cohort start | no | unlock time |
| `is_required` | bool | yes | true|false |  | no | video/reading always true; discussion false; assessments follow assessments.is_required |
| `est_minutes` | int | yes | 5..120 | minutes | no | >0 |
| `content_status` | enum | yes | {draft, published} |  | no | draft iff course draft |

## assessments  (Assessment)

Graded item attached 1:1 to a quiz/assignment/final_exam content item.

**Primary key:** `assessment_id`

**Foreign keys:** `course_id` -> `courses.course_id`; `content_id` -> `content_items.content_id`

| field | type | required | allowed values / format | unit | unique | validation rule |
|---|---|---|---|---|---|---|
| `assessment_id` | string | yes | ASM-2026-###### |  | yes | regex ^ASM-2026-\d{6}$ |
| `course_id` | string | yes | FK courses |  | no | must exist |
| `content_id` | string | yes | FK content_items |  | yes | 1:1; content_type in {quiz, assignment, final_exam} |
| `assessment_type` | enum | yes | {quiz, assignment, final_exam} |  | no | = content_type |
| `title` | string | yes |  |  | no |  |
| `max_score` | int | yes | quiz 20, assignment 50, final_exam 100 | points | no | >0 |
| `pass_score` | int | yes | ceil(max_score*pass_pct) | points | no | 0 < pass_score <= max_score |
| `weight_pct` | int | yes | 1..60 | percent | no | weights of a course sum to exactly 100 |
| `is_required` | bool | yes | true|false |  | no | final_exam always true |
| `max_attempts` | int | yes | quiz 3, assignment 2, final_exam 2 | attempts | no | >=1 |
| `time_limit_min` | int | no | quiz 20, final_exam 90, assignment null | minutes | no |  |
| `available_offset_days` | int | yes | >=0 | days after cohort start | no | <= due_offset_days |
| `due_offset_days` | int | yes |  | days after cohort start | no | <= duration_weeks*7-1 |
| `assessment_status` | enum | yes | {draft, published} |  | no | draft iff course draft |

## attempts  (Attempt)

One try by an enrolment at an assessment. Repeated attempts are separate rows (history preserved).

**Primary key:** `attempt_id`

**Foreign keys:** `enrollment_id` -> `enrollments.enrollment_id`; `assessment_id` -> `assessments.assessment_id`

| field | type | required | allowed values / format | unit | unique | validation rule |
|---|---|---|---|---|---|---|
| `attempt_id` | string | yes | ATT-######## |  | yes | regex ^ATT-\d{8}$ |
| `enrollment_id` | string | yes | FK enrollments |  | no | must exist |
| `assessment_id` | string | yes | FK assessments |  | no | assessment.course_id = enrolment.course_id |
| `attempt_no` | int | yes | 1..max_attempts |  | no | contiguous per (enrollment, assessment) |
| `started_at` | timestamp | yes | ISO-8601 UTC | UTC | no | > enrolled_at; < access end |
| `submitted_at` | timestamp | no | ISO-8601 UTC or null | UTC | no | >= started_at; null iff abandoned |
| `score` | float | no | 0..max_score step 0.5 | points | no | null iff abandoned |
| `max_score` | int | yes |  | points | no | = assessment.max_score |
| `percent_score` | float | no | 0..100 | percent | no | = round(score/max_score*100, 2) |
| `passed` | bool | no | true|false|null |  | no | = score >= assessment.pass_score; null iff abandoned |
| `is_late` | bool | yes | true|false |  | no | true iff submitted after due date end (UTC) |
| `attempt_status` | enum | yes | {submitted, abandoned} |  | no | enum |
| `duration_sec` | int | no | >=0 | seconds | no | = submitted_at - started_at; null iff abandoned |

## completion_rules  (CompletionRule)

Versioned, effective-dated rule defining course completion.

**Primary key:** `rule_id`

**Foreign keys:** `course_id` -> `courses.course_id`

| field | type | required | allowed values / format | unit | unique | validation rule |
|---|---|---|---|---|---|---|
| `rule_id` | string | yes | CRL-###### |  | yes | regex ^CRL-\d{6}$ |
| `course_id` | string | yes | FK courses |  | no | must exist |
| `rule_version` | int | yes | 1|2 |  | no | unique per course |
| `effective_from` | date | yes |  | date | no | rule applies to cohorts with start_date in [from, to] |
| `effective_to` | date | no | date or null (open-ended) | date | no | no gaps/overlaps between versions of a course |
| `min_required_content_pct` | int | yes | 80|90|100 | percent | no | share of REQUIRED video/reading items with a completion event |
| `min_weighted_score_pct` | int | yes | 60..75 | percent | no | sum(weight*best_percent)/sum(weight) |
| `grace_days_after_end` | int | yes | 14 | days | no | = cohort.access_end_date - end_date |
| `rule_status` | enum | yes | {active, superseded} |  | no | superseded iff effective_to not null |

## activity_events  (ActivityEvent)

Raw learning-platform event stream (as ingested; may contain duplicates / late data).

**Primary key:** `event_id`

**Foreign keys:** `enrollment_id` -> `enrollments.enrollment_id`; `learner_id` -> `learners.learner_id`; `course_id` -> `courses.course_id`; `content_id` -> `content_items.content_id` (optional); `attempt_id` -> `attempts.attempt_id` (optional)

| field | type | required | allowed values / format | unit | unique | validation rule |
|---|---|---|---|---|---|---|
| `event_id` | string | yes | EVT-<enrollment_id>-###### |  | yes | prefix = enrollment_id; seq reflects insertion order |
| `enrollment_id` | string | yes | FK enrollments (logical) |  | no | violations are labelled in ground truth (unenrolled_activity) |
| `learner_id` | string | yes | FK learners |  | no | must exist |
| `course_id` | string | yes | FK courses |  | no | must exist |
| `content_id` | string | no | FK content_items or null |  | no | null for session_start |
| `attempt_id` | string | no | FK attempts or null |  | no | only for assessment_start/submit |
| `event_type` | enum | yes | {session_start, content_view, video_play, video_complete, content_complete, assessment_start, assessment_submit, discussion_post, resource_download} |  | no | enum |
| `event_time_utc` | timestamp | yes | ISO-8601 UTC (device clock, offline-safe) | UTC | no | <= ingested_at_utc |
| `ingested_at_utc` | timestamp | yes | ISO-8601 UTC | UTC | no | >= event_time_utc; <= as_of |
| `client_tz_offset_min` | int | yes | -720..840 | minutes | no | UTC offset of the learner at event time |
| `reported_activity_date` | date | yes | YYYY-MM-DD | date | no | ETL-assigned day; should equal date(event_time_utc+offset) |
| `device_type` | enum | yes | {web, ios, android} |  | no | enum |
| `source` | enum | yes | {online, offline_sync} |  | no | offline_sync => queued on device, uploaded later |
| `duration_sec` | int | no | >=0 | seconds | no | session length / watch time / assessment time |
| `client_event_key` | string | yes | CK-<16 hex> |  | no | client idempotency key; duplicates share it; dedup key |

## course_outcomes  (CourseOutcome)

1:1 per enrollment. DERIVED from deduplicated valid events, attempts and the effective CompletionRule.

**Primary key:** `outcome_id`

**Foreign keys:** `enrollment_id` -> `enrollments.enrollment_id`; `learner_id` -> `learners.learner_id`; `course_id` -> `courses.course_id`; `cohort_id` -> `cohorts.cohort_id`; `rule_id` -> `completion_rules.rule_id`

| field | type | required | allowed values / format | unit | unique | validation rule |
|---|---|---|---|---|---|---|
| `outcome_id` | string | yes | OUT-<enrollment_id> |  | yes | 1:1 with enrolment |
| `enrollment_id` | string | yes | FK enrollments |  | yes | unique |
| `learner_id` | string | yes | FK learners |  | no |  |
| `course_id` | string | yes | FK courses |  | no |  |
| `cohort_id` | string | yes | FK cohorts |  | no |  |
| `rule_id` | string | yes | FK completion_rules |  | no | rule effective at cohort start_date |
| `evaluated_at` | timestamp | yes | as-of end of day UTC | UTC | no | = as_of 23:59:59Z |
| `required_content_items_total` | int | yes | >=1 | items | no | count of required video/reading items in course |
| `required_content_items_completed` | int | yes | 0..total | items | no | distinct required items with a completion event |
| `content_completion_pct` | float | yes | 0..100 | percent | no | = completed/total*100 |
| `required_assessments_total` | int | yes | >=1 | items | no |  |
| `required_assessments_passed` | int | yes | 0..total | items | no | distinct required assessments with a passing attempt |
| `weighted_score_pct` | float | yes | 0..100 | percent | no | sum(weight*best_percent)/sum(weight); unattempted = 0 |
| `total_attempts` | int | yes | >=0 |  | no | = count of attempts rows |
| `valid_event_count` | int | yes | >=0 |  | no | deduplicated, enrolled events |
| `active_days` | int | yes | >=0 | days | no | distinct local dates with a valid event |
| `active_weeks` | int | yes | >=0 | weeks | no | distinct cohort-relative weeks with a valid event |
| `first_activity_at` | timestamp | no |  | UTC | no | null iff no events |
| `last_activity_at` | timestamp | no |  | UTC | no | null iff no events |
| `completion_status` | enum | yes | {completed, in_progress, not_completed} |  | no | completed iff all three CompletionRule thresholds met |
| `completed_at` | timestamp | no |  | UTC | no | max of the three conditions' first-satisfied times; null unless completed |
| `completed_date_local` | date | no |  | date | no | learner-local date of completed_at |
| `days_to_complete` | float | no | >=0 | days | no | completed_at - enrolled_at |
| `engagement_band` | enum | yes | {inactive, low, medium, high} |  | no | inactive iff valid_event_count=0 else by active_weeks share |

## Ground truth (separate file, never an input)

`ground_truth/ground_truth.csv` columns: `gt_id`, `issue_type`, `label_class`, `entity_type`, `entity_id`, `related_entity_id`, `expected_decision`, `detail`

## Relationships and cardinality

| child | column | parent | cardinality |
|---|---|---|---|
| courses | instructor_id | instructors.instructor_id | Instructor 1:N Course |
| cohorts | course_id | courses.course_id | Course 1:N Cohort (draft courses have 0) |
| enrollments | learner_id | learners.learner_id | Learner 1:N Enrollment (bridge) |
| enrollments | course_id | courses.course_id | Course 1:N Enrollment (bridge) => Learner N:M Course |
| enrollments | cohort_id | cohorts.cohort_id | Cohort 1:N Enrollment |
| enrollment_status_history | enrollment_id | enrollments.enrollment_id | Enrollment 1:N history rows |
| content_items | course_id | courses.course_id | Course 1:N ContentItem |
| content_items | parent_content_id (optional) | content_items.content_id | ContentItem 1:N ContentItem (module->leaf) |
| assessments | course_id | courses.course_id | Course 1:N Assessment |
| assessments | content_id | content_items.content_id | ContentItem 1:0..1 Assessment |
| attempts | enrollment_id | enrollments.enrollment_id | Enrollment 1:N Attempt |
| attempts | assessment_id | assessments.assessment_id | Assessment 1:N Attempt |
| completion_rules | course_id | courses.course_id | Course 1:N CompletionRule (versioned) |
| activity_events | enrollment_id | enrollments.enrollment_id | Enrollment 1:N ActivityEvent (orphans = labelled anomaly) |
| activity_events | learner_id | learners.learner_id | Learner 1:N ActivityEvent |
| activity_events | course_id | courses.course_id | Course 1:N ActivityEvent |
| activity_events | content_id (optional) | content_items.content_id | ContentItem 1:N ActivityEvent (optional) |
| activity_events | attempt_id (optional) | attempts.attempt_id | Attempt 1:0..2 ActivityEvent (start/submit) |
| course_outcomes | enrollment_id | enrollments.enrollment_id | Enrollment 1:1 CourseOutcome |
| course_outcomes | learner_id | learners.learner_id |  |
| course_outcomes | course_id | courses.course_id |  |
| course_outcomes | cohort_id | cohorts.cohort_id |  |
| course_outcomes | rule_id | completion_rules.rule_id | CompletionRule 1:N CourseOutcome |
