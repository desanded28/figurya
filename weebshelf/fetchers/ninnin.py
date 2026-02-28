import httpx
from weebshelf.fetchers.base import BaseFetcher, JSON_HEADERS, logger
from weebshelf.models import Figurine
from weebshelf.config import MAX_RESULTS_PER_SOURCE


class NinNinFetcher(BaseFetcher):
    """Fetches figurine data from Nin-Nin Game (autocomplete JSON API)."""
    name = "Nin-Nin Game"
    BASE_URL = "https://www.nin-nin-game.com"

    async def _fetch(self, query: str) -> list[Figurine]:
        url = f"{self.BASE_URL}/en/search"
        params = {
            "ajaxSearch": "1",
            "id_lang": "1",
            "q": query,
        }

        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(url, params=params, headers=JSON_HEADERS)
            if resp.status_code != 200:
                logger.warning(f"[{self.name}] Status {resp.status_code}")
                return []
            return self._parse_results(resp.json())

    def _parse_results(self, data) -> list[Figurine]:
        figures = []
        products = data if isinstance(data, list) else data.get("products", data.get("results", []))

        for product in products[:MAX_RESULTS_PER_SOURCE]:
            try:
                name = product.get("pname", "").strip()
                if not name:
                    continue

                fig = Figurine(
                    name=name,
                    product_url=product.get("product_link", ""),
                    image_url=product.get("image_link", ""),
                    store=self.name,
                    price=None,
                    currency="GBP",
                    availability="unknown",
                    tags=self.extract_tags(name),
                    description=name,
                )
                figures.append(fig)
            except Exception as e:
                logger.error(f"[{self.name}] Parse error: {e}")
                continue

        return figures
