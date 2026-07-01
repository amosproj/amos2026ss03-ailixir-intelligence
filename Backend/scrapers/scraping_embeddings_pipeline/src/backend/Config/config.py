"""To add a new target type to the Config class:

1. __init__: Add a private variable to store instances of the new target type.
2. from_json: Parse JSON data to initialize instances of the new target type.
3. add_target: Handle the addition of new target type instances.
4. to_dict: Include the new target type in the dictionary representation.
5. write_to_json: Serialize instances of the new target type to JSON.
6. Property Method: Add a property method to retrieve instances of the new target type.
"""

import json

from src.backend.Config import CONFIG_FILE_PATH
from src.backend.ScrappingTarget.all_recipes_target import AllRecipesTarget
from src.backend.ScrappingTarget.archive_target import ArchiveTarget
from src.backend.ScrappingTarget.nutrition_target import NutritionTarget
from src.backend.ScrappingTarget.podcast_target import PodcastTarget
from src.backend.ScrappingTarget.pubmed_target import PubMedTarget
from src.backend.ScrappingTarget.youtube_target import YouTubeTarget


class Config:
    def __init__(self):
        self._all_recipes_targets: [] = []
        self._archive_targets: [] = []
        self._podcast_targets: [] = []
        self._pubmed_targets: [] = []
        self._youtube_targets: [] = []
        self._nutrition_targets: [] = []

    @classmethod
    def from_json(cls, path: str = CONFIG_FILE_PATH) -> 'Config':
        with open(path) as config_file:
            json_data = json.load(config_file)
            config = cls()
            config._all_recipes_targets = [
                AllRecipesTarget(**entry) for entry in json_data.get('all_recipes_targets', [])
            ]
            config._archive_targets = [
                ArchiveTarget(**entry) for entry in json_data.get('archive_targets', [])
            ]
            config._podcast_targets = [
                PodcastTarget(**entry) for entry in json_data.get('podcast_targets', [])
            ]
            config._pubmed_targets = [
                PubMedTarget(**entry) for entry in json_data.get('pubmed_targets', [])
            ]
            config._youtube_targets = [
                YouTubeTarget(**entry) for entry in json_data.get('youtube_targets', [])
            ]
            config._nutrition_targets = [
                NutritionTarget(**entry) for entry in json_data.get('nutrition_targets', [])
            ]
            return config

    def add_target(self, target):
        if isinstance(target, AllRecipesTarget):
            self._all_recipes_targets.append(target)
        elif isinstance(target, ArchiveTarget):
            self._archive_targets.append(target)
        elif isinstance(target, PodcastTarget):
            self._podcast_targets.append(target)
        elif isinstance(target, PubMedTarget):
            self._pubmed_targets.append(target)
        elif isinstance(target, YouTubeTarget):
            self._youtube_targets.append(target)
        elif isinstance(target, NutritionTarget):
            self._nutrition_targets.append(target)
        else:
            raise ValueError(f'Unknown target type: {type(target)}')

    def to_dict(self):
        return dict(
            all_recipes_targets=[target.to_dict() for target in self._all_recipes_targets],
            archive_targets=[target.to_dict() for target in self._archive_targets],
            podcast_targets=[target.to_dict() for target in self._podcast_targets],
            pubmed_targets=[target.to_dict() for target in self._pubmed_targets],
            youtube_targets=[target.to_dict() for target in self._youtube_targets],
            nutrition_targets=[target.to_dict() for target in self._nutrition_targets],
        )

    def write_to_json(self):
        config_data = json.dumps(self.to_dict(), sort_keys=True, indent=2)
        with open(CONFIG_FILE_PATH, 'w') as config_file:
            config_file.write(config_data)

    def get_all_targets(self) -> []:
        return (
            []
            + self._all_recipes_targets
            + self._archive_targets
            + self._pubmed_targets
            + self._youtube_targets
            + self.podcast_targets
            + self._nutrition_targets
        )

    @property
    def all_recipes_targets(self):
        return self._all_recipes_targets

    @property
    def archive_targets(self):
        return self._archive_targets

    @property
    def podcast_targets(self):
        return self._podcast_targets

    @property
    def pubmed_targets(self):
        return self._pubmed_targets

    @property
    def youtube_targets(self):
        return self._youtube_targets

    @property
    def nutrition_targets(self):
        return self._nutrition_targets
