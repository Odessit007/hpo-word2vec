from itertools import chain
from itertools import combinations
from itertools import repeat
import os
import pickle
from pathlib import Path
from typing import Dict
from typing import List
from typing import Literal

from gensim.models import FastText
from gensim.models import Word2Vec
import matplotlib.pyplot as plt
import numpy as np
from prefect import flow
from prefect import task
from scipy.spatial.distance import cosine as cosine_distance
from scipy.stats import wasserstein_distance
import seaborn as sns
import wandb


JOB_TYPES = {'eval', 'train', 'tune'}
RNG = np.random.RandomState(0)


def get_model_kwargs(
        model_name: Literal['word2vec', 'fasttext'] = 'word2vec',
        vector_size: int = 100,
        window: int = 5,
        min_count: int = 1,
        sg: bool = False,
        hs: bool = False,
        shrink_windows: bool = False,
        workers: int = 4,
        compute_loss: bool = True,
        seed: int = 42,
        **kwargs
):
    model_kwargs = dict(
        vector_size=vector_size,
        window=window,
        min_count=min_count,
        workers=workers,
        sg=sg,
        hs=hs,
        shrink_windows=shrink_windows,
        seed=seed,
    )
    if model_name == 'word2vec':
        model_kwargs['compute_loss'] = compute_loss
    return model_kwargs


@task(name='Create model')
def create_model(config: dict):
    model_name = config['model_name']
    model_class = Word2Vec if model_name == 'word2vec' else FastText
    model_kwargs = get_model_kwargs(**config)
    model = model_class(**model_kwargs)
    return model


def prepare_rng(random_state: int | np.random.RandomState | None = None):
    if random_state is None:
        return np.random.RandomState()
    elif isinstance(random_state, np.random.RandomState):
        return random_state
    elif isinstance(random_state, int):
        return np.random.RandomState(random_state)
    else:
        raise ValueError(f'`rng` must be int, None, or np.random.RandomState. Actual type is {type(random_state)}.')


def flatten_tokenized_data(hpo_to_tokens: Dict[str, List[List[str]]]):
    hpo_ids = list(chain.from_iterable(repeat(key, len(vals)) for key, vals in hpo_to_tokens.items()))
    tokenized_sentences = list(chain.from_iterable(hpo_to_tokens.values()))
    return tokenized_sentences, hpo_ids


def get_doc_vector(model, tokens):
    s = np.zeros(model.vector_size)
    n = 0
    for token in tokens:
        try:
            try:
                v = model.wv[token]
            except AttributeError:  # The input is either model object or model.wv
                v = model[token]
        except KeyError:
            continue
        s += v
        n += 1
    return s / n


def get_doc_distance(model, tokens_1: List[str], tokens_2: List[str]):
    v1 = get_doc_vector(model, tokens_1)
    v2 = get_doc_vector(model, tokens_2)
    return cosine_distance(v1, v2)


def get_pairwise_doc_distances(model, doc_pairs):
    return [get_doc_distance(model, tokens_1, tokens_2) for tokens_1, tokens_2 in doc_pairs]


def get_synonym_pairs(hpo_to_tokens):
    return list(chain.from_iterable((combinations(x, 2) for x in hpo_to_tokens.values())))


def get_non_synonym_pairs(hpo_to_tokens, n_pairs, random_state=None, max_iter=None):
    if max_iter is None:
        max_iter = 4 * n_pairs
    tokens, hpo_ids = flatten_tokenized_data(hpo_to_tokens)
    n = len(tokens)
    n_iter = 0
    non_synonym_pairs = []
    rng = prepare_rng(random_state)
    while len(non_synonym_pairs) < n_pairs or n_iter < max_iter:
        n_iter += 1
        i = rng.randint(0, n - 1)
        j = rng.randint(0, n - 1)
        if hpo_ids[i] == hpo_ids[j]:
            continue
        non_synonym_pairs.append((tokens[i], tokens[j]))
    return non_synonym_pairs


@task(name='Plot distributions')
def plot_distributions(
        model_name: str,
        synonym_dist: List[float],
        non_synonym_dist: List[float],
        wasserstein_dist: float,
):
    fig, ax = plt.subplots()
    plt.suptitle(f'[{model_name}] Pairwise distances (Wasserstein: {wasserstein_dist:.2f})')
    sns.histplot(synonym_dist, kde=True, stat='density', kde_kws=dict(cut=3), alpha=.4, edgecolor=(1, 1, 1, .4),
                 ax=ax, label='Pairwise synonym distances')
    sns.histplot(non_synonym_dist, kde=True, stat='density', kde_kws=dict(cut=3), alpha=.4, edgecolor=(1, 1, 1, .4),
                 ax=ax, label='Pairwise non-synonym distances')
    plt.legend()
    plt.show()


def log_dist_histogram(array: np.ndarray | List[float], title: str):
    table = wandb.Table(data=[[val] for val in array], columns=['distance'])
    wandb.log({title: wandb.plot.histogram(table, 'distance', title=title)}, step=0)


@task(name='Get synonym and non-synonym pairs')
def get_text_pairs(hpo_to_tokens: Dict[str, List[List[str]]], random_state=None):
    synonym_pairs = list(chain.from_iterable((combinations(x, 2) for x in hpo_to_tokens.values())))
    non_synonym_pairs = get_non_synonym_pairs(hpo_to_tokens, len(synonym_pairs), random_state)
    print('# of synonym pairs:', len(synonym_pairs))
    print('# of non-synonym pairs:', len(non_synonym_pairs))
    return synonym_pairs, non_synonym_pairs


def calculate_scores_on_dataset(
        model,
        synonym_pairs,
        non_synonym_pairs
):
    print('Calculating distances')
    synonym_dist = get_pairwise_doc_distances(model, synonym_pairs)
    non_synonym_dist = get_pairwise_doc_distances(model, non_synonym_pairs)
    mean_synonym_dist = np.mean(synonym_dist)
    mean_non_synonym_dist = np.mean(non_synonym_dist)
    wasserstein_dist = wasserstein_distance(synonym_dist, non_synonym_dist)
    print('Mean synonym pairwise distance:', mean_synonym_dist)
    print('Mean non-synonym pairwise distance:', mean_non_synonym_dist)
    print('Wasserstein distance between synonym and non-synonym pairwise distances:', wasserstein_dist)
    wandb.log({
        'Mean synonym pairwise distance': mean_synonym_dist,
        'Mean non-synonym pairwise distance': mean_non_synonym_dist,
        'Wasserstein distance': wasserstein_dist,
    }, step=0)
    return synonym_dist, non_synonym_dist, wasserstein_dist


@task(name='Initialize W&B run')
def init_run(job_type: Literal['tune', 'train', 'eval'], config: dict):
    if wandb.run is None:
        return wandb.init(
            project=os.environ['WANDB_PROJECT'],
            job_type=job_type,
            config=config
        )
    return wandb.run


@task(name='Download dataset')
def download_artifact(artifact_type: Literal['dataset', 'model'], config: dict):
    if artifact_type not in ['dataset', 'model']:
        raise ValueError(f'artifact_type must be "dataset" or "model". Received {artifact_type}')
    run = wandb.run
    if artifact_type == 'dataset':
        artifact_name = get_dataset_name_from_config(config)
    else:
        artifact_name = config['model_artifact_name']
    full_artifact_name = f'{run.entity}/{run.project}/{artifact_name}:latest'
    artifact = run.use_artifact(full_artifact_name, type=artifact_type)
    download_directory = artifact.download()
    return artifact_name, download_directory


@task(name='Update best model file')
def save_best_model(model, wasserstein_dist: float) -> Path | None:
    run = wandb.run
    sweep_id = f'{run.entity}/{run.project}/{run.sweep_id}'
    api = wandb.Api()
    sweep = api.sweep(sweep_id)
    best_run = sweep.best_run()
    update = False
    if best_run.state == 'running':
        update = True
    elif best_run.history()['Wasserstein distance'].iloc[0] < wasserstein_dist:
        update = True
    if not update:
        return
    best_model_directory = Path(os.environ['LOCAL_ARTIFACTS_DIR']) / 'models'
    best_model_directory.mkdir(parents=True, exist_ok=True)
    best_model_path = best_model_directory / 'best_model.pkl'
    with best_model_path.open('wb') as fout:
        pickle.dump(model.wv, fout)
    return best_model_path


@task(name='Update best model artifact')
def update_best_model_artifact(best_model_path: Path):
    run = wandb.run
    best_model = wandb.Artifact('best_model', type='model')
    best_model.add_file(str(best_model_path))
    run.log_artifact(best_model, aliases=['latest'])
    run.link_artifact(best_model, 'model-registry/Best Tuned Model')


@flow(name='Train model', log_prints=True)
def model_flow(job_type: Literal['tune', 'train', 'eval'], config: dict):
    if job_type not in JOB_TYPES:
        raise ValueError(f'job_type must be "tune", "train", or "eval". Received: {job_type}.')
    run = init_run(job_type, config)
    dataset_name, dataset_directory = download_artifact('dataset', config)
    with (Path(dataset_directory) / f'{dataset_name}.pkl').open('rb') as fin:
        hpo_to_tokens = pickle.load(fin)
    sentences, _ = flatten_tokenized_data(hpo_to_tokens)
    if job_type == 'eval':
        model_name, model_directory = download_artifact('model', config)
        with (Path(model_directory) / f'{model_name}.pkl').open('rb') as fin:
            model = pickle.load(fin)
    else:
        model = create_model(config)
        model.build_vocab(sentences)
        model.train(sentences, total_examples=model.corpus_count, epochs=model.epochs)
    synonym_pairs, non_synonym_pairs = get_text_pairs(hpo_to_tokens, RNG)
    synonym_dist, non_synonym_dist, wasserstein_dist = calculate_scores_on_dataset(model, synonym_pairs, non_synonym_pairs)
    if job_type != 'tune':
        return model, wasserstein_dist
    if run.sweep_id is None:
        raise RuntimeError(f'run.sweep_id is None, but if the job type is "tune", the job must run within a sweep.')
    best_model_path = save_best_model(model, wasserstein_dist)
    if best_model_path is not None:
        update_best_model_artifact(best_model_path)
    return model, wasserstein_dist


def get_dataset_name_from_config(config: dict):
    stop = config['use_stop_words']
    split = config['split_into_subwords']
    return f'tokens__stopwords_{int(stop)}__subwords_{int(split)}'


def objective():
    with wandb.init():
        config = dict(wandb.config)
        model_flow('tune', config)


def tune(n_runs: int):
    sweep_configuration = {
        'method': 'grid',
        'metric':
            {
                'goal': 'maximize',
                'name': 'Wasserstein distance'
            },
        'parameters':
            {
                'use_stop_words': {'values': [False, True]},
                'split_into_subwords': {'values': [False, True]},
                'model_name': {'values': ['word2vec', 'fasttext']},
                'vector_size': {'values': [10, 25, 50, 75, 100]},
                'window': {'values': [2, 3, 4, 5]},
                'min_count': {'values': [1, 2, 3, 4, 5]},
                'sg': {'values': [False, True]},
                'hs': {'values': [False, True]},
                'shrink_windows': {'values': [False, True]},
            }
    }
    sweep_id = wandb.sweep(
        sweep=sweep_configuration,
        project=os.environ['WANDB_PROJECT']
    )
    _ = wandb.agent(sweep_id, function=objective, count=n_runs)
    return sweep_id


# TODO
"""
[v] Saving best model locally to a pickle file
[v] Saving dataset as a W&B artifact linked to a run
[v] Saving best model as a W&B artifact linked to a run
[v] Loading W&B model from a run
[] Review Lambda deployment examples from weeks 3 and 6
"""

# def best_model_selection():
#     sweep_id = tune()
#     api = wandb.Api()
#     if current_model_loss < api.Sweep('...').best_run.config['loss']:
#         # Store model artifact
#         artifact = wandb.Artifact(...)
#         ...
#         run.log_artifact(artifact)



# tune()
# train_model('word2vec', {})

# # Retrieving vectors and corresponding words
# wv = model.wv
# for index, word in enumerate(wv.index_to_key):
#     if index == 10:
#         break
#     print(f"word #{index}/{len(wv.index_to_key)} is {word}")

# wv.most_similar(positive=[], negative=[], topn=5)
# wv.doesnt_match([])
