"""
dotenv files with credentials should not be shared on Git, but it's still important
for the users to know which keys must be set. This script processes the "hidden" dotenv
files with credentials and produces draft files containing only the keys, so that these
drafts can be shared on Git.
"""


import dotenv
from pathlib import Path


keys_to_keep_vals = ['HPO_OBO_PATH', 'LOCAL_ARTIFACTS_DIR', 'MODE', 'PREFECT_API_URL', 'REMOTE_ARTIFACTS_DIR']
config_root_dir = Path('config/')
files_with_credentials = ['.env.aws', '.env.prod']
for file in files_with_credentials:
    input_path = config_root_dir / file
    output_path = input_path.with_name(file + '.template')
    print(f'Processing {input_path}. Writing to {output_path}.')
    config = dotenv.dotenv_values(input_path)
    with output_path.open('w') as fout:
        for key, val in config.items():
            if key in keys_to_keep_vals:
                fout.write(f'{key}={val}\n')
            else:
                fout.write(f'{key}=\n')
