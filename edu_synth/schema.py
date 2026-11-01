"""Data dictionary = single source of truth for columns, enums, PK/FK and DDL generation."""
from __future__ import annotations

from collections import OrderedDict

from . import config as C

# F(name, type, required, allowed/format, unit, unique, validation rule)
def F(name, typ, req, allowed="", unit="", unique=False, rule=""):
    return dict(name=name, type=typ, required=req, allowed=allowed, unit=unit, unique=unique, rule=rule)

ENUM = lambda xs: "{" + ", ".join(xs) + "}"

TABLES: "OrderedDict[str, dict]" = OrderedDict()

TABLES["learners"] = dict(entity="Learner", pk="learner_id", desc="Registered person taking courses. No personal data (synthetic, de-identified).", fields=[
    F("learner_id", "string", True, "LRN-######", "", True, "regex ^LRN-\\d{6}$; immutable"),
    F("signup_date", "date", True, "2025-09-01..2026-04-15", "date", False, "<= first enrolment date - 1 day"),
    F("country_code", "string", True, "ISO-3166 alpha-2 (ZZ = unknown/UTC)", "", False, "consistent with timezone"),
    F("timezone", "string", True, "IANA tz name", "", False, "valid IANA zone; drives local-date derivation"),
    F("preferred_device", "enum", True, ENUM(C.DEVICES), "", False, "enum"),
    F("age_band", "enum", True, ENUM(C.AGE_BANDS), "", False, "enum"),
    F("signup_channel", "enum", True, ENUM(C.SIGNUP_CHANNELS), "", False, "enum"),
    F("account_status", "enum", True, ENUM(C.ACCOUNT_STATUS), "", False, "closed accounts have no activity"),
])
TABLES["instructors"] = dict(entity="Instructor (supporting)", pk="instructor_id", desc="Course owner/teacher (actor).", fields=[
    F("instructor_id", "string", True, "INS-####", "", True, "regex ^INS-\\d{4}$"),
    F("department", "string", True, "free text (10 categories)", "", False, ""),
    F("joined_date", "date", True, "2018-01-01..2025-12-31", "date", False, ""),
])
TABLES["courses"] = dict(entity="Course", pk="course_id", desc="Course master. Content hierarchy lives in content_items.", fields=[
    F("course_id", "string", True, "CRS-######", "", True, "regex ^CRS-\\d{6}$"),
    F("title", "string", True, "", "", True, "non-empty"),
    F("category", "string", True, "10 categories", "", False, ""),
    F("level", "enum", True, ENUM(C.LEVELS), "", False, "enum"),
    F("language", "string", True, "en|hi|es|pt", "", False, ""),
    F("duration_weeks", "int", True, "6|8|10", "weeks", False, "= cohort (end_date-start_date+1)/7"),
    F("instructor_id", "string", True, "FK instructors", "", False, "must exist"),
    F("course_status", "enum", True, ENUM(C.COURSE_STATUS), "", False, "draft => no cohorts/enrolments; archived => all cohorts closed"),
    F("created_date", "date", True, "2025-01-01..2025-12-31", "date", False, "before first cohort start"),
])
TABLES["cohorts"] = dict(entity="Cohort", pk="cohort_id", desc="Scheduled run of a course; comparison unit for analytics.", fields=[
    F("cohort_id", "string", True, "COH-######", "", True, "regex ^COH-\\d{6}$"),
    F("course_id", "string", True, "FK courses", "", False, "must exist, course not draft"),
    F("cohort_code", "string", True, "<course_id>-<YYYY>W<ww>", "", True, "unique"),
    F("start_date", "date", True, "Mondays 2026-01-05..2026-09-14", "date", False, "start_date <= end_date < access_end_date"),
    F("end_date", "date", True, "", "date", False, "= start_date + duration_weeks*7 - 1"),
    F("access_end_date", "date", True, "", "date", False, "= end_date + grace_days (14); events after it are invalid"),
    F("delivery_mode", "enum", True, ENUM(C.DELIVERY_MODES), "", False, "enum"),
    F("capacity", "int", True, "40..400", "learners", False, ">= 1"),
    F("cohort_status", "enum", True, ENUM(C.COHORT_STATUS), "", False, "closed iff access_end_date < as_of date"),
])
TABLES["enrollments"] = dict(entity="Enrollment (bridge Learner<->Course, scoped to Cohort)", pk="enrollment_id", desc="N:M bridge between Learner and Course; current state is the latest row of enrollment_status_history.", fields=[
    F("enrollment_id", "string", True, "ENR-<learner_id>-<course_id>", "", True, "= 'ENR-'+learner_id+'-'+course_id; one per learner/course"),
    F("learner_id", "string", True, "FK learners", "", False, "must exist"),
    F("course_id", "string", True, "FK courses", "", False, "must exist; = cohort.course_id"),
    F("cohort_id", "string", True, "FK cohorts", "", False, "must exist"),
    F("enrolled_at", "timestamp", True, "ISO-8601 UTC", "UTC", False, ">= signup_date+1d; <= cohort start+10d"),
    F("enrollment_source", "enum", True, ENUM(C.ENR_SOURCES), "", False, "enum"),
    F("current_status", "enum", True, ENUM(C.ENR_STATUSES), "", False, "= to_status of latest history row"),
    F("status_updated_at", "timestamp", True, "ISO-8601 UTC", "UTC", False, "= changed_at of latest history row"),
])
TABLES["enrollment_status_history"] = dict(entity="EnrollmentStatusHistory (event log of lifecycle)", pk="history_id", desc="Append-only lifecycle log; never overwritten.", fields=[
    F("history_id", "string", True, "ESH-<enrollment_id>-NN", "", True, "NN = 1-based sequence per enrollment"),
    F("enrollment_id", "string", True, "FK enrollments", "", False, "must exist"),
    F("from_status", "enum", False, ENUM(C.ENR_STATUSES) + " or null", "", False, "null only for first row"),
    F("to_status", "enum", True, ENUM(C.ENR_STATUSES), "", False, "transition must be in LEGAL_TRANSITIONS"),
    F("changed_at", "timestamp", True, "ISO-8601 UTC", "UTC", False, "non-decreasing per enrollment; <= as_of"),
    F("changed_by", "enum", True, ENUM(C.HISTORY_ACTORS), "", False, "enum"),
    F("reason_code", "string", True, "enrollment_created|first_activity|completion_rule_met|learner_request|inactivity_21d|access_window_closed", "", False, ""),
])
TABLES["content_items"] = dict(entity="ContentItem", pk="content_id", desc="Course content hierarchy: module (level 1) -> leaf items (level 2).", fields=[
    F("content_id", "string", True, "CNT-#######", "", True, "regex ^CNT-\\d{7}$"),
    F("course_id", "string", True, "FK courses", "", False, "must exist"),
    F("parent_content_id", "string", False, "FK content_items (self) or null", "", False, "null iff hierarchy_level=1; parent must be same course"),
    F("content_type", "enum", True, ENUM(C.CONTENT_TYPES), "", False, "module only at level 1"),
    F("title", "string", True, "", "", False, ""),
    F("hierarchy_level", "int", True, "1|2", "", False, ""),
    F("sequence_no", "int", True, ">=1", "", False, "order within parent"),
    F("course_order", "int", True, ">=1", "", False, "global order within course; unique per course"),
    F("week_number", "int", True, "1..duration_weeks", "week", False, "= release_offset_days//7+1"),
    F("release_offset_days", "int", True, ">=0", "days after cohort start", False, "unlock time"),
    F("is_required", "bool", True, "true|false", "", False, "video/reading always true; discussion false; assessments follow assessments.is_required"),
    F("est_minutes", "int", True, "5..120", "minutes", False, ">0"),
    F("content_status", "enum", True, ENUM(C.CONTENT_STATUS), "", False, "draft iff course draft"),
])
TABLES["assessments"] = dict(entity="Assessment", pk="assessment_id", desc="Graded item attached 1:1 to a quiz/assignment/final_exam content item.", fields=[
    F("assessment_id", "string", True, "ASM-2026-######", "", True, "regex ^ASM-2026-\\d{6}$"),
    F("course_id", "string", True, "FK courses", "", False, "must exist"),
    F("content_id", "string", True, "FK content_items", "", True, "1:1; content_type in {quiz, assignment, final_exam}"),
    F("assessment_type", "enum", True, ENUM(C.ASSESSMENT_TYPES), "", False, "= content_type"),
    F("title", "string", True, "", "", False, ""),
    F("max_score", "int", True, "quiz 20, assignment 50, final_exam 100", "points", False, ">0"),
    F("pass_score", "int", True, "ceil(max_score*pass_pct)", "points", False, "0 < pass_score <= max_score"),
    F("weight_pct", "int", True, "1..60", "percent", False, "weights of a course sum to exactly 100"),
    F("is_required", "bool", True, "true|false", "", False, "final_exam always true"),
    F("max_attempts", "int", True, "quiz 3, assignment 2, final_exam 2", "attempts", False, ">=1"),
    F("time_limit_min", "int", False, "quiz 20, final_exam 90, assignment null", "minutes", False, ""),
    F("available_offset_days", "int", True, ">=0", "days after cohort start", False, "<= due_offset_days"),
    F("due_offset_days", "int", True, "", "days after cohort start", False, "<= duration_weeks*7-1"),
    F("assessment_status", "enum", True, ENUM(C.ASSESSMENT_STATUS), "", False, "draft iff course draft"),
])
TABLES["attempts"] = dict(entity="Attempt", pk="attempt_id", desc="One try by an enrolment at an assessment. Repeated attempts are separate rows (history preserved).", fields=[
    F("attempt_id", "string", True, "ATT-########", "", True, "regex ^ATT-\\d{8}$"),
    F("enrollment_id", "string", True, "FK enrollments", "", False, "must exist"),
    F("assessment_id", "string", True, "FK assessments", "", False, "assessment.course_id = enrolment.course_id"),
    F("attempt_no", "int", True, "1..max_attempts", "", False, "contiguous per (enrollment, assessment)"),
    F("started_at", "timestamp", True, "ISO-8601 UTC", "UTC", False, "> enrolled_at; < access end"),
    F("submitted_at", "timestamp", False, "ISO-8601 UTC or null", "UTC", False, ">= started_at; null iff abandoned"),
    F("score", "float", False, "0..max_score step 0.5", "points", False, "null iff abandoned"),
    F("max_score", "int", True, "", "points", False, "= assessment.max_score"),
    F("percent_score", "float", False, "0..100", "percent", False, "= round(score/max_score*100, 2)"),
    F("passed", "bool", False, "true|false|null", "", False, "= score >= assessment.pass_score; null iff abandoned"),
    F("is_late", "bool", True, "true|false", "", False, "true iff submitted after due date end (UTC)"),
    F("attempt_status", "enum", True, ENUM(C.ATTEMPT_STATUS), "", False, "enum"),
    F("duration_sec", "int", False, ">=0", "seconds", False, "= submitted_at - started_at; null iff abandoned"),
])
TABLES["completion_rules"] = dict(entity="CompletionRule", pk="rule_id", desc="Versioned, effective-dated rule defining course completion.", fields=[
    F("rule_id", "string", True, "CRL-######", "", True, "regex ^CRL-\\d{6}$"),
    F("course_id", "string", True, "FK courses", "", False, "must exist"),
    F("rule_version", "int", True, "1|2", "", False, "unique per course"),
    F("effective_from", "date", True, "", "date", False, "rule applies to cohorts with start_date in [from, to]"),
    F("effective_to", "date", False, "date or null (open-ended)", "date", False, "no gaps/overlaps between versions of a course"),
    F("min_required_content_pct", "int", True, "80|90|100", "percent", False, "share of REQUIRED video/reading items with a completion event"),
    F("min_weighted_score_pct", "int", True, "60..75", "percent", False, "sum(weight*best_percent)/sum(weight)"),
    F("grace_days_after_end", "int", True, "14", "days", False, "= cohort.access_end_date - end_date"),
    F("rule_status", "enum", True, ENUM(C.RULE_STATUS), "", False, "superseded iff effective_to not null"),
])
TABLES["activity_events"] = dict(entity="ActivityEvent", pk="event_id", desc="Raw learning-platform event stream (as ingested; may contain duplicates / late data).", fields=[
    F("event_id", "string", True, "EVT-<enrollment_id>-######", "", True, "prefix = enrollment_id; seq reflects insertion order"),
    F("enrollment_id", "string", True, "FK enrollments (logical)", "", False, "violations are labelled in ground truth (unenrolled_activity)"),
    F("learner_id", "string", True, "FK learners", "", False, "must exist"),
    F("course_id", "string", True, "FK courses", "", False, "must exist"),
    F("content_id", "string", False, "FK content_items or null", "", False, "null for session_start"),
    F("attempt_id", "string", False, "FK attempts or null", "", False, "only for assessment_start/submit"),
    F("event_type", "enum", True, ENUM(C.EVENT_TYPES), "", False, "enum"),
    F("event_time_utc", "timestamp", True, "ISO-8601 UTC (device clock, offline-safe)", "UTC", False, "<= ingested_at_utc"),
    F("ingested_at_utc", "timestamp", True, "ISO-8601 UTC", "UTC", False, ">= event_time_utc; <= as_of"),
    F("client_tz_offset_min", "int", True, "-720..840", "minutes", False, "UTC offset of the learner at event time"),
    F("reported_activity_date", "date", True, "YYYY-MM-DD", "date", False, "ETL-assigned day; should equal date(event_time_utc+offset)"),
    F("device_type", "enum", True, ENUM(C.DEVICES), "", False, "enum"),
    F("source", "enum", True, ENUM(C.SOURCES), "", False, "offline_sync => queued on device, uploaded later"),
    F("duration_sec", "int", False, ">=0", "seconds", False, "session length / watch time / assessment time"),
    F("client_event_key", "string", True, "CK-<16 hex>", "", False, "client idempotency key; duplicates share it; dedup key"),
])
TABLES["course_outcomes"] = dict(entity="CourseOutcome", pk="outcome_id", desc="1:1 per enrollment. DERIVED from deduplicated valid events, attempts and the effective CompletionRule.", fields=[
    F("outcome_id", "string", True, "OUT-<enrollment_id>", "", True, "1:1 with enrolment"),
    F("enrollment_id", "string", True, "FK enrollments", "", True, "unique"),
    F("learner_id", "string", True, "FK learners", "", False, ""),
    F("course_id", "string", True, "FK courses", "", False, ""),
    F("cohort_id", "string", True, "FK cohorts", "", False, ""),
    F("rule_id", "string", True, "FK completion_rules", "", False, "rule effective at cohort start_date"),
    F("evaluated_at", "timestamp", True, "as-of end of day UTC", "UTC", False, "= as_of 23:59:59Z"),
    F("required_content_items_total", "int", True, ">=1", "items", False, "count of required video/reading items in course"),
    F("required_content_items_completed", "int", True, "0..total", "items", False, "distinct required items with a completion event"),
    F("content_completion_pct", "float", True, "0..100", "percent", False, "= completed/total*100"),
    F("required_assessments_total", "int", True, ">=1", "items", False, ""),
    F("required_assessments_passed", "int", True, "0..total", "items", False, "distinct required assessments with a passing attempt"),
    F("weighted_score_pct", "float", True, "0..100", "percent", False, "sum(weight*best_percent)/sum(weight); unattempted = 0"),
    F("total_attempts", "int", True, ">=0", "", False, "= count of attempts rows"),
    F("valid_event_count", "int", True, ">=0", "", False, "deduplicated, enrolled events"),
    F("active_days", "int", True, ">=0", "days", False, "distinct local dates with a valid event"),
    F("active_weeks", "int", True, ">=0", "weeks", False, "distinct cohort-relative weeks with a valid event"),
    F("first_activity_at", "timestamp", False, "", "UTC", False, "null iff no events"),
    F("last_activity_at", "timestamp", False, "", "UTC", False, "null iff no events"),
    F("completion_status", "enum", True, ENUM(C.OUTCOME_STATUS), "", False, "completed iff all three CompletionRule thresholds met"),
    F("completed_at", "timestamp", False, "", "UTC", False, "max of the three conditions' first-satisfied times; null unless completed"),
    F("completed_date_local", "date", False, "", "date", False, "learner-local date of completed_at"),
    F("days_to_complete", "float", False, ">=0", "days", False, "completed_at - enrolled_at"),
    F("engagement_band", "enum", True, ENUM(C.ENGAGEMENT_BANDS), "", False, "inactive iff valid_event_count=0 else by active_weeks share"),
])

# (child table, child column, parent table, parent column, nullable, cardinality)
FKS = [
    ("courses", "instructor_id", "instructors", "instructor_id", False, "Instructor 1:N Course"),
    ("cohorts", "course_id", "courses", "course_id", False, "Course 1:N Cohort (draft courses have 0)"),
    ("enrollments", "learner_id", "learners", "learner_id", False, "Learner 1:N Enrollment (bridge)"),
    ("enrollments", "course_id", "courses", "course_id", False, "Course 1:N Enrollment (bridge) => Learner N:M Course"),
    ("enrollments", "cohort_id", "cohorts", "cohort_id", False, "Cohort 1:N Enrollment"),
    ("enrollment_status_history", "enrollment_id", "enrollments", "enrollment_id", False, "Enrollment 1:N history rows"),
    ("content_items", "course_id", "courses", "course_id", False, "Course 1:N ContentItem"),
    ("content_items", "parent_content_id", "content_items", "content_id", True, "ContentItem 1:N ContentItem (module->leaf)"),
    ("assessments", "course_id", "courses", "course_id", False, "Course 1:N Assessment"),
    ("assessments", "content_id", "content_items", "content_id", False, "ContentItem 1:0..1 Assessment"),
    ("attempts", "enrollment_id", "enrollments", "enrollment_id", False, "Enrollment 1:N Attempt"),
    ("attempts", "assessment_id", "assessments", "assessment_id", False, "Assessment 1:N Attempt"),
    ("completion_rules", "course_id", "courses", "course_id", False, "Course 1:N CompletionRule (versioned)"),
    ("activity_events", "enrollment_id", "enrollments", "enrollment_id", False, "Enrollment 1:N ActivityEvent (orphans = labelled anomaly)"),
    ("activity_events", "learner_id", "learners", "learner_id", False, "Learner 1:N ActivityEvent"),
    ("activity_events", "course_id", "courses", "course_id", False, "Course 1:N ActivityEvent"),
    ("activity_events", "content_id", "content_items", "content_id", True, "ContentItem 1:N ActivityEvent (optional)"),
    ("activity_events", "attempt_id", "attempts", "attempt_id", True, "Attempt 1:0..2 ActivityEvent (start/submit)"),
    ("course_outcomes", "enrollment_id", "enrollments", "enrollment_id", False, "Enrollment 1:1 CourseOutcome"),
    ("course_outcomes", "learner_id", "learners", "learner_id", False, ""),
    ("course_outcomes", "course_id", "courses", "course_id", False, ""),
    ("course_outcomes", "cohort_id", "cohorts", "cohort_id", False, ""),
    ("course_outcomes", "rule_id", "completion_rules", "rule_id", False, "CompletionRule 1:N CourseOutcome"),
]

GROUND_TRUTH_COLUMNS = ["gt_id", "issue_type", "label_class", "entity_type", "entity_id",
                        "related_entity_id", "expected_decision", "detail"]

SQL_TYPES = {"string": "TEXT", "enum": "TEXT", "date": "TEXT", "timestamp": "TEXT",
             "int": "INTEGER", "float": "REAL", "bool": "INTEGER"}


def columns(table: str) -> list[str]:
    return [f["name"] for f in TABLES[table]["fields"]]


def ddl() -> str:
    out = ["-- Generated from edu_synth/schema.py. SQLite-compatible; booleans stored as 0/1 (CSV uses true/false).",
           "-- NOTE: activity_events.enrollment_id FK is declared but the seed deliberately contains labelled",
           "-- orphan rows (issue_type=unenrolled_activity); load with PRAGMA foreign_keys=OFF.", ""]
    for t, spec in TABLES.items():
        lines = []
        for f in spec["fields"]:
            nn = " NOT NULL" if f["required"] else ""
            pk = " PRIMARY KEY" if f["name"] == spec["pk"] else ""
            lines.append(f"  {f['name']} {SQL_TYPES[f['type']]}{nn}{pk}")
        for (ct, cc, pt, pc, _nullable, _card) in FKS:
            if ct == t:
                lines.append(f"  FOREIGN KEY ({cc}) REFERENCES {pt}({pc})")
        out.append(f"CREATE TABLE {t} (\n" + ",\n".join(lines) + "\n);")
    out += ["", "CREATE INDEX ix_events_enr ON activity_events(enrollment_id);",
            "CREATE INDEX ix_events_key ON activity_events(client_event_key);",
            "CREATE INDEX ix_enr_cohort ON enrollments(cohort_id);",
            "CREATE INDEX ix_attempt_enr ON attempts(enrollment_id);", ""]
    return "\n".join(out)


def dictionary_markdown() -> str:
    out = ["# Data dictionary", "",
           "Generated from `edu_synth/schema.py` (the same definitions drive validation and DDL).", "",
           "Timestamps are ISO-8601 UTC (`YYYY-MM-DDTHH:MM:SSZ`), dates are `YYYY-MM-DD`, booleans are `true`/`false`, null = empty cell.", ""]
    for t, spec in TABLES.items():
        out += [f"## {t}  ({spec['entity']})", "", spec["desc"], "", f"**Primary key:** `{spec['pk']}`", ""]
        fks = [x for x in FKS if x[0] == t]
        if fks:
            out.append("**Foreign keys:** " + "; ".join(f"`{c}` -> `{p}.{pc}`{' (optional)' if n else ''}" for (_, c, p, pc, n, _) in fks))
            out.append("")
        out += ["| field | type | required | allowed values / format | unit | unique | validation rule |", "|---|---|---|---|---|---|---|"]
        for f in spec["fields"]:
            out.append(f"| `{f['name']}` | {f['type']} | {'yes' if f['required'] else 'no'} | {f['allowed']} | {f['unit']} | "
                       f"{'yes' if f['unique'] or f['name'] == spec['pk'] else 'no'} | {f['rule']} |")
        out.append("")
    out += ["## Ground truth (separate file, never an input)", "",
            "`ground_truth/ground_truth.csv` columns: " + ", ".join(f"`{c}`" for c in GROUND_TRUTH_COLUMNS), "",
            "## Relationships and cardinality", "", "| child | column | parent | cardinality |", "|---|---|---|---|"]
    for (ct, cc, pt, pc, n, card) in FKS:
        out.append(f"| {ct} | {cc}{' (optional)' if n else ''} | {pt}.{pc} | {card} |")
    return "\n".join(out) + "\n"


def er_mermaid() -> str:
    lines = ["erDiagram"]
    rel = {("instructors", "courses"): "||--o{", ("courses", "cohorts"): "||--o{", ("learners", "enrollments"): "||--o{",
           ("courses", "enrollments"): "||--o{", ("cohorts", "enrollments"): "||--o{",
           ("enrollments", "enrollment_status_history"): "||--|{", ("courses", "content_items"): "||--|{",
           ("content_items", "content_items"): "|o--o{", ("content_items", "assessments"): "||--o|",
           ("enrollments", "attempts"): "||--o{", ("assessments", "attempts"): "||--o{",
           ("courses", "completion_rules"): "||--|{", ("enrollments", "activity_events"): "||--o{",
           ("attempts", "activity_events"): "|o--o{", ("enrollments", "course_outcomes"): "||--||",
           ("completion_rules", "course_outcomes"): "||--o{"}
    for (p, c), sym in rel.items():
        lines.append(f"    {p} {sym} {c} : has")
    return "\n".join(lines)
