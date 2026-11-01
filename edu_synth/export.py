"""Step 9: CSV / JSON / SQL exports + checksums."""
from __future__ import annotations

import csv
import hashlib
import json
import os
import sqlite3

import pandas as pd

from . import schema


def sha256(path: str, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while b := f.read(chunk):
            h.update(b)
    return h.hexdigest()


def _fmt(df: pd.DataFrame, table: str) -> pd.DataFrame:
    cols = schema.columns(table)
    assert set(cols) == set(df.columns), (table, set(cols) ^ set(df.columns))
    df = df[cols].copy()
    for f in schema.TABLES[table]["fields"]:
        if f["type"] == "bool":
            df[f["name"]] = df[f["name"]].map({True: "true", False: "false"}).astype(object).where(df[f["name"]].notna(), "")
    return df


def write_tables(tables: dict, outdir: str) -> dict:
    d = os.path.join(outdir, "data"); os.makedirs(d, exist_ok=True)
    info = {}
    for t, df in tables.items():
        p = os.path.join(d, f"{t}.csv")
        _fmt(df, t).to_csv(p, index=False, na_rep="", lineterminator="\n")
        info[f"data/{t}.csv"] = dict(rows=len(df), sha256=sha256(p), bytes=os.path.getsize(p))
        if len(df) <= 25_000:
            jd = os.path.join(outdir, "json"); os.makedirs(jd, exist_ok=True)
            _fmt(df, t).where(lambda x: x.notna(), None).to_json(os.path.join(jd, f"{t}.json"), orient="records", indent=1)
    return info


def write_ground_truth(gt: pd.DataFrame, latent: pd.DataFrame, expected: pd.DataFrame, outdir: str) -> dict:
    d = os.path.join(outdir, "ground_truth"); os.makedirs(d, exist_ok=True)
    info = {}
    for name, df in (("ground_truth", gt), ("latent_learner_traits", latent), ("expected_weekly_metrics", expected)):
        p = os.path.join(d, f"{name}.csv")
        df.to_csv(p, index=False, na_rep="", lineterminator="\n")
        info[f"ground_truth/{name}.csv"] = dict(rows=len(df), sha256=sha256(p), bytes=os.path.getsize(p))
    summ = {"rows": int(len(gt)),
            "by_issue_type": gt.groupby(["issue_type", "label_class"]).size().rename("n").reset_index().to_dict("records"),
            "note": "Ground truth is NEVER part of the input tables. Detectors/validators may read it only for scoring."}
    p = os.path.join(d, "ground_truth_summary.json")
    with open(p, "w") as f: json.dump(summ, f, indent=2)
    info["ground_truth/ground_truth_summary.json"] = dict(rows=len(summ["by_issue_type"]), sha256=sha256(p), bytes=os.path.getsize(p))
    return info


def write_sql(outdir: str, with_seed: bool) -> None:
    d = os.path.join(outdir, "sql"); os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "schema.sql"), "w") as f:
        f.write(schema.ddl())
    if with_seed:
        db = os.path.join(d, "seed.sqlite")
        if os.path.exists(db): os.remove(db)
        build_sqlite(os.path.join(outdir, "data"), db)
        con = sqlite3.connect(db)
        with open(os.path.join(d, "seed.sql"), "w") as f:
            f.write("PRAGMA foreign_keys=OFF;\nBEGIN TRANSACTION;\n")
            for line in con.iterdump():
                if line.startswith(("BEGIN", "COMMIT", "PRAGMA")): continue
                f.write(line + "\n")
            f.write("COMMIT;\n")
        con.close(); os.remove(db)


def build_sqlite(data_dir: str, db_path: str) -> None:
    """Load the CSVs into SQLite with the generated DDL (booleans -> 0/1, empty -> NULL)."""
    con = sqlite3.connect(db_path)
    con.executescript(schema.ddl())
    for t, spec in schema.TABLES.items():
        types = {f["name"]: f["type"] for f in spec["fields"]}
        cols = list(types)
        with open(os.path.join(data_dir, f"{t}.csv"), newline="") as fh:
            rd = csv.reader(fh); next(rd)
            def conv(row):
                out = []
                for c, v in zip(cols, row):
                    if v == "": out.append(None)
                    elif types[c] == "bool": out.append(1 if v == "true" else 0)
                    elif types[c] == "int": out.append(int(v))
                    elif types[c] == "float": out.append(float(v))
                    else: out.append(v)
                return out
            batch = []
            q = f"INSERT INTO {t} ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})"
            for row in rd:
                batch.append(conv(row))
                if len(batch) >= 50_000:
                    con.executemany(q, batch); batch = []
            if batch: con.executemany(q, batch)
    con.commit(); con.close()


def load_tables(data_dir: str) -> dict:
    out = {}
    for t in schema.TABLES:
        dtypes = {c: "category" for c in ("enrollment_id", "learner_id", "course_id", "content_id", "attempt_id", "event_type", "device_type", "source")} if t == "activity_events" else {}
        out[t] = pd.read_csv(os.path.join(data_dir, f"{t}.csv"), dtype={**{c: str for c in schema.columns(t)}, **dtypes}, keep_default_na=False, na_values=[""], low_memory=False)
        for f in schema.TABLES[t]["fields"]:
            c = f["name"]
            if f["type"] == "int":
                out[t][c] = pd.to_numeric(out[t][c]).astype("Int64") if f["required"] is False else pd.to_numeric(out[t][c]).astype("int64")
            elif f["type"] == "float":
                out[t][c] = pd.to_numeric(out[t][c])
            elif f["type"] == "bool":
                out[t][c] = out[t][c].map({"true": True, "false": False}).astype("boolean")
    return out
