from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path
import asyncio

from weebshelf.query import parse_query, build_search_terms
from weebshelf.fetchers.mfc import HobbySearchFetcher
from weebshelf.fetchers.amiami import HLJFetcher
from weebshelf.fetchers.solaris import SolarisFetcher
from weebshelf.fetchers.tom import TOMFetcher
from weebshelf.fetchers.cdjapan import CDJapanFetcher
from weebshelf.fetchers.hobbygenki import HobbyGenkiFetcher
from weebshelf.fetchers.ninnin import NinNinFetcher
from weebshelf.fetchers.amazon import AmazonFetcher
from weebshelf.ranker import rank_results
from weebshelf.reviews import summarize_reviews
from weebshelf.database import get_cached_results, queue_search_term, store_search_results, get_conn, get_db_stats
from weebshelf.crawler import crawler_loop, run_initial_crawl
from weebshelf.models import Figurine

FETCHERS = [
    HobbySearchFetcher(),
    HLJFetcher(),
    SolarisFetcher(),
    TOMFetcher(),
    CDJapanFetcher(),
    HobbyGenkiFetcher(),
    NinNinFetcher(),
    AmazonFetcher(),
]

crawler_task = None
initial_crawl_task = None


async def _background_startup():
    """Run initial crawl + start crawler loop, all in background."""
    await run_initial_crawl(FETCHERS)
    await crawler_loop(FETCHERS, interval_hours=12)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global crawler_task
    # Start crawling in background — don't block server startup
    crawler_task = asyncio.create_task(_background_startup())
    yield
    # Shutdown
    if crawler_task:
        crawler_task.cancel()


app = FastAPI(title="WeebShelf", lifespan=lifespan)

BASE_DIR = Path(__file__).parent
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@app.get("/")
async def home(request: Request, q: str = "", sort: str = "relevance"):
    if not q.strip():
        stats = get_db_stats()
        return templates.TemplateResponse("index.html", {
            "request": request,
            "query": "",
            "results": [],
            "parsed": None,
            "sort": sort,
            "stats": stats,
        })

    parsed = parse_query(q)
    search_term = build_search_terms(parsed)

    # Step 1: Check the database for cached results
    cached = get_cached_results(search_term)

    if cached:
        figurines = [Figurine(**f) for f in cached]
    else:
        # Step 2: Not in DB — do a live fetch (just this once), store it, and queue for future crawls
        tasks = [fetcher.search(search_term) for fetcher in FETCHERS]
        results_lists = await asyncio.gather(*tasks, return_exceptions=True)

        figurines = []
        for result in results_lists:
            if isinstance(result, list):
                figurines.extend(result)

        # Store in the proper database
        if figurines:
            conn = get_conn()
            store_search_results(conn, search_term, [f.model_dump() for f in figurines])
            conn.close()
        else:
            # Queue the term so the crawler picks it up next cycle
            queue_search_term(search_term)

    # Rank results
    results = rank_results(figurines, parsed)

    # Generate review summaries
    for r in results:
        if r.figurine.reviews:
            r.review_summary = summarize_reviews(r.figurine.reviews)

    # Sort
    if sort == "price_low":
        results.sort(key=lambda r: r.figurine.price_usd or 99999)
    elif sort == "price_high":
        results.sort(key=lambda r: -(r.figurine.price_usd or 0))
    elif sort == "rating":
        results.sort(key=lambda r: -(r.figurine.rating or 0))
    # default: relevance (already sorted by final_score)

    stats = get_db_stats()

    return templates.TemplateResponse("index.html", {
        "request": request,
        "query": q,
        "results": results,
        "parsed": parsed,
        "sort": sort,
        "stats": stats,
    })


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("weebshelf.app:app", host="127.0.0.1", port=8000, reload=True)
