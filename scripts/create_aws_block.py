import logging
import os
from pathlib import Path

import dotenv


logger = logging.getLogger(Path(__file__).name)
logger.setLevel(logging.INFO)

logger.info('Loading environment variables')
dotenv.load_dotenv('config/.env.aws', verbose=True, override=True)
dotenv.load_dotenv('config/.env.cloud', verbose=True, override=True)
block_name = os.environ['AWS_BLOCK_NAME']


def create_block():
    from prefect_aws import AwsCredentials  # This import must happen after the load_dotenv call
    aws_credentials_block = AwsCredentials(
        aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
        aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
        aws_session_token=os.getenv('AWS_SESSION_TOKEN')
    )
    aws_credentials_block.save(block_name, overwrite=True)
    logger.info(f'Block {block_name} was successfully created.')


create_block()
