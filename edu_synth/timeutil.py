from __future__ import annotations

import numpy as np


def iso_ts(sec, valid=None) -> np.ndarray:
    """int64 epoch seconds -> 'YYYY-MM-DDTHH:MM:SSZ' (object array; '' where invalid)."""
    s = np.asarray(sec, dtype=np.int64)
    out = np.char.add(s.astype("datetime64[s]").astype(str), "Z").astype(object)
    if valid is not None:
        out[~np.asarray(valid)] = ""
    return out


def iso_date(day, valid=None) -> np.ndarray:
    d = np.asarray(day, dtype=np.int64)
    out = d.astype("datetime64[D]").astype(str).astype(object)
    if valid is not None:
        out[~np.asarray(valid)] = ""
    return out
