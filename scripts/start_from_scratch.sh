echo "Using Python $1"

echo "Cleaning environment"
rm -rf venv/
rm .pdm-python pyproject.toml pdm.lock

echo "Creating new virtual environment"
python3.10 -m venv venv

echo "Initializing PDM project"
pdm init

echo "Installing dev dependencies"
pdm add -G dev black notebook pre-commit pytest ruff

echo "Installing prod dependencies"
pdm add evidently gensim mlflow prefect prefect-aws python-dotenv
