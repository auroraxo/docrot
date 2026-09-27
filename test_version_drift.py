"""Tests for docrot version_drift module."""

import unittest

import version_drift as vd


class DeclaredVersionParsingTests(unittest.TestCase):
    def test_pyproject_toml(self):
        txt = """
[project]
name = "my-pkg"
version = "1.4.2"
description = "Sample"
"""
        v, src = vd.parse_declared_version({"pyproject.toml": txt})
        self.assertEqual(v, "1.4.2")
        self.assertEqual(src, "pyproject.toml")

    def test_package_json(self):
        txt = '{\n  "name": "foo",\n  "version": "2.0.1",\n  "main": "index.js"\n}'
        v, src = vd.parse_declared_version({"package.json": txt})
        self.assertEqual(v, "2.0.1")
        self.assertEqual(src, "package.json")

    def test_monorepo_placeholder_ignored(self):
        txt = '{\n  "name": "monorepo-root",\n  "version": "0.0.0"\n}'
        v, src = vd.parse_declared_version({"package.json": txt})
        self.assertIsNone(v)
        self.assertIsNone(src)

    def test_cargo_toml(self):
        txt = """
[package]
name = "crate"
version = "0.9.15"
edition = "2021"
"""
        v, src = vd.parse_declared_version({"Cargo.toml": txt})
        self.assertEqual(v, "0.9.15")
        self.assertEqual(src, "Cargo.toml")

    def test_version_file(self):
        v, src = vd.parse_declared_version({"VERSION": "v3.1.0\n"})
        self.assertEqual(v, "3.1.0")
        self.assertEqual(src, "VERSION")

    def test_manifest_priority_order(self):
        files = {
            "Cargo.toml": 'version = "0.5.0"',
            "pyproject.toml": 'version = "1.0.0"',
            "package.json": '{"version": "2.0.0"}',
        }
        v, src = vd.parse_declared_version(files)
        # pyproject.toml comes first in MANIFESTS
        self.assertEqual(v, "1.0.0")
        self.assertEqual(src, "pyproject.toml")

    def test_highest_tag_fallback(self):
        tags = [
            {"name": "v0.1.0"},
            {"name": "v0.2.1"},
            {"name": "v0.1.9"},
            {"name": "nightly-build"},
            {"name": "0.2.0"},
        ]
        self.assertEqual(vd._highest_tag(tags), "0.2.1")


class ExtractVersionLiteralsTests(unittest.TestCase):
    def test_extract_various_pin_contexts(self):
        doc = """
# Getting Started

[![Release](https://img.shields.io/badge/release-v0.1.6-blue.svg)](link)

Install from release wheel:
https://github.com/org/repo/releases/download/v0.1.6/pkg-0.1.6-py3-none-any.whl

Or via pip:
```bash
pip install my-tool==0.1.4
npm install my-app@1.2.0
```

Current version v0.1.6 running live.
Python 3.11.2 is required.
"""
        literals = vd.extract_version_literals(doc)
        # Check contexts
        contexts = {ctx for _, ctx, _ in literals}
        versions = [v for _, _, v in literals]
        self.assertIn("badge", contexts)
        self.assertIn("release-link", contexts)
        self.assertIn("pip-pin", contexts)
        self.assertIn("npm-pin", contexts)
        self.assertIn("0.1.4", versions)
        self.assertIn("1.2.0", versions)
        # Python 3.11.2 runtime mention should be excluded
        self.assertNotIn("3.11.2", versions)

    def test_changelog_headings_excluded(self):
        doc = """
# Changelog

## 0.1.2 - 2026-01-01
- Initial release

## v0.1.1
- Bugfix
"""
        literals = vd.extract_version_literals(doc)
        self.assertEqual(literals, [])

    def test_classification_current_stale_and_mentions(self):
        literals = [
            (5, "badge", "0.1.6"),
            (10, "pip-pin", "0.1.4"),
            (15, "text", "0.1.6"),
            (20, "text", "0.0.4"),
        ]
        current, stale, mentions = vd.classify_literals(literals, declared="0.1.6")
        # bare text mentions never count as current or stale
        self.assertEqual(current, 1)
        self.assertEqual(len(stale), 1)
        self.assertEqual(stale[0]["version"], "0.1.4")
        self.assertEqual(stale[0]["context"], "pip-pin")
        self.assertEqual(len(mentions), 2)
        self.assertEqual({m["version"] for m in mentions}, {"0.1.6", "0.0.4"})


if __name__ == "__main__":
    unittest.main()
