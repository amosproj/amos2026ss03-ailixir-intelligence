from src.backend.Types.base_type import TypeBaseScrappingData


class TypePubMedScrappingData(TypeBaseScrappingData):
    title: str
    authors: list
    publicationDate: str
    abstract: str
    transcript: str
    doi: str
