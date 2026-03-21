# Figurya

Figurya searches 15 Japanese figurine stores at once and ranks results by relevance, price, and seller reliability. You can search by character name, or throw in vibe words like "gothic rem" or "pink miku girly" and it'll parse out the aesthetics, colors, and scales to filter results.

## Stack

FastAPI, BeautifulSoup, httpx, Pydantic, SQLite (WAL mode), Jinja2

## Running it

```bash
git clone https://github.com/desanded28/figurya.git && cd figurya
pip install -r requirements.txt
uvicorn weebshelf.app:app --reload
```

Open `http://localhost:8000`. For deploy, there's a `render.yaml` included.

## How it works

- 15 async scrapers run in parallel via httpx (HobbySearch, HLJ, Solaris, TOM, CDJapan, etc.)
- Query parser pulls out colors, aesthetics, and figure scales from natural language input
- Results get a composite score based on relevance match, price, availability, and store reliability ratings
- SQLite cache with 24h TTL so repeated searches don't hammer the stores
- Background crawler pre-caches popular search terms
