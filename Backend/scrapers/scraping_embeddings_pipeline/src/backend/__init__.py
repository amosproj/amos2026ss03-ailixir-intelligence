import os

from dotenv import find_dotenv, load_dotenv

# Change current working directory (CWD) to the root if it's within 'src'
cwd = os.getcwd()
if 'src' in cwd:
    while os.path.basename(cwd) != 'src':
        cwd = os.path.dirname(cwd)
    os.chdir(os.path.dirname(cwd))

# Define paths for data directory, .env file, and .env template
DATA_DIR_PATH = os.path.join('data')
ENV_FILE_PATH = os.path.join('.env')
ENV_TEMPLATE_PATH = os.path.join('.env.template')

# Create data directory if it does not exist
if not os.path.exists(DATA_DIR_PATH):
    try:
        os.mkdir(DATA_DIR_PATH)
        print('Data directory created successfully.')
    except Exception as e:
        print(f'Failed to create the data directory. Error: {e}')

# create log directory if it does not exist
if not os.path.exists(os.path.join('data', 'log')):
    try:
        os.mkdir(os.path.join('data', 'log'))
    except Exception as e:
        print(f'Failed to create the log directory. Error: {e}')


def read_env(file_path):
    """Read the contents of an environment file into a dictionary."""
    if not os.path.exists(file_path):
        return {}
    try:
        with open(file_path, 'r') as file:
            return dict(
                line.strip().split('=', 1)
                for line in file
                if line.strip() and not line.startswith('#')
            )
    except Exception as e:
        print(f'Failed to read {file_path}. Error: {e}')
        return {}


def write_env(file_path, env_dict):
    """Write the contents of a dictionary to an environment file."""
    try:
        with open(file_path, 'w') as file:
            file.writelines(f'{key}={value}\n' for key, value in env_dict.items())
        print(f'{file_path} has been updated.')
    except Exception as e:
        print(f'Failed to write to {file_path}. Error: {e}')


def get_missing_env_value(key, default_value):
    """Use template defaults without blocking CLI commands for user input."""
    return default_value


# Load both .env.template and .env
template_env = read_env(ENV_TEMPLATE_PATH)
actual_env = read_env(ENV_FILE_PATH)

# Check and prompt for missing values
updated = False
for key in template_env:
    if key not in actual_env:
        actual_env[key] = get_missing_env_value(key, template_env[key])
        updated = True

# Write the updated .env file if there were changes
if updated:
    write_env(ENV_FILE_PATH, actual_env)

# Load .env file using python-dotenv
load_dotenv(find_dotenv('.env'))
