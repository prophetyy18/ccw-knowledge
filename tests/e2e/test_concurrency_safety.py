"""End-to-end: atomic writes, no half-written files."""

import os
import unittest
from pathlib import Path

from ccw_knowledge import vault as vault_mod, scope as scope_mod
from ccw_knowledge.knowledge import new_candidate, read_document, write_document_atomic


class ConcurrencySafetyTests(unittest.TestCase):
    def test_atomic_write_leaves_no_partial_files(self):
        from tests.e2e._harness import fresh_environment

        with fresh_environment() as (tmp, home, vault):
            r = home / "ccw"
            vault_mod.init_vault(vault)
            layout = vault_mod.resolve_vault()
            project_dir = tmp / "lp"
            project_dir.mkdir()
            os.chdir(project_dir)

            from ccw_knowledge import cli as cli_mod

            cli_mod.main(["attach", "--project-id", "lp"])

            # Force a Candidate write.
            scopes = scope_mod.ScopeSet.parse(["project:lp", "shared"])
            roots = scope_mod.ScopeRoots.from_vault(layout, scopes)
            from ccw_knowledge.capture import capture_text

            doc = capture_text(
                vault=layout,
                scopes=scopes,
                roots=roots,
                project_id="lp",
                title="Atomic",
                body="Body content here.",
            )
            # No leftover tmp files alongside.
            candidates_dir = layout.project_space("lp").candidates
            leftover = list(candidates_dir.glob("*.tmp"))
            self.assertEqual(leftover, [])

    def test_review_atomicity(self):
        from tests.e2e._harness import fresh_environment
        from ccw_knowledge import cli as cli2

        with fresh_environment() as (tmp, home, vault):
            project_dir = tmp / "lp3"
            project_dir.mkdir()
            os.chdir(project_dir)

            cli2.main(["init", "--vault", str(vault)])
            cli2.main(["attach", "--project-id", "lp3"])

            cli2.main([
                "capture",
                "--project", "lp3",
                "--text", "real content",
                "--title", "Atomic2",
            ])
            # find candidate id
            layout = vault_mod.resolve_vault()
            cand_path = list(layout.project_space("lp3").candidates.glob("*.md"))[0]
            doc = read_document(cand_path)

            cli2.main([
                "review",
                "--project", "lp3",
                "--candidate", doc.id,
                "--action", "approve",
                "--reviewer", "ci",
            ])
            # No leftover tmp files.
            for d in (layout.project_space("lp3").candidates, layout.project_space("lp3").knowledge):
                leftover = list(d.glob("*.tmp"))
                self.assertEqual(leftover, [])
            # knowledge/ bucket should hold the new doc.
            reviewed = [
                p for p in layout.project_space("lp3").knowledge.glob("**/*.md")
                if not p.name.startswith("deprecated")
            ]
            self.assertGreaterEqual(len(reviewed), 1)


if __name__ == "__main__":
    unittest.main()
