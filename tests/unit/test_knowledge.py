"""Unit tests for the knowledge document model."""

import unittest
from pathlib import Path

from ccw_knowledge.knowledge import (
    VALID_STATUSES,
    ALLOWED_TRANSITIONS,
    KnowledgeDocument,
    new_candidate,
    prepare_promotion,
    read_document,
    write_document_atomic,
)


class KnowledgeDocumentTests(unittest.TestCase):
    def test_new_candidate_defaults(self):
        doc = new_candidate(title="The Pattern", body="A reusable idea.", sources=["a.md"])
        self.assertEqual(doc.status, "candidate")
        self.assertEqual(doc.id, doc.id)  # presence
        self.assertIn("sources", doc.frontmatter)
        self.assertEqual(doc.short_summary, "A reusable idea.")

    def test_lifecycle_transitions(self):
        self.assertIn("reviewed", ALLOWED_TRANSITIONS["candidate"])
        self.assertIn("stale", ALLOWED_TRANSITIONS["candidate"])
        self.assertNotIn("reviewed", ALLOWED_TRANSITIONS["superseded"])

    def test_promotion_requires_legal_target(self):
        doc = new_candidate(title="X")
        promoted = prepare_promotion(doc, target="reviewed", reviewer="human")
        self.assertEqual(promoted.status, "reviewed")
        self.assertEqual(promoted.frontmatter["reviewed_by"], "human")

        # terminal state
        promoted2 = prepare_promotion(promoted, target="superseded", reviewer="h")
        self.assertEqual(promoted2.status, "superseded")

        # superseded -> reviewed is illegal (terminal state)
        from ccw_knowledge.errors import KnowledgeError
        with self.assertRaises(KnowledgeError):
            prepare_promotion(promoted2, target="reviewed", reviewer="h")

        # superseded -> candidate is illegal
        with self.assertRaises(KnowledgeError):
            prepare_promotion(promoted2, target="candidate", reviewer="h")

    def test_write_atomic(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "doc.md"
            doc = new_candidate(title="AtomicTest")
            write_document_atomic(doc, target)
            self.assertTrue(target.exists())
            reread = read_document(target)
            self.assertEqual(reread.title, "AtomicTest")
            self.assertEqual(reread.status, "candidate")

    def test_invalid_status(self):
        # Reading a doc with bad status is permissive (audit flags it);
        # structural_review finds the issue.
        from ccw_knowledge.review import structural_review
        doc = new_candidate(title="Foo")
        doc.frontmatter["status"] = "bogus"
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "doc.md"
            doc.path = path
            write_document_atomic(doc, path)
            reread = read_document(path)
            rep = structural_review(reread)
            self.assertTrue(any(f.code == "invalid-status" for f in rep.findings))


if __name__ == "__main__":
    unittest.main()
