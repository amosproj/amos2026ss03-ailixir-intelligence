"""Scrape PubMed topics relevant to one patient's extracted diagnoses.

The patient graph is scoped by Firebase UID (Graphiti ``group_id``), so this
runner accepts ``--uid``. It reads Diagnosis nodes from Neo4j, maps them to the
curated disease topics in ``topics.py``, then reuses the existing PubMed scraper
for those topic keywords.

Run from ``Backend/``:

    python -m scrapers.run_patient --uid <firebase_uid> --max-results 5
"""

from __future__ import annotations

import argparse

from .patient_topics import resolve_topics_for_uid
from .pubmed_target import PubMedTarget


def main():
    parser = argparse.ArgumentParser(
        description="Scrape PubMed literature for diseases found in a patient's graph."
    )
    parser.add_argument(
        "--uid",
        required=True,
        help="Firebase UID / Graphiti group_id for the patient namespace",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=5,
        help="max PubMed results per resolved disease",
    )
    parser.add_argument(
        "--diagnosis-limit",
        type=int,
        default=200,
        help="max Diagnosis nodes to inspect from the patient graph",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print resolved diseases and keywords without scraping PubMed",
    )
    args = parser.parse_args()

    resolution = resolve_topics_for_uid(args.uid, limit=args.diagnosis_limit)
    print(f"Found {len(resolution.diagnoses)} diagnosis node(s) for uid {args.uid!r}.")

    if not resolution.topics:
        print("No curated disease topics matched this patient's diagnoses.")
        print("Add aliases/ICD prefixes in scrapers/topics.py if this is expected.")
        return

    print("Resolved disease topic(s):")
    for topic in resolution.topics:
        print(f"  - {topic['disease']}: {', '.join(topic['keywords'])}")

    if args.dry_run:
        print("Dry run complete. No PubMed scraping was performed.")
        return

    for topic in resolution.topics:
        print(f"\n=== {topic['label']} ({topic['disease']}) ===")
        target = PubMedTarget(
            keywords=topic["keywords"],
            max_results=args.max_results,
            disease=topic["disease"],
        )
        elements = target.get_all_new_target_elements()
        print(f"  {len(elements)} new article(s).")
        for element in elements:
            element.scrape_and_save()

    print("\nDone.")


if __name__ == "__main__":
    main()
