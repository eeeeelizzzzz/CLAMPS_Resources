# Publishing to Zenodo (DOI)

## Recommended: two DOIs

| Record | Content | Type |
|--------|---------|------|
| **Data** | `deliverables/clamps_review_corpus_clean.csv` + README | Dataset |
| **Software** | GitHub release archive (full repo) | Software |

Both can cite the CLAMPS review paper as the related publication.

---

## Software DOI via GitHub integration

1. Push to GitHub — either as the repo root (`bibliometrics/` contents) or as `bibliometrics/` inside a broader CLAMPS monorepo.
2. Create a GitHub release (e.g. `v1.0.0`) when the paper is accepted.
3. Log in to [Zenodo](https://zenodo.org) → Account → GitHub → enable the repository.
4. Zenodo builds an archive from the release tag and assigns a DOI.
5. Copy the DOI into `CITATION.cff` and `README.md`.

Each new GitHub release can get a new Zenodo version DOI (versioned); the concept DOI stays stable.

---

## Dataset DOI (corpus CSV)

1. Zenodo → New upload → Upload files:
   - `deliverables/clamps_review_corpus_clean.csv`
   - `deliverables/clamps_review_corpus_clean_README.txt`
2. Resource type: **Dataset**
3. Title: e.g. "CLAMPS review bibliometric corpus (726 works)"
4. Description: one paragraph on discovery channels and inclusion rules (from README).
5. Related identifier: link to software Zenodo DOI and the review paper.
6. Publish → copy DOI.

---

## Binder + Zenodo together

- **Zenodo** = permanent archive + DOI (cite in paper)
- **Binder** = interactive demo (link from README; no separate DOI)

Binder can build from:
- GitHub repo URL (recommended while developing), or
- Zenodo DOI (after upload — select "Zenodo DOI" on mybinder.org)

Badge template (replace `USER` and `REPO`):

```markdown
[![Binder](https://mybinder.org/badge_logo.svg)](https://mybinder.org/v2/gh/eeeeelizzzzz/CLAMPS_Resources/HEAD?urlpath=lab%2Ftree%2Fbibliometrics%2Fnotebooks%2Freproduce.ipynb)
```

---

## What to put in the paper

> "The 726-work bibliometric corpus is available at [data DOI]. Analysis code and an interactive reproduction notebook are available at [software DOI]."

Optional: link to Binder for interactive exploration.
