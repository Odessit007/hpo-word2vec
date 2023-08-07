import logging
import os

import dotenv

logger = logging.getLogger(__file__)
logger.setLevel(logging.INFO)
logger.addHandler(logging.StreamHandler())

MODE = 'cloud'
dotenv.load_dotenv(f'config/.env.{MODE}', verbose=True, override=True)
dotenv.load_dotenv(f'config/.env.aws', verbose=True, override=True)


if __name__ == '__main__':
    # Moving import here so that dotenv always runs before and loads the necessary environment variables
    from hpw.data_preprocessing import prepare_data
    logger.info(f'PREFECT_API_URL = {os.getenv("PREFECT_API_URL")}')
    # prepare_data(force_download=True, verify_ssl=False)
    from hpw.training import model_flow, tune
    tune()
    # _, score = model_flow('eval', dict(
    #     model_name='word2vec',
    #     use_stop_words=False,
    #     split_into_subwords=True,
    #     model_artifact_name='best_model',
    # ))
    # print(score)
