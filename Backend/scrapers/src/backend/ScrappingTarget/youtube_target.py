from typing import List

from src.backend.ScrappingTarget.base_target import BaseTarget


class YouTubeTarget(BaseTarget):
    def __init__(self, url=str, limit=10, domain='medical', sub_domain='nutrition', category=''):
        self.url = url
        self.limit = limit
        self.domain = domain
        self.sub_domain = sub_domain
        self.category = category

    def get_all_new_target_elements(self) -> List:
        from src.backend.Scrapers.YouTube.you_tube import YouTubeScraper

        return YouTubeScraper.get_all_possible_elements(self)
