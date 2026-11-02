# data-ready — repository readiness checker

Run `data-ready` on a dataset folder **before** you deposit it. It lists what Zenodo, Dryad,
Figshare or the NIH Data Management & Sharing (DMS) policy will ask for, and what is missing.

FAIR checkers such as F-UJI assess data that is already published. `data-ready` runs earlier,
on the folder on your laptop, so you can fix problems before a curator finds them.

Each rule cites the official page it comes from, so a data steward or librarian can check it.

```bash
pip install -e .            # Python 3.9+; add [excel] to inspect .xlsx columns
data-ready check path/to/dataset --target zenodo
data-ready check path/to/dataset -t dryad -t nih-dms --out report/ --draft-metadata zenodo
data-ready targets          # list targets and their source URLs
```

## What it checks

| Area | What it looks for |
|---|---|
| Metadata | Required and recommended fields for the target (title, creators, affiliations, emails, keywords, license, research domain, funding…), read from `.zenodo.json`, `datacite.json`, `CITATION.cff` or `metadata.yaml`. A value found only in the README is a WARN: you still have to enter it on the deposit form. |
| README / data dictionary | A README exists and is in the right format (Dryad needs `.md`). It covers the expected topics (files, variables, units, missing-value codes…). **Every file** and **every CSV/TSV/Excel column** is mentioned in the README or a data dictionary/codebook. |
| Formats | Proprietary formats (`.xlsx`, `.mat`, `.sav`, `.dta`, `.pkl`, `.docx`…) get a suggestion for an open alternative. An open-format twin with the same name (for example `results.csv` next to `results.xlsx`) clears the warning. Formats the repository rejects (Dryad: `.rar`) are a FAIL. |
| License | A license in the metadata or a recognised `LICENSE` file. Dryad accepts CC0 only. |
| File naming | Spaces, special or non-ASCII characters, very long names, names that differ only in case, and junk files (`.DS_Store`, `~$` lock files, `__MACOSX`). |
| Sensitive data | Column names and sample values that look like direct identifiers: names, emails, date of birth, MRN, SSN, phone, address, IP. This is a FAIL for Dryad and NIH DMS and a WARN elsewhere. It is a heuristic only and does **not** replace a disclosure review. |
| Checksums | Checks any `manifest-sha256.txt`, `md5sum.txt` or `SHA256SUMS` file against the data. `--write-manifest` creates one in BagIt format. |
| Sizes | Empty files, per-file limits, total size and file count (Zenodo: 100 files / 50 GB; Figshare: 20 GB; Dryad: 10 GB per file recommended, 2 TB total). |

## Output

- A short summary in the terminal.
- With `--out DIR`: two reports.
  - `readiness-report.md`: a plain-English **fix-it list** (FAIL first, then WARN, each with a source link) and a table of every check.
  - `readiness-report.json`: the same findings plus a per-file SHA-256 and column inventory, for scripts and dashboards.
- `--draft-metadata zenodo|datacite` writes `.zenodo.draft.json` / `datacite.draft.json` from what is known. **It never invents values.** Each value comes from your metadata file, the README's first heading and paragraph, or the LICENSE text. Anything unknown becomes `"TODO: …"`.
- `--strict` exits with code 1 if any target FAILs. Use it in CI.

## Targets are data, not code

Rule files live in [`src/data_ready/rules/`](src/data_ready/rules/). Each one names its sources
and the date it was last verified. Every target inherits shared format and naming advice from
`_common.yaml`.

| Target | File | Main sources |
|---|---|---|
| Zenodo | `zenodo.yaml` | help.zenodo.org: create-new-upload, licenses, manage-files |
| Dryad | `dryad.yaml` | datadryad.org/help: requirements/metadata, requirements/files, guides/best_practices |
| Figshare | `figshare.yaml` | info.figshare.com: metadata schema overview, file size limits |
| NIH DMS | `nih-dms.yaml` | NOT-OD-21-013 (policy), NOT-OD-21-014 (plan elements), NIH repository characteristics |

`nih-dms` is a **policy profile**, not a repository. Combine it with the repository you will
actually use, for example `-t zenodo -t nih-dms`.

To add a repository, copy a YAML file, change it, and run
`data-ready check DIR -t path/to/myrepo.yaml`, or point `--rules-dir` at a folder of rule files.
Minimal example:

```yaml
id: myrepo
name: My Institutional Repository
extends: _common
sources: [https://example.org/deposit-guide]
required_metadata:
  - {field: title, label: Title, why: "Required on deposit form.", source: "https://example.org/deposit-guide"}
license: {required: true, source: "https://example.org/deposit-guide"}
size_limits: {max_file_bytes: 5000000000, source: "https://example.org/deposit-guide"}
```

These are the canonical metadata field names: `title`, `creators` (each with `name`,
`affiliation`, `email`, `orcid`), `description`, `keywords`, `subjects`, `license`,
`publication_date`, `resource_type`, `funding`, `related_identifiers`, `methods`, `version`,
`journal`. To require a value for every creator, use `creator_affiliation`, `creator_email` or
`creator_orcid`.

## Development

```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
```

There are two fixture datasets in `tests/fixtures/`: `good_dataset` and `messy_dataset`.
See [docs/real-world-test.md](docs/real-world-test.md) for a run on five public Zenodo datasets.

## Limitations

- The README checks look for keywords and names. They can tell whether a column is *mentioned*, not whether it is explained well.
- PII detection only reads tabular files (CSV/TSV/Excel). It checks column names and the first 2,000 rows. It does not read free text, images or other formats.
- Excel parsing assumes the header is in row 1 of each sheet.
- Repository rules change. Every target records the date it was verified; check its sources again before relying on it.
