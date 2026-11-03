"""data-ready must never crash on messy input. Each case runs the full CLI on all targets."""
import json
import os
import zipfile
from pathlib import Path

import pytest

from data_ready.cli import main

ALL = ["-t", "zenodo", "-t", "dryad", "-t", "figshare", "-t", "nih-dms"]


def check(root: Path, tmp_path: Path, *extra) -> dict:
    out = tmp_path / "out"
    rc = main(["check", str(root), *ALL, "--out", str(out), *extra])
    assert rc in (0, 1)
    rep = json.loads((out / "readiness-report.json").read_text(encoding="utf-8"))
    assert (out / "readiness-report.md").read_text(encoding="utf-8").startswith("# Repository readiness report")
    return rep


def findings(rep, target="zenodo"):
    return next(t for t in rep["targets"] if t["id"] == target)["findings"]


def test_empty_folder(tmp_path):
    root = tmp_path / "empty"
    root.mkdir()
    rep = check(root, tmp_path)
    assert rep["summary"]["files"] == 0


def test_binary_and_nul_bytes_in_csv(tmp_path):
    root = tmp_path / "ds"
    root.mkdir()
    (root / "random.csv").write_bytes(os.urandom(5000))
    (root / "nul.csv").write_bytes(b"a,b\x00,c\n1,2\x00,3\n")
    (root / "empty.csv").write_bytes(b"")
    (root / "header_only.tsv").write_text("x\ty\n")
    check(root, tmp_path)


def test_non_utf8_csv_reported_politely(tmp_path):
    root = tmp_path / "ds"
    root.mkdir()
    (root / "latin.csv").write_bytes("nom,ville\nJosé,Montréal\n".encode("cp1252"))
    (root / "utf16.csv").write_bytes("a,b\n1,2\n".encode("utf-16"))
    rep = check(root, tmp_path)
    enc = [f for f in findings(rep) if f["check"] == "encoding"]
    assert any("not UTF-8" in f["title"] and "latin.csv" in f["files"] for f in enc)


@pytest.mark.parametrize("name,content", [
    (".zenodo.json", "{ not json"),
    ("metadata.yaml", "title: [unclosed"),
    ("metadata.yaml", "- just\n- a list\n"),
    ("datacite.json", '{"data": {"attributes": {"titles": "not-a-list", "creators": 5}}}'),
    ("CITATION.cff", "\xff\xfe garbage"),
])
def test_malformed_metadata_is_a_finding_not_a_crash(tmp_path, name, content):
    root = tmp_path / "ds"
    root.mkdir()
    (root / name).write_bytes(content.encode("latin-1"))
    rep = check(root, tmp_path)
    assert any(f["title"] in ("Metadata file could not be read",) or f["title"].startswith("No recognised fields")
               for f in findings(rep))


def test_explicit_metadata_path_missing_fields(tmp_path):
    root = tmp_path / "ds"
    root.mkdir()
    md = tmp_path / "dataverse.json"
    md.write_text(json.dumps({"status": "OK", "data": {"id": 1}}))
    rep = check(root, tmp_path, "-m", str(md))
    assert any(f["title"].startswith("No recognised fields") for f in findings(rep))


def test_corrupt_archives_images_and_excel(tmp_path):
    root = tmp_path / "ds"
    root.mkdir()
    (root / "broken.zip").write_bytes(b"PK\x03\x04 this is not really a zip")
    (root / "broken.xlsx").write_bytes(b"PK\x03\x04 nor is this a workbook")
    (root / "broken.png").write_bytes(b"\x89PNG\r\n\x1a\n" + os.urandom(100))
    (root / "fake.mat").write_bytes(b"MATLAB 5.0" + os.urandom(64))
    rep = check(root, tmp_path)
    titles = [f["title"] for f in findings(rep)]
    assert any("could not be opened" in t for t in titles)


def test_zip_contents_are_reported(tmp_path):
    root = tmp_path / "ds"
    root.mkdir()
    with zipfile.ZipFile(root / "bundle.zip", "w") as zf:
        zf.writestr("__MACOSX/._data.csv", "x")
        zf.writestr("inner/more.zip", "x")
        zf.writestr("data.csv", "a\n1\n")
    rep = check(root, tmp_path)
    titles = [f["title"] for f in findings(rep)]
    assert any("inside archives" in t for t in titles)
    assert any("nested inside" in t for t in titles)
    assert any("were not checked" in t for t in titles)


def test_huge_sparse_files(tmp_path):
    root = tmp_path / "ds"
    root.mkdir()
    with (root / "huge.bin").open("wb") as f:   # 60 GB sparse: over Zenodo's 50 GB limit
        f.truncate(60_000_000_000)
    with (root / "big.csv").open("wb") as f:    # 3 GB of NUL bytes posing as CSV
        f.write(b"a,b\n")
        f.truncate(3_000_000_000)
    rep = check(root, tmp_path)
    assert any(f["status"] == "fail" and f["check"] == "size" for f in findings(rep))
    big = next(x for x in rep["files"] if x["path"] == "huge.bin")
    assert big["sha256"] is None  # too big to hash by default; never silently claimed


def test_symlink_loop_and_broken_link(tmp_path):
    root = tmp_path / "ds"
    (root / "sub").mkdir(parents=True)
    (root / "sub" / "data.csv").write_text("a\n1\n")
    os.symlink(root, root / "sub" / "loop")          # directory loop
    os.symlink(root / "nowhere.csv", root / "dangling.csv")
    rep = check(root, tmp_path)
    links = [f for f in findings(rep) if "symbolic link" in f["title"]]
    assert links and set(links[0]["files"]) == {"dangling.csv", "sub/loop"}


def test_unicode_and_odd_paths(tmp_path):
    root = tmp_path / "ds"
    (root / "données 🧪").mkdir(parents=True)
    (root / "données 🧪" / "résultats.csv").write_text("é,ü\n1,2\n", encoding="utf-8")
    (root / "été.csv").write_text("a\n1\n")                  # NFD and NFC mixed
    (root / ("x" * 200 + ".csv")).write_text("a\n1\n")
    (root / "-leading-dash.txt").write_text("hi")
    rep = check(root, tmp_path)
    names = [f for f in findings(rep) if f["check"] == "naming"]
    assert any("non-ASCII" in f["title"] for f in names)
    assert any("longer than" in f["title"] for f in names)


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores file permissions")
def test_unreadable_file_and_folder(tmp_path):
    root = tmp_path / "ds"
    (root / "locked").mkdir(parents=True)
    (root / "locked" / "x.csv").write_text("a\n1\n")
    secret = root / "secret.csv"
    secret.write_text("a\n1\n")
    secret.chmod(0)
    (root / "locked").chmod(0)
    try:
        rep = check(root, tmp_path)
        titles = " ".join(f["detail"] for f in findings(rep) if f["check"] == "encoding")
        assert "permission denied" in titles and "folder could not be read" in titles
    finally:
        secret.chmod(0o644)
        (root / "locked").chmod(0o755)


def test_bad_cli_arguments(tmp_path, capsys):
    assert main(["check", str(tmp_path / "missing"), "-t", "zenodo"]) == 2
    f = tmp_path / "file.txt"
    f.write_text("x")
    assert main(["check", str(f), "-t", "zenodo"]) == 2


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores file permissions")
def test_unwritable_output_and_manifest(tmp_path, capsys):
    root = tmp_path / "ds"
    root.mkdir()
    (root / "a.csv").write_text("a\n1\n")
    root.chmod(0o555)
    try:
        assert main(["check", str(root), "-t", "zenodo", "--write-manifest"]) == 2
        assert main(["check", str(root), "-t", "zenodo", "--out", str(root / "out")]) == 2
    finally:
        root.chmod(0o755)
