import logging
import os
from pathlib import Path

import dotenv
from prefect_aws import AwsCredentials


logger = logging.getLogger(Path(__file__).name)
logger.setLevel(logging.INFO)
logger.info('Loading environment variables')
dotenv.load_dotenv('config/.env.aws', verbose=True, override=True)
dotenv.load_dotenv('config/.env.prod', verbose=True, override=True)
block_name = os.environ['AWS_BLOCK_NAME']
try:
    aws_credentials_block = AwsCredentials.load(block_name)
    logger.info(f'Block {block_name} already exists.')
except ValueError:
    aws_credentials_block = AwsCredentials(
        aws_access_key_id=os.environ['AWS_ACCESS_KEY_ID'],
        aws_secret_access_key=os.environ['AWS_SECRET_ACCESS_KEY'],
        aws_session_token=os.environ['AWS_SESSION_TOKEN'],
        region_name=os.environ['AWS_REGION']
    )
    aws_credentials_block.save(block_name, overwrite=True)
    logger.info(f'Block {block_name} was successfully created.')
