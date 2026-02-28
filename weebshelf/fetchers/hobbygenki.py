import httpx
from bs4 import BeautifulSoup
from weebshelf.fetchers.base import BaseFetcher
from weebshelf.models import Figurine
from weebshelf.config import MAX_RESULTS_PER_SOURCE
import re


class HobbyGenkiFetcher(BaseFetcher):
    """Fetches figurine data from Hobby Genki (PrestaShop SSR)."""
    name = "Hobby Genki"
    BASE_URL = "https://hobby-genki.com"

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    async def search(self, query: str) -> list[Figurine]:
        url = f"{self.BASE_URL}/en/search"
        params = {
            "controller": "search",
            "s": query,
        }

        try:
            async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
                resp = await client.get(url, params=params, headers=self.HEADERS)
                if resp.status_code != 200:
                    print(f"[HobbyGenki] Status {resp.status_code}")
                    return []
                return self._parse_results(resp.text)
        except Exception as e:
            print(f"[HobbyGenki] Error: {e}")
            return []

    def _parse_results(self, html: str) -> list[Figurine]:
        soup = BeautifulSoup(html, "html.parser")
        figures = []

        articles = soup.select("article.product-miniature")

        for article in articles[:MAX_RESULTS_PER_SOURCE]:
            try:
                # Name and link
                title_el = article.select_one(".product-title a")
                if not title_el:
                    continue
                name = title_el.get_text(strip=True)
                if not name:
                    continue
                href = title_el.get("href", "")

                # Image
                img = article.select_one("img")
                img_src = ""
                if img:
                    img_src = img.get("data-full-size-image-url", "") or img.get("src", "")
                    if img_src and not img_src.startswith("http"):
                        img_src = self.BASE_URL + img_src

                # Price
                price = None
                price_el = article.select_one(".product-price-and-shipping .price")
                if price_el:
                    price_text = price_el.get_text(strip=True)
                    # Price format: "¥2,345" or "2345 JPY" or just numbers
                    match = re.search(r"[¥]?\s*([\d,]+)", price_text)
                    if match:
                        price = int(match.group(1).replace(",", ""))

                # Availability - check for flags
                flags = article.select(".product-flag")
                flag_texts = [f.get_text(strip=True).lower() for f in flags]
                availability = "in_stock"  # default for Hobby Genki (they mostly show available items)
                if any("sold" in f or "out" in f for f in flag_texts):
                    availability = "sold_out"
                elif any("pre" in f for f in flag_texts):
                    availability = "preorder"

                # Discount info
                discount_el = article.select_one(".discount-percentage")
                discount = discount_el.get_text(strip=True) if discount_el else ""

                tags = []
                name_lower = name.lower()
                for tag_word in ["nendoroid", "figma", "scale", "prize", "pop up parade",
                                 "figure", "statue", "pvc"]:
                    if tag_word in name_lower:
                        tags.append(tag_word)
                if discount:
                    tags.append(f"sale {discount}")

                fig = Figurine(
                    name=name,
                    product_url=href,
                    image_url=img_src,
                    store="Hobby Genki",
                    price=price,
                    currency="JPY",
                    availability=availability,
                    tags=tags,
                    description=name,
                )
                figures.append(fig)
            except Exception as e:
                print(f"[HobbyGenki] Parse error: {e}")
                continue

        return figures
