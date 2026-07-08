import argparse
from datetime import date

from src.backend.Config.config import Config
from src.backend.ScrappingTarget.archive_target import ArchiveTarget
from src.backend.ScrappingTarget.pubmed_target import PubMedTarget
from src.backend.ScrappingTarget.youtube_target import YouTubeTarget


def parse_args():
    parser = argparse.ArgumentParser(description='Build data/config.json for scraper orchestration.')
    parser.add_argument('--targets', nargs='+', choices=['archive', 'pubmed', 'youtube'],
                        default=['pubmed'], help='Targets to include in data/config.json.')
    parser.add_argument('--keywords', nargs='+', default=[],
                        help='Search keywords for PubMed and arXiv.')
    parser.add_argument('--since-date', type=date.fromisoformat, default=None, metavar='YYYY-MM-DD',
                        help='Only papers published on/after this date (PubMed and arXiv).')
    parser.add_argument('--max-results', type=int, default=3,
                        help='Maximum search results per keyword target.')
    parser.add_argument('--archive-query-mode', choices=['and', 'or', 'raw'], default='and',
                        help='How arXiv combines keywords; raw passes them unchanged.')
    parser.add_argument('--domain', default='medical', help='Broad domain stored in vector metadata.')
    parser.add_argument('--sub-domain', default='nutrition', help='Sub-domain stored in vector metadata.')
    parser.add_argument('--category', default='',
                        help='Free-form category stored in vector metadata for filtering.')
    parser.add_argument('--youtube-url', default='', help='YouTube channel or video URL to scrape.')
    parser.add_argument('--youtube-limit', type=int, default=10,
                        help='Maximum newest YouTube videos inspected per run.')
    return parser.parse_args()


def build_config(args) -> Config:
    config = Config()
    since = args.since_date.isoformat() if args.since_date else None

    if 'archive' in args.targets:
        config.add_target(ArchiveTarget(
            keywords=args.keywords, max_results=args.max_results, query_mode=args.archive_query_mode,
            domain=args.domain, sub_domain=args.sub_domain, category=args.category, since_date=since,
        ))
    if 'pubmed' in args.targets:
        config.add_target(PubMedTarget(
            keywords=args.keywords, max_results=args.max_results,
            domain=args.domain, sub_domain=args.sub_domain, category=args.category, since_date=since,
        ))
    if 'youtube' in args.targets:
        if not args.youtube_url:
            raise ValueError('--youtube-url is required when target youtube is selected.')
        config.add_target(YouTubeTarget(
            url=args.youtube_url, limit=args.youtube_limit,
            domain=args.domain, sub_domain=args.sub_domain, category=args.category,
        ))
    return config


if __name__ == '__main__':
    build_config(parse_args()).write_to_json()
