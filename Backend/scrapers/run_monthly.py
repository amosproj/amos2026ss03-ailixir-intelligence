#!/usr/bin/env python3
"""Monthly scraper entrypoint for the Cloud Run Job.

Flow each run:
  1. Pull the persistent ``data/`` tree (dedup indexes + paper registry +
     YouTube channel_map) down from the GCS state bucket.
  2. Compute the "last month" window for date-filtered paper sources.
  3. Drive config + orchestrator ONCE PER keyword phrase (papers) and ONCE PER
     channel (YouTube) — because PubMed AND-joins keyword tokens and arXiv is
     run with ``--archive-query-mode and``, so a whole CSV must not be dumped
     into a single query.
  4. Push the updated ``data/`` tree back to the bucket so next month's run
     knows what was already ingested.

Every knob is an environment variable so the same image serves any schedule or
corpus without a rebuild:

  STATE_BUCKET     GCS bucket holding the persistent data/ tree. Without it the
                   run still works but re-scrapes from scratch every month
                   (AstraDB's deterministic IDs still prevent duplicate vectors,
                   but you waste embedding calls).
  SCRAPER_TARGETS  space-separated paper targets per keyword (default
                   "pubmed archive").
  RUN_YOUTUBE      "1" to also run the YouTube channel loop (default "1").
  MAX_RESULTS      results per keyword query per source (default "5").
  YOUTUBE_LIMIT    newest videos inspected per channel (default "25").
  DOMAIN/SUB_DOMAIN vector metadata (default "medical" / "oncology").
  KEYWORDS_DIR     folder with *_keywords.csv + the channels csv (default
                   "<pipeline root>/key_words").
  SINCE_DATE       override the auto-computed since-date (YYYY-MM-DD).
"""
import csv
import json
import os
import subprocess
import sys
from datetime import date

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(ROOT, 'data')
STATE_PREFIX = 'data/'
STATUS_LOG = os.path.join(DATA_DIR, 'log', 'scrape_status.jsonl')

# Without these the run produces nothing, so fail fast instead of an hour later.
REQUIRED_ENV = ('OPEN_AI_API', 'ASTRA_DB_API_ENDPOINT', 'ASTRA_DB_TOKEN',
                'ASTRA_DB_NAMESPACE', 'ASTRA_DB_COLLECTION')

_subprocess_errors = 0


# ── GCS state persistence ─────────────────────────────────────────────────────

def _bucket(name):
    # Imported lazily so the script runs locally without google-cloud-storage
    # when STATE_BUCKET is unset.
    from google.cloud import storage

    return storage.Client().bucket(name)


def sync_state_down(bucket_name):
    bucket = _bucket(bucket_name)
    count = 0
    for blob in bucket.list_blobs(prefix=STATE_PREFIX):
        if blob.name.endswith('/'):
            continue
        local = os.path.join(ROOT, blob.name.replace('/', os.sep))
        os.makedirs(os.path.dirname(local), exist_ok=True)
        blob.download_to_filename(local)
        count += 1
    print(f'[state] pulled {count} object(s) from gs://{bucket_name}/{STATE_PREFIX}')


def sync_state_up(bucket_name):
    bucket = _bucket(bucket_name)
    count = 0
    for dirpath, _dirs, files in os.walk(DATA_DIR):
        for name in files:
            local = os.path.join(dirpath, name)
            rel = os.path.relpath(local, ROOT).replace(os.sep, '/')
            bucket.blob(rel).upload_from_filename(local)
            count += 1
    print(f'[state] pushed {count} object(s) to gs://{bucket_name}/{STATE_PREFIX}')


# ── scraping ──────────────────────────────────────────────────────────────────

def first_of_previous_month(today):
    year = today.year - 1 if today.month == 1 else today.year
    month = 12 if today.month == 1 else today.month - 1
    return date(year, month, 1).isoformat()


def run(cmd):
    global _subprocess_errors
    print('[run]', ' '.join(cmd), flush=True)
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        # One bad phrase/channel must not abort the whole monthly run; the
        # orchestrator already isolates per-element failures, this guards the
        # discovery step (e.g. a transient arXiv/PubMed error).
        _subprocess_errors += 1
        print(f'[warn] exit {result.returncode}: {" ".join(cmd)}', file=sys.stderr)


def scrape_phrase(targets, keyword, category, since, cfg):
    build = [
        sys.executable, '-m', 'src.backend.Config.main',
        '--targets', *targets,
        '--keywords', *keyword.split(),
        '--category', category,
        '--domain', cfg['domain'], '--sub-domain', cfg['sub_domain'],
        '--max-results', cfg['max_results'],
        '--archive-query-mode', 'and',
    ]
    if since:
        build += ['--since-date', since]
    run(build)
    run([sys.executable, '-m', 'src.backend.Orchestrator.main'])


def scrape_channel(url, category, cfg):
    run([
        sys.executable, '-m', 'src.backend.Config.main',
        '--targets', 'youtube',
        '--youtube-url', url, '--youtube-limit', cfg['youtube_limit'],
        '--category', category,
        '--domain', cfg['domain'], '--sub-domain', cfg['sub_domain'],
    ])
    run([sys.executable, '-m', 'src.backend.Orchestrator.main'])


def keyword_rows(path):
    with open(path, newline='', encoding='utf-8') as handle:
        for row in csv.DictReader(handle):
            keyword = (row.get('keyword') or '').strip()
            if keyword:
                yield (row.get('category') or '').strip(), keyword


def channel_url(row):
    """Resolve a channel row to a URL the YouTube scraper can use.

    The shipped channels CSV has display names only; get_channel_id() needs a
    real URL/handle. Add a ``url`` or ``handle`` column (e.g. ``@PCRI``) and it
    is picked up here. Rows without one are skipped with a warning.
    """
    for key in ('url', 'channel_url', 'handle'):
        value = (row.get(key) or '').strip()
        if not value:
            continue
        return value if value.startswith('http') else f'https://www.youtube.com/@{value.lstrip("@")}'
    return ''


def line_count(path):
    try:
        with open(path, encoding='utf-8') as handle:
            return sum(1 for _ in handle)
    except FileNotFoundError:
        return 0


def status_counts(start_line):
    """Tally scrape_status.jsonl entries appended after `start_line`."""
    counts = {'success': 0, 'failed': 0, 'skipped': 0}
    try:
        with open(STATUS_LOG, encoding='utf-8') as handle:
            for index, line in enumerate(handle):
                if index < start_line:
                    continue
                try:
                    status = json.loads(line).get('status', '')
                except json.JSONDecodeError:
                    continue
                if status in counts:
                    counts[status] += 1
    except FileNotFoundError:
        pass
    return counts


def exit_code(counts, subprocess_errors):
    # Work was attempted but nothing succeeded -> systemic failure (bad creds,
    # network down, quota). A clean no-op (everything skipped) stays 0.
    if (counts['failed'] or subprocess_errors) and not counts['success']:
        return 1
    return 0


def main():
    missing = [key for key in REQUIRED_ENV if not os.getenv(key)]
    if missing:
        print(f'[fatal] missing required env: {", ".join(missing)}', file=sys.stderr)
        sys.exit(2)

    cfg = {
        'domain': os.getenv('DOMAIN', 'medical'),
        'sub_domain': os.getenv('SUB_DOMAIN', 'oncology'),
        'max_results': os.getenv('MAX_RESULTS', '5'),
        'youtube_limit': os.getenv('YOUTUBE_LIMIT', '25'),
    }
    targets = os.getenv('SCRAPER_TARGETS', 'pubmed archive').split()
    kw_dir = os.getenv('KEYWORDS_DIR', os.path.join(ROOT, 'key_words'))
    since = os.getenv('SINCE_DATE') or first_of_previous_month(date.today())
    bucket = os.getenv('STATE_BUCKET', '').strip()

    run_youtube = os.getenv('RUN_YOUTUBE', '1') == '1'
    if run_youtube and not os.getenv('YOUTUBE_DATA_API_V3'):
        print('[warn] RUN_YOUTUBE=1 but YOUTUBE_DATA_API_V3 is unset — skipping YouTube.',
              file=sys.stderr)
        run_youtube = False

    print(f'[config] targets={targets} youtube={run_youtube} since={since} '
          f'bucket={bucket or "(none)"} max_results={cfg["max_results"]} '
          f'youtube_limit={cfg["youtube_limit"]}')

    if bucket:
        sync_state_down(bucket)

    start_line = line_count(STATUS_LOG)
    try:
        # Papers: one config+orchestrator pass per keyword phrase.
        if targets and os.path.isdir(kw_dir):
            for name in sorted(f for f in os.listdir(kw_dir) if f.endswith('_keywords.csv')):
                for category, keyword in keyword_rows(os.path.join(kw_dir, name)):
                    scrape_phrase(targets, keyword, category, since, cfg)

        # YouTube: one pass per channel that resolves to a URL/handle.
        if run_youtube:
            channels_csv = os.path.join(kw_dir, 'cancer_youtube_channels.csv')
            if os.path.exists(channels_csv):
                seen = set()
                with open(channels_csv, newline='', encoding='utf-8') as handle:
                    for row in csv.DictReader(handle):
                        url = channel_url(row)
                        if not url:
                            print(f'[skip] no url/handle for channel: {row.get("channel")}')
                            continue
                        if url in seen:
                            continue
                        seen.add(url)
                        scrape_channel(url, (row.get('category') or '').strip(), cfg)
    finally:
        if bucket:
            sync_state_up(bucket)

    counts = status_counts(start_line)
    print(f'[summary] success={counts["success"]} failed={counts["failed"]} '
          f'skipped={counts["skipped"]} subprocess_errors={_subprocess_errors}')
    sys.exit(exit_code(counts, _subprocess_errors))


if __name__ == '__main__':
    main()
