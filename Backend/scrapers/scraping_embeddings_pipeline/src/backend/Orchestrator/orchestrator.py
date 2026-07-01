from typing import List

from src.backend.Config.config import Config
from src.backend.log.log import write_to_log
from src.backend.Scrapers.BaseScraper.base_scraper import BaseScraper, record_scrape_status


class Orchestrator:
    def __init__(self, config: Config):
        self._config = config

    @classmethod
    def run_target(cls, target):
        all_new_target_elements: List[BaseScraper] = []
        all_new_target_elements.extend(target.get_all_new_target_elements())
        for element in all_new_target_elements:
            try:
                element.scrape_and_save()
            except Exception as e:
                print(f'Failed to scrape {element}: {e}')
                write_to_log(str(element), element.__class__.__name__, f'Failed due to {e}')
                element.record_status('failed', str(e))

    def run(self):
        target_groups = self._config.get_all_targets()
        all_new_target_elements: List[BaseScraper] = []
        for target in target_groups:
            try:
                all_new_target_elements.extend(target.get_all_new_target_elements())
            except Exception as e:
                print(f'Failed to get elements for {target}: {e}')
                write_to_log(str(target), target.__class__.__name__, f'Failed due to {e}')
                record_scrape_status(
                    target.__class__.__name__, str(target), 'failed', str(e)
                )
        for element in all_new_target_elements:
            try:
                element.scrape_and_save()
            except Exception as e:
                print(f'Failed to scrape {element}: {e}')
                write_to_log(str(element), element.__class__.__name__, f'Failed due to {e}')
                element.record_status('failed', str(e))
