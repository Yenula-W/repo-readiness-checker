"""Regression tests for wrong results found by hand-checking the held-out real-world run.
Each test names the public dataset where the problem was seen (see EVALUATION.md)."""
from pathlib import Path

from data_ready.checks import Context, run_all
from data_ready.rules_loader import load_target
from data_ready.scan import scan


def run(root: Path, target="zenodo", metadata=None):
    ctx = Context(root=root, files=scan(root), rules=load_target(target), metadata=metadata or {},
                  inferred={}, metadata_path=None)
    return run_all(ctx)


def by_check(findings, check):
    return [f for f in findings if f.check == check]


def test_rtf_readme_smart_quotes_do_not_hide_file_names(tmp_path):
    # zenodo 4095406: \'91Characteristics_field.csv\'92 was not seen as a mention.
    (tmp_path / "Readme_x.rtf").write_text(
        r"{\rtf1\ansi Datafile \'91Characteristics_field.csv\'92, file containing variables in units of cm.\par}")
    (tmp_path / "Characteristics_field.csv").write_text("a\n1\n")
    f = run(tmp_path)
    assert not any("not mentioned" in x.title for x in f)


def test_folder_named_in_prose_covers_its_files(tmp_path):
    (tmp_path / "README.md").write_text("# T\n\nFolder 'Photos_field' holds 15 images.\n")
    (tmp_path / "Photos_field").mkdir()
    (tmp_path / "Photos_field" / "a.png").write_bytes(b"\x89PNG")
    assert not any("not mentioned" in x.title for x in run(tmp_path))


def test_species_name_column_is_not_pii(tmp_path):
    # zenodo 4988910: column "Name" holds species codes like "G.pan".
    rows = "\n".join(f"{c},alien" for c in ["G.pan", "D.ten", "L.het", "Achillea millefolium"])
    (tmp_path / "plants.csv").write_text("Name,Origin\n" + rows + "\n")
    assert [x.status for x in by_check(run(tmp_path, "dryad"), "sensitive")] == ["pass"]


def test_name_column_with_people_is_pii(tmp_path):
    rows = "\n".join(["Ada Lovelace,1", "Alan Turing,2", "Grace Hopper,3", "Lovelace, Ada,4"])
    (tmp_path / "people.csv").write_text("Name,score\n" + rows + "\n")
    assert any(x.status == "fail" for x in by_check(run(tmp_path, "dryad"), "sensitive"))


def test_birthdate_in_mortality_data_is_flagged(tmp_path):
    # dataverse DVN/DHDNIC: a true positive that must stay.
    (tmp_path / "m.csv").write_text("uniqueid,gender,birthdate,deathdate\n4823,Female,15-Aug-21,15-Aug-21\n")
    assert any("date of birth" in x.detail for x in by_check(run(tmp_path), "sensitive"))


def test_dryad_without_license_is_info_not_pass(tmp_path):
    # Every held-out dataset without a license got "License compatible with CC0" (overstated).
    (tmp_path / "a.csv").write_text("a\n1\n")
    lic = by_check(run(tmp_path, "dryad"), "license")
    assert [x.status for x in lic] == ["info"] and "No license stated" in lic[0].title


def test_rar_is_discouraged_everywhere_and_rejected_by_dryad(tmp_path):
    # osf smj2n: .rar passed the Zenodo format check.
    (tmp_path / "data.rar").write_bytes(b"Rar!\x1a\x07\x00")
    assert any(x.status == "warn" for x in by_check(run(tmp_path, "zenodo"), "formats"))
    assert any(x.status == "fail" for x in by_check(run(tmp_path, "dryad"), "formats"))


def test_readme_under_another_name_is_recognised(tmp_path):
    # zenodo 4771158 (Yamada_and_Wada_(2021).txt) and zenodo 5812145 (FileDescription.docx).
    (tmp_path / "Yamada_and_Wada_(2021).txt").write_text("Explanation for the variables:\n Release day ...")
    (tmp_path / "Field_Survey.csv").write_text("Release day\n1\n")
    f = run(tmp_path)
    r = by_check(f, "readme")[0]
    assert r.status == "warn" and "looks like one" in r.title
    assert by_check(run(tmp_path, "dryad"), "readme")[0].status == "fail"


def test_file_description_docx_is_readme_like(tmp_path):
    (tmp_path / "FileDescription.docx").write_bytes(b"PK\x03\x04")
    (tmp_path / "a.xlsx").write_bytes(b"PK\x03\x04")
    titles = [x.title for x in by_check(run(tmp_path), "readme")]
    assert any("FileDescription.docx looks like one" in t for t in titles)
    assert any("could not be read as text" in t for t in titles)


def test_metadata_csv_counts_as_data_dictionary(tmp_path):
    # zenodo 7717258: Metadata_for_publication_2023.csv defines every column.
    (tmp_path / "README.md").write_text("# T\n\nData_for_publication_2023.csv and Metadata_for_publication_2023.csv.\n")
    (tmp_path / "Data_for_publication_2023.csv").write_text("lot.id,site.name\n1,a\n")
    (tmp_path / "Metadata_for_publication_2023.csv").write_text(
        "Establishment by seed source,.\n,\nVariable name,description\nlot.id,an ID\nsite.name,Site name\n")
    assert not any("column(s) not defined" in x.title for x in run(tmp_path))


def test_uninspectable_data_files_are_disclosed(tmp_path):
    # Many held-out datasets had only .xls/.sav/.dta; a PII "pass" alone overstated what was checked.
    for n in ("Table 1.xls", "SES Data.sav", "d.dta"):
        (tmp_path / n).write_bytes(b"\x00" * 10)
    s = by_check(run(tmp_path), "sensitive")
    assert s[0].status == "info" and len(s[0].files) == 3
    assert "0 tabular file(s)" in s[1].title


def test_utf8_character_split_at_buffer_edge_is_not_an_encoding_error(tmp_path):
    body = ("é" * 40000 + "\n")  # 80 KB of 2-byte characters on one line
    (tmp_path / "t.csv").write_text("col\n" + body * 3, encoding="utf-8")
    assert not by_check(run(tmp_path), "encoding")


def test_cp1252_csv_is_reported_as_not_utf8(tmp_path):
    # osf gzx8j: Hungarian free text saved as Windows-1252.
    (tmp_path / "a.csv").write_bytes("q\nSenki nem veszít\n".encode("cp1252"))
    enc = by_check(run(tmp_path), "encoding")
    assert enc and "not UTF-8" in enc[0].title
