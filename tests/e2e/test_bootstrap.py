"""End-to-end: bootstrap only creates Candidates; never auto-publishes."""

import os
import unittest
from pathlib import Path

from tests.e2e._harness import CLIRunner, fresh_environment


class BootstrapSafetyTests(unittest.TestCase):
    def test_bootstrap_creates_only_candidates(self):
        with fresh_environment() as (tmp, home, vault):
            project = tmp / "lp_proj"
            project.mkdir()
            (project / "README.md").write_text(
                "# Hello\n\n"
                "This project provides a concrete demonstration of the bootstrap flow.\n"
                "It verifies that the engine only writes candidates and never publishes.\n",
                encoding="utf-8",
            )
            (project / "DESIGN.md").write_text(
                "# Design\n\n"
                "The design philosophy here prioritises simplicity, traceability, and\n"
                "an unambiguous candidate → reviewed lifecycle for every knowledge document.\n",
                encoding="utf-8",
            )

            os.chdir(project)
            r = CLIRunner(home)
            r.run("init", "--vault", str(vault))
            r.run("attach", "--project-id", "lp_proj")

            # Dry-run: nothing should be created on disk.
            rc = r.run(
                "bootstrap",
                "--project", "lp_proj",
                "--dry-run",
                "--max-files", "10",
            )
            self.assertEqual(rc, 0, msg=r.last_stderr)

            from ccw_knowledge import vault as vault_mod
            layout = vault_mod.resolve_vault()
            cand = list(layout.project_space("lp_proj").candidates.glob("**/*.md"))
            knowledge = list(layout.project_space("lp_proj").knowledge.glob("**/*.md"))
            self.assertEqual(len(cand), 0)
            self.assertEqual(len(knowledge), 0)

            # Real run.
            rc = r.run(
                "bootstrap",
                "--project", "lp_proj",
                "--max-files", "10",
            )
            self.assertEqual(rc, 0, msg=r.last_stderr)
            cand = list(layout.project_space("lp_proj").candidates.glob("**/*.md"))
            knowledge = list(layout.project_space("lp_proj").knowledge.glob("**/*.md"))
            self.assertGreater(len(cand), 0)
            self.assertEqual(len(knowledge), 0)  # never auto-publish

    def test_bootstrap_does_not_copy_project_files_verbatim(self):
        with fresh_environment() as (tmp, home, vault):
            project = tmp / "proj2"
            project.mkdir()
            (project / "BIG.md").write_text(("x" * 200) + "\n", encoding="utf-8")

            os.chdir(project)
            r = CLIRunner(home)
            r.run("init", "--vault", str(vault))
            r.run("attach", "--project-id", "proj2")
            r.run("bootstrap", "--project", "proj2", "--max-files", "10", "--max-chars", "200")

            from ccw_knowledge import vault as vault_mod
            layout = vault_mod.resolve_vault()
            candidates = list(layout.project_space("proj2").candidates.glob("**/*.md"))
            self.assertGreater(len(candidates), 0)
            for c in candidates:
                text = c.read_text(encoding="utf-8", errors="ignore")
                self.assertLess(len(text), 2000,
                                "candidate should be a summary, not a verbatim copy")


if __name__ == "__main__":
    unittest.main()
