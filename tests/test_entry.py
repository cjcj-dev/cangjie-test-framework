import csv
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
        with (self.root / "logs/cost_time.csv").open(encoding="utf-8", newline="") as report:
            [(case, seconds)] = csv.reader(report)
        self.assertEqual(str(Path("cases") / "excluded.cj"), case)
        self.assertGreaterEqual(float(seconds), 0)

    def test_multi_cfg_timing_keeps_each_execution(self):
        # Both targets and their cases have the same display name; visit the
        # first target twice, repeat each case, and retry failures only.
        left, right = (self.root / side / "suite" for side in ("left", "right"))
        for suite, cmd in ((left, "false"), (right, "echo 中文")):
            suite.mkdir(parents=True)
            (suite / "test.cfg").write_text("[suffix]\ncj = //\n", encoding="utf-8")
            (suite / "testlist").write_text("[ALL-TEST-CASE]\n*.cj\n", encoding="utf-8")
            (suite / "同,名.cj").write_text("// EXEC: " + cmd + "\n", encoding="utf-8")
        cfg = self.root / "maple.cfg"
        cfg.write_text("[test-home]\ndir = {}:{}:{}\n[running]\ntemp_dir = {}\n"
                       "[logging]\nname = {}\nlevel = INFO\n".format(
                           left, right, left, self.root / "work", self.root / "logs"), encoding="utf-8")
        report = self.root / "logs" / "cost_time.csv"
        report.parent.mkdir()
        report.write_text("previous invocation\n", encoding="utf-8")
        proc = subprocess.run([sys.executable, "-B", str(ENTRY), "--cfg", str(cfg),
                               "--repeat", "2", "--retry", "1", "-j", "2", "--fail_exit",
                               "--progress=silent", "--json_output", str(self.root / "results.json"),
                               "--output", str(self.root / "results.txt")],
                              cwd=self.root, capture_output=True, text=True)
        self.assertEqual(1, proc.returncode, proc.stderr)
        groups = json.loads((self.root / "results.json").read_text(encoding="utf-8"))
        self.assertEqual(3, len(groups))
        for group, suite, status in zip(groups, (left, right, left), ("FAIL", "PASS", "FAIL")):
            self.assertCountEqual([(str(suite / "test.cfg"), "同,名.cj#r{}".format(i), status)
                                   for i in (1, 2)],
                                  [(row["cfg"], Path(row["name"]).name, row["result"])
                                   for row in group["tests"]])

        # The public reader unpacks exactly two fields. Equal display names
        # are separate observations: 2 failing visits x 2 attempts + 1 pass.
        with report.open(encoding="utf-8", newline="") as f:
            timings = [(case, float(seconds)) for case, seconds in csv.reader(f)]
        self.assertCountEqual([str(Path("suite") / "同,名.cj#r{}".format(i))
                               for i in (1, 2)] * 5, [case for case, _ in timings])
        self.assertTrue(all(seconds >= 0 for _, seconds in timings))
        for suite in (left, right):
            self.assertFalse((suite / "cost_time.csv").exists())
