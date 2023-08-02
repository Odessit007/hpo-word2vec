import logging
import os

import dotenv

DEV = 0
suffix = 'dev' if DEV else 'prod'
dotenv.load_dotenv(f'config/.env.{suffix}', verbose=True, override=True)
logger = logging.getLogger(__file__)
logger.setLevel(logging.INFO)


if __name__ == '__main__':
    # Moving import here so that dotenv always runs before and loads the necessary environment variables
    from hpw.data_preprocessing import prepare_data
    logger.info(f'PREFECT_API_URL = {os.getenv("PREFECT_API_URL")}')
    prepare_data(force_download=True, verify_ssl=False, save_to_s3=True)  # run_id='test')
