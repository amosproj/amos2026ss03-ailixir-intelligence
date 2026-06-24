"""Standalone PubMed scraper runner.

Ported from amos2024ss06-health-ai-framework (MIT). Searches PubMed for free
full-text articles matching the given keywords, downloads + extracts their text,
chunks it, and ingests the chunks into the AstraDB vector store.

Replaces the original Orchestrator/Config plumbing (which eagerly imported every
scraper type) with a direct, PubMed-only run.

Run from ``Backend/``:

    python -m scrapers.run_pubmed --keywords nutrition health --max-results 3
"""

import argparse

from .pubmed_target import PubMedTarget


def main():
    parser = argparse.ArgumentParser(
        description='Scrape PubMed free-full-text articles into the AstraDB vector store.'
    )
    parser.add_argument(
        '--keywords', nargs='+', default=['nutrition', 'health'], help='search keywords'
    )
    parser.add_argument(
        '--max-results', type=int, default=3, help='max number of PubMed results to fetch'
    )
    args = parser.parse_args()

    target = PubMedTarget(keywords=args.keywords, max_results=args.max_results)
    elements = target.get_all_new_target_elements()
    print(f'Found {len(elements)} new article(s) to scrape for keywords {args.keywords!r}.')
    for element in elements:
        element.scrape_and_save()
    print('Done.')


if __name__ == '__main__':
    main()
