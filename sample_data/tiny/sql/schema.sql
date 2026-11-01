-- Generated from edu_synth/schema.py. SQLite-compatible; booleans stored as 0/1 (CSV uses true/false).
-- NOTE: activity_events.enrollment_id FK is declared but the seed deliberately contains labelled
-- orphan rows (issue_type=unenrolled_activity); load with PRAGMA foreign_keys=OFF.

CREATE TABLE learners (
  learner_id TEXT NOT NULL PRIMARY KEY,
  signup_date TEXT NOT NULL,
  country_code TEXT NOT NULL,
  timezone TEXT NOT NULL,
  preferred_device TEXT NOT NULL,
  age_band TEXT NOT NULL,
  signup_channel TEXT NOT NULL,
  account_status TEXT NOT NULL
);
CREATE TABLE instructors (
  instructor_id TEXT NOT NULL PRIMARY KEY,
  department TEXT NOT NULL,
  joined_date TEXT NOT NULL
);
CREATE TABLE courses (
  course_id TEXT NOT NULL PRIMARY KEY,
  title TEXT NOT NULL,
  category TEXT NOT NULL,
  level TEXT NOT NULL,
  language TEXT NOT NULL,
  duration_weeks INTEGER NOT NULL,
  instructor_id TEXT NOT NULL,
  course_status TEXT NOT NULL,
  created_date TEXT NOT NULL,
  FOREIGN KEY (instructor_id) REFERENCES instructors(instructor_id)
);
CREATE TABLE cohorts (
  cohort_id TEXT NOT NULL PRIMARY KEY,
  course_id TEXT NOT NULL,
  cohort_code TEXT NOT NULL,
  start_date TEXT NOT NULL,
  end_date TEXT NOT NULL,
  access_end_date TEXT NOT NULL,
  delivery_mode TEXT NOT NULL,
  capacity INTEGER NOT NULL,
  cohort_status TEXT NOT NULL,
  FOREIGN KEY (course_id) REFERENCES courses(course_id)
);
CREATE TABLE enrollments (
  enrollment_id TEXT NOT NULL PRIMARY KEY,
  learner_id TEXT NOT NULL,
  course_id TEXT NOT NULL,
  cohort_id TEXT NOT NULL,
  enrolled_at TEXT NOT NULL,
  enrollment_source TEXT NOT NULL,
  current_status TEXT NOT NULL,
  status_updated_at TEXT NOT NULL,
  FOREIGN KEY (learner_id) REFERENCES learners(learner_id),
  FOREIGN KEY (course_id) REFERENCES courses(course_id),
  FOREIGN KEY (cohort_id) REFERENCES cohorts(cohort_id)
);
CREATE TABLE enrollment_status_history (
  history_id TEXT NOT NULL PRIMARY KEY,
  enrollment_id TEXT NOT NULL,
  from_status TEXT,
  to_status TEXT NOT NULL,
  changed_at TEXT NOT NULL,
  changed_by TEXT NOT NULL,
  reason_code TEXT NOT NULL,
  FOREIGN KEY (enrollment_id) REFERENCES enrollments(enrollment_id)
);
CREATE TABLE content_items (
  content_id TEXT NOT NULL PRIMARY KEY,
  course_id TEXT NOT NULL,
  parent_content_id TEXT,
  content_type TEXT NOT NULL,
  title TEXT NOT NULL,
  hierarchy_level INTEGER NOT NULL,
  sequence_no INTEGER NOT NULL,
  course_order INTEGER NOT NULL,
  week_number INTEGER NOT NULL,
  release_offset_days INTEGER NOT NULL,
  is_required INTEGER NOT NULL,
  est_minutes INTEGER NOT NULL,
  content_status TEXT NOT NULL,
  FOREIGN KEY (course_id) REFERENCES courses(course_id),
  FOREIGN KEY (parent_content_id) REFERENCES content_items(content_id)
);
CREATE TABLE assessments (
  assessment_id TEXT NOT NULL PRIMARY KEY,
  course_id TEXT NOT NULL,
  content_id TEXT NOT NULL,
  assessment_type TEXT NOT NULL,
  title TEXT NOT NULL,
  max_score INTEGER NOT NULL,
  pass_score INTEGER NOT NULL,
  weight_pct INTEGER NOT NULL,
  is_required INTEGER NOT NULL,
  max_attempts INTEGER NOT NULL,
  time_limit_min INTEGER,
  available_offset_days INTEGER NOT NULL,
  due_offset_days INTEGER NOT NULL,
  assessment_status TEXT NOT NULL,
  FOREIGN KEY (course_id) REFERENCES courses(course_id),
  FOREIGN KEY (content_id) REFERENCES content_items(content_id)
);
CREATE TABLE attempts (
  attempt_id TEXT NOT NULL PRIMARY KEY,
  enrollment_id TEXT NOT NULL,
  assessment_id TEXT NOT NULL,
  attempt_no INTEGER NOT NULL,
  started_at TEXT NOT NULL,
  submitted_at TEXT,
  score REAL,
  max_score INTEGER NOT NULL,
  percent_score REAL,
  passed INTEGER,
  is_late INTEGER NOT NULL,
  attempt_status TEXT NOT NULL,
  duration_sec INTEGER,
  FOREIGN KEY (enrollment_id) REFERENCES enrollments(enrollment_id),
  FOREIGN KEY (assessment_id) REFERENCES assessments(assessment_id)
);
CREATE TABLE completion_rules (
  rule_id TEXT NOT NULL PRIMARY KEY,
  course_id TEXT NOT NULL,
  rule_version INTEGER NOT NULL,
  effective_from TEXT NOT NULL,
  effective_to TEXT,
  min_required_content_pct INTEGER NOT NULL,
  min_weighted_score_pct INTEGER NOT NULL,
  grace_days_after_end INTEGER NOT NULL,
  rule_status TEXT NOT NULL,
  FOREIGN KEY (course_id) REFERENCES courses(course_id)
);
CREATE TABLE activity_events (
  event_id TEXT NOT NULL PRIMARY KEY,
  enrollment_id TEXT NOT NULL,
  learner_id TEXT NOT NULL,
  course_id TEXT NOT NULL,
  content_id TEXT,
  attempt_id TEXT,
  event_type TEXT NOT NULL,
  event_time_utc TEXT NOT NULL,
  ingested_at_utc TEXT NOT NULL,
  client_tz_offset_min INTEGER NOT NULL,
  reported_activity_date TEXT NOT NULL,
  device_type TEXT NOT NULL,
  source TEXT NOT NULL,
  duration_sec INTEGER,
  client_event_key TEXT NOT NULL,
  FOREIGN KEY (enrollment_id) REFERENCES enrollments(enrollment_id),
  FOREIGN KEY (learner_id) REFERENCES learners(learner_id),
  FOREIGN KEY (course_id) REFERENCES courses(course_id),
  FOREIGN KEY (content_id) REFERENCES content_items(content_id),
  FOREIGN KEY (attempt_id) REFERENCES attempts(attempt_id)
);
CREATE TABLE course_outcomes (
  outcome_id TEXT NOT NULL PRIMARY KEY,
  enrollment_id TEXT NOT NULL,
  learner_id TEXT NOT NULL,
  course_id TEXT NOT NULL,
  cohort_id TEXT NOT NULL,
  rule_id TEXT NOT NULL,
  evaluated_at TEXT NOT NULL,
  required_content_items_total INTEGER NOT NULL,
  required_content_items_completed INTEGER NOT NULL,
  content_completion_pct REAL NOT NULL,
  required_assessments_total INTEGER NOT NULL,
  required_assessments_passed INTEGER NOT NULL,
  weighted_score_pct REAL NOT NULL,
  total_attempts INTEGER NOT NULL,
  valid_event_count INTEGER NOT NULL,
  active_days INTEGER NOT NULL,
  active_weeks INTEGER NOT NULL,
  first_activity_at TEXT,
  last_activity_at TEXT,
  completion_status TEXT NOT NULL,
  completed_at TEXT,
  completed_date_local TEXT,
  days_to_complete REAL,
  engagement_band TEXT NOT NULL,
  FOREIGN KEY (enrollment_id) REFERENCES enrollments(enrollment_id),
  FOREIGN KEY (learner_id) REFERENCES learners(learner_id),
  FOREIGN KEY (course_id) REFERENCES courses(course_id),
  FOREIGN KEY (cohort_id) REFERENCES cohorts(cohort_id),
  FOREIGN KEY (rule_id) REFERENCES completion_rules(rule_id)
);

CREATE INDEX ix_events_enr ON activity_events(enrollment_id);
CREATE INDEX ix_events_key ON activity_events(client_event_key);
CREATE INDEX ix_enr_cohort ON enrollments(cohort_id);
CREATE INDEX ix_attempt_enr ON attempts(enrollment_id);
