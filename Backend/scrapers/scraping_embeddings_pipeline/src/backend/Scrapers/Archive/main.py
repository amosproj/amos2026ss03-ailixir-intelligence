from src.backend.Orchestrator.orchestrator import Orchestrator
from src.backend.ScrappingTarget.archive_target import ArchiveTarget

if __name__ == '__main__':
    target = ArchiveTarget(keywords=['nutrition', 'health'], max_results=3)
    Orchestrator.run_target(target)
