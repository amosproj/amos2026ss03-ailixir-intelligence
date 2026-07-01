from typing import List

from src.backend.Types.base_type import TypeBaseScrappingData


class TypeYouTubeScrappingData(TypeBaseScrappingData):
    author: str
    videoId: str
    title: str
    keywords: List[str]
    viewCount: str
    shortDescription: str
    transcript: str
