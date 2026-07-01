import argparse
from datetime import date

from src.backend.Config.config import Config
from src.backend.ScrappingTarget.all_recipes_target import AllRecipesTarget
from src.backend.ScrappingTarget.archive_target import ArchiveTarget
from src.backend.ScrappingTarget.nutrition_target import NutritionTarget
from src.backend.ScrappingTarget.podcast_target import PodcastTarget
from src.backend.ScrappingTarget.pubmed_target import PubMedTarget
from src.backend.ScrappingTarget.youtube_target import YouTubeTarget


def parse_args():
    parser = argparse.ArgumentParser(
        description='Build data/config.json for scraper orchestration.'
    )
    parser.add_argument(
        '--since-date',
        type=date.fromisoformat,
        default=None,
        metavar='YYYY-MM-DD',
        help='Only search for papers published on/after this date (PubMed and arXiv).',
    )
    parser.add_argument(
        '--keywords',
        nargs='+',
        default=[],
        help='Keywords used by keyword-based targets such as PubMed and arXiv.',
    )
    parser.add_argument(
        '--domain',
        default='medical',
        help='Broad domain stored in vector metadata.',
    )
    parser.add_argument(
        '--sub-domain',
        default='nutrition',
        help='Sub-domain stored in vector metadata.',
    )
    parser.add_argument(
        '--targets',
        nargs='+',
        choices=['all_recipes', 'archive', 'nutrition', 'podcast', 'pubmed', 'youtube'],
        default=['nutrition'],
        help='Targets to include in data/config.json.',
    )
    parser.add_argument(
        '--max-results',
        type=int,
        default=3,
        help='Maximum search results per keyword target.',
    )
    parser.add_argument(
        '--archive-query-mode',
        choices=['and', 'or', 'raw'],
        default='and',
        help='How arXiv combines keywords; raw passes the joined keywords unchanged.',
    )
    parser.add_argument(
        '--all-recipes-url',
        default='https://www.allrecipes.com/',
        help='AllRecipes URL to scrape.',
    )
    parser.add_argument(
        '--all-recipes-limit',
        type=int,
        default=10,
        help='Maximum AllRecipes items to scrape.',
    )
    parser.add_argument(
        '--nutrition-pages',
        type=int,
        default=1,
        help='Maximum NutritionFacts pages when using the nutrition target.',
    )
    parser.add_argument(
        '--nutrition-url',
        default='https://nutritionfacts.org/blog/',
        help='NutritionFacts URL to scrape.',
    )
    parser.add_argument(
        '--podcast-url',
        default='https://peterattiamd.com/podcast/archive/',
        help='Podcast archive URL to scrape.',
    )
    parser.add_argument(
        '--num-podcasts',
        type=int,
        default=1,
        help='Maximum podcast episodes to scrape.',
    )
    parser.add_argument(
        '--youtube-url',
        default='',
        help='YouTube channel or video URL to scrape.',
    )
    parser.add_argument(
        '--youtube-limit',
        type=int,
        default=10,
        help='Maximum newest YouTube videos inspected per run.',
    )
    parser.add_argument(
        '--podcast-audio-fallback',
        action='store_true',
        help='Allow local audio download/Vosk transcription when page text is unavailable.',
    )
    return parser.parse_args()


def build_config(args) -> Config:
    config = Config()

    if 'all_recipes' in args.targets:
        config.add_target(
            AllRecipesTarget(
                url=args.all_recipes_url,
                limit=args.all_recipes_limit,
                domain=args.domain,
                sub_domain=args.sub_domain,
            )
        )
    if 'archive' in args.targets:
        config.add_target(
            ArchiveTarget(
                keywords=args.keywords,
                max_results=args.max_results,
                query_mode=args.archive_query_mode,
                domain=args.domain,
                sub_domain=args.sub_domain,
                since_date=args.since_date.isoformat() if args.since_date else None,
            )
        )
    if 'pubmed' in args.targets:
        config.add_target(
            PubMedTarget(
                keywords=args.keywords,
                max_results=args.max_results,
                domain=args.domain,
                sub_domain=args.sub_domain,
                since_date=args.since_date.isoformat() if args.since_date else None,
            )
        )
    if 'nutrition' in args.targets:
        config.add_target(
            NutritionTarget(
                url=args.nutrition_url,
                max_pages=args.nutrition_pages,
                domain=args.domain,
                sub_domain=args.sub_domain,
            )
        )
    if 'podcast' in args.targets:
        config.add_target(
            PodcastTarget(
                url=args.podcast_url,
                num_podcasts=args.num_podcasts,
                use_audio_fallback=args.podcast_audio_fallback,
                domain=args.domain,
                sub_domain=args.sub_domain,
            )
        )
    if 'youtube' in args.targets:
        if not args.youtube_url:
            raise ValueError('--youtube-url is required when target youtube is selected.')
        config.add_target(
            YouTubeTarget(
                url=args.youtube_url,
                limit=args.youtube_limit,
                domain=args.domain,
                sub_domain=args.sub_domain,
            )
        )

    return config

if __name__ == '__main__':
    c = build_config(parse_args())
    c.write_to_json()
