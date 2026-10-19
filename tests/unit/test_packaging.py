"""What the wheel must carry: every data file under src is named by a package-data glob; the typing marker; the version."""
from __future__ import annotations

import re
import unittest
from fnmatch import fnmatch
from pathlib import Path

import fdo_consume

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "fdo_consume"


def package_data_globs() -> list[str]:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    block = re.search(r"\[tool\.setuptools\.package-data\]\s*fdo_consume\s*=\s*\[(.*?)\]", text, re.S).group(1)
    return re.findall(r'"([^"]+)"', block)


class PackagingTest(unittest.TestCase):

    def test_every_data_file_under_src_is_covered_by_a_package_data_glob(self):
        globs = package_data_globs()
        for path in SRC.rglob("*"):
            if path.is_dir() or path.suffix in (".py", ".pyc") or "__pycache__" in path.parts:
                continue
            relative = path.relative_to(SRC).as_posix()
            with self.subTest(file=relative):
                self.assertTrue(any(fnmatch(relative, glob) for glob in globs), f"{relative} is not in package-data {globs}")

    def test_the_typing_marker_ships(self):
        self.assertTrue((SRC / "py.typed").is_file())
        self.assertIn("py.typed", package_data_globs())

    def test_the_version_is_a_release_number(self):
        self.assertRegex(fdo_consume.__version__, r"^\d+\.\d+\.\d+$")

    def test_an_unwritable_report_path_is_a_request_error_not_a_traceback(self):
        import contextlib, io
        from fdo_consume import cli
        err = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            code = cli.main(["consume", "https://example.org/scenarios/cs3-dashboard/full", "--contract", "cs3-metadata-v1",
                             "--recorded-dir", str(ROOT / "fixtures" / "scenarios" / "cs3-dashboard"), "--report", "md",
                             "--out", str(ROOT / "no-such-folder" / "report.md")])
        self.assertEqual(code, 2)
        self.assertIn("cannot write", err.getvalue())
