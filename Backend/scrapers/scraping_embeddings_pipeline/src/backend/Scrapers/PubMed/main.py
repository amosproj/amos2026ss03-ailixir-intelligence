from src.backend.Orchestrator.orchestrator import Orchestrator
from src.backend.ScrappingTarget.pubmed_target import PubMedTarget

if __name__ == '__main__':
    target = PubMedTarget(keywords=['nutrition', 'health'], max_results=3)
    Orchestrator.run_target(target)
