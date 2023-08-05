# TODO ?? Remove ??
# if shuffle_before_split:
#     hpo_ids = list(hpo_to_tokens.keys())
#     rng.shuffle(hpo_ids)
#     hpo_to_tokens = {hpo_id: hpo_to_tokens[hpo_id] for hpo_id in hpo_ids}
#     n_total_2 = sum(len(vals) for vals in hpo_to_tokens.values())
#     assert n_total_2 == n_total


# TODO
# def train_test_split(
#         hpo_to_tokens: Dict[str, List[List[str]]],
#         test_size: float = 0.2,
#         random_state: int | np.random.RandomState | None = None,
# ):
#     n_total = sum(len(vals) for vals in hpo_to_tokens.values())
#     print(n_total)
#     rng = _prepare_rng(random_state)
#     random_scores = rng.random(len(hpo_to_tokens))
#     train, test = {}, {}
#     for random_score, (hpo_id, tokens) in zip(random_scores, hpo_to_tokens.items()):
#         output = test if random_score <= test_size else train
#         output[hpo_id] = tokens
#     n_train = sum(len(vals) for vals in train.values())
#     n_test = sum(len(vals) for vals in test.values())
#     print(f'{n_train / n_total:.3f}, {n_test / n_total: .3f}')
#     return train, test
