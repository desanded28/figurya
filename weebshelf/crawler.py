import asyncio
import time
from weebshelf.database import get_conn, store_search_results, get_pending_terms, get_db_stats
from weebshelf.config import REQUEST_DELAY

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
    print(f"[Crawler] Crawling: {term}")
    conn = get_conn()

    all_figurines = []

    for fetcher in fetchers:
        try:
            results = await fetcher.search(term)
            if results:
                print(f"  [{fetcher.name}] {len(results)} results")
                for fig in results:
                    all_figurines.append(fig.model_dump())
            # Delay between fetchers to be polite
            await asyncio.sleep(REQUEST_DELAY)
        except Exception as e:
            print(f"  [{fetcher.name}] Error: {e}")

    if all_figurines:
        store_search_results(conn, term, all_figurines)
        print(f"  Stored {len(all_figurines)} figurines for '{term}'")
    else:
        print(f"  No results for '{term}'")

    conn.close()


async def run_crawl_cycle(fetchers: list, max_terms: int = 100):
    """Run one full crawl cycle — process all pending/stale terms."""
    # Seed the database with popular terms if empty
    conn = get_conn()
    term_count = conn.execute("SELECT COUNT(*) as c FROM search_terms").fetchone()["c"]
    if term_count == 0:
        print("[Crawler] Seeding database with popular terms...")
        now = time.time()
        for term in SEED_TERMS:
            conn.execute("""
                INSERT OR IGNORE INTO search_terms (term, popularity, last_crawled, queued, created_at)
                VALUES (?, 10, 0, 1, ?)
            """, (term, now))
        conn.commit()
    conn.close()

    # Get terms that need crawling
    pending = get_pending_terms(limit=max_terms)
    if not pending:
        print("[Crawler] No pending terms to crawl")
        return

    print(f"[Crawler] Starting cycle: {len(pending)} terms to crawl")
    start = time.time()

    for i, term in enumerate(pending):
        print(f"\n[Crawler] [{i+1}/{len(pending)}] {term}")
        await crawl_term(fetchers, term)
        # Extra delay between terms
        if i < len(pending) - 1:
            await asyncio.sleep(2)

    elapsed = time.time() - start
    stats = get_db_stats()
    print(f"\n[Crawler] Cycle complete in {elapsed:.0f}s")
    print(f"  DB: {stats['figurines']} figurines, {stats['search_terms']} terms, {stats['pending_crawls']} pending")
    print(f"  Stores: {stats['stores']}")


async def crawler_loop(fetchers: list, interval_hours: float = 12):
    """Run the crawler in a loop. Call this as a background task."""
    interval_seconds = interval_hours * 3600

    while True:
        try:
            await run_crawl_cycle(fetchers)
        except Exception as e:
            print(f"[Crawler] Error in cycle: {e}")

        print(f"[Crawler] Next cycle in {interval_hours}h")
        await asyncio.sleep(interval_seconds)


async def run_initial_crawl(fetchers: list):
    """Run a quick initial crawl with just a few top terms to populate the DB fast."""
    conn = get_conn()
    fig_count = conn.execute("SELECT COUNT(*) as c FROM figurines").fetchone()["c"]
    conn.close()

    if fig_count > 0:
        print(f"[Crawler] DB already has {fig_count} figurines, skipping initial crawl")
        return

    print("[Crawler] Running initial crawl with top terms...")
    quick_terms = SEED_TERMS[:10]  # Just the top 10 to start fast

    for i, term in enumerate(quick_terms):
        print(f"\n[Crawler] Initial [{i+1}/{len(quick_terms)}] {term}")
        await crawl_term(fetchers, term)
        await asyncio.sleep(1)

    stats = get_db_stats()
    print(f"\n[Crawler] Initial crawl done: {stats['figurines']} figurines from {len(stats['stores'])} stores")
