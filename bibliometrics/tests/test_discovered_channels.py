from __future__ import annotations

from pathlib import Path

import pandas as pd

from clamps_biblio.discovered_channels import (
    dedupe_discovered_records,
    merge_discovery_sources,
    missing_ground_truth_rows,
)
from clamps_biblio.pdf_resolver import normalize_doi


def test_dedupe_prefers_stronger_channel():
    rows = [
        {"doi": "10.1/a", "discovery_source": "channel_e:CHEESEHEAD"},
        {"doi": "10.1/a", "discovery_source": "channel_g:ground_truth"},
    ]
    out = dedupe_discovered_records(rows)
    assert len(out) == 1
    assert out[0]["discovery_source"] == "channel_g:ground_truth"


def test_missing_ground_truth_rows_adds_registry_only(tmp_path: Path):
    gt = tmp_path / "gt.csv"
    gt.write_text(
        "doi,title,year,authors\n"
        "10.1/known,Known Paper,2020,Alice\n"
        "10.1/missing,Missing Paper,2021,Bob\n",
        encoding="utf-8",
    )
    rows = [{"doi": "10.1/known", "discovery_source": "channel_g:ground_truth"}]
    missing = missing_ground_truth_rows(rows, tmp_path, ground_truth_path=gt)
    assert len(missing) == 1
    assert missing[0]["doi"] == "10.1/missing"
    assert missing[0]["discovery_source"] == "channel_g:ground_truth"


def test_merge_discovery_sources_includes_all_ground_truth(tmp_path: Path):
    root = Path(__file__).resolve().parent.parent
    gt = root / "data" / "ground_truth_clamps_papers.csv"
    base = tmp_path / "base.csv"
    base.write_text(
        "doi,title,discovery_source\n"
        "10.1175/bams-d-19-0346.1,Known Paper,channel_d:Alice\n",
        encoding="utf-8",
    )
    merged, stats = merge_discovery_sources(
        root,
        base_path=base,
        thesis_repos_path=None,
        thesis_openalex_path=None,
        ground_truth_path=gt,
    )
    registry = pd.read_csv(gt)
    merged_dois = {normalize_doi(str(d)) for d in merged["doi"].dropna()}
    registry_dois = {normalize_doi(str(d)) for d in registry["doi"].dropna()}
    assert registry_dois.issubset(merged_dois)
    assert stats["ground_truth_overlay"] == len(registry)
    channel_g = merged[merged["discovery_source"].astype(str).str.startswith("channel_g")]
    assert len(channel_g) == len(registry)
