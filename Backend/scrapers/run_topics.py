"""Scrape the curated disease list into the global AstraDB literature corpus.

Iterates `topics.DISEASE_TOPICS`; for each disease it runs a PubMed search with that
disease's keywords and ingests the results tagged with the disease's canonical
`disease` metadata (so the chat retriever can filter by it later).

Run from ``Backend/``:

    python -m scrapers.run_topics --max-results 5
    python -m scrapers.run_topics --disease prostate_cancer --max-results 10
"""

import argparse

from .pubmed_target import PubMedTarget
from .topics import DISEASE_TOPICS


def main():
    parser = argparse.ArgumentParser(
        description='Scrape the curated disease list into the global AstraDB corpus.'
    )
    parser.add_argument(
        '--disease', default=None, help='only scrape this one disease tag (default: all)'
    )
    parser.add_argument(
        '--max-results', type=int, default=5, help='max PubMed results per disease'
    )
    args = parser.parse_args()

    topics = DISEASE_TOPICS
    if args.disease:
        topics = [t for t in topics if t['disease'] == args.disease]
        if not topics:
            known = ', '.join(t['disease'] for t in DISEASE_TOPICS)
            parser.error(f'unknown disease {args.disease!r}. Known: {known}')

    for topic in topics:
        print(f"\n=== {topic['label']} ({topic['disease']}) ===")
        target = PubMedTarget(
            keywords=topic['keywords'],
            max_results=args.max_results,
            disease=topic['disease'],
        )
        elements = target.get_all_new_target_elements()
        print(f'  {len(elements)} new article(s).')
        for element in elements:
            element.scrape_and_save()
    print('\nDone.')


if __name__ == '__main__':
    main()
