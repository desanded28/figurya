import httpx
from bs4 import BeautifulSoup
from weebshelf.fetchers.base import BaseFetcher
from weebshelf.models import Figurine
from weebshelf.config import MAX_RESULTS_PER_SOURCE
import re


class CDJapanFetcher(BaseFetcher):
    """Fetches figurine data from CDJapan (HTML fragment API)."""
    name = "CDJapan"
    BASE_URL = "https://www.cdjapan.co.jp"

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "text/html",
    }

    async def search(self, query: str) -> list[Figurine]:
        url = f"{self.BASE_URL}/api/products/html"
        params = {
            "q": f"{query} figure",
            "rows": "24",
        }

        try:
            async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
                resp = await client.get(url, params=params, headers=self.HEADERS)
                if resp.status_code != 200:
                    print(f"[CDJapan] Status {resp.status_code}")
                    return []
                return self._parse_results(resp.text)
        except Exception as e:
            print(f"[CDJapan] Error: {e}")
            return []

    def _parse_results(self, html: str) -> list[Figurine]:
        soup = BeautifulSoup(html, "html.parser")
        figures = []

        items = soup.select("li.item") or soup.select(".product-item") or soup.select("[itemtype*=Product]")

        for item in items[:MAX_RESULTS_PER_SOURCE]:
            try:
                # Name
                title_el = item.select_one(".title") or item.select_one("h3") or item.select_one("a.item-wrap")
                if not title_el:
                    continue
                name = title_el.get_text(strip=True)
                if not name:
                    continue

                # Link
                link = item.select_one("a[href]")
                href = link.get("href", "") if link else ""
                if href and not href.startswith("http"):
                    href = self.BASE_URL + href

                # Image
                img = item.select_one("img[src]")
                img_src = ""
                if img:
                    img_src = img.get("src", "") or img.get("data-src", "")
                    if img_src.startswith("//"):
                        img_src = "https:" + img_src
                    elif img_src and not img_src.startswith("http"):
                        img_src = self.BASE_URL + img_src

                # Price
                price = None
                price_el = item.select_one("[itemprop=price]")
                if price_el:
                    price_val = price_el.get("content", "")
                    try:
                        price = int(float(price_val))
                    except (ValueError, TypeError):
                        pass
                if price is None:
                    price_text = item.get_text()
                    match = re.search(r"([\d,]+)\s*yen", price_text, re.I)
                    if match:
                        price = int(match.group(1).replace(",", ""))

                # Availability
                status_el = item.select_one(".status")
                status_text = status_el.get_text(strip=True).lower() if status_el else ""
                availability = "unknown"
                if "in stock" in status_text:
                    availability = "in_stock"
                elif "no longer" in status_text or "out of" in status_text:
                    availability = "sold_out"
                elif "pre" in status_text or "order" in status_text:
                    availability = "preorder"

                tags = []
                name_lower = name.lower()
                for tag_word in ["nendoroid", "figma", "scale", "prize", "figure", "statue"]:
                    if tag_word in name_lower:
                        tags.append(tag_word)

                fig = Figurine(
                    name=name,
                    product_url=href,
                    image_url=img_src,
                    store="CDJapan",
                    price=price,
                    currency="JPY",
                    availability=availability,
                    tags=tags,
                    description=name,
                )
                figures.append(fig)
            except Exception as e:
                print(f"[CDJapan] Parse error: {e}")
                continue

        return figures
