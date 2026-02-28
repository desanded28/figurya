import sqlite3
import json
import time
from pathlib import Path
from weebshelf.config import CACHE_TTL_HOURS


DB_PATH = Path(__file__).parent.parent / "cache.db"


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS search_cache (
            key TEXT PRIMARY KEY,
            data TEXT NOT NULL,
            timestamp REAL NOT NULL
        )
    """)
    conn.commit()
    return conn


def get_cached(key: str) -> list[dict] | None:
    conn = _get_conn()
    row = conn.execute(
        "SELECT data, timestamp FROM search_cache WHERE key = ?", (key,)
    ).fetchone()
    conn.close()
    if row is None:
        return None
    data, ts = row
    age_hours = (time.time() - ts) / 3600
    if age_hours > CACHE_TTL_HOURS:
        return None
    return json.loads(data)


def set_cached(key: str, data: list[dict]) -> None:
    conn = _get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO search_cache (key, data, timestamp) VALUES (?, ?, ?)",
        (key, json.dumps(data), time.time()),
    )
    conn.commit()
    conn.close()
