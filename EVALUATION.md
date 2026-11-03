# Evaluation: data-ready against the adoption-ready bar

Evaluated 2026-11-02/03 on commit `cdb3a4b` and later. Every item of `ADOPTION_BAR.md` is listed below,
with numbers. An item that is not fully met says so.

**Headline precision: 70/73 = 95.9 %, every check type 87.5 % or higher.** This is the first-run
result, with no changes made, on round 5: 31 fresh datasets never used before
([§4c](#4c-untouched-rounds-4-and-5)). The two untouched rounds before it fell short:

| Untouched round | Datasets | Findings judged | Overall | Checks below 80 % | Code |
|---|---|---|---|---|---|
| 3 | 20 | 60 | 91.7 % | encoding, readme, PII | `f2d4e97` |
| 4 | 31 | 72 | 93.1 % | license (5/8) | `a035550` |
| **5** | **31** | **73** | **95.9 %** | **none** | `c6a59a2` |

Each round's errors were fixed (with regression tests) only after its verdicts were committed.
Rounds 1–2 were measured on the set used while fixing, so they are not independent.

| # | Bar item | Status |
|---|---|---|
| 1 | Never crashes on messy input | **Met.** 17 robustness tests; 3 crash/hang classes found and fixed; 0 crashes in any held-out run (216 on the final code) |
| 2 | Clean install from GitHub on 3.9 / 3.12 / 3.13, README quickstart verbatim | **Met** (macOS, fresh venvs) |
| 3 | Held-out run on 20+ real inputs, zero crashes | **Met.** 108 datasets in four sets (Zenodo, Dryad-curated, Figshare, Dataverse, OSF), 0 crashes. All 108 re-run on the final code: 216 runs, 0 crashes |
| 4 | Hand-checked precision ≥ 90 % overall, no check type < 80 % | **Met on the round-5 untouched sample: 70/73 = 95.9 %, lowest check 87.5 %** (encoding, metadata, readme 7/8). Rounds 3 and 4 missed the per-check floor; see [§4c](#4c-untouched-rounds-4-and-5) |
| 5 | Never invents or overstates | **Met after fixes.** 9 overstated or invented outputs found in rounds 1–2, plus a CC BY-SA license reported as CC0 (round 4) and a paper title offered as the abstract (round 5); all fixed |
| 6 | CI green on GitHub, repo private | **Met.** Run 41562437197 on `d12da53`: 4/4 jobs green; repo `PRIVATE` |
| 7 | This file | Done |

## 1. Robustness

`tests/test_robustness.py` runs the full CLI with all four targets on each case and checks that valid
Markdown and JSON reports come out:

- an empty folder
- random binary data and NUL bytes in `.csv` files; empty and header-only tables
- Windows-1252 and UTF-16 CSVs
- malformed `.zenodo.json`, YAML, a YAML list, DataCite JSON with wrong types, a non-UTF-8 `CITATION.cff`, and an unrecognised JSON (a Dataverse export)
- corrupt `.zip`, `.xlsx`, `.png` and `.mat` files; a zip holding `__MACOSX` junk and a nested zip
- a 60 GB sparse file (over Zenodo's 50 GB limit) and a 3 GB single-line "CSV"
- a symlink loop and a dangling symlink
- emoji, accented NFC and NFD, 200-character and leading-dash file names
- an unreadable file and an unreadable folder (`chmod 000`)
- a missing path, a file instead of a folder, and an unwritable `--out` or manifest location

Crashes and hangs found and fixed at the root:

| Problem | Cause | Fix |
|---|---|---|
| Crash on malformed metadata file | `load_metadata` raised on bad JSON/YAML/structure | Raises `MetadataError`; reported as a WARN finding |
| Crash on unreadable file or unwritable output | Hashing and writes were outside `try` | Per-file error capture; `cmd_check` returns exit code 2 with a message |
| Possible infinite walk on symlink loops | `Path.rglob` | `os.walk(followlinks=False)`; links are reported, never followed |
| 52 s and multi-GB memory on a 3 GB single-line CSV | `csv` read the whole "line" | Tables are parsed from the first 4 MB only |
| 35 s on one 80 KB cell (ReDoS) | Unbounded email regex | Bounded regex and 256-character cell cap |
| False "not UTF-8" on valid files | The 64 KB prefix split a multi-byte character | Incremental decoder that tolerates a truncated tail |

## 2. Install from GitHub

The README quickstart was copied verbatim into fresh venvs (macOS arm64). It runs
`pip install "data-ready[excel] @ git+https://github.com/Yenula-W/repo-readiness-checker"`,
creates a demo folder, runs two checks and lists the targets.

| Python | Result |
|---|---|
| 3.9.7 (python.org framework build, pip 21.2.3) | OK: reports and draft written |
| 3.12.15 (uv) | OK |
| 3.13.16 (uv) | OK |

The repository is private, so `git` needs credentials (`gh auth setup-git`); the README says this.

## 3. Held-out real-world run

The five Zenodo datasets used during development ([docs/real-world-test.md](docs/real-world-test.md))
were excluded. The 26 held-out datasets were picked to be messy: Excel only, no README, README in
RTF/Word/PDF, zip/7z/rar archives, nested folders, non-ASCII names, Windows-1252 text, a
human-subjects survey, health data, GIS shapefiles, and files up to 146 MB.

To reproduce:

```bash
python -I eval/fetch_heldout.py eval/heldout.json HELDOUT
python eval/run_heldout.py HELDOUT RESULTS
python eval/run_heldout.py HELDOUT RESULTS_MD --with-metadata
python eval/sample_findings.py RESULTS RESULTS_MD --per-check 7 --seed=20261103
```

Dryad's file download API needs a token, so Dryad is represented by three Dryad-curated datasets
mirrored on Zenodo (DOIs `10.5061/dryad.*`).

| Dataset | Source / field | Files | MB | Seconds | Report bytes |
|---|---|---|---|---|---|
| [7717258](https://zenodo.org/records/7717258) | Dryad (via Zenodo) / prairie ecology | 3 | 0.0 | 2.19 | 62,554 |
| [4988910](https://zenodo.org/records/4988910) | Dryad (via Zenodo) / plant invasion | 2 | 2.0 | 4.30 | 64,051 |
| [4771158](https://zenodo.org/records/4771158) | Dryad (via Zenodo) / fish evolution | 6 | 0.0 | 1.64 | 65,088 |
| [5812145](https://zenodo.org/records/5812145) | Zenodo / human-subjects survey | 5 | 2.7 | 2.19 | 59,528 |
| [13801349](https://zenodo.org/records/13801349) | Zenodo / GIS field survey | 8 | 0.1 | 0.99 | 51,138 |
| [17193374](https://zenodo.org/records/17193374) | Zenodo / geophysics (one zip) | 1 | 16.1 | 1.16 | 50,895 |
| [4095406](https://zenodo.org/records/4095406) | Zenodo / coastal ecology | 55 | 145.6 | 4.28 | 96,598 |
| [17990263](https://zenodo.org/records/17990263) | Zenodo / expert survey | 3 | 0.7 | 9.01 | 60,953 |
| [18492962](https://zenodo.org/records/18492962) | Zenodo / coastal geomorphology | 7 | 2.9 | 1.65 | 52,834 |
| [34890881](https://figshare.com/articles/dataset/34890881) | Figshare / survey (xlsx only) | 1 | 0.1 | 1.21 | 53,342 |
| [34864659](https://figshare.com/articles/dataset/34864659) | Figshare / mycology (zip) | 1 | 9.3 | 2.21 | 57,164 |
| [34857158](https://figshare.com/articles/dataset/34857158) | Figshare / clinical (docx+pdf) | 2 | 0.2 | 1.58 | 49,546 |
| [34891525](https://figshare.com/articles/dataset/34891525) | Figshare / docking (Table 1.xls) | 1 | 0.0 | 0.37 | 52,721 |
| [DVN/29709](https://doi.org/10.7910/DVN/29709) | Dataverse / political science (Stata) | 4 | 2.1 | 0.95 | 59,026 |
| [DVN/DHDNIC](https://doi.org/10.7910/DVN/DHDNIC) | Dataverse / climate & mortality | 3 | 0.2 | 2.37 | 58,845 |
| [DVN/9O4CEK](https://doi.org/10.7910/DVN/9O4CEK) | Dataverse / survey methods (SPSS) | 3 | 0.3 | 3.11 | 56,999 |
| [DVN/MJIVGR](https://doi.org/10.7910/DVN/MJIVGR) | Dataverse / migration attitudes | 3 | 0.4 | 1.05 | 57,249 |
| [DVN/7BG06U](https://doi.org/10.7910/DVN/7BG06U) | Dataverse / paleoclimate (7z) | 10 | 40.1 | 2.32 | 53,795 |
| [DVN/4S6SZU](https://doi.org/10.7910/DVN/4S6SZU) | Dataverse / climate solutions | 37 | 198.1 | 29.42 | 86,297 |
| [DVN/25628](https://doi.org/10.7910/DVN/25628) | Dataverse / conflict studies | 2 | 22.3 | 1.14 | 53,436 |
| [osf gzx8j](https://osf.io/gzx8j/) | OSF / multi-lab psychology | 23 | 2.9 | 2.37 | 98,887 |
| [osf smj2n](https://osf.io/smj2n/) | OSF / EEG (rar only) | 1 | 6.4 | 0.92 | 53,830 |
| [osf 9fpwj](https://osf.io/9fpwj/) | OSF / education (SPSS) | 4 | 0.3 | 0.33 | 54,865 |
| [osf 7dbzg](https://osf.io/7dbzg/) | OSF / medical education survey | 2 | 0.1 | 0.46 | 56,523 |
| [osf pu9rd](https://osf.io/pu9rd/) | OSF / psychology word norms (xlsx) | 12 | 20.6 | 16.97 | 74,394 |
| [osf c846s](https://osf.io/c846s/) | OSF / cognitive psychology | 49 | 26.0 | 3.77 | 73,187 |

**Totals:** 248 files, 500 MB, **0 crashes** in 52 runs (26 datasets, each run with and without
metadata). Median runtime is 2.2 s; the maximum is 29.4 s. Time is dominated by `openpyxl`
opening large workbooks (about 3 s each), and the machine was shared with other jobs during the run.
Reports are 50–99 KB (Markdown and JSON together, all four targets).

Overall results:

- **Without metadata** (the pre-deposit use case): all 26 datasets FAIL every target. This is
  expected: repositories require title, creators and so on, and none was supplied.
- **With each Zenodo record's own metadata** (9 datasets): **0 Zenodo FAILs**, so the Zenodo rules
  are not stricter than Zenodo itself. Dryad, Figshare and NIH still fail for the right reasons:
  CC-BY instead of CC0, no author emails, no Figshare categories, no NIH award.

## 4. Precision, judged by hand

`eval/sample_findings.py` draws a seeded random sample, stratified by check type and, within each
type, by status, so passes are judged as well as problems. Findings that repeat across targets or
runs are counted once. Each finding was judged against the real files and the repository's
published rule. The full sheets, with a note on every judgment, are
[`eval/precision_round1.csv`](eval/precision_round1.csv) and
[`eval/precision_round2.csv`](eval/precision_round2.csv).

| Check | Round 1 correct | Round 1 debatable | Round 2 correct (after fixes) |
|---|---|---|---|
| archives | 6/6 | 0 | 6/6 |
| checksums | 0/7 | 7 | 7/7 |
| encoding | 2/2 | 0 | 2/2 ¹ |
| formats | 4/7 | 3 | 7/7 |
| license | 7/7 | 0 | 7/7 |
| metadata | 7/7 | 0 | 7/7 |
| naming | 7/7 | 0 | 7/7 |
| readme | 6/7 | 1 | 7/7 |
| sensitive (PII) | 7/7 | 0 | 7/7 |
| size | 7/7 | 0 | 7/7 |
| **Total** | **53/64 (83 %)** | **11** | **64/64 (100 %)** |

¹ The round 1–2 set produced only two encoding findings. Round 3 adds three more (§4b). Both are verified (bytes `0xEA` and `0x96`, Windows-1252).

Round 1 had no outright wrong results, but 11 were debatable because they overstated:

- **checksums (7):** a WARN for a missing manifest, although none of the four targets requires
  one. It is now INFO: "No checksum manifest (optional)".
- **formats (3):** `.xlsx`/`.docx` were called "proprietary/closed", although they are ISO/IEC 29500
  standards. The title is now "an open format is preferred".
- **readme (1):** "No README found" when the only file was a zip that might contain one. The
  message now says so.

Before the formal sample, an unsampled pass over all held-out findings (plus the metadata runs)
found the errors below. Each was fixed and has a regression test in
[`tests/test_regressions.py`](tests/test_regressions.py).

| Wrong output | Dataset | Fix |
|---|---|---|
| PII FAIL on a `Name` column of species codes (`G.pan`) | zenodo 4988910 | A bare `name` column needs values that look like people's names |
| "License compatible with CC0" when no license was stated | all Dryad runs | INFO: "No license stated; the repository applies CC0" |
| Dryad rejected Zenodo's CC0 id `cc-zero` | zenodo 7717258, 4988910 | License aliases normalised |
| "Funding present" and "NIH award number present" for DFG/DOE grants (parsed as `[None]`) | zenodo 17193374, 18492962 | Grants parsed as "Funder: code"; NIH award pattern |
| PII "pass" when 0 files were inspected | DVN/25628 and others | No pass unless something was read; uninspected files listed |
| `.rar` passed the Zenodo format check | osf smj2n | `.rar` discouraged for all targets (still FAIL for Dryad) |
| File names in an RTF README missed (smart-quote escapes) | zenodo 4095406 | RTF decoded before matching |
| README named `read me.rtf`, `FileDescription.docx` or an unnamed `.txt` not recognised | zenodo 15351301, 5812145, 4771158 | README-like detection; message asks to rename |
| `Metadata_for_publication.csv` data dictionary ignored | zenodo 7717258 | `metadata` names count as dictionaries |
| Draft title `Title: Where should…` | zenodo 7717258 | `Title:` label stripped |

PII true positive kept: DVN/DHDNIC publishes full dates of birth alongside unique IDs in a
mortality file. Under HIPAA Safe Harbor that is an identifier, and the tool flags it (FAIL for Dryad
and NIH, WARN elsewhere).

## 4b. Fresh untouched held-out sample (round 3)

The datasets used in rounds 1–2 were also used for fixing, so those numbers are not an independent
estimate. Round 3 used **20 new datasets** ([`eval/heldout2.json`](eval/heldout2.json)), none seen
before. The selection included non-UTF-8 text: GBK, Mac Roman and UTF-16. Five OSF datasets were
also listed, but OSF's API returned HTTP 502/503 for over 12 minutes on 2026-11-03, so they could
not be fetched and are not included.

The code was frozen at commit `f2d4e97`. It was run with and without the Zenodo records as
metadata, and a new seeded sample was drawn (`--per-check 7 --seed=20261104`, 60 findings).
Every finding was judged before anything was changed, and the verdicts were committed in
`6bb924e` ([`eval/precision_round3_untouched.csv`](eval/precision_round3_untouched.csv)).

**Crashes:** 0 in 40 runs (20 datasets, each with and without metadata). The datasets total 72 files
and 59 MB; the median runtime was 0.38 s and the maximum 8.15 s. The 26 earlier datasets were
re-run on the final code, also with 0 crashes.

| Dataset | Source | What it exercises | Files | MB | Seconds | Report bytes |
|---|---|---|---|---|---|---|
| [34797510](https://figshare.com/articles/dataset/34797510) | Figshare | RDS + README.txt + CSV | 4 | 0.3 | 0.36 | 60,747 |
| [34804749](https://figshare.com/articles/dataset/34804749) | Figshare | data_dictionary.csv + provenance.json | 7 | 0.0 | 0.33 | 56,416 |
| [34827726](https://figshare.com/articles/dataset/34827726) | Figshare | Single SPSS .sav | 1 | 0.0 | 0.28 | 51,727 |
| [34843410](https://figshare.com/articles/dataset/34843410) | Figshare | Well documented: README, DATA_DICTIONARY, LICENSE | 6 | 0.0 | 0.30 | 55,321 |
| [34874547](https://figshare.com/articles/dataset/34874547) | Figshare | Survey raw/processed CSV, Chinese docx, RAR | 5 | 0.4 | 0.48 | 77,660 |
| [10352789](https://zenodo.org/records/10352789) | Zenodo | French humanities survey CSV + JSON | 2 | 0.2 | 0.37 | 58,626 |
| [10803768](https://zenodo.org/records/10803768) | Zenodo | Dutch survey; README named LEESMIJ.md | 2 | 3.5 | 2.12 | 56,357 |
| [1098538](https://zenodo.org/records/1098538) | Zenodo | Spanish Google Forms export | 1 | 0.1 | 0.32 | 56,678 |
| [12180686](https://zenodo.org/records/12180686) | Zenodo | Precipitation series: .mat files + stations CSV | 5 | 17.1 | 0.36 | 60,898 |
| [12200702](https://zenodo.org/records/12200702) | Zenodo | German survey, 17 files incl. SPSS syntax | 17 | 6.0 | 8.15 | 110,084 |
| [13307952](https://zenodo.org/records/13307952) | Zenodo | German history database: CSV + MS Access .mdb | 4 | 22.0 | 1.39 | 63,335 |
| [14802255](https://zenodo.org/records/14802255) | Zenodo | Tick/bird TXT tables with spaces in names | 2 | 0.0 | 0.33 | 52,171 |
| [15148905](https://zenodo.org/records/15148905) | Zenodo | French survey 'données.csv' | 2 | 2.7 | 0.39 | 58,641 |
| [4938181](https://zenodo.org/records/4938181) | Dryad (via Zenodo) | .xls + README txt | 2 | 0.0 | 0.29 | 59,093 |
| [4945122](https://zenodo.org/records/4945122) | Dryad (via Zenodo) | single TXT with & in name | 1 | 0.0 | 0.54 | 61,023 |
| [4997172](https://zenodo.org/records/4997172) | Dryad (via Zenodo) | mindfulness trial, docx README + xlsx | 2 | 0.0 | 0.71 | 59,558 |
| [5024407](https://zenodo.org/records/5024407) | Dryad (via Zenodo) | README_for_*.txt, spaces in names | 3 | 0.0 | 0.53 | 59,840 |
| [7090079](https://zenodo.org/records/7090079) | Dryad (via Zenodo) | README.txt + CSV | 2 | 0.0 | 0.38 | 58,722 |
| [7420965](https://zenodo.org/records/7420965) | Dryad (via Zenodo) | long README name + CSV | 2 | 0.0 | 0.35 | 59,150 |
| [8437097](https://zenodo.org/records/8437097) | Dryad (via Zenodo) | 6.5 MB CSV + README.md | 2 | 6.5 | 0.55 | 59,249 |

### Untouched first-run precision (headline)

| Check | Correct | Wrong | Debatable | Precision |
|---|---|---|---|---|
| archives | 1 | 0 | 0 | 1/1 = 100 % ¹ |
| checksums | 7 | 0 | 0 | 100 % |
| encoding | 2 | 1 | 0 | **67 %** |
| formats | 7 | 0 | 0 | 100 % |
| license | 7 | 0 | 0 | 100 % |
| metadata | 7 | 0 | 0 | 100 % |
| naming | 7 | 0 | 0 | 100 % |
| readme | 5 | 2 | 0 | **71 %** |
| sensitive (PII) | 5 | 1 | 1 | **71 %** |
| size | 7 | 0 | 0 | 100 % |
| **Total** | **55** | **4** | **1** | **91.7 %** |

¹ Only one dataset in this set contained an archive, so only one archives finding existed.

The bar is not met on this independent sample: the total is above 90 %, but three check types are
below 80 %. The errors were:

| # | Wrong output | Dataset | Root cause → fix |
|---|---|---|---|
| 11 | Detail said three UTF-16 files were "read as Windows-1252/Latin-1" | zenodo 12200702 | The message was fixed text. It now states per file "UTF-16 encoded" or "encoding unknown; read as Windows-1252" |
| 42 | 7 columns "not defined", but the README defines them as `Veg\_type` (Markdown-escaped) | zenodo 8437097 | Markdown escapes are removed before matching. The 2 columns still reported (`N`, `N.SD`) really are undocumented |
| 45 | Data file "not mentioned", but the README names `me\_biomass\_for\_repository.csv` | zenodo 8437097 | Same fix |
| 50 | PII: the author's contact email in a `#Contact …` comment line was read as data | zenodo 4945122 | Leading `#` comment lines are skipped. The file used classic-Mac CR line endings, which are now normalised |
| 51 | (debatable) `IP` column flagged without saying its values are masked (`10.20.*.*`) | figshare 34874547 | The message now says the values appear partly masked and asks the author to check the masking is enough |

One more error was noticed outside the sample and also fixed: the Dutch README `LEESMIJ.md` was
reported as "No README found" (zenodo 10803768). README names in Dutch, German, French, Spanish,
Portuguese and Swedish are now recognised.

Each fix has a regression test, marked "round 3" in `tests/test_regressions.py`. After the fixes,
the same 60 findings were re-judged and all 60 are correct
([`eval/precision_round3_after_fix.csv`](eval/precision_round3_after_fix.csv)). This is **not** an
independent estimate. A further untouched sample would be needed to confirm the fixed readme, PII
and encoding checks reach 80 % or more.

True positive worth noting: zenodo 10803768's `data_anon.csv` ("anonymised") still contains
respondents' personal email addresses in free-text answers. The tool flags it (FAIL for Dryad and
NIH, WARN elsewhere).

## 4c. Untouched rounds 4 and 5

Same protocol as round 3: new datasets only (none from earlier rounds), code frozen, run with and
without the Zenodo records as metadata, a seeded sample drawn (`--per-check 8`), every finding judged
against the files and the verdicts committed **before** any change. The datasets were chosen to stress
the three checks that failed round 3: non-UTF-8 text (screened by reading the bytes, before running the
tool), READMEs in RTF, PDF, Word and ODT, and survey files with personal-data-like columns. OSF was
reachable again and is included.

### Round 4 ([`eval/heldout3.json`](eval/heldout3.json))

Code `a035550`, seed 20261105, verdicts committed in `9fd2786`
([`eval/precision_round4_untouched.csv`](eval/precision_round4_untouched.csv)).
31 datasets: 21 Zenodo, 4 Figshare, 6 OSF; 136 files, 486 MB. **Crashes: 0 in 62 runs** (median 0.42 s,
max 7.61 s). Three `.dta` files over 150 MB in osf pkvrj were not downloaded.

| Check | Correct / judged | Precision |
|---|---|---|
| checksums | 8/8 | 100 % |
| encoding | 8/8 | 100 % |
| formats | 8/8 | 100 % |
| license | 5/8 | **62.5 %** |
| metadata | 7/8 (1 debatable) | 87.5 % |
| naming | 8/8 | 100 % |
| readme | 7/8 | 87.5 % |
| sensitive (PII) | 8/8 | 100 % |
| size | 8/8 | 100 % |
| **Total** | **67/72** | **93.1 %** |

The round-3 fixes held: encoding, README and PII were 8/8, 7/8 and 8/8. License missed the floor:

| # | Wrong output | Dataset | Root cause → fix (`c6a59a2`) |
|---|---|---|---|
| 27, 30 | `license.txt` (CC BY-SA 4.0 legal code) reported as CC0, so Dryad "compatible" | osf hq3k2 | Every CC 4.0 legal code ends with a sentence about CC0. The license named **first** now wins; BY-NC-SA, BY-ND, BY-NC-ND and CC URLs added |
| 29 | "No LICENSE file or license metadata found", but README.md has a `## Licence` section (CC0) and `datapackage.json` declares CC0 | zenodo 23070603 | A license in a README License/Licence section now counts; Frictionless `datapackage.json` is read as metadata |
| 54 | "Missing data codes" topic not found, but the README defines `empty`, `ND = not detected`, `- = not applicable` | zenodo 23506397 | Topic keywords include "not applicable", "not detected", "empty =" and similar |
| 39 | (debatable) NIH "Related publications present" when the only related identifier is a cited dataset | zenodo 6522672 | Label is now "Related identifiers (e.g. publications)" |

True positives worth noting: osf jrsbn has a respondent's personal gmail address in a free-text
answer; osf pkvrj has Prolific relay addresses (`<id>@email.prolific.com`) shifted into a `proceed` column.

<details><summary>Round 4 datasets</summary>

| Dataset | Source | What it exercises | Files | MB | Seconds |
|---|---|---|---|---|---|
| [22976119](https://zenodo.org/records/22976119) | Zenodo | Italian survey CSV, ISO-8859-1 | 2 | 0.1 | 0.29 |
| [23572673](https://zenodo.org/records/23572673) | Zenodo | Spanish survey 'Diagnóstico TS.csv', not UTF-8 | 1 | 0.0 | 0.26 |
| [22405099](https://zenodo.org/records/22405099) | Zenodo | Portuguese questionnaire raw data, not UTF-8 | 1 | 0.0 | 0.27 |
| [20159150](https://zenodo.org/records/20159150) | Zenodo | Spanish online-game survey export, not UTF-8 | 1 | 0.7 | 0.70 |
| [13983577](https://zenodo.org/records/13983577) | Zenodo | Spanish citizen-science participation CSVs, not UTF-8 | 2 | 0.1 | 0.24 |
| [6522672](https://zenodo.org/records/6522672) | Zenodo | French ReadMe_ENSAAM.txt, not UTF-8 | 6 | 2.8 | 0.53 |
| [4776828](https://zenodo.org/records/4776828) | Zenodo | 'READ Me file.txt' not UTF-8 | 5 | 2.7 | 1.26 |
| [10015789](https://zenodo.org/records/10015789) | Zenodo | German survey CSVs in UTF-16 | 3 | 0.1 | 0.34 |
| [7431668](https://zenodo.org/records/7431668) | Zenodo | German medical-student survey CSV, not UTF-8 | 4 | 0.2 | 0.26 |
| [3249965](https://zenodo.org/records/3249965) | Zenodo | German LimeSurvey export, not UTF-8 | 1 | 0.2 | 0.25 |
| [23506397](https://zenodo.org/records/23506397) | Zenodo | README.rtf + biochar CSVs | 8 | 0.4 | 0.44 |
| [23082735](https://zenodo.org/records/23082735) | Zenodo | README.rtf + clinical TXT tables | 13 | 0.1 | 0.26 |
| [21871545](https://zenodo.org/records/21871545) | Zenodo | README.rtf + SNP metadata CSV/VCF | 6 | 3.5 | 0.31 |
| [23422742](https://zenodo.org/records/23422742) | Zenodo | README.pdf + classroom observation CSVs | 10 | 1.1 | 0.25 |
| [21130210](https://zenodo.org/records/21130210) | Zenodo | README.pdf + Portuguese curation log CSV | 2 | 0.0 | 0.27 |
| [23388383](https://zenodo.org/records/23388383) | Zenodo | README.docx + data_dictionary.csv | 5 | 0.3 | 0.40 |
| [23105051](https://zenodo.org/records/23105051) | Zenodo | README.docx + studentdata.csv | 3 | 0.0 | 0.26 |
| [6558309](https://zenodo.org/records/6558309) | Zenodo | README.odt + choices CSV | 2 | 0.0 | 0.25 |
| [18848264](https://zenodo.org/records/18848264) | Zenodo | Voting experiment incl. voters.csv | 8 | 1.1 | 0.82 |
| [23070603](https://zenodo.org/records/23070603) | Zenodo | Street interviews CSV + datapackage.json | 4 | 0.4 | 0.50 |
| [21404001](https://zenodo.org/records/21404001) | Zenodo | EMA participant-level data + codebook | 3 | 0.1 | 0.30 |
| [34893234](https://figshare.com/articles/dataset/34893234) | Figshare | Participant HRV task data CSVs | 2 | 3.0 | 0.52 |
| [28498397](https://figshare.com/articles/dataset/28498397) | Figshare | Spanish student mobility survey | 1 | 0.6 | 0.70 |
| [26798023](https://figshare.com/articles/dataset/26798023) | Figshare | Spanish open-data survey | 1 | 1.0 | 0.46 |
| [32520411](https://figshare.com/articles/dataset/32520411) | Figshare | Literature data with .Rhistory/.RData junk | 19 | 68.1 | 1.32 |
| [jrsbn](https://osf.io/jrsbn/) | OSF | Breathwork survey data | 1 | 0.4 | 1.07 |
| [p5gta](https://osf.io/p5gta/) | OSF | Inflation expectation survey data | 2 | 0.8 | 1.75 |
| [pdhvk](https://osf.io/pdhvk/) | OSF | Anonymised survey data | 1 | 0.6 | 0.52 |
| [hq3k2](https://osf.io/hq3k2/) | OSF | Consumer survey data, cooking | 3 | 28.8 | 3.98 |
| [pkvrj](https://osf.io/pkvrj/) | OSF | Singlehood survey data | 15 | 366.8 | 7.61 |
| [a5dcn](https://osf.io/a5dcn/) | OSF | Heatwave survey dataset | 1 | 1.8 | 0.70 |

</details>

### Round 5 ([`eval/heldout4.json`](eval/heldout4.json)) — headline

Code `c6a59a2` (round-4 fixes), seed 20261106, verdicts committed in `57b4fe3`
([`eval/precision_round5_untouched.csv`](eval/precision_round5_untouched.csv)).
31 datasets: 24 Zenodo, 2 Figshare, 5 OSF; 126 files, 95 MB. **Crashes: 0 in 62 runs** (median 0.41 s,
max 2.83 s).

| Check | Correct / judged | Precision |
|---|---|---|
| archives | 1/1 | 100 % |
| checksums | 8/8 | 100 % |
| encoding | 7/8 | 87.5 % |
| formats | 8/8 | 100 % |
| license | 8/8 | 100 % |
| metadata | 7/8 | 87.5 % |
| naming | 8/8 | 100 % |
| readme | 7/8 | 87.5 % |
| sensitive (PII) | 8/8 | 100 % |
| size | 8/8 | 100 % |
| **Total** | **70/73** | **95.9 %** |

The bar is met on this sample, so no further round was run. The 3 errors were still fixed afterwards:

| # | Wrong output | Dataset | Root cause → fix |
|---|---|---|---|
| 10 | "encoding unknown; read as Windows-1252" for a UTF-8 file with 47 corrupt bytes (785 valid umlauts) | zenodo 8238711 | Files that are mostly valid UTF-8 are now read as UTF-8 and reported as "mostly UTF-8, but N invalid byte(s)" |
| 41 | Dryad "Abstract only found in README" with the quoted title of the paper as the value | zenodo 23779100 | A quoted title, a lead-in ending in ":", a `Label: value` line or a numbered item is not taken as the description |
| 52 | 10 "columns" not defined, which were one-cell sheet captions above the real header | zenodo 23493423 | A one-cell first row is skipped when a later row has 2+ cells; caption-only sheets are skipped (Excel and CSV) |

Column names with a unit suffix (`Extract loading (mg/g sample)`) now also match a README line that
names the column without the unit; this was seen in the same dataset after the caption fix.
Each fix has a regression test ("round 4" and "round 5" in `tests/test_regressions.py`; 91 tests).

<details><summary>Round 5 datasets</summary>

| Dataset | Source | What it exercises | Files | MB | Seconds |
|---|---|---|---|---|---|
| [6954073](https://zenodo.org/records/6954073) | Zenodo | Spanish Google Forms responses, not UTF-8 | 1 | 0.1 | 0.27 |
| [7023185](https://zenodo.org/records/7023185) | Zenodo | German master's survey raw CSV, not UTF-8 | 6 | 9.0 | 0.52 |
| [3554884](https://zenodo.org/records/3554884) | Zenodo | Swiss canteen survey CSVs, not UTF-8 | 5 | 1.0 | 0.87 |
| [19192846](https://zenodo.org/records/19192846) | Zenodo | Portuguese repository survey CSVs, not UTF-8 | 6 | 5.7 | 1.63 |
| [4278158](https://zenodo.org/records/4278158) | Zenodo | Portuguese open-science survey, not UTF-8 | 2 | 0.9 | 0.34 |
| [8238711](https://zenodo.org/records/8238711) | Zenodo | German teacher dataset, not UTF-8 | 1 | 0.0 | 0.31 |
| [17496176](https://zenodo.org/records/17496176) | Zenodo | Colombian well profile CSV in UTF-16 | 3 | 0.9 | 0.45 |
| [17230494](https://zenodo.org/records/17230494) | Zenodo | Spanish clinical database CSV, not UTF-8 | 1 | 0.2 | 0.30 |
| [4602382](https://zenodo.org/records/4602382) | Zenodo | Mexican COVID survey, 'READ Me file.txt' not UTF-8 | 6 | 2.8 | 1.20 |
| [23646197](https://zenodo.org/records/23646197) | Zenodo | README.rtf + xlsx | 2 | 0.1 | 0.39 |
| [23603753](https://zenodo.org/records/23603753) | Zenodo | README.rtf + R + xlsx | 6 | 0.2 | 0.44 |
| [18023312](https://zenodo.org/records/18023312) | Zenodo | README.rtf + RNA-seq CSVs + R | 12 | 3.0 | 0.60 |
| [21460944](https://zenodo.org/records/21460944) | Zenodo | README.rtf + CSVs | 4 | 0.7 | 0.41 |
| [23493423](https://zenodo.org/records/23493423) | Zenodo | README.txt and README.pdf + xlsx | 3 | 0.1 | 0.40 |
| [23446062](https://zenodo.org/records/23446062) | Zenodo | README.docx + CSVs | 5 | 0.5 | 0.72 |
| [23182496](https://zenodo.org/records/23182496) | Zenodo | README.docx + xlsx + Python | 3 | 0.1 | 0.38 |
| [5273319](https://zenodo.org/records/5273319) | Zenodo | README.odt + xlsx | 2 | 0.1 | 0.45 |
| [23577459](https://zenodo.org/records/23577459) | Zenodo | README.pdf + .rda + xlsx | 5 | 9.6 | 0.65 |
| [23883870](https://zenodo.org/records/23883870) | Zenodo | Children's robot perception responses | 3 | 0.0 | 0.28 |
| [23779100](https://zenodo.org/records/23779100) | Zenodo | Participant food-frequency data | 4 | 0.0 | 0.27 |
| [18147733](https://zenodo.org/records/18147733) | Zenodo | Advance-directive survey, anonymised | 2 | 0.0 | 0.34 |
| [21404316](https://zenodo.org/records/21404316) | Zenodo | EMA platform participant data + dictionary | 3 | 0.1 | 0.35 |
| [20511024](https://zenodo.org/records/20511024) | Zenodo | SUS raw survey data + README | 2 | 0.0 | 0.29 |
| [22252280](https://zenodo.org/records/22252280) | Zenodo | Drug purchasing survey CSV + SPSS | 4 | 1.0 | 0.83 |
| [34892736](https://figshare.com/articles/dataset/34892736) | Figshare | Grain size measurement CSVs | 3 | 1.2 | 0.59 |
| [34893045](https://figshare.com/articles/dataset/34893045) | Figshare | Lipidomics xlsx + result CSVs | 10 | 0.1 | 0.40 |
| [2bd38](https://osf.io/2bd38/) | OSF | Multidomain well-being survey | 9 | 40.3 | 2.83 |
| [edm75](https://osf.io/edm75/) | OSF | REDIRECT survey dataset | 1 | 0.8 | 0.30 |
| [3ubcy](https://osf.io/3ubcy/) | OSF | Full survey datasets | 1 | 10.8 | 0.35 |
| [d876v](https://osf.io/d876v/) | OSF | Amphibian pet trade socioeconomic survey | 4 | 5.5 | 0.63 |
| [9fgrv](https://osf.io/9fgrv/) | OSF | UK food bank use survey | 7 | 0.1 | 0.32 |

</details>

## 5. Never invents or overstates

- **Drafts:** across all 26 datasets, the only non-TODO values in `.zenodo.draft.json` are:
  - `upload_type: dataset`, since this is a dataset tool;
  - one title and description copied from `zenodo_7717258/README.md`.
  `access_right` used to default to `open`, which could be wrong for human-subjects data, so it is
  now a TODO.
- **Severity:** FAIL is used only when a target's published rule says *required* or *not accepted*.
  Recommendations are WARN; facts and limits of the tool are INFO.
- **Tone:** messages say "possible", "looks like" and "check these columns" for heuristics. They
  give a fix and a source link. No message calls a recommendation an error.
- **Scope of claims:** the tool states what it did not inspect: archive contents, `.xls`, `.sav`,
  `.dta` and similar files, unreadable files and symlinks.

## 6. CI

`.github/workflows/ci.yml` runs pytest and a CLI smoke test:

- Python 3.9, 3.12 and 3.13 on Ubuntu
- Python 3.9 on macOS

Run [41552597005](https://github.com/Yenula-W/repo-readiness-checker/actions/runs/41552597005) is
green on all four jobs. The first run failed only because `ubuntu-latest` is now Ubuntu 26.04, which has
no Python 3.9 build, so 3.9 is pinned to `ubuntu-24.04`. The repository is private (`gh repo view`
reports `PRIVATE`).

## Known limitations

- **Encoding detection:** non-UTF-8 files are reported, but the real encoding (GBK, Mac Roman, DOS CP850, Windows-1252…) is not identified, only UTF-16 and mostly-UTF-8. Column names in a GBK file are therefore read garbled, and the PII header patterns may miss them.
- **OSF was not in the round-3 set** because its API was unavailable during the run; rounds 4–5 include 11 OSF datasets.
- **Files named like documentation are not checked for PII:** a CSV whose name matches "dictionary", "codebook" or "metadata" (e.g. `sample_metadata.csv`) is treated as documentation and skipped by the PII check (seen in zenodo 18023312; that file held no identifiers).
- **PII detection:** reads only CSV/TSV/TXT and `.xlsx`, and only column names plus the first
  2,000 rows (4 MB). Header patterns are English-only; the Chinese headers in osf pu9rd (被试,
  年龄…) are not matched. Quasi-identifiers (age + sex + ethnicity) are not assessed. It does not
  replace a disclosure review.
- **README checks:** they find *mentions* of files and columns, not explanations. "Topic"
  detection is keyword-based.
- **Archives:** contents are listed (zip only) but not checked. 7z, tar and rar are not opened.
- **Metadata formats:** Figshare, Dataverse and OSF record exports are not parsed (Frictionless `datapackage.json` is). The tool says
  "No recognised fields" instead of guessing.
- **Runtime:** large `.xlsx` workbooks take about 3 s each to open.
- **Rules can go stale:** the rule files were verified on 2026-11-02 against the cited pages.
  Dryad's live upload limits and Figshare institutional instances may differ.
