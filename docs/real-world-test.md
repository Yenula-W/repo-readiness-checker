# Real-world test run (2026-11-02)

Five public, openly licensed Zenodo datasets were downloaded into a scratch folder
(not committed) and checked against all four targets: first without metadata
(as a researcher would run it before filling in a deposit form), then with each
record's real Zenodo metadata (`-m record.json`, the JSON from
`https://zenodo.org/api/records/<id>`).

| Zenodo record | Files | What it exercises |
|---|---|---|
| [17864815](https://zenodo.org/records/17864815) rTg4510 Behavioral Dataset | 3 | README.txt + `Data_Dictionary.csv`: every column documented |
| [23023244](https://zenodo.org/records/23023244) Implicit aiming, Wang et al. | 10 | README.md, 7 `.mat` + 1 `.xlsx`, undocumented columns |
| [20021867](https://zenodo.org/records/20021867) Media Narratives Survey (2025) | 6 | SPSS `.sav`, Stata `.dta`, `.xls` with CSV twin, no README, Latin-1 CSV |
| [15351301](https://zenodo.org/records/15351301) Floral shape and heat | 5 | README named `apland_2025 read me.rtf`, R code, spaces in names |
| [19071460](https://zenodo.org/records/19071460) DyNiSb transport properties | 13 | No README, spaces and `( ) ,` in file names |

## Results with the records' real metadata

| Record | Zenodo | Dryad | Figshare | NIH DMS |
|---|---|---|---|---|
| 17864815 | WARN (0 fail) | FAIL (4) | FAIL (1) | FAIL (1) |
| 23023244 | WARN (0 fail) | FAIL (4) | FAIL (2) | FAIL (1) |
| 20021867 | WARN (0 fail) | FAIL (4) | FAIL (1) | FAIL (2) |
| 15351301 | WARN (0 fail) | FAIL (6) | FAIL (2) | FAIL (1) |
| 19071460 | WARN (0 fail) | FAIL (5) | FAIL (2) | FAIL (1) |

Sanity check: every record was accepted by Zenodo and none gets a Zenodo FAIL, so
the Zenodo rules are not stricter than Zenodo itself. Cross-repository failures
are expected and correct:

- **Dryad**: CC-BY-4.0 is incompatible with Dryad's CC0-only rule; no author
  emails or OECD research domain in Zenodo metadata; README.txt/.rtf instead of `.md`.
- **Figshare**: Zenodo has no "categories" field; three records had no keywords.
- **NIH DMS**: none of these are NIH-funded, so "NIH award number" fails; the
  survey with no README also fails the documentation rule.

## Bugs found and fixed by this run

- README detection missed `apland_2025 read me.rtf` and `..._ReadME.txt`
  (now matched anywhere in the name, with word boundaries so `thread_metrics.txt`
  is not a README).
- Word/PDF READMEs were being read as text (garbage); now reported as
  "could not be read as text".
- Zenodo/Figshare marked "No README" as FAIL; neither repository requires one,
  so it is now WARN there (still FAIL for Dryad and NIH DMS).
- Very long Excel header cells (figure captions used as headers) flooded the
  report; column names are now truncated in the detail line.

## Not tested on real data

- Dryad downloads now need an API token (`401` on `/api/v2/.../download`), so no
  Dryad-hosted dataset was used. Dryad rules were tested with fixtures only.
- No real dataset contained PII (as expected for published data); PII detection is
  tested with fixtures.
