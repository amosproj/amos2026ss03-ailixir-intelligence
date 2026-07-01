import datetime
import os


def write_to_log(url, message, scraping_target, log_file=os.path.join('data', 'log', 'log.txt')):
    """Writes a message to a log file with a timestamp.

    Parameters
    ----------
    message (str): The message to write to the log file.
    log_file (str): The path to the log file. Default is 'logfile.txt'.

    """
    try:
        with open(log_file, 'a') as file:
            timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            file.write(f'{timestamp} - {url} - {scraping_target} - {message}\n')
        print(f'Message logged to {log_file}')
    except Exception as e:
        print(f'An error occurred while writing to the log file: {e}')
