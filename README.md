# Figurya

Search figurines across 8 stores by character, style, or vibe.

## What it does

Figurya is a free, open-source figurine search engine. Type a character name with optional aesthetic descriptors (like "pink miku girly" or "gothic rem") and get results from 8 stores ranked by relevance, price, and seller reliability.

### Stores searched
HobbySearch, HobbyLink Japan, Solaris Japan, Tokyo Otaku Mode, CDJapan, Hobby Genki, Nin-Nin Game, Amazon

### Features
- **Vibe search** — colors, aesthetics, and styles are parsed from your query
- **Price comparison** — see prices across all stores at once
- **Smart ranking** — results scored by relevance, price, availability, and store reliability
- **Review summaries** — community opinions condensed into key positives/negatives
- **Background crawling** — popular terms are pre-cached for instant results

## Run locally

```bash
# Clone
git clone https://github.com/desanded28/figurya.git
cd figurya

# Set up venv
python3 -m venv venv
source venv/bin/activate

# Install
pip install -r requirements.txt

# Run
uvicorn weebshelf.app:app --reload
```

Visit `http://localhost:8000`

## Deploy to Render

1. Push to GitHub
2. Create a new **Web Service** on [Render](https://render.com)
3. Connect your GitHub repo
4. Set build command: `pip install -r requirements.txt`
5. Set start command: `uvicorn weebshelf.app:app --host 0.0.0.0 --port $PORT`
6. Set Python version to 3.11

Or use the included `render.yaml` for one-click deploy.

## Tech stack

- **FastAPI** + Jinja2 templates
- **httpx** — async HTTP client for parallel store fetching
- **BeautifulSoup** — HTML parsing
- **SQLite** (WAL mode) — caching with 24h TTL
- **Pydantic** — data models

## Project structure

```
weebshelf/
    app.py              # FastAPI routes + rate limiting
    models.py           # Figurine, Review, SearchResult
    query.py            # Query parser (colors, aesthetics, scales)
    ranker.py           # Composite scoring
    reviews.py          # Sentiment summarization
    database.py         # SQLite cache
    crawler.py          # Background crawl loop
    config.py           # Settings + store reliability scores
    fetchers/           # One file per store
    templates/           # Jinja2 HTML
    static/             # CSS, logo, favicon
```

## Support

Figurya is free. Donations help keep the server running:
[ko-fi.com/figurya](https://ko-fi.com/figurya)

## License

MIT
