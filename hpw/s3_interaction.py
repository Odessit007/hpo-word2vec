import os
from pathlib import Path
from typing import Dict
from typing import Literal
from typing import Optional
from typing import Union


from prefect import get_run_logger
from prefect import flow
from prefect import task
from prefect_aws import AwsCredentials


def get_s3_client():
    block_name = os.environ['AWS_BLOCK_NAME']
    aws_block = AwsCredentials.load(block_name)
    session = aws_block.get_boto3_session()
    endpoint_url = os.getenv('ENDPOINT_URL')
    if endpoint_url:
        return session.client('s3', endpoint_url=endpoint_url)
    client = session.client('s3')
    return client


def _construct_target_path(
        source_path: Union[Path, str],
        action: Literal['download', 'upload'],
) -> Path:
    if action == 'download':
        directory = os.environ['LOCAL_ARTIFACTS_DIR']
    else:
        directory = os.environ['REMOTE_ARTIFACTS_DIR']
    filename = Path(source_path).name
    return Path(directory) / filename


def _get_log_message(
        source_path: Union[Path, str],
        bucket_name: Optional[str],
        target_path: Optional[Union[Path, str]],
        action: Literal['download', 'upload'],
) -> str:
    if action == 'download':
        source_path_repr = f's3://{bucket_name}/{target_path}'
        target_path_repr = target_path
    else:
        source_path_repr = source_path
        target_path_repr = f's3://{bucket_name}/{source_path}'
    return f'{action.title()}ing from {source_path_repr} to {target_path_repr}'


def _get_file_from_s3(
        source_path: Union[Path, str],
        bucket_name: Optional[str],
        target_path: Optional[Union[Path, str]],
        action: Literal['download', 'upload'],
) -> Path:
    if target_path is None:
        target_path = _construct_target_path(source_path, action)
    if bucket_name is None:
        bucket_name = os.environ['S3_BUCKET']
    logger = get_run_logger()
    logger.info(_get_log_message(source_path, bucket_name, target_path, action))
    s3_client = get_s3_client()
    if action == 'download':
        s3_client.download_file(bucket_name, str(source_path), str(target_path))
    elif action == 'upload':
        s3_client.upload_file(str(source_path), bucket_name, str(target_path))
    else:
        raise ValueError(f'Unsupported action {action}.')
    return target_path


def download_from_s3(
        remote_path: Union[Path, str],
        bucket_name: Optional[str] = None,
        local_path: Optional[Union[Path, str]] = None,
) -> Path:
    logger = get_run_logger()
    logger.info('Trying to download to S3')
    return _get_file_from_s3(remote_path, bucket_name, local_path, 'download')


def upload_to_s3(
        local_path: Union[Path, str],
        bucket_name: Optional[str] = None,
        remote_path: Optional[Union[Path, str]] = None,
) -> Path:
    return _get_file_from_s3(local_path, bucket_name, remote_path, 'upload')


def _s3_task_wrapper(name: str):
    return task(name=name, retries=1, retry_delay_seconds=5, timeout_seconds=30)


download_from_s3_task = _s3_task_wrapper('Download from S3')(download_from_s3)
upload_to_s3_task = _s3_task_wrapper('Upload to S3')(upload_to_s3)


@flow(name='Download artifacts from S3')
def download_artifacts_from_s3(artifacts_data: Dict[str, Union[Path, str]]):
    """
    A utility function used to download remote files from S3. Bucket name is resolved via S3_BUCKET env. var.
    :param artifacts_data: dictionary of the form {"name": Path or 'path'}
    """
    output_data = {}
    for name, local_artifact_path in artifacts_data.items():
        output_data[name] = download_from_s3_task(local_artifact_path)
    return output_data


@flow(name='Upload artifacts to S3')
def upload_artifacts_to_s3(artifacts_data: Dict[str, Union[Path, str]]):
    """
    A utility function used to upload local files to S3. Bucket name is resolved via S3_BUCKET env. var.
    :param artifacts_data: dictionary of the form {"name": Path or 'path'}
    """
    output_data = {}
    for name, local_artifact_path in artifacts_data.items():
        output_data[name] = upload_to_s3_task(local_artifact_path)
    return output_data
