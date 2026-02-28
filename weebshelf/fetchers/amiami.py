import httpx
from bs4 import BeautifulSoup
from weebshelf.fetchers.base import BaseFetcher
from weebshelf.models import Figurine
from weebshelf.config import MAX_RESULTS_PER_SOURCE
import re


class HLJFetcher(BaseFetcher):
    """Fetches figurine data from HobbyLink Japan (hlj.com)."""
    name = "HobbyLink Japan"
    BASE_URL = "https://www.hlj.com"

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    async def search(self, query: str) -> list[Figurine]:
        search_url = f"{self.BASE_URL}/search/"
        params = {
            "q": f"{query} figure",
            "Word": f"{query} figure",
        }

        try:
            async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
                resp = await client.get(
                    search_url, params=params, headers=self.HEADERS
                )
                if resp.status_code != 200:
                    print(f"[HLJ] Search returned status {resp.status_code}")
                    return []
                return self._parse_results(resp.text)
        except Exception as e:
            print(f"[HLJ] Error fetching: {e}")
            return []

    def _parse_results(self, html: str) -> list[Figurine]:
        soup = BeautifulSoup(html, "html.parser")
        blocks = soup.select(".search-widget-block")
        figures = []

        for block in blocks[:MAX_RESULTS_PER_SOURCE]:
            try:
                # Name
                name_el = block.select_one(".product-item-name")
                if not name_el:
                    continue
                link = name_el.select_one("a")
                if not link:
                    continue
                name = link.get_text(strip=True)
                if not name:
                    continue
                href = link.get("href", "")
                product_url = self.BASE_URL + href if href.startswith("/") else href

                # Image
                img_wrapper = block.select_one(".item-img-wrapper")
                img = img_wrapper.select_one("img") if img_wrapper else None
                img_src = ""
                if img:
                    img_src = img.get("src", "") or img.get("data-src", "")
                    if img_src.startswith("//"):
                        img_src = "https:" + img_src
                    elif img_src and not img_src.startswith("http"):
                        img_src = self.BASE_URL + img_src

                # Price
                price_el = block.select_one(".price")
                price_text = price_el.get_text(strip=True) if price_el else ""
                price = None
                currency = "JPY"

                # Try JPY first, then USD
                jpy_match = re.search(r"([\d,]+)\s*(?:JPY|yen)", price_text, re.I)
                usd_match = re.search(r"\$([\d,.]+)", price_text)
                if jpy_match:
                    price = int(jpy_match.group(1).replace(",", ""))
                    currency = "JPY"
                elif usd_match:
                    price = float(usd_match.group(1).replace(",", ""))
                    currency = "USD"

                # Availability
                stock_el = block.select_one(".stock")
                stock_text = stock_el.get_text(strip=True) if stock_el else ""
                availability = "unknown"
                if "In Stock" in stock_text or "Available" in stock_text:
                    availability = "in_stock"
                elif "Pre-Order" in stock_text or "Backorder" in stock_text:
                    availability = "preorder"
                elif "Sold Out" in stock_text or "Out of Stock" in stock_text:
                    availability = "sold_out"

                # Tags from name
                tags = []
                name_lower = name.lower()
                for tag_word in ["nendoroid", "figma", "scale", "prize", "pop up parade",
                                 "pvc", "figure", "statue"]:
                    if tag_word in name_lower:
                        tags.append(tag_word)

                fig = Figurine(
                    name=name,
                    product_url=product_url,
                    image_url=img_src,
                    store="HobbyLink Japan",
                    price=price,
                    currency=currency,
                    availability=availability,
                    tags=tags,
                    description=name,
                )
                figures.append(fig)
            except Exception as e:
                print(f"[HLJ] Error parsing block: {e}")
                continue

        return figures
