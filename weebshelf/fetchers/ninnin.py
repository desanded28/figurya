import httpx
from weebshelf.fetchers.base import BaseFetcher
from weebshelf.models import Figurine
from weebshelf.config import MAX_RESULTS_PER_SOURCE


class NinNinFetcher(BaseFetcher):
    """Fetches figurine data from Nin-Nin Game (autocomplete JSON API)."""
    name = "Nin-Nin Game"
    BASE_URL = "https://www.nin-nin-game.com"

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "application/json",
    }

    async def search(self, query: str) -> list[Figurine]:
        url = f"{self.BASE_URL}/en/search"
        params = {
            "ajaxSearch": "1",
            "id_lang": "1",
            "q": query,
        }

        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                resp = await client.get(url, params=params, headers=self.HEADERS)
                if resp.status_code != 200:
                    print(f"[NinNin] Status {resp.status_code}")
                    return []
                return self._parse_results(resp.json())
        except Exception as e:
            print(f"[NinNin] Error: {e}")
            return []

    def _parse_results(self, data) -> list[Figurine]:
        figures = []
        products = data if isinstance(data, list) else data.get("products", data.get("results", []))

        for product in products[:MAX_RESULTS_PER_SOURCE]:
            try:
                name = product.get("pname", "").strip()
                if not name:
                    continue

                image_url = product.get("image_link", "")
                product_url = product.get("product_link", "")

                # NinNin autocomplete doesn't include price
                tags = []
                name_lower = name.lower()
                for tag_word in ["nendoroid", "figma", "scale", "prize", "figure", "statue"]:
                    if tag_word in name_lower:
                        tags.append(tag_word)

                fig = Figurine(
                    name=name,
                    product_url=product_url,
                    image_url=image_url,
                    store="Nin-Nin Game",
                    price=None,
                    currency="GBP",
                    availability="unknown",
                    tags=tags,
                    description=name,
                )
                figures.append(fig)
            except Exception as e:
                print(f"[NinNin] Parse error: {e}")
                continue

        return figures
