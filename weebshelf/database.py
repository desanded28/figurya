import os
import sqlite3
import json
import logging
import time
from contextlib import contextmanager
from pathlib import Path
from weebshelf.config import CACHE_TTL_HOURS

logger = logging.getLogger("figurya.db")

# Data directory can be overridden via FIGURYA_DATA_DIR env var (for Railway persistent volume)
DATA_DIR = Path(os.environ.get("FIGURYA_DATA_DIR", str(Path(__file__).parent.parent)))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "weebshelf.db"


@contextmanager
def db_conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    """Create tables if they don't exist. Call once at startup."""
    with db_conn() as conn:
        _init_tables(conn)


def _init_tables(conn: sqlite3.Connection):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS figurines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            character TEXT DEFAULT '',
            series TEXT DEFAULT '',
            manufacturer TEXT DEFAULT '',
            price REAL,
            currency TEXT DEFAULT 'JPY',
            image_url TEXT DEFAULT '',
            product_url TEXT NOT NULL,
            store TEXT NOT NULL,
            availability TEXT DEFAULT 'unknown',
            rating REAL,
            tags TEXT DEFAULT '[]',
            description TEXT DEFAULT '',
            last_updated REAL NOT NULL,
            UNIQUE(product_url)
        );

        CREATE TABLE IF NOT EXISTS search_terms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            term TEXT NOT NULL UNIQUE,
            popularity INTEGER DEFAULT 1,
            last_crawled REAL DEFAULT 0,
            queued INTEGER DEFAULT 1,
            created_at REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS term_results (
            term_id INTEGER NOT NULL,
            figurine_id INTEGER NOT NULL,
            relevance_score REAL DEFAULT 0,
            PRIMARY KEY (term_id, figurine_id),
            FOREIGN KEY (term_id) REFERENCES search_terms(id),
            FOREIGN KEY (figurine_id) REFERENCES figurines(id)
        );

        CREATE INDEX IF NOT EXISTS idx_figurines_store ON figurines(store);
        CREATE INDEX IF NOT EXISTS idx_figurines_last_updated ON figurines(last_updated);
        CREATE INDEX IF NOT EXISTS idx_search_terms_term ON search_terms(term);
        CREATE INDEX IF NOT EXISTS idx_search_terms_queued ON search_terms(queued, last_crawled);
    """)



def upsert_figurine(conn: sqlite3.Connection, fig_data: dict) -> int:
    now = time.time()

    # Sanitize tags
    tags_raw = fig_data.get("tags", [])
    if not isinstance(tags_raw, list):
        tags_raw = []
    tags_json = json.dumps(tags_raw[:50])

    # Truncate overly long fields
    name = str(fig_data.get("name", ""))[:500]
    description = str(fig_data.get("description", ""))[:2000]
    image_url = str(fig_data.get("image_url", ""))[:1000]
    product_url = str(fig_data.get("product_url", ""))[:1000]

    cursor = conn.execute("""
        INSERT INTO figurines (name, character, series, manufacturer, price, currency,
                               image_url, product_url, store, availability, rating,
                               tags, description, last_updated)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(product_url) DO UPDATE SET
            name=excluded.name, price=excluded.price, currency=excluded.currency,
            image_url=excluded.image_url, availability=excluded.availability,
            rating=excluded.rating, tags=excluded.tags, description=excluded.description,
            last_updated=excluded.last_updated
    """, (
        name,
        str(fig_data.get("character", ""))[:200],
        str(fig_data.get("series", ""))[:200],
        str(fig_data.get("manufacturer", ""))[:200],
        fig_data.get("price"),
        str(fig_data.get("currency", "JPY"))[:10],
        image_url,
        product_url,
        str(fig_data.get("store", ""))[:100],
        str(fig_data.get("availability", "unknown"))[:20],
        fig_data.get("rating"),
        tags_json,
        description,
        now,
    ))
    conn.commit()
    row = conn.execute(
        "SELECT id FROM figurines WHERE product_url = ?", (product_url,)
    ).fetchone()
    return row["id"]


def store_search_results(conn: sqlite3.Connection, term: str, figurines: list[dict]):
    now = time.time()
    try:
        conn.execute("""
            INSERT INTO search_terms (term, popularity, last_crawled, queued, created_at)
            VALUES (?, 1, ?, 0, ?)
            ON CONFLICT(term) DO UPDATE SET
                last_crawled=excluded.last_crawled, queued=0
        """, (term, now, now))
        conn.commit()

        term_row = conn.execute(
            "SELECT id FROM search_terms WHERE term = ?", (term,)
        ).fetchone()
        term_id = term_row["id"]

        for fig_data in figurines:
            try:
                fig_id = upsert_figurine(conn, fig_data)
                conn.execute("""
                    INSERT OR IGNORE INTO term_results (term_id, figurine_id, relevance_score)
                    VALUES (?, ?, 0)
                """, (term_id, fig_id))
            except Exception as e:
                logger.error(f"Error upserting figurine: {e}")
                continue
        conn.commit()
    except Exception as e:
        logger.error(f"Error storing search results for '{term}': {e}")



def get_cached_results(term: str) -> list[dict] | None:
    """Get cached figurines for a search term if fresh enough."""
    with db_conn() as conn:
        try:
            row = conn.execute(
                "SELECT id, last_crawled FROM search_terms WHERE term = ?", (term,)
            ).fetchone()

            if row is None:
                return None

            age_hours = (time.time() - row["last_crawled"]) / 3600
            if age_hours > CACHE_TTL_HOURS:
                return None

            rows = conn.execute("""
                SELECT f.* FROM figurines f
                JOIN term_results tr ON f.id = tr.figurine_id
                WHERE tr.term_id = ?
                ORDER BY f.last_updated DESC
            """, (row["id"],)).fetchall()

            results = []
            for r in rows:
                d = dict(r)
                try:
                    d["tags"] = json.loads(d.get("tags", "[]"))
                except (json.JSONDecodeError, TypeError):
                    d["tags"] = []
                d.pop("id", None)
                d.pop("last_updated", None)
                results.append(d)
            return results
        except Exception as e:
            logger.error(f"Error getting cached results for '{term}': {e}")
            return None


def queue_search_term(term: str):
    """Add a new search term to be crawled in the next cycle."""
    with db_conn() as conn:
        try:
            now = time.time()
            conn.execute("""
                INSERT INTO search_terms (term, popularity, last_crawled, queued, created_at)
                VALUES (?, 1, 0, 1, ?)
                ON CONFLICT(term) DO UPDATE SET
                    popularity = popularity + 1,
                    queued = CASE WHEN last_crawled = 0 THEN 1 ELSE queued END
            """, (term, now))
            conn.commit()
        except Exception as e:
            logger.error(f"Error queuing search term '{term}': {e}")


def get_pending_terms(limit: int = 100) -> list[str]:
    """Get terms that need crawling, prioritized by popularity."""
    with db_conn() as conn:
        try:
            rows = conn.execute("""
                SELECT term FROM search_terms
                WHERE queued = 1 OR (? - last_crawled) / 3600.0 > ?
                ORDER BY popularity DESC, last_crawled ASC
                LIMIT ?
            """, (time.time(), CACHE_TTL_HOURS, limit)).fetchall()
            return [r["term"] for r in rows]
        except Exception as e:
            logger.error(f"Error getting pending terms: {e}")
            return []


def get_db_stats() -> dict:
    with db_conn() as conn:
        try:
            fig_count = conn.execute("SELECT COUNT(*) as c FROM figurines").fetchone()["c"]
            term_count = conn.execute("SELECT COUNT(*) as c FROM search_terms").fetchone()["c"]
            pending = conn.execute("SELECT COUNT(*) as c FROM search_terms WHERE queued = 1").fetchone()["c"]
            stores = conn.execute("SELECT store, COUNT(*) as c FROM figurines GROUP BY store ORDER BY c DESC").fetchall()
            return {
                "figurines": fig_count,
                "search_terms": term_count,
                "pending_crawls": pending,
                "stores": {r["store"]: r["c"] for r in stores},
            }
        except Exception as e:
            logger.error(f"Error getting DB stats: {e}")
            return {"figurines": 0, "search_terms": 0, "pending_crawls": 0, "stores": {}}
