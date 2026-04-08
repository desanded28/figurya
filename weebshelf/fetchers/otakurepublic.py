from bs4 import BeautifulSoup
from weebshelf.fetchers.base import BaseFetcher, DEFAULT_HEADERS, logger, proxied_get
from weebshelf.models import Figurine
from weebshelf.config import MAX_RESULTS_PER_SOURCE


class OtakuRepublicFetcher(BaseFetcher):
    name = "Otaku Republic"
    BASE_URL = "https://otakurepublic.com"

    async def _fetch(self, query: str) -> list[Figurine]:
        url = f"{self.BASE_URL}/product/text_search.html"
        params = {"q": f"{query} figure"}

        resp = await proxied_get(url, params=params, headers=DEFAULT_HEADERS)
        if resp.status_code != 200:
            logger.warning(f"[{self.name}] Status {resp.status_code}")
            return []
        return self._parse_results(resp.text)

    def _parse_results(self, html: str) -> list[Figurine]:
        soup = BeautifulSoup(html, "html.parser")
        container = soup.select_one(".product_thumbnail_list")
        if not container:
            return []
        items = container.select("li")
        figures = []

        for item in items[:MAX_RESULTS_PER_SOURCE]:
            try:
                link = item.select_one("a.product_preview_link")
                if not link:
                    continue

                # Name from title span or image alt or aria-label
                title_span = item.select_one(".thumbnail_info_product_title")
                name = ""
                if title_span:
                    name = title_span.get("data-title-default", "")
                if not name:
                    img = item.select_one("img")
                    name = img.get("alt", "") if img else ""
                if not name:
                    name = link.get("aria-label", "").replace("goto item page: ", "")
                if not name:
                    continue

                href = link.get("href", "")
                product_url = self.make_absolute(href, self.BASE_URL)

                img = item.select_one("img.thumbnail_img")
                img_url = ""
                if img:
                    img_url = img.get("src", "") or img.get("data-src", "")
                    img_url = self.make_absolute(img_url, self.BASE_URL)

                # Price (USD) — from offscreen span for clean number
                price = None
                price_el = item.select_one(".price_with_unit_offscreen")
                if price_el:
                    try:
                        price = float(price_el.get_text(strip=True).replace(",", ""))
                    except ValueError:
                        pass

                fig = Figurine(
                    name=name,
                    product_url=product_url,
                    image_url=img_url,
                    store=self.name,
                    price=price,
                    currency="USD",
                    availability="in_stock",
                    tags=self.extract_tags(name),
                    description=name,
                )
                figures.append(fig)
            except Exception as e:
                logger.error(f"[{self.name}] Parse error: {e}")
                continue

        return figures
