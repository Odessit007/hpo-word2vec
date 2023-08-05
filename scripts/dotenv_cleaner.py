"""
dotenv files with credentials should not be shared on Git, but it's still important
for the users to know which keys must be set. This script processes the "hidden" dotenv
files with credentials and produces draft files containing only the keys, so that these
drafts can be shared on Git.
"""


import dotenv
from pathlib import Path


keys_to_keep_vals = [
    'AWS_BLOCK_NAME', 'HPO_OBO_PATH', 'LOCAL_ARTIFACTS_DIR', 'MODE', 'N_SWEEP_RUNS', 'NUMPY_RANDOM_SEED',
    'PREFECT_API_ENABLE_HTTP2', 'PREFECT_API_URL', 'PREFECT_LOGGING_EXTRA_LOGGERS', 'PREFECT_LOGGING_LEVEL',
    'PYTHONHASHSEED', 'REMOTE_ARTIFACTS_DIR', 'WANDB_BASE_URL', 'WANDB_MODE'
]
config_root_dir = Path('config/')
files_with_credentials = ['.env.aws', '.env.cloud', '.env.local']
for file in files_with_credentials:
    input_path = config_root_dir / file
    output_path = input_path.with_name(file + '.template')
    print(f'Processing {input_path}. Writing to {output_path}.')
    with input_path.open() as fin:
        config = {}
        for line in fin:
            line = line.strip().removeprefix('export ')
            if not line:
                continue
            key, val = line.split('=', maxsplit=1)
            config[key] = val
    with output_path.open('w') as fout:
        for key in sorted(config):
            if key in keys_to_keep_vals or key.removeprefix('# ') in keys_to_keep_vals:
                fout.write(f'{key}={config[key]}\n')
            else:
                fout.write(f'{key}={"?" * 50}\n')
