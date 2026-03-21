import httpx
from bs4 import BeautifulSoup
from weebshelf.fetchers.base import BaseFetcher, DEFAULT_HEADERS, logger
from weebshelf.models import Figurine
from weebshelf.config import MAX_RESULTS_PER_SOURCE
import re


class HLJFetcher(BaseFetcher):
    name = "HobbyLink Japan"
    BASE_URL = "https://www.hlj.com"

    async def _fetch(self, query: str) -> list[Figurine]:
        search_url = f"{self.BASE_URL}/search/"
        params = {
            "q": f"{query} figure",
            "Word": f"{query} figure",
        }

        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            resp = await client.get(search_url, params=params, headers=DEFAULT_HEADERS)
            if resp.status_code != 200:
                logger.info(f"[{self.name}] Status {resp.status_code}")
                return []
            return self._parse_results(resp.text)

    def _parse_results(self, html: str) -> list[Figurine]:
        soup = BeautifulSoup(html, "html.parser")
        blocks = soup.select(".search-widget-block")
        figures = []

        for block in blocks[:MAX_RESULTS_PER_SOURCE]:
            try:
                name_el = block.select_one(".product-item-name")
                if not name_el:
                    continue
                link = name_el.select_one("a")
                if not link:
                    continue
                name = link.get_text(strip=True)
                if not name:
                    continue
                product_url = self.make_absolute(link.get("href", ""), self.BASE_URL)

                img_wrapper = block.select_one(".item-img-wrapper")
                img = img_wrapper.select_one("img") if img_wrapper else None
                img_src = ""
                if img:
                    img_src = img.get("src", "") or img.get("data-src", "")
                    img_src = self.make_absolute(img_src, self.BASE_URL)

                price_el = block.select_one(".price")
                price_text = price_el.get_text(strip=True) if price_el else ""
                price = None
                currency = "JPY"

                jpy_match = re.search(r"([\d,]+)\s*(?:JPY|yen)", price_text, re.I)
                usd_match = re.search(r"\$([\d,.]+)", price_text)
                if jpy_match:
                    price = int(jpy_match.group(1).replace(",", ""))
                    currency = "JPY"
                elif usd_match:
                    price = float(usd_match.group(1).replace(",", ""))
                    currency = "USD"

                stock_el = block.select_one(".stock")
                stock_text = stock_el.get_text(strip=True) if stock_el else ""
                availability = "unknown"
                if "In Stock" in stock_text or "Available" in stock_text:
                    availability = "in_stock"
                elif "Pre-Order" in stock_text or "Backorder" in stock_text:
                    availability = "preorder"
                elif "Sold Out" in stock_text or "Out of Stock" in stock_text:
                    availability = "sold_out"

                fig = Figurine(
                    name=name,
                    product_url=product_url,
                    image_url=img_src,
                    store=self.name,
                    price=price,
                    currency=currency,
                    availability=availability,
                    tags=self.extract_tags(name),
                    description=name,
                )
                figures.append(fig)
            except Exception as e:
                logger.error(f"[{self.name}] Parse error: {e}")
                continue

        return figures
