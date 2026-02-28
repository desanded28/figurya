import httpx
from bs4 import BeautifulSoup
from weebshelf.fetchers.base import BaseFetcher
from weebshelf.models import Figurine
from weebshelf.config import MAX_RESULTS_PER_SOURCE
import re


class HobbySearchFetcher(BaseFetcher):
    """Fetches figurine data from HobbySearch (1999.co.jp)."""
    name = "HobbySearch"
    BASE_URL = "https://www.1999.co.jp"

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    async def search(self, query: str) -> list[Figurine]:
        search_url = f"{self.BASE_URL}/eng/search"
        params = {
            "typ1_c": "101",  # Figures category
            "cat": "",
            "target": "SeriesTitle",
            "searchkey": query,
            "qty": str(MAX_RESULTS_PER_SOURCE),
        }

        try:
            async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
                resp = await client.get(
                    search_url, params=params, headers=self.HEADERS
                )
                if resp.status_code != 200:
                    print(f"[HobbySearch] Search returned status {resp.status_code}")
                    return []
                return self._parse_results(resp.text)
        except Exception as e:
            print(f"[HobbySearch] Error fetching: {e}")
            return []

    def _parse_results(self, html: str) -> list[Figurine]:
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select(".c-card")
        figures = []

        for card in cards[:MAX_RESULTS_PER_SOURCE]:
            try:
                # Image and name
                img = card.select_one('img[src*="/itbig"]') or card.select_one('img[src*="/itsmall"]')
                if not img:
                    continue
                name = img.get("alt", "").strip()
                if not name:
                    continue

                img_src = img.get("src", "")
                if img_src and not img_src.startswith("http"):
                    img_src = self.BASE_URL + img_src

                # Price
                price_el = card.select_one('[class*=price]')
                price_text = price_el.get_text(strip=True) if price_el else ""
                price_match = re.search(r"([\d,]+)\s*JPY", price_text)
                price = int(price_match.group(1).replace(",", "")) if price_match else None

                # Product link
                link_el = card.select_one('a[href*="/eng/1"]')
                href = link_el.get("href", "") if link_el else ""
                product_url = self.BASE_URL + href if href.startswith("/") else href

                # Availability
                card_text = card.get_text()
                availability = "unknown"
                if "In Stock" in card_text:
                    availability = "in_stock"
                elif "Back-order" in card_text or "Pre-order" in card_text:
                    availability = "preorder"
                elif "Sold Out" in card_text:
                    availability = "sold_out"

                # Tags from name
                tags = []
                name_lower = name.lower()
                for tag_word in ["nendoroid", "figma", "scale", "prize", "pop up parade",
                                 "pvc", "plastic model", "completed", "plamo"]:
                    if tag_word in name_lower:
                        tags.append(tag_word)

                fig = Figurine(
                    name=name,
                    product_url=product_url,
                    image_url=img_src,
                    store="HobbySearch",
                    price=price,
                    currency="JPY",
                    availability=availability,
                    tags=tags,
                    description=name,
                )
                figures.append(fig)
            except Exception as e:
                print(f"[HobbySearch] Error parsing card: {e}")
                continue

        return figures
