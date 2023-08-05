from itertools import chain
from itertools import combinations
from itertools import repeat
import os
import pickle
from pathlib import Path
from time import time
from typing import Dict
from typing import List
from typing import Literal
from typing import Union

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

from hpw.s3_interaction import download_from_s3


def load_local_pickled_artifact(local_path: Union[Path, str]):
    with Path(local_path).open('rb') as fin:
        return pickle.load(fin)


@task(name='Load pickled artifact', task_run_name='Loading {artifact_filename}', retries=3, retry_delay_seconds=5, timeout_seconds=30)
def load_pickled_artifact(artifact_filename):
    if os.getenv('MODE') == 'cloud':
        directory = os.environ['REMOTE_ARTIFACTS_DIR']
        remote_path = Path(directory) / artifact_filename
        local_path = download_from_s3(remote_path=remote_path)
    else:
        local_path = Path(os.environ['LOCAL_ARTIFACTS_DIR']) / artifact_filename
    return load_local_pickled_artifact(local_path)


def get_model_kwargs(
        model_name: Literal['word2vec', 'fasttext'],
        vector_size: int = 100,
        window: int = 5,
        min_count: int = 1,
        sg: bool = False,
        hs: bool = False,
        shrink_windows: bool = False,
        workers: int = 4,
        compute_loss: bool = True,
        seed: int = 42,
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
def create_model(model_name: Literal['word2vec', 'fasttext'], model_kwargs: dict):
    model_class = Word2Vec if model_name == 'word2vec' else FastText
    model_kwargs = get_model_kwargs(model_name, **model_kwargs)
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


# @task(name='Split data into train and test')
# def _train_test_split(dataset: List[List[List[str]]], test_size: float = 0.2):
#     index_array = np.random.rand(len(dataset))
#     train_dataset, test_dataset = [], []
#     for index, entry in zip(index_array, dataset):
#         if index <= test_size:
#             test_dataset.append(entry)
#         else:
#             train_dataset.append(entry)
#     return train_dataset, test_dataset


def get_doc_vector(model, tokens):
    s = np.zeros(model.vector_size)
    n = 0
    for token in tokens:
        try:
            v = model.wv[token]
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


@flow(name='Calculate scores', log_prints=True)
def calculate_scores_on_dataset(
        model,
        synonym_pairs,
        non_synonym_pairs,
        wandb_run=None
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
    if wandb_run:
        wandb.log({
            'Mean synonym pairwise distance': mean_synonym_dist,
            'Mean non-synonym pairwise distance': mean_non_synonym_dist,
            'Wasserstein distance': wasserstein_dist,
        }, step=0)
    return synonym_dist, non_synonym_dist, wasserstein_dist


@flow(name='Train model', log_prints=True)
def train_model(dataset_name: str, model_name: Literal['word2vec', 'fasttext'], model_kwargs: dict, wandb_run=None):
    dataset_name = f'tokens__stop_words=0__subwords=1.pkl'
    hpo_to_tokens = load_pickled_artifact(dataset_name)
    rng = np.random.RandomState(0)
    sentences, _ = flatten_tokenized_data(hpo_to_tokens)
    model = create_model(model_name, model_kwargs)
    model.build_vocab(sentences)
    model.train(sentences, total_examples=model.corpus_count, epochs=model.epochs)
    synonym_dist, non_synonym_dist, wasserstein_dist = calculate_scores_on_dataset(model, hpo_to_tokens, rng, wandb_run)
    if not wandb_run:
        plot_distributions('test', synonym_dist, non_synonym_dist, wasserstein_dist)
    else:
        api = wandb.Api()
        sweep_id = f'{wandb_run.entity}/{wandb_run.project}/{wandb_run.sweep_id}'
        sweep = api.sweep(sweep_id)
        best_run = sweep.best_run()
        if best_run.state != 'running':
            print('*' * 50)
            print(best_run.history()['Wasserstein distance'].iloc[0])
            print('*' * 50)
    return model


def objective():
    with wandb.init() as run:
        config = dict(wandb.config)
        model_name = config['model_name']
        del config['model_name']
        train_model(model_name, config, run)


def tune():
    sweep_configuration = {
        'method': 'grid',
        'metric':
            {
                'goal': 'maximize',
                'name': 'Wasserstein distance'
            },
        'parameters':
            {
                # 'tokens__stop_words={int(stop)}__subwords={int(split)}'
                'use_stop_words': {'values': [False, True]},
                'split_into_subwords': {'values': [False, True]},
                'model_name': {'values': ['word2vec', 'fasttext']},
                'vector_size': {'values': [10, 25, 50, 75, 100]},
                'window': {'values': [2, 3, 4, 5]},
                'min_count': {'values': [1, 2, 3, 4, 5]},
                # 'sg': {'values': [False, True]},
                # 'hs': {'values': [False, True]},
                # 'shrink_windows': {'values': [False, True]},
            }
    }
    sweep_id = wandb.sweep(
        sweep=sweep_configuration,
        project='hpo-test-3'
    )
    wandb.agent(sweep_id, function=objective, count=4)
    return sweep_id


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
