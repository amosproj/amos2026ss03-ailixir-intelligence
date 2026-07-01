from typing import List

from src.backend.ScrappingTarget.base_target import BaseTarget


class NutritionTarget(BaseTarget):
    def __init__(
        self,
        url='https://nutritionfacts.org/blog/',
        max_pages=3,
        domain='medical',
        sub_domain='nutrition',
    ):
        self.url = url
        self.max_pages = max_pages  # max pages None if all pages should be scraped
        self.domain = domain
        self.sub_domain = sub_domain

    def get_all_new_target_elements(self) -> List:
        from src.backend.Scrapers.Nutritionfacts.nutrition import NutritionScraper

        return NutritionScraper.get_all_possible_elements(self)
