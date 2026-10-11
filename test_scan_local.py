import json
import os
import sys
import tempfile
import unittest

import scan
import scan_local


def _write(root, rel, text):
    full = os.path.join(root, rel)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w") as f:
        f.write(text)


class ScanLocalTests(unittest.TestCase):
    def test_walk_tree_skips_noise(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, "README.md", "")
            _write(d, "docs/index.md", "")
            _write(d, "node_modules/evil.md", "should be skipped")
            _write(d, ".git/HEAD", "ref: refs/heads/main")
            _write(d, "vendor/x.md", "skipped")
            _write(d, "src/main.py", "ignored, not md")
            tree = scan_local.walk_tree(d)
            self.assertIn("README.md", tree)
            self.assertIn("docs/index.md", tree)
            self.assertIn("src/main.py", tree)
            self.assertNotIn("node_modules/evil.md", tree)
            self.assertNotIn(".git/HEAD", tree)
            self.assertNotIn("vendor/x.md", tree)

    def test_scan_local_clean_repo(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, "README.md", "![logo](assets/logo.png)\n")
            _write(d, "assets/logo.png", "fake")
            summary = scan_local.scan_local(d)
            self.assertEqual(summary["uniqueImages"], 1)
            self.assertEqual(summary["inRepo"], 1)
            self.assertEqual(summary["missingInRepo"], 0)
            self.assertEqual(summary["externalThirdPartyBroken"], 0)
            self.assertEqual(summary["brokenTotal"], 0)
            self.assertEqual(summary["actionExit"], 0)

    def test_scan_local_counts_missing_and_unresolvable_separately(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, "README.md",
                   "![ghost](gone.png)\n"
                   "![tpl]({{ template }})\n"
                   "![site](/images/from-docs.png)\n")
            _write(d, "docs/index.md", "![docsite](/img/x.png)\n")
            summary = scan_local.scan_local(d)
            kinds = {i["kind"] for i in summary["images"]}
            self.assertIn("missing", kinds)
            self.assertIn("unresolvable", kinds)
            # Two top-level missing refs: gone.png (relative miss) and
            # /images/from-docs.png (root-relative miss at top level — no
            # docs/ prefix on README.md). Both match scan.py behaviour.
            self.assertEqual(summary["missingInRepo"], 2)
            # The {{ template }} placeholder is unresolvable; the docs-site
            # root-relative at top level is missing (not unresolvable)
            # because no docs/ prefix is set on README.md. Both behaviours
            # match scan.py.
            self.assertGreaterEqual(summary["unresolvable"], 1)

    def test_scan_local_marks_broken_external(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as d:
            _write(d, "README.md",
                   "![dead](https://example.invalid/nope.png)\n")
            with patch.object(scan, "check",
                              return_value=(0, "unreachable")):
                summary = scan_local.scan_local(d)
            self.assertEqual(summary["externalThirdPartyBroken"], 1)
            self.assertEqual(summary["brokenTotal"], 1)
            self.assertEqual(summary["actionExit"], 0)  # default warn

    def test_scan_local_fail_on_broken_exits_nonzero(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as d:
            _write(d, "README.md",
                   "![dead](https://example.invalid/nope.png)\n")
            with patch.object(scan, "check",
                              return_value=(0, "unreachable")):
                summary = scan_local.scan_local(d, fail_on_broken=True)
            self.assertEqual(summary["actionExit"], 1)
            self.assertEqual(summary["brokenTotal"], 1)

    def test_scan_local_writes_json_file(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, "README.md", "![ok](assets/a.png)\n")
            _write(d, "assets/a.png", "x")
            out = os.path.join(d, "out.json")
            rc = 0
            old = sys.argv
            sys.argv = ["scan_local.py", d, out]
            try:
                scan_local.main()
            except SystemExit as e:
                rc = e.code or 0
            finally:
                sys.argv = old
            self.assertEqual(rc, 0)
            with open(out) as f:
                data = json.load(f)
            self.assertEqual(data["repo"], os.path.basename(d))
            self.assertIn("generatedAt", data)


if __name__ == "__main__":
    unittest.main()
