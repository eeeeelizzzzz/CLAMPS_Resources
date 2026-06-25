CLAMPS review collection (clean export)
=====================================
File: clamps_review_corpus_clean.csv
Works: 726

This file supports the bibliometric figures in the CLAMPS review paper.
One row per work in the finalized review collection.

Column guide
------------
work_key              Unique identifier (doi:… or openalex:…)
doi                   Digital Object Identifier (normalized)
openalex_id           OpenAlex work URL/id
title                 Work title
year                  Publication/deposit year
work_type             Article | Report | Dataset | Thesis
corpus_class          Internal class (article/report/dataset/thesis)
corpus_source         Pipeline source (hc_publications, ground_truth_mandatory,
                      data_deposits, theses_master)
inclusion_pathway     Human-readable inclusion rule applied
in_ground_truth_registry  yes if listed in data/ground_truth_clamps_papers.csv
in_seed_dataset_registry  yes if listed in data/clamps_dataset_dois.txt (datasets)
discovery_channel     Discovery channel bucket (A–H, G=ground truth)
discovery_source      Full discovery provenance string
confidence_tier       Discovery confidence (high/medium/low)
campaign_labels_auto  Campaign tags from automated rules (title, discovery,
                      anchors, abstract, PDF mentions)
campaign_labels_final Campaign tags after manual review overrides (Supp. Fig. S1)
manual_campaign_review yes if work appears in data/campaign_review_overrides.csv
source_link           Landing page or publisher link
pdf_url               Resolved PDF URL when available
cited_by_count        OpenAlex citation count at discovery time
openalex_type         OpenAlex work type
manual_thesis_flag    y for manually accepted theses

Build command
-------------
  python scripts/ensure_mandatory_corpus_inputs.py
  python scripts/build_review_corpus.py
  python scripts/export_review_corpus_clean.py

Counts by work_type
-------------------
work_type
Article    570
Dataset    107
Report      20
Thesis      29

Counts by inclusion_pathway
---------------------------
inclusion_pathway
High-confidence publication              461
Ground-truth registry (mandatory)        132
Seed dataset DOI registry (mandatory)     65
Validated data deposit                    42
Manually accepted thesis                  26
