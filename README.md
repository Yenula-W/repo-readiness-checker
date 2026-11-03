# data-ready — repository readiness checker

Run `data-ready` on a dataset folder **before** you deposit it. It lists what Zenodo, Dryad,
Figshare or the NIH Data Management & Sharing (DMS) policy will ask for, and what is missing.

FAIR checkers such as F-UJI assess data that is already published. `data-ready` runs earlier,
on the folder on your laptop, so you can fix problems before a curator finds them.

Each rule cites the official page it comes from, so a data steward or librarian can check it.

## Quickstart

Needs Python 3.9 or newer (tested on 3.9, 3.12 and 3.13). The repository is private, so `git`
must be able to reach it (for example after `gh auth setup-git`).

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install "data-ready[excel] @ git+https://github.com/Yenula-W/repo-readiness-checker"
mkdir -p demo && printf 'sample,email\ns1,ada@example.org\n' > demo/data.csv
data-ready check demo --target zenodo
data-ready check demo -t dryad -t nih-dms --out report --draft-metadata zenodo
data-ready targets
```

The second check writes `report/readiness-report.md`, `report/readiness-report.json` and a
draft `report/.zenodo.draft.json`. Point it at your own folder instead of `demo`. Use
`--metadata FILE` if your metadata file is not in the dataset folder.

## What it checks

| Area | What it looks for |
|---|---|
| Metadata | Required and recommended fields for the target (title, creators, affiliations, emails, keywords, license, research domain, funding…), read from `.zenodo.json`, `datacite.json`, `CITATION.cff` or `metadata.yaml`. A value found only in the README is a WARN: you still have to enter it on the deposit form. |
| README / data dictionary | A README exists and is in the right format (Dryad needs `.md`). It covers the expected topics (files, variables, units, missing-value codes…). **Every file** and **every CSV/TSV/Excel column** is mentioned in the README or a data dictionary/codebook. |
| Formats | Proprietary formats (`.xlsx`, `.mat`, `.sav`, `.dta`, `.pkl`, `.docx`…) get a suggestion for an open alternative. An open-format twin with the same name (for example `results.csv` next to `results.xlsx`) clears the warning. Formats the repository rejects (Dryad: `.rar`) are a FAIL. |
| License | A license in the metadata or a recognised `LICENSE` file. Dryad accepts CC0 only. |
| File naming | Spaces, special or non-ASCII characters, very long names, names that differ only in case, and junk files (`.DS_Store`, `~$` lock files, `__MACOSX`). |
| Sensitive data | Column names and sample values that look like direct identifiers: names, emails, date of birth, MRN, SSN, phone, address, IP. This is a FAIL for Dryad and NIH DMS and a WARN elsewhere. A bare `Name` column is flagged only if its values look like people's names (so species or site names are not). Files it cannot read (`.xls`, `.sav`, `.dta`, `.mat`…) are listed for a manual check. It is a heuristic only and does **not** replace a disclosure review. |
| Checksums | Checks any `manifest-sha256.txt`, `md5sum.txt` or `SHA256SUMS` file against the data. `--write-manifest` creates one in BagIt format. A missing manifest is only INFO: the repositories compute their own checksums. |
| Archives | Lists what is inside `.zip` files. Flags archives that will not open, archives nested inside archives, and `__MACOSX`/`.DS_Store` junk. Files inside archives are not checked otherwise, and the report says so. |
| Readability | Text files that are not UTF-8, files or folders that cannot be read, and symbolic links (which are never followed). |
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

See [EVALUATION.md](EVALUATION.md) for the held-out test on 26 public datasets and the hand-checked precision.

- The README checks look for keywords and names. They can tell whether a column is *mentioned*, not whether it is explained well.
- PII detection reads only CSV/TSV/TXT and `.xlsx` files. It checks column names and the first 2,000 rows (4 MB). The header patterns are in English only, and it does not read free text, images, `.xls`, SPSS, Stata or other formats.
- Excel parsing assumes the header is in row 1 of each sheet. Large workbooks are slow to open (about 3 s each).
- Files inside archives are not checked; unpack them first.
- Supported metadata formats: Zenodo (`.zenodo.json` or a record from `zenodo.org/api/records/<id>`), DataCite JSON, `CITATION.cff` and `metadata.yaml`. Figshare, Dataverse and OSF exports are not read. The tool tells you so instead of guessing.
- Repository rules change. Every target records the date it was verified; check its sources again before relying on it.
