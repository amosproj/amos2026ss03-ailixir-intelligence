import datetime
import os

from . import LOG_DIR


def write_to_log(url, message, scraping_target, log_file=None):
    """Writes a message to a log file with a timestamp.

    Parameters
    ----------
    url (str): Identifier of the scraped element.
    message (str): The message to write to the log file.
    scraping_target (str): The scraper / target the message originated from.
    log_file (str): The path to the log file. Defaults to ``data/log/log.txt``.

    """
    if log_file is None:
        log_file = os.path.join(LOG_DIR, 'log.txt')
    try:
        with open(log_file, 'a') as file:
            timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            file.write(f'{timestamp} - {url} - {scraping_target} - {message}\n')
        print(f'Message logged to {log_file}')
    except Exception as e:
        print(f'An error occurred while writing to the log file: {e}')
