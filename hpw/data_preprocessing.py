from collections import defaultdict
from copy import copy
from copy import deepcopy
from itertools import chain
import os
from pathlib import Path
import pickle
import re
import string
from typing import Any
from typing import Dict
from typing import List

import httpx
import networkx as nx
import obonet
from prefect import flow
from prefect import get_run_logger
from prefect import task
import tqdm

from hpw.s3_interaction import upload_artifacts_to_s3


CUSTOM_PUNCTUATION = string.punctuation.replace('-', '').replace('/', '')
STOP_WORDS = {'a', 'abnormal', 'abnormality', 'an', 'and', 'are', 'as', 'at',
              'by', 'from', 'in', 'is', 'level', 'of', 'on', 'or', 'so',
              'such', 'that', 'the', 'to', 'which', 'with'}
HPO_URL = 'http://purl.obolibrary.org/obo/hp.obo'
ROOT = 'HP:0000118'


@task(name='Set up local directories')
def set_up_local_directories(local_dir: str):
    path = Path(local_dir)
    if not path.exists():
        path.mkdir(parents=True)


def _save_response_to_file(response: httpx.Response, target_path: Path):
    with target_path.open('wb') as fout:
        total = int(response.headers["Content-Length"])
        with tqdm.tqdm(total=total, unit_scale=True, unit_divisor=1024, unit="B") as progress:
            num_bytes_downloaded = response.num_bytes_downloaded
            for chunk in response.iter_bytes():
                fout.write(chunk)
                progress.update(response.num_bytes_downloaded - num_bytes_downloaded)
                num_bytes_downloaded = response.num_bytes_downloaded


@task(name='Download hp.obo', retries=2, retry_delay_seconds=5, timeout_seconds=240)
def download_hpo_file(local_dir: str, force_download: bool = False, verify_ssl: bool = True) -> Path:
    target_path = Path(local_dir) / "hp.obo"
    if target_path.exists() and not force_download:
        return target_path
    client = httpx.Client(verify=verify_ssl, follow_redirects=True)
    url = os.environ.get('HPO_OBO_PATH', HPO_URL)
    with client.stream("GET", url) as response:
        _save_response_to_file(response, target_path)
    return target_path


def _extract_phenotypic_abnormality_subgraph(graph: nx.MultiDiGraph, inplace=False) -> nx.MultiDiGraph:
    if not inplace:
        graph = deepcopy(graph)
    global_root_id = 'HP:0000001'
    pheno_root_id = ROOT
    top_nodes = [child for (child, _) in graph.in_edges(global_root_id)]
    for node in top_nodes:
        if node == pheno_root_id:
            continue
        ancestors = nx.ancestors(graph, node) | {node}
        graph.remove_nodes_from(ancestors)
    graph.remove_node(global_root_id)
    del graph.nodes[pheno_root_id]['is_a']
    return graph


@task(name="Build HPO graph")
def get_hpo_graph(path: str) -> nx.MultiDiGraph:
    full_graph = obonet.read_obo(path)
    return _extract_phenotypic_abnormality_subgraph(full_graph)


def _get_texts_from_node(node: dict, statistics: dict) -> List[str]:
    texts = [node['name']]
    synonyms = node.get('synonym', [])
    for synonym in synonyms:
        if 'obsolete_synonym' in synonym:
            statistics['n_skipped_obsolete'] += 1
            continue
        _, synonym, details = synonym.split('"')
        if synonym == 'ASD':
            statistics['n_skipped_asd'] += 1
            continue
        texts.append(synonym)
    def_ = re.findall('"(.+)"', node.get('def', ''))
    if def_:
        texts.append(def_[0])
    return texts


@task(name='Extract texts')
def extract_texts(graph: nx.MultiDiGraph) -> tuple:
    hpo_to_texts = defaultdict(set)
    text_to_hpo = {}
    statistics = {'n_skipped_obsolete': 0, 'n_skipped_asd': 0}
    for hpo_id, node in graph.nodes(data=True):
        texts = _get_texts_from_node(node, statistics)
        for text in texts:
            hpo_to_texts[hpo_id].add(text)
            text_to_hpo[text] = hpo_id
    logger = get_run_logger()
    logger.info(f'# of skipped obsolete synonyms: {statistics["n_skipped_obsolete"]}')
    logger.info(f'# of skipped ASD entries: {statistics["n_skipped_asd"]}')
    logger.info(f'# of HPO terms with texts: {len(hpo_to_texts)}')
    logger.info(f'# of sentences (names, synonyms, definitions): {len(text_to_hpo)}')
    return hpo_to_texts, text_to_hpo


def pickle_artifact(artifact: Any, local_dir: str, filename: str) -> Path:
    target_path = Path(local_dir) / filename
    target_path = target_path.with_suffix('.pkl')
    with target_path.open('wb') as fout:
        pickle.dump(artifact, fout)
    return target_path


def tokenizer(
        text: str,
        use_stop_words: bool = True,
        split_words: bool = True
):
    stop_words = STOP_WORDS if use_stop_words else set()
    stop_words.add('')
    punctuation = CUSTOM_PUNCTUATION if split_words else string.punctuation
    words = text.strip().lower().translate(str.maketrans('', '', punctuation)).split(' ')
    tokens = []
    for word in words:
        if word in stop_words:
            continue
        tokens.append(word)
        if not split_words:
            continue
        if '-' in word or '/' in word:
            subwords = [sw for sw in chain.from_iterable(s.split('-') for s in word.split('/')) if sw]
            tokens.extend(subwords)

    if split_words:
        prefixes = ['hyper', 'hypo', 'micro', 'macro']
        current_tokens = copy(tokens)
        for token in current_tokens:
            for prefix in prefixes:
                if token.startswith(prefix):
                    tokens.append(prefix)
                    tokens.append(token[len(prefix):])
                    break
    tokens = [token for token in tokens if token not in stop_words]
    return tokens


@task(name='Tokenize texts', task_run_name='Tokenize texts (use_stop_words={stop}; split_into_subwords={split})')
def tokenize_texts(hpo_to_texts: Dict[str, List[str]], stop: bool, split: bool):
    return {
        hpo_id: [tokenizer(text, stop, split) for text in texts]
        for hpo_id, texts in hpo_to_texts.items()
    }


@flow(name='Prepare data')
def prepare_data(
        local_dir: str = '/opt/data/hpo_w2v/',
        force_download: bool = False,
        verify_ssl: bool = True,
):
    set_up_local_directories(local_dir)
    hpo_file_path = download_hpo_file(local_dir, force_download, verify_ssl)
    graph = get_hpo_graph(hpo_file_path)
    hpo_to_texts, text_to_hpo = extract_texts(graph)
    artifacts = {
        'hpo_to_texts': pickle_artifact(hpo_to_texts, local_dir, 'hpo_to_texts'),
        'text_to_hpo': pickle_artifact(hpo_to_texts, local_dir, 'text_to_hpo'),
    }
    for stop in [True, False]:
        for split in [True, False]:
            name = f'tokens__stop_words={int(stop)}__subwords={int(split)}'
            hpo_to_tokens = tokenize_texts(hpo_to_texts, stop, split)
            artifacts[name] = pickle_artifact(hpo_to_tokens, local_dir, name)
    if os.environ.get('MODE') == 'cloud':
        upload_artifacts_to_s3(artifacts)
