from src.backend.Orchestrator.orchestrator import Orchestrator
from src.backend.ScrappingTarget.podcast_target import PodcastTarget

if __name__ == '__main__':
    target = PodcastTarget(num_podcasts=1)
    Orchestrator.run_target(target)
