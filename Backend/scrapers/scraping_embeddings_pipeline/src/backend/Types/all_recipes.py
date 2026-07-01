from typing import Dict, List, TypedDict

from src.backend.Types.base_type import TypeBaseScrappingData


class NutritionInfo(TypedDict):
    Amount: str
    DailyValue: str


class TypeAllRecipeScrappingData(TypeBaseScrappingData):
    title: str
    subTitle: str
    rating: float
    recipeDetails: Dict[str, str]
    ingredients: List[str]
    steps: List[str]
    nutritionFacts: Dict[str, str]
    nutritionInfo: Dict[str, NutritionInfo]
