from collections import defaultdict
from copy import deepcopy
from pathlib import Path
import pickle
import re

import httpx
import networkx as nx
import obonet
from prefect import flow
from prefect import get_run_logger
from prefect import task
import tqdm


HPO_URL = 'http://purl.obolibrary.org/obo/hp.obo'
ROOT = 'HP:0000118'


@task(name='Set up local directories')
def set_up_local_directories(local_dir: str):
    logger = get_run_logger()
    logger.info('Test')
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
def download_hpo_file(local_dir: str, force_download: bool = False, verify_ssl: bool = True):
    target_path = Path(local_dir) / "hp.obo"
    if target_path.exists() and not force_download:
        return target_path
    client = httpx.Client(verify=verify_ssl, follow_redirects=True)
    with client.stream("GET", HPO_URL) as response:
        _save_response_to_file(response, target_path)
    return target_path


def _extract_phenotypic_abnormality_subgraph(graph: nx.MultiDiGraph, inplace=False):
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
def get_hpo_graph(path: str):
    full_graph = obonet.read_obo(path)
    return _extract_phenotypic_abnormality_subgraph(full_graph)


def _get_texts_from_node(node: dict, statistics: dict):
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


@task(name='Extract text data')
def get_texts(graph: nx.MultiDiGraph):
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
    artifacts = {'hpo_to_texts': hpo_to_texts, 'text_to_hpo': text_to_hpo}
    return artifacts


@task(name='Pickle artifact')
def pickle_artifact(artifact: dict, local_dir: str, filename: str):
    target_path = Path(local_dir) / filename
    with target_path.with_suffix('.pkl').open('wb') as fout:
        pickle.dump(artifact, fout)


@flow(name='Prepare data')
def prepare_data(
        local_dir: str = '/opt/data/hpo_w2v/',
        force_download: bool = False,
        verify_ssl: bool = True
):
    set_up_local_directories(local_dir)
    hpo_file = download_hpo_file(local_dir, force_download, verify_ssl)
    graph = get_hpo_graph(hpo_file)
    artifacts = get_texts(graph)
    for name, artifact in artifacts.items():
        pickle_artifact(artifact, local_dir, name)
