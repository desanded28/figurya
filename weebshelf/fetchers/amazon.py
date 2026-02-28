import httpx
from bs4 import BeautifulSoup
from weebshelf.fetchers.base import BaseFetcher
from weebshelf.models import Figurine
from weebshelf.config import MAX_RESULTS_PER_SOURCE
import re


class AmazonFetcher(BaseFetcher):
    """Fetches figurine data from Amazon.com search results."""
    name = "Amazon"
    BASE_URL = "https://www.amazon.com"

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    async def search(self, query: str) -> list[Figurine]:
        search_url = f"{self.BASE_URL}/s"
        params = {
            "k": f"{query} figure",
            "i": "toys-and-games",
        }

        try:
            async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
                resp = await client.get(
                    search_url, params=params, headers=self.HEADERS
                )
                if resp.status_code != 200:
                    print(f"[Amazon] Status {resp.status_code}")
                    return []
                if "captcha" in resp.text.lower()[:2000] or "robot" in resp.text.lower()[:2000]:
                    print("[Amazon] Captcha detected, skipping")
                    return []
                return self._parse_results(resp.text)
        except Exception as e:
            print(f"[Amazon] Error: {e}")
            return []

    def _parse_results(self, html: str) -> list[Figurine]:
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select('[data-component-type="s-search-result"]')
        figures = []

        for card in cards[:MAX_RESULTS_PER_SOURCE]:
            try:
                # Name
                title_el = card.select_one("h2 a span") or card.select_one("h2 span")
                if not title_el:
                    continue
                name = title_el.get_text(strip=True)
                if not name:
                    continue

                # Link — first a with a real product href
                link = card.select_one("h2 a[href]")
                href = ""
                if link:
                    href = link.get("href", "")
                    if href and not href.startswith("http"):
                        href = self.BASE_URL + href
                    # Clean the URL — remove tracking params
                    href = re.sub(r"\?.*", "", href) if "/dp/" in href else href

                # Image
                img = card.select_one("img.s-image")
                img_src = img.get("src", "") if img else ""

                # Price
                price = None
                price_whole = card.select_one(".a-price-whole")
                price_frac = card.select_one(".a-price-fraction")
                if price_whole:
                    pw = price_whole.get_text(strip=True).replace(",", "").replace(".", "")
                    pf = price_frac.get_text(strip=True) if price_frac else "00"
                    try:
                        price = float(f"{pw}.{pf}")
                    except (ValueError, TypeError):
                        pass

                # Rating
                rating = None
                rating_el = card.select_one(".a-icon-star-small .a-icon-alt")
                if rating_el:
                    rating_match = re.search(r"([\d.]+)", rating_el.get_text())
                    if rating_match:
                        # Amazon uses 5-star scale, convert to 10
                        rating = float(rating_match.group(1)) * 2

                # Availability — Amazon search results are generally available
                availability = "in_stock"

                # Tags
                tags = []
                name_lower = name.lower()
                for tag_word in ["nendoroid", "figma", "scale", "prize", "pop up parade",
                                 "figure", "statue", "pvc", "action figure"]:
                    if tag_word in name_lower:
                        tags.append(tag_word)

                # Skip sponsored/ad results that aren't figures
                skip_words = ["poster", "sticker", "keychain", "phone case", "t-shirt", "shirt"]
                if any(w in name_lower for w in skip_words) and "figure" not in name_lower:
                    continue

                fig = Figurine(
                    name=name,
                    product_url=href,
                    image_url=img_src,
                    store="Amazon",
                    price=price,
                    currency="USD",
                    availability=availability,
                    rating=rating,
                    tags=tags,
                    description=name,
                )
                figures.append(fig)
            except Exception as e:
                print(f"[Amazon] Parse error: {e}")
                continue

        return figures
