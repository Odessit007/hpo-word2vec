import logging
import os
from pathlib import Path

from dotenv import load_dotenv


logger = logging.getLogger(__file__)
logger.setLevel(logging.INFO)

run_mode = os.environ.get('RUN_MODE', 'cloud')
dotenv_file = Path('config') / ('.env.' + run_mode)
if not dotenv_file.exists():
    raise RuntimeError(f"Dotenv file {dotenv_file} doesn't exist.")
load_dotenv(dotenv_file)
logger.info(f'Loaded environment variables from {dotenv_file}.')
