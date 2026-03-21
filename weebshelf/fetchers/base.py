import logging
from abc import ABC, abstractmethod
from weebshelf.models import Figurine

logger = logging.getLogger("figurya.fetchers")

# Shared tag words used by all fetchers
TAG_WORDS = [
    "nendoroid", "figma", "scale", "prize", "pop up parade",
    "figure", "statue", "pvc", "action figure", "plastic model",
    "completed", "plamo",
]

# most stores block default python-requests UA
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

JSON_HEADERS = {
    "User-Agent": DEFAULT_HEADERS["User-Agent"],
    "Accept": "application/json",
}


class BaseFetcher(ABC):
    name: str = "base"

    @abstractmethod
    async def _fetch(self, query: str) -> list[Figurine]:
        pass

    async def search(self, query: str) -> list[Figurine]:
        try:
            results = await self._fetch(query)
            if results:
                logger.info(f"[{self.name}] Found {len(results)} results for '{query}'")
            return results
        except Exception as e:
            logger.error(f"[{self.name}] Error: {e}")
            return []

    @staticmethod
    def extract_tags(name: str, extra_tags: list[str] | None = None) -> list[str]:
        tags = []
        name_lower = name.lower()
        for tag_word in TAG_WORDS:
            if tag_word in name_lower:
                tags.append(tag_word)
        if extra_tags:
            tags.extend(extra_tags)
        return tags

    @staticmethod
    def make_absolute(url: str, base_url: str) -> str:
        if not url:
            return ""
        if url.startswith("//"):
            return "https:" + url
        if url.startswith("/"):
            return base_url + url
        if url.startswith("http"):
            return url
        return base_url + "/" + url
