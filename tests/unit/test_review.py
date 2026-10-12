"""Unit tests for the review module (structural + lifecycle)."""

import unittest
from pathlib import Path

from ccw_knowledge.knowledge import (
    new_candidate,
    read_document,
    write_document_atomic,
)
from ccw_knowledge.review import structural_review


class ReviewTests(unittest.TestCase):
    def test_structural_review_clean(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "doc.md"
            write_document_atomic(
                new_candidate(title="Clean", body="This is a document with body.")
                ,
                path,
            )
            doc = read_document(path)
            rep = structural_review(doc)
            self.assertEqual(rep.critical_count, 0)

    def test_structural_review_invalid_status(self):
        import tempfile
        from ccw_knowledge.errors import KnowledgeError

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "doc.md"
            doc = new_candidate(title="Bad status")
            doc.frontmatter["status"] = "garbage"
            write_document_atomic(doc, path)
            reread = read_document(path)
            # structural_review should fire finding for invalid status
            rep = structural_review(reread)
            self.assertGreaterEqual(rep.critical_count, 1)
            self.assertTrue(any(f.code == "invalid-status" for f in rep.findings))


if __name__ == "__main__":
    unittest.main()
