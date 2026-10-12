"""Unit tests for scope handling."""

import unittest
from pathlib import Path

from ccw_knowledge.errors import ScopeError
from ccw_knowledge.scope import ScopeRoots, ScopeSet, resolve_target_path


class ScopeSetTests(unittest.TestCase):
    def test_parse_string(self):
        s = ScopeSet.parse("shared, project:lp2")
        self.assertIn("shared", s.scopes)
        self.assertIn("project:lp2", s.scopes)

    def test_empty_default(self):
        s = ScopeSet.parse([])
        # default fallback to project:default (refuses truly empty)
        self.assertEqual(len(s.scopes), 1)

    def test_invalid_scope(self):
        with self.assertRaises(ValueError):
            ScopeSet(("random",))


class ResolveTests(unittest.TestCase):
    def setUp(self):
        self.scopes = ScopeSet.parse(["project:lp2", "shared"])
        # Fake roots.
        from pathlib import Path

        self.tmp_root = Path("/tmp/ccw-scope-test")
        layout = {
            "shared": {
                "sources": self.tmp_root / "shared" / "sources",
                "candidates": self.tmp_root / "shared" / "candidates",
                "knowledge": self.tmp_root / "shared" / "knowledge",
            },
            "project:lp2": {
                "sources": self.tmp_root / "projects" / "lp2" / "sources",
                "candidates": self.tmp_root / "projects" / "lp2" / "candidates",
                "knowledge": self.tmp_root / "projects" / "lp2" / "knowledge",
            },
        }
        for paths in layout.values():
            for p in paths.values():
                p.mkdir(parents=True, exist_ok=True)
        self.roots = ScopeRoots(buckets=layout)

    def test_normal_resolve(self):
        p = resolve_target_path(self.roots, "project:lp2", "candidates", "foo.md")
        self.assertTrue(str(p).endswith("candidates/foo.md"))

    def test_traversal_rejected(self):
        with self.assertRaises(ScopeError):
            resolve_target_path(self.roots, "project:lp2", "candidates", "../etc/passwd")

    def test_out_of_scope(self):
        with self.assertRaises(ScopeError):
            resolve_target_path(self.roots, "project:other", "candidates", "x.md")


if __name__ == "__main__":
    unittest.main()
