"""Unit tests for search and indexing."""

import unittest
from pathlib import Path

from ccw_knowledge.index import KnowledgeIndex


class IndexTests(unittest.TestCase):
    def _doc(self, path: Path, title: str, tags, body):
        from ccw_knowledge.frontmatter import render

        path.parent.mkdir(parents=True, exist_ok=True)
        text = render(
            {
                "id": path.stem,
                "title": title,
                "status": "reviewed",
                "tags": tags,
                "created": "2026-01-01",
                "updated": "2026-01-01",
            },
            body,
        )
        path.write_text(text, encoding="utf-8")

    def test_index_basic(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            candidates = vault / "shared" / "candidates"
            knowledge = vault / "shared" / "knowledge"
            for d in (candidates, knowledge):
                d.mkdir(parents=True, exist_ok=True)

            self._doc(
                knowledge / "alpha.md",
                "Alpha knowledge",
                ["alpha", "first"],
                "This is the body of alpha.",
            )
            self._doc(
                knowledge / "beta.md",
                "Beta knowledge",
                ["beta"],
                "Body of beta that mentions alpha.",
            )

            idx = KnowledgeIndex()
            # Manually register the docs since we skip KnowledgeIndex.build
            # (which requires a VaultLayout). We use the internal method.
            from ccw_knowledge.knowledge import read_document

            for p in (knowledge / "alpha.md", knowledge / "beta.md"):
                idx._register(read_document(p))

            ranked = idx.search_tokens("alpha", limit=10)
            self.assertGreaterEqual(len(ranked), 1)


class SearchDepthTests(unittest.TestCase):
    def test_depth_quick_excludes_excerpt(self):
        from ccw_knowledge.search import search, EvidencePack
        import tempfile
        from ccw_knowledge import vault as vault_mod

        with tempfile.TemporaryDirectory() as tmp:
            v = Path(tmp) / "vault"
            vault_mod.init_vault(v)
            layout = vault_mod.resolve_vault()
            from ccw_knowledge.scope import ScopeSet, ScopeRoots
            from ccw_knowledge.knowledge import new_candidate, write_document_atomic

            scopes = ScopeSet.parse(["shared"])
            roots = ScopeRoots.from_vault(layout, scopes)

            doc = new_candidate(title="Searchable item", body="body")
            write_document_atomic(doc, layout.shared_candidates / "searchable.md")

            idx = KnowledgeIndex.build(layout, scopes, roots)
            pack = search("Searchable", index=idx, vault=layout, scopes=scopes, roots=roots, depth="quick")
            # quick depth: no excerpt included
            self.assertEqual(pack.matches[0].excerpt, "")


if __name__ == "__main__":
    unittest.main()
