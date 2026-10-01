from __future__ import annotations

import argparse
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone

import pandas as pd

from . import catalog, harmonize, ingest, quality, warehouse
from config import config
from utils.helpers import log_event

_state: dict = {}


def t_raw():        return {"files": len(ingest.load_raw())}
def t_bronze():     return ingest.build_bronze()
def t_catalog():
    _state["meta"] = catalog.build_catalog()
    return {k: len(v) for k, v in _state["meta"].items()}
def t_silver():     return harmonize.build_silver()
def t_warehouse():
    if "meta" not in _state:           # resumed run: rebuild metadata cheaply from Bronze
        _state["meta"] = catalog.build_catalog()
    return warehouse.build_warehouse(_state["meta"])
def t_quality():
    r = quality.run_quality()
    return {"checks": len(r), "failed_warn": int(((r.severity == "warn") & ~r.passed).sum())}
def t_tests():
    res = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
                         cwd=config.PROJECT_DIR, capture_output=True, text=True)
    summary = (res.stdout.strip().splitlines() or ["no output"])[-1]
    if res.returncode != 0:
        raise RuntimeError(f"tests failed: {summary}\n{res.stdout[-2000:]}")
    return summary


# (name, function, upstream dependencies)
DAG = [
    ("raw", t_raw, []),
    ("bronze", t_bronze, ["raw"]),
    ("catalog", t_catalog, ["bronze"]),
    ("silver", t_silver, ["bronze"]),
    ("warehouse", t_warehouse, ["catalog", "silver"]),
    ("quality", t_quality, ["warehouse"]),
    ("tests", t_tests, ["quality"]),
]


def run(start_from: str | None = None, retries: int = 1) -> list[dict]:
    run_id = uuid.uuid4().hex[:12]
    names = [n for n, _, _ in DAG]
    todo = names[names.index(start_from):] if start_from else names
    history = []
    for name, fn, deps in DAG:
        if name not in todo:
            continue
        for attempt in range(1, retries + 2):
            t0 = time.time()
            log_event("task_start", run_id=run_id, task=name, attempt=attempt, depends_on=deps)
            try:
                out = fn()
                rec = dict(run_id=run_id, task=name, status="success", attempt=attempt,
                           seconds=round(time.time() - t0, 2), output=str(out))
                log_event("task_end", **rec)
                history.append(rec)
                break
            except Exception as exc:  # noqa: BLE001 - we log, retry, then re-raise
                rec = dict(run_id=run_id, task=name, status="failed", attempt=attempt,
                           seconds=round(time.time() - t0, 2), output=repr(exc)[:500])
                log_event("task_failed", **rec)
                history.append(rec)
                # data errors won't fix themselves on retry; only retry I/O-type failures
                if attempt > retries or isinstance(exc, (AssertionError, ValueError, KeyError, RuntimeError)):
                    _save_history(history)
                    raise
    _save_history(history)
    return history


def _save_history(history: list[dict]) -> None:
    try:
        with warehouse.connect() as con:
            df = pd.DataFrame(history).assign(logged_at=datetime.now(timezone.utc).isoformat())
            con.register("_h", df)
            con.execute("CREATE TABLE IF NOT EXISTS ops_pipeline_runs AS SELECT * FROM _h LIMIT 0")
            con.execute("INSERT INTO ops_pipeline_runs SELECT * FROM _h")
    except Exception as exc:  # noqa: BLE001 - run history must never mask the real error
        log_event("history_write_failed", error=repr(exc))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--from", dest="start_from", choices=[n for n, _, _ in DAG])
    args = p.parse_args()
    for h in run(args.start_from):
        print(f"{h['task']:<10} {h['status']:<8} {h['seconds']:>7}s  {h['output'][:90]}")
