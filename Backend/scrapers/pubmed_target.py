from typing import List

from .base_target import BaseTarget
from .pubmed import PubMedScraper


class PubMedTarget(BaseTarget):
    def __init__(self, keywords=None, max_results=1, disease=None):
        self.keywords = keywords if keywords is not None else []
        self.max_results = max_results  # max search query results for the set of keywords
        self.disease = disease  # curated disease tag stored in each chunk's metadata

    def get_all_new_target_elements(self) -> List[PubMedScraper]:
        return PubMedScraper.get_all_possible_elements(self)
