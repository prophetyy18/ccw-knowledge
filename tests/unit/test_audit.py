"""Unit tests for the audit module."""

import unittest
from pathlib import Path
from datetime import date

from ccw_knowledge.audit import audit, AuditReport


class AuditTests(unittest.TestCase):
    def test_no_findings_for_clean(self):
        import tempfile
        from ccw_knowledge import vault as vault_mod
        from ccw_knowledge.scope import ScopeSet, ScopeRoots
        from ccw_knowledge.index import KnowledgeIndex
        from ccw_knowledge.knowledge import new_candidate, write_document_atomic

        with tempfile.TemporaryDirectory() as tmp:
            v = Path(tmp) / "vault"
            vault_mod.init_vault(v)
            layout = vault_mod.resolve_vault()
            scopes = ScopeSet.parse(["shared"])
            roots = ScopeRoots.from_vault(layout, scopes)
            doc = new_candidate(title="X", body="x" * 200)
            doc.frontmatter["status"] = "reviewed"
            doc.frontmatter["updated"] = date.today().isoformat()
            write_document_atomic(doc, layout.shared_knowledge / "x.md")
            idx = KnowledgeIndex.build(layout, scopes, roots)
            rep = audit(vault=layout, scopes=scopes, roots=roots, index=idx)
            self.assertEqual(len(rep.findings), 0)

    def test_detects_missing_source(self):
        import tempfile
        from ccw_knowledge import vault as vault_mod
        from ccw_knowledge.scope import ScopeSet, ScopeRoots
        from ccw_knowledge.index import KnowledgeIndex
        from ccw_knowledge.knowledge import new_candidate, write_document_atomic

        with tempfile.TemporaryDirectory() as tmp:
            v = Path(tmp) / "vault"
            vault_mod.init_vault(v)
            layout = vault_mod.resolve_vault()
            scopes = ScopeSet.parse(["shared"])
            roots = ScopeRoots.from_vault(layout, scopes)
            doc = new_candidate(title="X", body="x" * 200, sources=["/nonexistent/file.md"])
            doc.frontmatter["status"] = "reviewed"
            doc.frontmatter["updated"] = date.today().isoformat()
            write_document_atomic(doc, layout.shared_knowledge / "y.md")
            idx = KnowledgeIndex.build(layout, scopes, roots)
            rep = audit(vault=layout, scopes=scopes, roots=roots, index=idx)
            self.assertTrue(any(f.code == "missing-source" for f in rep.findings))


if __name__ == "__main__":
    unittest.main()
