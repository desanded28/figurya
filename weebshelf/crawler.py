import asyncio
import logging
import time
from weebshelf.database import db_conn, store_search_results, get_pending_terms, get_db_stats
from weebshelf.config import REQUEST_DELAY

logger = logging.getLogger("figurya.crawler")

# Default popular search terms to seed the database
SEED_TERMS = [
    "miku", "rem", "emilia", "asuna", "zero two", "nezuko",
    "marin", "anya", "makima", "power", "gojo", "naruto",
    "luffy", "goku", "saber", "tohka", "albedo", "ainz",
    "mikasa", "levi", "ichigo", "sakura", "hinata", "rin",
    "raphtalia", "aqua", "megumin", "darkness", "konosuba",
    "demon slayer", "one piece", "dragon ball", "jujutsu kaisen",
    "spy x family", "chainsaw man", "attack on titan",
    "nendoroid", "figma", "prize figure",
]


async def crawl_term(fetchers: list, term: str):
    """Crawl all sources for a single search term and store results."""
    logger.info(f"Crawling: {term}")

    all_figurines = []

    for fetcher in fetchers:
        try:
            results = await fetcher.search(term)
            if results:
                logger.info(f"  [{fetcher.name}] {len(results)} results")
                for fig in results:
                    all_figurines.append(fig.model_dump())
            await asyncio.sleep(REQUEST_DELAY)
        except Exception as e:
            logger.error(f"  [{fetcher.name}] Error: {e}")

    if all_figurines:
        with db_conn() as conn:
            store_search_results(conn, term, all_figurines)
        logger.info(f"  Stored {len(all_figurines)} figurines for '{term}'")
    else:
        logger.info(f"  No results for '{term}'")


async def run_crawl_cycle(fetchers: list, max_terms: int = 100):
    """Run one full crawl cycle — process all pending/stale terms."""
    # Seed the database with popular terms if empty
    with db_conn() as conn:
        term_count = conn.execute("SELECT COUNT(*) as c FROM search_terms").fetchone()["c"]
        if term_count == 0:
            logger.info("Seeding database with popular terms...")
            now = time.time()
            for term in SEED_TERMS:
                conn.execute("""
                    INSERT OR IGNORE INTO search_terms (term, popularity, last_crawled, queued, created_at)
                    VALUES (?, 10, 0, 1, ?)
                """, (term, now))
            conn.commit()

    # Get terms that need crawling
    pending = get_pending_terms(limit=max_terms)
    if not pending:
        logger.info("No pending terms to crawl")
        return

    logger.info(f"Starting cycle: {len(pending)} terms to crawl")
    start = time.time()

    for i, term in enumerate(pending):
        logger.info(f"[{i+1}/{len(pending)}] {term}")
        await crawl_term(fetchers, term)
        # Extra delay between terms
        if i < len(pending) - 1:
            await asyncio.sleep(2)

    elapsed = time.time() - start
    stats = get_db_stats()
    logger.info(f"Cycle complete in {elapsed:.0f}s — {stats['figurines']} figurines, {stats['search_terms']} terms")


async def crawler_loop(fetchers: list, interval_hours: float = 12):
    """Run the crawler in a loop. Call this as a background task."""
    interval_seconds = interval_hours * 3600

    while True:
        try:
            await run_crawl_cycle(fetchers)
        except Exception as e:
            logger.error(f"Error in crawl cycle: {e}")

        logger.info(f"Next cycle in {interval_hours}h")
        await asyncio.sleep(interval_seconds)


async def run_initial_crawl(fetchers: list):
    """Run a quick initial crawl with just a few top terms to populate the DB fast."""
    with db_conn() as conn:
        fig_count = conn.execute("SELECT COUNT(*) as c FROM figurines").fetchone()["c"]

    if fig_count > 0:
        logger.info(f"DB already has {fig_count} figurines, skipping initial crawl")
        return

    logger.info("Running initial crawl with top terms...")
    quick_terms = SEED_TERMS[:10]  # Just the top 10 to start fast

    for i, term in enumerate(quick_terms):
        logger.info(f"Initial [{i+1}/{len(quick_terms)}] {term}")
        await crawl_term(fetchers, term)
        await asyncio.sleep(1)

    stats = get_db_stats()
    logger.info(f"Initial crawl done: {stats['figurines']} figurines from {len(stats['stores'])} stores")
