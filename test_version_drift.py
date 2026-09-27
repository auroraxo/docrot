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
        self.assertEqual(v, "1.0.0")
        self.assertEqual(src, "pyproject.toml")

    def test_monorepo_placeholder_ignored(self):
        txt = '{\n  "name": "monorepo-root",\n  "version": "0.0.0"\n}'
        v, src = vd.parse_declared_version({"package.json": txt})
        self.assertIsNone(v)
        self.assertIsNone(src)

    def test_highest_tag_fallback(self):
        tags = [
            {"name": "v0.1.0"},
            {"name": "v0.2.1"},
            {"name": "v0.1.9"},
            {"name": "nightly-build"},
            {"name": "0.2.0"},
        ]
        self.assertEqual(vd._highest_tag(tags), "0.2.1")


class SelfNameTests(unittest.TestCase):
    def test_exact_and_org_prefixed(self):
        self.assertTrue(vd.is_self_name("aurora-node-auditor", "aurora-node-auditor"))
        self.assertTrue(vd.is_self_name("apache-airflow", "airflow"))
        self.assertTrue(vd.is_self_name("Apache_Airflow", "airflow"))

    def test_dependencies_and_placeholders_are_not_self(self):
        self.assertFalse(vd.is_self_name("botocore", "localstack"))
        self.assertFalse(vd.is_self_name("package", "core"))
        self.assertFalse(vd.is_self_name("dbt", "dbt-core"))
        self.assertFalse(vd.is_self_name("", "core"))


class ExtractVersionLiteralsTests(unittest.TestCase):
    def test_extract_various_pin_contexts(self):
        doc = """
# Getting Started

[![Release](https://img.shields.io/badge/release-v0.1.6-blue.svg)](link)

Install from release wheel:
https://github.com/acme/my-tool/releases/download/v0.1.6/my-tool-0.1.6-py3-none-any.whl

Or via pip:
```bash
pip install my-tool==0.1.4
pip install botocore==1.31.81
npm install my-app@1.2.0
```

Current version v0.1.6 running live.
Python 3.11.2 is required.
"""
        literals = vd.extract_version_literals(doc, repo_full="acme/my-tool")
        contexts = {ctx for _, ctx, _ in literals}
        versions = [v for _, _, v in literals]
        self.assertIn("badge", contexts)
        self.assertIn("release-link", contexts)   # github.com/acme/my-tool/... is this repo
        self.assertIn("pip-pin", contexts)        # my-tool==0.1.4 is this repo
        self.assertIn("dep-pin", contexts)        # botocore and my-app are not
        self.assertIn("0.1.4", versions)
        self.assertIn("1.2.0", versions)
        self.assertNotIn("3.11.2", versions)      # runtime mention excluded

    def test_external_release_link_is_not_self(self):
        doc = "See [v0.16.0](https://github.com/google/jsonnet/releases/tag/v0.16.0)."
        literals = vd.extract_version_literals(doc, repo_full="prometheus/prometheus")
        contexts = {ctx for _, ctx, _ in literals}
        self.assertIn("ext-release-link", contexts)
        self.assertNotIn("release-link", contexts)

    def test_relative_release_link_is_self(self):
        doc = "Download from [releases](releases/tag/v3.14.0)."
        literals = vd.extract_version_literals(doc, repo_full="prometheus/prometheus")
        contexts = {ctx for _, ctx, _ in literals}
        self.assertIn("release-link", contexts)

    def test_example_release_link_is_mention(self):
        doc = "For example: https://github.com/envoyproxy/envoy/releases/tag/v1.39.0."
        literals = vd.extract_version_literals(doc, repo_full="envoyproxy/envoy")
        contexts = {ctx for _, ctx, _ in literals}
        self.assertIn("example-link", contexts)
        self.assertNotIn("release-link", contexts)

    def test_prerelease_and_4part_pins_not_truncated(self):
        doc = """
A resolver only picks one under an explicit `dbt-core==2.0.0rc1` pin.
And tool==1.2.3.4 is four components.
"""
        literals = vd.extract_version_literals(doc, repo_full="dbt-labs/dbt-core")
        # neither 2.0.0rc1 nor 1.2.3.4 should enter as a 2.0.0 / 1.2.3 pip-pin
        pip_pins = [v for _, ctx, v in literals if ctx == "pip-pin"]
        self.assertEqual(pip_pins, [])

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

    def test_changelog_path_detection(self):
        self.assertTrue(vd.is_changelog_path("CHANGELOG.md"))
        self.assertTrue(vd.is_changelog_path("docs/changelog.md"))
        self.assertTrue(vd.is_changelog_path("CHANGES.rst"))
        self.assertFalse(vd.is_changelog_path("README.md"))
        self.assertFalse(vd.is_changelog_path("docs/change-notes.md"))


class ClassifyTests(unittest.TestCase):
    def test_classification_current_stale_and_mentions(self):
        literals = [
            (5, "badge", "0.1.6"),
            (10, "pip-pin", "0.1.4"),
            (15, "text", "0.1.6"),
            (20, "text", "0.0.4"),
            (25, "dep-pin", "1.31.81"),
            (30, "ext-release-link", "0.16.0"),
        ]
        current, stale, mentions = vd.classify_literals(literals, declared="0.1.6")
        self.assertEqual(current, 1)
        self.assertEqual(len(stale), 1)
        self.assertEqual(stale[0]["version"], "0.1.4")
        self.assertEqual(stale[0]["context"], "pip-pin")
        self.assertEqual(len(mentions), 4)

    def test_latest_release_rescues_unreleased_manifest_pin(self):
        # main declares 3.4.0 (unreleased); README pins the newest real release
        literals = [(10, "pip-pin", "3.3.2")]
        current, stale, mentions = vd.classify_literals(
            literals, declared="3.4.0", also_current=["3.3.2"])
        self.assertEqual(current, 1)
        self.assertEqual(stale, [])

    def test_pin_matching_neither_is_stale(self):
        literals = [(10, "pip-pin", "3.3.0")]
        current, stale, mentions = vd.classify_literals(
            literals, declared="3.4.0", also_current=["3.3.2"])
        self.assertEqual(current, 0)
        self.assertEqual(len(stale), 1)


if __name__ == "__main__":
    unittest.main()
