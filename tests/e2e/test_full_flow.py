"""End-to-end: capture -> review -> search flow."""

import os
import unittest
from pathlib import Path

from tests.e2e._harness import CLIRunner, fresh_environment


class CaptureReviewSearchTests(unittest.TestCase):
    def test_full_lifecycle(self):
        with fresh_environment() as (tmp, home, vault):
            project = tmp / "lp2"
            project.mkdir()
            os.chdir(project)
            r = CLIRunner(home)
            r.run("init", "--vault", str(vault))
            r.run("attach", "--project-id", "lp2")

            # Capture a candidate.
            rc = r.run(
                "capture",
                "--project", "lp2",
                "--text", "Y is because X.",
                "--title", "Why Y exists",
                "--tags", "origin,design",
            )
            self.assertEqual(rc, 0, msg=r.last_stderr)
            self.assertIn("candidate captured", r.last_stdout)
            cand_id = self._candidate_id(r.last_stdout)

            # Quick search hits it.
            rc = r.run(
                "search", "why y exists", "--depth", "quick", "--project", "lp2", "--json"
            )
            self.assertEqual(rc, 0)
            pack = r.json()
            self.assertGreaterEqual(len(pack["matches"]), 1)

            # Status is still 'candidate' (no auto-publish).
            from ccw_knowledge.scope import ScopeSet, ScopeRoots
            from ccw_knowledge import vault as vault_mod
            from ccw_knowledge.knowledge import read_document

            vault_layout = vault_mod.resolve_vault()
            scopes = ScopeSet.parse(["project:lp2", "shared"])
            cand_path = list(
                (vault_layout.project_space("lp2").candidates).glob("*.md")
            )
            self.assertGreaterEqual(len(cand_path), 1)
            doc = read_document(cand_path[0])
            self.assertEqual(doc.status, "candidate")

            # Audit-only review.
            rc = r.run(
                "review",
                "--project", "lp2",
                "--candidate", cand_id,
                "--action", "defer",
                "--audit-only",
            )
            self.assertEqual(rc, 0, msg=r.last_stderr)

            # Now approve for real.
            rc = r.run(
                "review",
                "--project", "lp2",
                "--candidate", cand_id,
                "--action", "approve",
                "--reviewer", "e2e",
                "--notes", "Looks good.",
            )
            self.assertEqual(rc, 0, msg=r.last_stderr)

            # Knowledge must now be in the knowledge/ bucket.
            knowledge_paths = list(
                (vault_layout.project_space("lp2").knowledge).glob("**/*.md")
            )
            knowledge_paths = [
                p for p in knowledge_paths if not p.name.startswith("deprecated")
            ]
            self.assertGreaterEqual(len(knowledge_paths), 1)
            doc_after = read_document(knowledge_paths[0])
            self.assertEqual(doc_after.status, "reviewed")

    def _candidate_id(self, stdout: str) -> str:
        for line in stdout.splitlines():
            if line.strip().startswith("id:"):
                return line.split(":", 1)[1].strip()
        raise AssertionError(f"could not find candidate id in output: {stdout!r}")


if __name__ == "__main__":
    unittest.main()
