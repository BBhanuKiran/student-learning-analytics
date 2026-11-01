"""Central configuration: seed, scale presets, anomaly rates, enums, ID helpers."""
from __future__ import annotations

import zlib
from dataclasses import dataclass, replace

import numpy as np

SEED = 20261022
AS_OF_DATE = "2026-10-22"          # data extraction date (UTC). No event/ingest after 23:59:59Z of this day.
GRACE_DAYS = 14                    # access window after cohort end_date
ID_YEAR = 2026
LATE_ARRIVAL_HOURS = 72            # ingest lag above which an offline-sync event is "late"
DEDUP_KEY = "client_event_key"
COMPARISON_WINDOW_WEEKS = 8        # engagement window used for all cohort comparisons


@dataclass(frozen=True)
class Scale:
    learners: int
    courses: int
    enrollments: int
    events: int          # total ActivityEvent rows INCLUDING injected anomalous rows


PRESETS = {
    "full": Scale(20_000, 500, 100_000, 2_000_000),
    "starter": Scale(1_000, 25, 5_000, 100_000),
    "tiny": Scale(200, 10, 1_000, 20_000),
}


def resolve_scale(name: str, **overrides) -> Scale:
    sc = PRESETS[name]
    ov = {k: v for k, v in overrides.items() if v is not None}
    return replace(sc, **ov) if ov else sc


# Injected anomaly rates (fractions of the relevant population)
DUP_RATE = 0.02            # of total events -> duplicate rows (extra rows)
UNENROLLED_RATE = 0.004    # of total events -> events from unenrolled learner/course pairs (extra rows)
TZ_RATE = 0.005            # of baseline events -> reported_activity_date uses UTC instead of local date
COMPLETION_ANOM_RATE = 0.012   # of enrollments -> 'completed' recorded before required assessment satisfied

# ----- Enumerations (single source of truth, reused by data dictionary + validator) -----
EVENT_TYPES = ["session_start", "content_view", "video_play", "video_complete", "content_complete",
               "assessment_start", "assessment_submit", "discussion_post", "resource_download"]
COMPLETION_EVENT_TYPES = ["video_complete", "content_complete"]
CONTENT_TYPES = ["module", "video", "reading", "discussion", "quiz", "assignment", "final_exam"]
ASSESSMENT_TYPES = ["quiz", "assignment", "final_exam"]
ENR_STATUSES = ["enrolled", "active", "completed", "dropped", "expired"]
TERMINAL = {"completed", "dropped", "expired"}
LEGAL_TRANSITIONS = {
    None: {"enrolled"},
    "enrolled": {"active", "dropped", "expired"},
    "active": {"completed", "dropped", "expired"},
    "completed": set(), "dropped": set(), "expired": set(),
}
ENR_SOURCES = ["self_enrol", "employer_assigned", "admin_import"]
DEVICES = ["web", "ios", "android"]
SOURCES = ["online", "offline_sync"]
COURSE_STATUS = ["draft", "published", "archived"]
COHORT_STATUS = ["running", "closed"]
DELIVERY_MODES = ["instructor_led", "self_paced"]
LEVELS = ["beginner", "intermediate", "advanced"]
ACCOUNT_STATUS = ["active", "closed"]
AGE_BANDS = ["18-24", "25-34", "35-44", "45+"]
SIGNUP_CHANNELS = ["organic", "employer", "university", "referral"]
ATTEMPT_STATUS = ["submitted", "abandoned"]
OUTCOME_STATUS = ["completed", "in_progress", "not_completed"]
ENGAGEMENT_BANDS = ["inactive", "low", "medium", "high"]
RULE_STATUS = ["active", "superseded"]
CONTENT_STATUS = ["draft", "published"]
ASSESSMENT_STATUS = ["draft", "published"]
HISTORY_ACTORS = ["learner", "system", "admin"]
ISSUE_TYPES = ["duplicate_event", "unenrolled_activity", "completion_before_required_assessment",
               "timezone_day_shift", "inactive_learner", "late_arriving_event"]


# ----- ID helpers (deterministic, zero-padded, immutable) -----
def lrn(i): return f"LRN-{i:06d}"
def crs(i): return f"CRS-{i:06d}"
def coh(i): return f"COH-{i:06d}"
def cnt(i): return f"CNT-{i:07d}"
def asm(i): return f"ASM-{ID_YEAR}-{i:06d}"
def crl(i): return f"CRL-{i:06d}"
def ins(i): return f"INS-{i:04d}"
def att(i): return f"ATT-{i:08d}"
def enr(l, c): return f"ENR-{l}-{c}"
def evt(e, n): return f"EVT-{e}-{n:06d}"


def rng(seed: int, name: str) -> np.random.Generator:
    """Independent, named, deterministic random stream (adding a stream never perturbs others)."""
    return np.random.default_rng(np.random.SeedSequence([int(seed), zlib.crc32(name.encode())]))
