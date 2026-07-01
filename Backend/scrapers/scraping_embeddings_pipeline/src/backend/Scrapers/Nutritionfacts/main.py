from src.backend.Orchestrator.orchestrator import Orchestrator
from src.backend.ScrappingTarget.nutrition_target import NutritionTarget

if __name__ == '__main__':
    target = NutritionTarget(max_pages=1)
    Orchestrator.run_target(target)
