from abc import ABC, abstractmethod
from weebshelf.models import Figurine


class BaseFetcher(ABC):
    name: str = "base"

    @abstractmethod
    async def search(self, query: str) -> list[Figurine]:
        pass
