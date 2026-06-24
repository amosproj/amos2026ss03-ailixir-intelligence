from typing import TypedDict


class TypeBaseScrappingData(TypedDict):
    ref: str


class TypePubMedScrappingData(TypeBaseScrappingData):
    title: str
    authors: list
    publicationDate: str
    abstract: str
    transcript: str
