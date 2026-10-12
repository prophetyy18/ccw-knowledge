"""Unit tests for the frontmatter parser/writer."""

import unittest

from ccw_knowledge.frontmatter import parse, render, ensure_required_keys, FrontmatterError


class FrontmatterParseTests(unittest.TestCase):
    def test_simple_kv(self):
        text = "---\nid: foo-1\nstatus: candidate\n---\nbody line\n"
        fm, body = parse(text)
        self.assertEqual(fm.get("id"), "foo-1")
        self.assertEqual(fm.get("status"), "candidate")
        self.assertEqual(body.strip(), "body line")

    def test_no_frontmatter(self):
        fm, body = parse("plain\ntext\n")
        self.assertEqual(fm, {})
        self.assertEqual(body, "plain\ntext\n")

    def test_list_inline(self):
        text = "---\ntags: [a, b, c]\n---\n"
        fm, _ = parse(text)
        self.assertEqual(fm.get("tags"), ["a", "b", "c"])

    def test_list_block(self):
        text = "---\nsources:\n  - /tmp/a.md\n  - /tmp/b.md\n---\n"
        fm, _ = parse(text)
        self.assertEqual(fm.get("sources"), ["/tmp/a.md", "/tmp/b.md"])

    def test_scalar_coercion(self):
        text = "---\nflag: true\ncount: 3\nratio: 1.5\nname: hello\nempty:\n---\n"
        fm, _ = parse(text)
        self.assertIs(fm["flag"], True)
        self.assertEqual(fm["count"], 3)
        self.assertEqual(fm["ratio"], 1.5)
        self.assertEqual(fm["name"], "hello")
        self.assertEqual(fm["empty"], "")


class FrontmatterWriteTests(unittest.TestCase):
    def test_roundtrip(self):
        original = {"id": "foo-2", "status": "reviewed", "tags": ["a", "b"]}
        text = render(original, "body content")
        fm, body = parse(text)
        self.assertEqual(fm.get("id"), "foo-2")
        self.assertEqual(fm.get("status"), "reviewed")
        self.assertEqual(fm.get("tags"), ["a", "b"])
        self.assertTrue(body.strip().endswith("body content"))

    def test_required_keys(self):
        fm = ensure_required_keys({"id": "x"}, ["id", "title"], defaults={"title": "T"})
        self.assertEqual(fm.get("title"), "T")
        with self.assertRaises(FrontmatterError):
            ensure_required_keys({}, ["missing"])

    def test_quotes_special_chars(self):
        text = render({"id": "x", "title": 'has: colon and "quote"'}, "")
        fm, _ = parse(text)
        self.assertEqual(fm.get("title"), 'has: colon and "quote"')


if __name__ == "__main__":
    unittest.main()
