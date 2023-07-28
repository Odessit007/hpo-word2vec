# hpo-word2vec
ML Ops showcase -- Creating Word2Vec on HPO data for similarity search



# The problem

HPO is the [Human Phenotype Ontology](https://hpo.jax.org/app/). Slightly simplified, you can think of it as a hierarchy
of human disease symptoms. These are mostly used to describe rare genetic diseases.

Each symptom has a name, definition and an optional set of synonyms - all in plain English. The idea of this project is
to try using word2vec for converting the texts from HPO into vectors and using those to do some simple semantic search.

The approach I'm curious to try is this:
* try different word2vec models via `gensim` package: doc2vec, fasttext, bm25, varembed, wordrank with different
embedding dimensions and window sizes
* combine the word vectors into a text vector using simple averaging ot tf-idf-weighted averaging
* assessing the quality of the vectorization by calculating the mean similarity across all pairs of synonyms (going to
treat term definition as one of its synonyms)



# The data

For the purposes of this project, we'll work only with part of the HPO called "phenotypic abnormalities". Let's make
some definitions:
* phenotype is an observable characteristic of the patient
* thus, phenotypic abnormality is an observable abnormality of the patient; a symptom.

It's not always simple to exactly identify a symptom, otherwise medical diagnosis would have been an easy task.
One doctor may identify that the patient has `gangliocytoma` which is a type of brain tumor. The other doctor might
not be sure in the type of tumor (for whatever reason) and might say that there is `brain tumor`. Yet another doctor
might just observe `abnormality of the brain`. All these three terms are examples of the real phenotypes listed in HPO.
As one can guess, these have different levels of specificity growing from gangliocytoma to brain tumor to brain abnormality.

This example highlights the idea of "hierarchy of phenotypes" notion that I mentioned in the first passage. To be more
precise, HPO is a directed acyclic graph ([DAG](https://en.wikipedia.org/wiki/Directed_acyclic_graph)) with a single 
source node called "Phenotypic abnormality" and for each node its children represent more specific symptoms. The children 
of "Phenotypic abnormality", in particular, represent high-level abnormalities of nervous system, immune system, eye, blood,
ear, etc. Going back to example above, `gangliocytoma` lives somewhere in the graph downstream of `abnormality of the 
nervous system`.

Each HPO term has a unique identifier, an official name, a description and (optionally) a set of synonyms:
* `gangliocytoma` has id `HP:0034952`, it's defined as 
```
A low-grade central nervous system tumor composed of dysplastic ganglion cells, usually presenting in children or young 
adults and located in the cerebral hemispheres
```
and doesn't have any synonyms.
* `brain tumor` is actually a synonym of the term HP:0030692 called `brain neoplasm` and defined as
```
A benign or malignant neoplasm that arises from or metastasizes to the brain
```
yet another synonym if `brain tumoUr` which is probably a British English spelling.
* `Abnormality of the brain` is a synonym of the term HP:0012443 called `abnormality of brain morphology` that also has 
one more synonym - `abnormal shape of brain` and is defined as
```
A structural abnormality of the brain, which has as its parts the forebrain, midbrain, and hindbrain
```

I hope you got the idea.



# How to run?
## Installing dependencies
I'm using [PDM](#https://pdm.fming.dev/latest/) to manage dependencies since it provides richer functionality
compared to Pipenv.

Please, check the [installation docs](#https://pdm.fming.dev/latest/#recommended-installation-method) for your 
platform.

```bash
pdm add {packge_1, ..., package_n}  # Install more than one package :)
  -d: add packages to dev dependencies
  -G {group_name}: add packages to a specific group
pdm init  # Create a new project
pdm info  # Get information about the current project
pdm install  # Check the project file for changes, update the lock file if needed, then sync
pdm list  # List installed packages
pdm sync  # Install packages from from the lockfile
  --clean: remove packages no longer in the lockfile
pdm update  # Update the lock file, then sync
```



# The plan

The flow:
[] Data flow:
    [] download HPO file
    [] extract all texts from it
    [] split data into 80/20 train/test split
    [] generate synonym pairs for train and test datasets
    [] add Prefect orchestration
    [] store results locally or in S3 (control via the config file)
[] Modeling:
    [] run modeling experiments using MLflow for experiment tracking
    [] use 5-fold cross-validation for each combination of hyperparameters
    [] use mean of cosine similarity as a metric on each fold
    [] use mean of means as the target metric optimized with Optuna
    [] choose the best-performing model and set of hyperparameters
