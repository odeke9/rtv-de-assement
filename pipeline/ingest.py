from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

sys.path.append(str(Path(__file__).parent.parent))

from config import config
from utils.helpers import log_event, normalize_column, sha256_file

DROP_COLUMNS = {"Unnamed: 0"}  # pandas index written into the export; carries no data
CURRENT = config.RAW_DIR / "_current.json"


def _version(sha: str) -> str:
    return sha[:12]


def current_versions() -> dict:
    return json.loads(CURRENT.read_text())


def raw_path(code: str, kind: str) -> Path:
    cycle = config.CYCLE_BY_CODE[code]
    fname = cycle.csv if kind == "data" else cycle.form
    sha = current_versions()[code][kind]
    return config.RAW_DIR / f"cycle={code}" / f"v={_version(sha)}" / fname


def bronze_path(code: str) -> Path:
    sha = current_versions()[code]["data"]
    return config.BRONZE_DIR / f"cycle={code}" / f"v={_version(sha)}.parquet"


def load_raw() -> list[dict]:
    """Land each source file once per content version: raw/cycle=<code>/v=<sha12>/<file>.

    A changed export lands next to the old one instead of overwriting it; _current.json points
    later stages at the newest version.
    """
    config.RAW_DIR.mkdir(parents=True, exist_ok=True)
    manifest = config.RAW_DIR / "_manifest.jsonl"
    current, entries = {}, []
    for cycle in config.CYCLES:
        current[cycle.code] = {}
        for kind, fname in [("data", cycle.csv), ("form", cycle.form)]:
            src = config.DATA_DIR / fname
            if not src.exists():
                raise FileNotFoundError(f"Missing source file {src}. Set RTV_DATA_DIR.")
            digest = sha256_file(src)
            dest = config.RAW_DIR / f"cycle={cycle.code}" / f"v={_version(digest)}" / fname
            entry = {"survey_cycle": cycle.code, "kind": kind, "file": fname, "sha256": digest,
                     "bytes": src.stat().st_size, "raw_path": str(dest.relative_to(config.LAKE_DIR))}
            if dest.exists():
                entry["status"] = "unchanged"
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
                if sha256_file(dest) != digest:
                    raise IOError(f"copy of {fname} does not match its source hash")
                entry |= {"status": "landed", "landed_at": datetime.now(timezone.utc).isoformat()}
                with open(manifest, "a") as f:
                    f.write(json.dumps(entry) + "\n")
            current[cycle.code][kind] = digest
            entries.append(entry)
            log_event("raw_file", **entry)
    CURRENT.write_text(json.dumps(current, indent=2))
    return entries


def read_raw_csv(path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""], low_memory=False)


def row_hashes(df: pd.DataFrame) -> pd.Series:
    """64-bit content hash of each row's source values (deterministic across runs)."""
    return pd.util.hash_pandas_object(df, index=False).map("{:016x}".format)


def build_bronze() -> dict[str, int]:
    """Write-once Bronze: one Parquet per cycle and source version, never overwritten."""
    counts = {}
    for cycle in config.CYCLES:
        out = bronze_path(cycle.code)
        if out.exists():
            counts[cycle.code] = pq.read_metadata(out).num_rows
            log_event("bronze_unchanged", survey_cycle=cycle.code, path=str(out))
            continue

        df = read_raw_csv(raw_path(cycle.code, "data"))
        df = df.drop(columns=[c for c in df.columns if c in DROP_COLUMNS])
        new_cols = [normalize_column(c) for c in df.columns]
        collisions = pd.Series(new_cols)[pd.Series(new_cols).duplicated()].tolist()
        if collisions:
            raise ValueError(f"{cycle.code}: header normalisation collision {collisions[:5]}")
        df.columns = new_cols

        meta = pd.DataFrame({
            "_survey_cycle": cycle.code,
            "_source_file": cycle.csv,
            "_source_sha256": current_versions()[cycle.code]["data"],
            "_source_row": range(1, len(df) + 1),
            "_row_hash": row_hashes(df),
            "_ingested_at": datetime.now(timezone.utc).isoformat(),
        })
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix(".tmp")
        pd.concat([meta, df], axis=1).to_parquet(tmp, index=False)
        tmp.replace(out)
        counts[cycle.code] = len(df)
        log_event("bronze_written", survey_cycle=cycle.code, rows=len(df), columns=df.shape[1], path=str(out))
    return counts


def read_bronze(code: str, columns: list[str] | None = None) -> pd.DataFrame:
    return pd.read_parquet(bronze_path(code), columns=columns)


def bronze_columns(code: str) -> list[str]:
    return pq.read_schema(bronze_path(code)).names
