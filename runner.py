import logging
import os

import dotenv

logger = logging.getLogger(__file__)
logger.setLevel(logging.INFO)
logger.addHandler(logging.StreamHandler())
logger.info(f'PREFECT_API_URL = {os.getenv("PREFECT_API_URL")}')

# MODE = 'cloud'
# dotenv.load_dotenv(f'config/.env.{MODE}', verbose=True, override=True)


if __name__ == '__main__':
    # Moving import here so that dotenv always runs before and loads the necessary environment variables
    from hpw.data_preprocessing import prepare_data
    logger.info(f'PREFECT_API_URL = {os.getenv("PREFECT_API_URL")}')
    # prepare_data(force_download=True, verify_ssl=False)  # run_id='test')
