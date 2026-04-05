# Figurya Scraping Proxy

Cloudflare Worker that proxies scraping requests through CF's edge
network to bypass IP-based blocks on stores like Amazon and Hobby Genki.

## Setup

### Option A: Via Cloudflare dashboard (easier)

1. Go to https://dash.cloudflare.com → **Workers & Pages** → **Create**
2. Pick **"Create Worker"** → name it `figurya-proxy` → **Deploy**
3. Click **"Edit code"** → replace the default code with contents of `worker.js`
4. Click **"Deploy"**
5. Go to **Settings → Variables** → add a **Secret** named `PROXY_KEY` with a strong random value (save it — we need it for Railway)
6. Copy the worker URL (e.g. `https://figurya-proxy.<account>.workers.dev`)

### Option B: Via Wrangler CLI

```bash
cd cf-worker
npm install -g wrangler
wrangler login
wrangler secret put PROXY_KEY  # paste a strong random value
wrangler deploy
```

## Usage

```
GET https://figurya-proxy.<account>.workers.dev/?url=<urlencoded-target>
Header: X-Proxy-Key: <PROXY_KEY>
```

Returns the upstream response body with its content-type.

## Limits (free tier)

- 100,000 requests/day
- 10ms CPU time per request
- No persistent state (stateless only)
