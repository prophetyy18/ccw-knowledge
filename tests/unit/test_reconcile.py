"""Unit tests for the reconciliation module."""

import unittest
from pathlib import Path

from ccw_knowledge.knowledge import new_candidate


class ReconcileTests(unittest.TestCase):
    def test_no_overlap_returns_new(self):
        from ccw_knowledge.index import KnowledgeIndex
        from ccw_knowledge.reconcile import reconcile_candidate

        idx = KnowledgeIndex()
        cand = new_candidate(title="Unique thing", body="x")
        plan = reconcile_candidate(cand, index=idx)
        self.assertEqual(plan.action, "new")

    def test_overlap_returns_merge_or_defer(self):
        from ccw_knowledge.index import KnowledgeIndex
        from ccw_knowledge.reconcile import reconcile_candidate
        from ccw_knowledge.knowledge import read_document, write_document_atomic

        import tempfile
        from ccw_knowledge.frontmatter import render

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            existing_path = base / "existing.md"
            write_document_atomic(
                new_candidate(title="Same Title", tags=["x", "y"]),
                existing_path,
            )
            idx = KnowledgeIndex()
            idx._register(read_document(existing_path))

            cand = new_candidate(title="Same Title", tags=["x", "y", "z"])
            plan = reconcile_candidate(cand, index=idx)
            self.assertIn(plan.action, {"merge", "defer"})


if __name__ == "__main__":
    unittest.main()
