from typing import List

from src.backend.ScrappingTarget.base_target import BaseTarget


class ArchiveTarget(BaseTarget):
    def __init__(
        self,
        keywords=None,
        max_results=1,
        query_mode='and',
        domain='medical',
        sub_domain='nutrition',
        since_date=None,
    ):
        self.keywords = keywords or []
        self.max_results = max_results  # max search query results per keyword
        self.query_mode = query_mode
        self.domain = domain
        self.sub_domain = sub_domain
        self.since_date = since_date

    def get_all_new_target_elements(self) -> List:
        from src.backend.Scrapers.Archive.archive import ArchiveScraper

        return ArchiveScraper.get_all_possible_elements(self)
