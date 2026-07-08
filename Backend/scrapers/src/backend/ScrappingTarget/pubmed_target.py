from typing import List

from src.backend.ScrappingTarget.base_target import BaseTarget


class PubMedTarget(BaseTarget):
    def __init__(
        self,
        keywords=None,
        max_results=1,
        domain='medical',
        sub_domain='nutrition',
        category='',
        since_date=None,
    ):
        self.keywords = keywords or []
        self.max_results = max_results  # max search query results for the set of keywords
        self.domain = domain
        self.sub_domain = sub_domain
        self.category = category
        self.since_date = since_date

    def get_all_new_target_elements(self) -> List:
        from src.backend.Scrapers.PubMed.pub_med import PubMedScraper

        return PubMedScraper.get_all_possible_elements(self)
