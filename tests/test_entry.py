import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ENTRY = Path(__file__).resolve().parents[1] / "main.py"


class EntryTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.cases = self.root / "cases"
        self.cases.mkdir()
        (self.cases / "test.cfg").write_text("[suffix]\ncj = //\n", encoding="utf-8")
        (self.cases / "testlist").write_text(
            "[ALL-TEST-CASE]\n*.cj\n[EXCLUDE-TEST-CASE]\nexcluded.cj\n", encoding="utf-8")
        for name, command in (("中文", "echo 中文"), ("fail", "false"), ("excluded", "echo excluded")):
            (self.cases / (name + ".cj")).write_text("// EXEC: " + command + "\n", encoding="utf-8")

    def invoke(self, *names, use_list=True):
        args = [sys.executable, "-B", str(ENTRY), "--test_cfg", str(self.cases / "test.cfg"),
                "-j", "1", "--fail_exit", "--progress=silent", "--json_output", "results.json",
                "--log_dir", "logs", "--temp_dir", "work", "--output", "results.txt"]
        if use_list:
            args += ["--test_list", str(self.cases / "testlist")]
        result = subprocess.run(args + [str(self.cases / name) for name in names], cwd=self.root,
                                capture_output=True, text=True)
        raw = json.loads((self.root / "results.json").read_text(encoding="utf-8"))
        rows = [(Path(row["name"]).name, row["result"]) for group in raw for row in group["tests"]]
        return result, rows

    def test_explicit_list_and_failure_across_paths(self):
        result, rows = self.invoke("fail.cj", "excluded.cj", "中文.cj")
        self.assertEqual([("fail.cj", "FAIL"), ("中文.cj", "PASS")], rows)
        self.assertEqual(1, result.returncode, result.stderr)

    def test_standalone_and_read_only_sources(self):
        before = sorted(self.cases.iterdir())
        result, rows = self.invoke("excluded.cj", use_list=False)
        self.assertEqual([("excluded.cj", "PASS")], rows)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(before, sorted(self.cases.iterdir()))
        self.assertTrue((self.root / "logs/cost_time.csv").is_file())
