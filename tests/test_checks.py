import json
import shutil
from pathlib import Path

import pytest

from data_ready import draft
from data_ready.checks import Context, check_naming, run_all
from data_ready.cli import main
from data_ready.metadata import detect_license_text, infer_from_readme, load_metadata
from data_ready.rules_loader import available_targets, load_target
from data_ready.scan import FileInfo, scan

FIX = Path(__file__).parent / "fixtures"
GOOD = FIX / "good_dataset"
MESSY = FIX / "messy_dataset"
TARGETS = ["zenodo", "dryad", "figshare", "nih-dms"]


def run(root, target, metadata=None, inferred=None):
    md, md_path = ({}, None)
    for name in ("metadata.yaml", ".zenodo.json", "CITATION.cff"):
        if (root / name).exists():
            md_path = root / name
            md, _ = load_metadata(md_path)
            break
    if metadata is not None:
        md = metadata
    ctx = Context(root=root, files=scan(root), rules=load_target(target), metadata=md,
                  inferred=inferred or {}, metadata_path=md_path)
    return run_all(ctx)


def statuses(findings, check=None):
    return [f.status for f in findings if check is None or f.check == check]


def titles(findings, status):
    return " | ".join(f.title for f in findings if f.status == status)


# --- rule files --------------------------------------------------------------

def test_all_targets_present():
    assert set(TARGETS) <= set(available_targets())


@pytest.mark.parametrize("target", TARGETS)
def test_every_rule_cites_a_source(target):
    t = load_target(target)
    assert t["sources"], "target must list its sources"
    for spec in t["required_metadata"] + t["recommended_metadata"]:
        assert spec["source"].startswith("https://"), spec
    for section in ("license", "readme", "sensitive_data", "file_naming", "checksums"):
        assert t[section].get("source", "").startswith("https://"), section


def test_extends_merges_common_formats():
    t = load_target("dryad")
    assert ".xlsx" in t["formats"]["discouraged"]  # inherited
    assert ".rar" in t["formats"]["rejected"]       # Dryad-specific


def test_custom_rules_file(tmp_path):
    rules = tmp_path / "myrepo.yaml"
    rules.write_text("id: myrepo\nextends: _common\nname: My Repo\nrequired_metadata:\n"
                     "  - {field: title, label: Title, source: 'https://example.org'}\n")
    t = load_target(str(rules))
    assert t["name"] == "My Repo" and t["readme"]["required"]


# --- good fixture ---------------------------------------------------------------

@pytest.mark.parametrize("target", ["zenodo", "figshare", "nih-dms"])
def test_good_dataset_passes(target):
    findings = run(GOOD, target)
    assert "fail" not in statuses(findings), titles(findings, "fail")
    assert "warn" not in statuses(findings), titles(findings, "warn")


def test_good_dataset_dryad_flags_non_cc0_license():
    findings = run(GOOD, "dryad")
    fails = [f for f in findings if f.status == "fail"]
    assert len(fails) == 1 and fails[0].check == "license"


def test_checksums_verified_and_tamper_detected(tmp_path):
    root = tmp_path / "ds"
    shutil.copytree(GOOD, root)
    assert "pass" in statuses(run(root, "zenodo"), "checksums")
    (root / "data" / "leaf_temp.csv").write_text("plant_id\nP99\n", encoding="utf-8")
    f = run(root, "zenodo")
    assert "fail" in statuses(f, "checksums")


# --- messy fixture --------------------------------------------------------------

def test_messy_dataset_problems_found(tmp_path):
    root = tmp_path / "messy"
    shutil.copytree(MESSY, root)
    (root / ".DS_Store").write_bytes(b"x")
    f = run(root, "dryad")
    by = {(x.check, x.status) for x in f}
    assert ("readme", "fail") in by
    assert ("formats", "fail") in by          # .rar rejected by Dryad
    assert ("sensitive", "fail") in by        # PII is a hard stop for Dryad
    assert ("checksums", "info") in by
    t = titles(f, "warn")
    assert ".mat" in t and "spaces" in t and "system/temporary" in t and "empty" in t
    pii = next(x for x in f if x.check == "sensitive" and "PII" in x.title)
    for word in ("personal name", "date of birth", "email", "medical record"):
        assert word in pii.detail


def test_pii_is_warn_for_zenodo():
    f = run(MESSY, "zenodo")
    assert "warn" in statuses(f, "sensitive")


def test_pii_value_detection_without_suspicious_header(tmp_path):
    (tmp_path / "README.md").write_text("# x\n", encoding="utf-8")
    (tmp_path / "t.csv").write_text("id,contact\n1,a@b.org\n2,c@d.org\n", encoding="utf-8")
    f = run(tmp_path, "zenodo")
    assert "email" in next(x for x in f if x.check == "sensitive" and "PII" in x.title).detail


def test_species_name_is_not_pii(tmp_path):
    (tmp_path / "t.csv").write_text("species_name,file_name,gene_name\nA,b,c\n", encoding="utf-8")
    assert statuses(run(tmp_path, "zenodo"), "sensitive") == ["pass"]


# --- README coverage --------------------------------------------------------------

def test_undocumented_columns_and_files(tmp_path):
    (tmp_path / "README.md").write_text("# T\n\nFiles: a.csv has column alpha in units of m. Missing = NA.\n", encoding="utf-8")
    (tmp_path / "a.csv").write_text("alpha,beta\n1,2\n", encoding="utf-8")
    (tmp_path / "b.csv").write_text("gamma\n3\n", encoding="utf-8")
    f = run(tmp_path, "zenodo")
    cols = next(x for x in f if "column(s) not defined" in x.title)
    assert "beta" in cols.detail and "gamma" in cols.detail and "alpha" not in cols.detail
    files = next(x for x in f if "not mentioned" in x.title)
    assert files.files == ["b.csv"]


def test_folder_mention_covers_files_inside(tmp_path):
    (tmp_path / "README.md").write_text("# T\n\nThe images/ folder holds raw microscope TIFFs.\n", encoding="utf-8")
    (tmp_path / "images").mkdir()
    for i in range(3):
        (tmp_path / "images" / f"img_{i}.tif").write_bytes(b"II*\x00")
    f = run(tmp_path, "zenodo")
    assert not any("not mentioned" in x.title for x in f)


def test_dryad_requires_markdown_readme(tmp_path):
    (tmp_path / "README.txt").write_text("summary of files and variables", encoding="utf-8")
    f = run(tmp_path, "dryad")
    assert any(x.status == "fail" and "README must be" in x.title for x in f)


# --- formats / Excel ---------------------------------------------------------------

def test_xlsx_flagged_and_columns_read(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    wb.active.append(["sample", "Email Address"])
    wb.active.append(["s1", "x@y.com"])
    wb.save(tmp_path / "results.xlsx")
    f = run(tmp_path, "figshare")
    assert any(x.check == "formats" and x.status == "warn" for x in f)
    assert any(x.check == "sensitive" and x.status == "warn" for x in f)


def test_xlsx_with_csv_twin_not_flagged(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    wb.save(tmp_path / "results.xlsx")
    (tmp_path / "results.csv").write_text("a\n1\n", encoding="utf-8")
    assert statuses(run(tmp_path, "zenodo"), "formats") == ["pass"]


# --- naming / sizes ------------------------------------------------------------------

def test_case_collision():
    files = [FileInfo(rel="Data.csv", path=Path("x"), size=1, ext=".csv"),
             FileInfo(rel="data.csv", path=Path("y"), size=1, ext=".csv")]
    ctx = Context(root=Path("."), files=files, rules=load_target("zenodo"), metadata={}, inferred={},
                  metadata_path=None)
    assert any(f.status == "fail" for f in check_naming(ctx))


def test_zenodo_file_count_limit(tmp_path):
    for i in range(101):
        (tmp_path / f"f{i:03}.txt").write_text("x", encoding="utf-8")
    f = run(tmp_path, "zenodo")
    assert any(x.check == "size" and x.status == "fail" and "101 files" in x.title for x in f)


# --- metadata ------------------------------------------------------------------------

def test_dryad_needs_three_keywords():
    md = {"title": "t", "keywords": ["a", "b"]}
    f = run(GOOD, "dryad", metadata=md)
    assert any("Keywords has 2, needs 3+" in x.title for x in f)


def test_inferred_title_is_warn_not_pass(tmp_path):
    f = run(tmp_path, "zenodo", metadata={}, inferred={"title": "From README"})
    t = next(x for x in f if "Title" in x.title)
    assert t.status == "warn" and "only found in README" in t.title


def test_load_zenodo_json_and_cff_and_datacite(tmp_path):
    z = tmp_path / ".zenodo.json"
    z.write_text(json.dumps({"title": "T", "upload_type": "dataset", "license": "cc-by-4.0",
                             "creators": [{"name": "Doe, J", "affiliation": "U"}], "keywords": ["k"]}))
    md, fmt = load_metadata(z)
    assert fmt == "zenodo" and md["creators"][0]["affiliation"] == "U" and md["resource_type"] == "dataset"
    c = tmp_path / "CITATION.cff"
    c.write_text("cff-version: 1.2.0\ntitle: T\nauthors:\n  - family-names: Doe\n    given-names: Jane\n"
                 "    orcid: https://orcid.org/0000-0002-1825-0097\nlicense: CC0-1.0\n")
    md, fmt = load_metadata(c)
    assert fmt == "cff" and md["creators"][0]["name"] == "Doe, Jane" and md["license"] == "CC0-1.0"
    d = tmp_path / "datacite.json"
    d.write_text(json.dumps({"data": {"attributes": {"titles": [{"title": "T"}], "creators": [{"name": "X"}],
                                                     "rightsList": [{"rightsIdentifier": "cc0-1.0"}]}}}))
    md, fmt = load_metadata(d)
    assert fmt == "datacite" and md["license"] == "cc0-1.0"


def test_license_detection():
    assert detect_license_text("Creative Commons Attribution 4.0 International") == "CC-BY-4.0"
    assert detect_license_text("CC0 1.0 Universal") == "CC0-1.0"
    assert detect_license_text("all rights reserved") is None


def test_readme_inference_only_uses_text():
    inf = infer_from_readme("# My Data\n\nThis dataset contains measurements of something important here.\n")
    assert inf == {"title": "My Data",
                   "description": "This dataset contains measurements of something important here."}


# --- drafts ----------------------------------------------------------------------------

def test_draft_marks_unknowns_as_todo():
    z = draft.zenodo_json({}, {})
    assert z["title"].startswith("TODO") and z["creators"][0]["name"].startswith("TODO")
    assert draft.count_todos(z) >= 5
    d = draft.datacite_json({"title": "Real", "keywords": ["a"]}, {})
    attrs = d["data"]["attributes"]
    assert attrs["titles"][0]["title"] == "Real" and attrs["doi"].startswith("TODO")


# --- CLI ---------------------------------------------------------------------------------

def test_cli_writes_reports_and_drafts(tmp_path, capsys):
    out = tmp_path / "out"
    rc = main(["check", str(MESSY), "-t", "zenodo", "-t", "nih-dms", "--out", str(out),
               "--draft-metadata", "zenodo", "--draft-metadata", "datacite", "--strict"])
    assert rc == 1
    rep = json.loads((out / "readiness-report.json").read_text(encoding="utf-8"))
    assert [t["id"] for t in rep["targets"]] == ["zenodo", "nih-dms"]
    assert rep["targets"][0]["status"] == "fail"
    md = (out / "readiness-report.md").read_text(encoding="utf-8")
    assert "Fix-it list" in md and "source" in md
    assert (out / ".zenodo.draft.json").exists() and (out / "datacite.draft.json").exists()


def test_cli_write_manifest(tmp_path):
    root = tmp_path / "ds"
    shutil.copytree(MESSY, root)
    main(["check", str(root), "-t", "zenodo", "--write-manifest"])
    text = (root / "manifest-sha256.txt").read_text(encoding="utf-8")
    assert "analysis.mat" in text
    f = run(root, "zenodo")
    assert "pass" in statuses(f, "checksums")


def test_cli_unknown_target(capsys):
    assert main(["check", str(GOOD), "-t", "nope"]) == 2
