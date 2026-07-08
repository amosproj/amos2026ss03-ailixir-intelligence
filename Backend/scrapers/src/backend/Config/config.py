"""Serializable set of scraping targets, persisted to data/config.json.

To add a target type: give it a private list in __init__, parse it in from_json,
route it in add_target, and emit it in to_dict / get_all_targets.
"""
import json

from src.backend.Config import CONFIG_FILE_PATH
from src.backend.ScrappingTarget.archive_target import ArchiveTarget
from src.backend.ScrappingTarget.pubmed_target import PubMedTarget
from src.backend.ScrappingTarget.youtube_target import YouTubeTarget


class Config:
    def __init__(self):
        self._archive_targets = []
        self._pubmed_targets = []
        self._youtube_targets = []

    @classmethod
    def from_json(cls, path: str = CONFIG_FILE_PATH) -> 'Config':
        with open(path) as config_file:
            data = json.load(config_file)
        config = cls()
        config._archive_targets = [ArchiveTarget(**entry) for entry in data.get('archive_targets', [])]
        config._pubmed_targets = [PubMedTarget(**entry) for entry in data.get('pubmed_targets', [])]
        config._youtube_targets = [YouTubeTarget(**entry) for entry in data.get('youtube_targets', [])]
        return config

    def add_target(self, target):
        if isinstance(target, ArchiveTarget):
            self._archive_targets.append(target)
        elif isinstance(target, PubMedTarget):
            self._pubmed_targets.append(target)
        elif isinstance(target, YouTubeTarget):
            self._youtube_targets.append(target)
        else:
            raise ValueError(f'Unknown target type: {type(target)}')

    def to_dict(self):
        return {
            'archive_targets': [target.to_dict() for target in self._archive_targets],
            'pubmed_targets': [target.to_dict() for target in self._pubmed_targets],
            'youtube_targets': [target.to_dict() for target in self._youtube_targets],
        }

    def write_to_json(self):
        with open(CONFIG_FILE_PATH, 'w') as config_file:
            config_file.write(json.dumps(self.to_dict(), sort_keys=True, indent=2))

    def get_all_targets(self):
        return self._archive_targets + self._pubmed_targets + self._youtube_targets

    @property
    def archive_targets(self):
        return self._archive_targets

    @property
    def pubmed_targets(self):
        return self._pubmed_targets

    @property
    def youtube_targets(self):
        return self._youtube_targets
