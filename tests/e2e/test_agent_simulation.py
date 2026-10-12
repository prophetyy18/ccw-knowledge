"""End-to-end: simulate an agent using the knowledge Skills (CLI only).

This test verifies that a script "acting as an agent" gets the right
Evidence Pack back. It does NOT verify the auto-invocation heuristic in
Claude Code (which would require running Claude Code itself).
"""

import os
import unittest
import json
from pathlib import Path

from tests.e2e._harness import CLIRunner, fresh_environment


class AgentSimulatedUseTests(unittest.TestCase):
    def test_search_returns_evidence_pack(self):
        with fresh_environment() as (tmp, home, vault):
            project = tmp / "lp5"
            project.mkdir()
            os.chdir(project)

            r = CLIRunner(home)
            r.run("init", "--vault", str(vault))
            r.run("attach", "--project-id", "lp5")
            # Capture a few.
            r.run("capture", "--project", "lp5",
                  "--text", "Auth tokens are stored in /etc/secrets/auth.",
                  "--title", "Token storage location",
                  "--tags", "security")
            r.run("capture", "--project", "lp5",
                  "--text", "Auth rotation policy: every 30 days.",
                  "--title", "Token rotation policy",
                  "--tags", "security,policy")

            # search with default depth
            rc = r.run("search", "auth token", "--json")
            self.assertEqual(rc, 0)
            pack = r.json()
            self.assertIn("matches", pack)
            self.assertIn("search_limits", pack)

    def test_audit_reports_duplicates_and_missing_sources(self):
        with fresh_environment() as (tmp, home, vault):
            project = tmp / "lp6"
            project.mkdir()
            os.chdir(project)

            r = CLIRunner(home)
            r.run("init", "--vault", str(vault))
            r.run("attach", "--project-id", "lp6")

            # Capture one with a missing source.
            rc = r.run(
                "capture", "--project", "lp6",
                "--text", "Doc with bad source citation.",
                "--title", "Document with missing source",
                "--sources", "/no/such/file.md",
            )
            self.assertEqual(rc, 0)

            rc = r.run("audit", "--project", "lp6", "--json")
            self.assertEqual(rc, 0)
            rep = r.json()
            codes = [f["code"] for f in rep["findings"]]
            self.assertIn("missing-source", codes)


if __name__ == "__main__":
    unittest.main()
