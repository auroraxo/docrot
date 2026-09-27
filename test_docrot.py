import json
import os
import tempfile
import unittest

import generate_report
import scan

TREE = {
    "docs/images/real.png",
    "assets/logo.svg",
    "img/site.png",
    "docs/My Folder/space file.png",
}


def c(ref, md_path="README.md"):
    return scan.classify(ref, md_path, TREE)


class ExtractImageRefsTests(unittest.TestCase):
    def test_markdown_and_html_forms(self):
        text = """
![one](assets/logo.svg "title")
![two](<docs/My Folder/space file.png>)
<img alt="three" src="docs/images/real.png">
<IMG SRC='https://cdn.example/four.png' alt='four'>
<img src=unquoted.svg>
<img
   class="x"
   src="multiline.png">
[not an image](ignored.png)
"""
        self.assertEqual(scan.extract_image_refs(text), [
            "assets/logo.svg",
            "docs/My Folder/space file.png",
            "docs/images/real.png",
            "https://cdn.example/four.png",
            "unquoted.svg",
            "multiline.png",
        ])

    def test_empty_sources_ignored(self):
        self.assertEqual(scan.extract_image_refs('<img src="">![x]()'), [])


class ClassifyTests(unittest.TestCase):
    def test_absolute_url_is_external(self):
        self.assertEqual(c("https://cdn.example/a.png"),
                         ("external", "https://cdn.example/a.png"))

    def test_protocol_relative_url_is_normalised(self):
        self.assertEqual(c("//cdn.example/a.png"),
                         ("external", "https://cdn.example/a.png"))

    def test_relative_hit_in_tree_is_in_repo(self):
        self.assertEqual(c("images/real.png", "docs/guide.md"),
                         ("in-repo", "docs/images/real.png"))

    def test_percent_encoded_path_resolves(self):
        self.assertEqual(c("My%20Folder/space%20file.png", "docs/guide.md"),
                         ("in-repo", "docs/My Folder/space file.png"))

    def test_relative_miss_in_docsite_is_unresolvable(self):
        self.assertEqual(c("images/gone.png", "docs/guide.md"),
                         ("unresolvable", "docsite-relative-missing"))

    def test_relative_miss_at_top_level_is_missing(self):
        self.assertEqual(c("images/gone.png", "guide.md"),
                         ("missing", "images/gone.png"))

    def test_root_relative_hit_is_in_repo(self):
        self.assertEqual(c("/img/site.png", "docs/guide.md"),
                         ("in-repo", "img/site.png"))

    def test_root_relative_miss_in_docsite_is_unresolvable(self):
        self.assertEqual(c("/img/tutorial/x.png", "docs/de/advanced.md"),
                         ("unresolvable", "docsite-root-relative"))

    def test_root_relative_miss_at_top_level_is_missing(self):
        self.assertEqual(c("/img/tutorial/x.png", "README.md"),
                         ("missing", "img/tutorial/x.png"))

    def test_template_placeholders_are_unresolvable(self):
        for ref in ("{{ sponsor.img }}", "{% static 'a.png' %}", "${BASE}/a.png"):
            self.assertEqual(c(ref)[0], "unresolvable", ref)

    def test_braced_jsx_source_is_unresolvable(self):
        self.assertEqual(c('{require("@site/static/x.png").default}'),
                         ("unresolvable", "template-placeholder"))
        self.assertEqual(c("{imageVariable}"),
                         ("unresolvable", "template-placeholder"))

    def test_non_http_schemes_are_unresolvable(self):
        self.assertEqual(c("cid:logo@company"),
                         ("unresolvable", "non-http-scheme"))
        self.assertEqual(c("data:image/png;base64,AAA")[1], "data-uri")

    def test_query_and_fragment_stripped(self):
        self.assertEqual(c("/img/site.png?v=2#x", "docs/g.md"),
                         ("in-repo", "img/site.png"))

    def test_escaping_repo_root_is_unresolvable(self):
        self.assertEqual(c("../../../etc/passwd", "README.md"),
                         ("unresolvable", "escapes-repo-root"))


from unittest.mock import patch, MagicMock
import urllib.error


class CheckTests(unittest.TestCase):
    @patch("urllib.request.urlopen")
    def test_head_refused_falls_back_to_get_success(self, mock_urlopen):
        # 403 on HEAD, 200 on GET
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.headers = {"Content-Type": "image/png"}
        mock_response.read.return_value = b"bytes"
        mock_response.__enter__.return_value = mock_response

        err_403 = urllib.error.HTTPError("https://example.com/img.png", 403, "Forbidden", {}, None)
        mock_urlopen.side_effect = [err_403, mock_response]

        status, ctype = scan.check("https://example.com/img.png")
        self.assertEqual(status, 200)
        self.assertEqual(ctype, "image/png")
        self.assertEqual(mock_urlopen.call_count, 2)
        self.assertEqual(mock_urlopen.call_args_list[0][0][0].get_method(), "HEAD")
        self.assertEqual(mock_urlopen.call_args_list[1][0][0].get_method(), "GET")

    @patch("urllib.request.urlopen")
    def test_unreachable_zero_status_renders_no_response_label(self, mock_urlopen):
        mock_urlopen.side_effect = Exception("network down")
        status, note = scan.check("https://example.com/dead.png")
        self.assertEqual(status, 0)
        self.assertEqual(note, "Exception")


SAMPLE = {
    "tool": "docrot", "version": 2, "generatedAt": "2026-09-11T06:00:00Z",
    "method": {"markdownFileCapPerRepo": 150, "timeoutSeconds": 15,
               "externalBrokenDefinition": "HTTP status >= 400 or no response"},
    "repos": [
        {"repo": "o/good", "stars": 10, "commit": "a" * 40, "defaultBranch": "main",
         "treeTruncated": False, "markdownFilesScanned": 3, "markdownFilesTotal": 3,
         "imageRefs": 2, "uniqueImages": 2, "inRepo": 2, "missingInRepo": 0,
         "unresolvable": 0, "external": 0, "externalThirdParty": 0,
         "externalBroken": 0, "externalThirdPartyBroken": 0, "thirdPartyHosts": [],
         "images": [{"kind": "in-repo", "target": "a.png", "broken": False,
                     "refCount": 1, "refs": [["README.md", "a.png"]]},
                    {"kind": "in-repo", "target": "b.png", "broken": False,
                     "refCount": 1, "refs": [["README.md", "b.png"]]}]},
        {"repo": "o/rotten", "stars": 0, "commit": "b" * 40, "defaultBranch": "main",
         "treeTruncated": False, "markdownFilesScanned": 150, "markdownFilesTotal": 400,
         "imageRefs": 3, "uniqueImages": 2, "inRepo": 0, "missingInRepo": 1,
         "unresolvable": 0, "external": 2, "externalThirdParty": 1,
         "externalBroken": 2, "externalThirdPartyBroken": 1,
         "thirdPartyHosts": ["cdn.example"],
         "images": [{"kind": "external", "target": "https://cdn.example/x<y>.png",
                     "host": "cdn.example", "status": 404, "note": "http-error",
                     "githubHosted": False, "broken": True, "refCount": 2,
                     "refs": [["docs/a.md", "https://cdn.example/x<y>.png"],
                              ["docs/b.md", "https://cdn.example/x<y>.png"]]},
                    {"kind": "external", "target": "https://cdn.example/dead.png",
                     "host": "cdn.example", "status": 0, "note": "unreachable",
                     "githubHosted": False, "broken": True, "refCount": 1,
                     "refs": [["docs/c.md", "https://cdn.example/dead.png"]]},
                    {"kind": "missing", "target": "docs/img/gone.png", "broken": True,
                     "refCount": 1, "refs": [["docs/a.md", "img/gone.png"]]}]},
        {"repo": "o/failed", "error": "HTTPError: 404"},
    ],
}


class StripCodeTests(unittest.TestCase):
    def test_fenced_block_images_ignored(self):
        text = """
![real](real.png)
```python
st.markdown("![Alt](https://example.com/image.png)")
```
~~~
![also fake](fake2.png)
~~~
"""
        self.assertEqual(scan.extract_image_refs(text), ["real.png"])

    def test_inline_code_images_ignored(self):
        text = "Syntax is `![alt](path)` — here is one: ![real](a.png)"
        self.assertEqual(scan.extract_image_refs(text), ["a.png"])

    def test_html_img_in_fence_ignored(self):
        text = '```\n<img src="/file=image.png">\n```\n<img src="real.png">'
        self.assertEqual(scan.extract_image_refs(text), ["real.png"])


class NormalizeUrlTests(unittest.TestCase):
    def test_spaces_encoded(self):
        self.assertEqual(
            scan.normalize_http_url("https://h/img/SOC2 T2 - green.png"),
            "https://h/img/SOC2%20T2%20-%20green.png")

    def test_delimiters_and_existing_escapes_preserved(self):
        u = "https://img.shields.io/badge/a-%23FF0000.svg?style=flat&logo=x#frag"
        self.assertEqual(scan.normalize_http_url(u), u)

    def test_classify_normalises_external(self):
        self.assertEqual(
            scan.classify("https://h/a b.png", "README.md", set()),
            ("external", "https://h/a%20b.png"))


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.html = generate_report.render(SAMPLE)

    def test_totals_rendered(self):
        self.assertIn("1 / 2", self.html)          # repos with a broken image
        self.assertIn("docrot.json", self.html)

    def test_broken_detail_present(self):
        self.assertIn("HTTP 404", self.html)
        self.assertIn("no response", self.html)
        self.assertNotIn("HTTP no response", self.html)
        self.assertIn("not in repository", self.html)
        self.assertIn("docs/img/gone.png", self.html)

    def test_zero_stars_rendered(self):
        self.assertIn("<td>0</td>", self.html)

    def test_user_content_is_escaped(self):
        self.assertNotIn("x<y>.png", self.html)
        self.assertIn("x&lt;y&gt;.png", self.html)

    def test_sampled_repo_shows_both_counts(self):
        self.assertIn("150", self.html)
        self.assertIn("400", self.html)

    def test_failed_repo_disclosed(self):
        self.assertIn("o/failed", self.html)

    def test_method_section_declares_exclusion(self):
        self.assertIn("Unresolvable", self.html)

    def test_main_writes_file(self):
        d = tempfile.mkdtemp()
        src, dst = os.path.join(d, "r.json"), os.path.join(d, "i.html")
        with open(src, "w") as f:
            json.dump(SAMPLE, f)
        import sys
        old = sys.argv
        sys.argv = ["generate_report.py", src, dst]
        try:
            generate_report.main()
        finally:
            sys.argv = old
        self.assertGreater(os.path.getsize(dst), 1000)


if __name__ == "__main__":
    unittest.main()


class AdevDocsiteTests(unittest.TestCase):
    """Angular's docs engine tree (adev/) rewrites image refs to the site root.

    Found in the wild: 18 'missing' hits in angular/angular whose 13 distinct
    targets all serve HTTP 200 from https://angular.dev/assets/ (2026-09-27).
    A missing verdict from adev/ markdown is a misclassification, not rot.
    """

    def test_relative_miss_in_adev_content_is_unresolvable(self):
        self.assertEqual(
            c("assets/images/angie/greeting.svg", "adev/src/content/tutorials/signals/intro/README.md"),
            ("unresolvable", "docsite-relative-missing"))

    def test_root_relative_miss_in_adev_content_is_unresolvable(self):
        self.assertEqual(
            c("/assets/images/angie/greeting.svg", "adev/src/content/tutorials/signals/intro/README.md"),
            ("unresolvable", "docsite-root-relative"))

    def test_relative_hit_in_adev_tree_still_in_repo(self):
        tree = TREE | {"adev/src/assets/images/angie/greeting.svg"}
        self.assertEqual(
            scan.classify("../../../../assets/images/angie/greeting.svg",
                          "adev/src/content/tutorials/signals/intro/README.md", tree),
            ("in-repo", "adev/src/assets/images/angie/greeting.svg"))

    def test_outside_adev_unchanged(self):
        self.assertEqual(c("img/none.png", "guide/README.md"),
                         ("missing", "guide/img/none.png"))
