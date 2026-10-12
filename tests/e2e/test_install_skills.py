"""End-to-end: install-skills command for both user and project targets."""

import os
import unittest
from pathlib import Path

from tests.e2e._harness import CLIRunner, fresh_environment


class InstallSkillsTests(unittest.TestCase):
    def test_install_user_target(self):
        with fresh_environment() as (tmp, home, vault):
            r = CLIRunner(home)
            rc = r.run("install-skills", "--target", "user")
            self.assertEqual(rc, 0, msg=r.last_stderr)
            # global ~/.ccw-knowledge/skills/ must contain the five Skills.
            from ccw_knowledge.pathutil import global_config_root
            skills_root = global_config_root() / "skills"
            installed = sorted(p.name for p in skills_root.iterdir())
            for skill in (
                "knowledge-context",
                "knowledge-capture",
                "knowledge-review",
                "knowledge-audit",
                "knowledge-bootstrap",
            ):
                self.assertIn(skill, installed)

    def test_install_project_target(self):
        with fresh_environment() as (tmp, home, vault):
            project_dir = tmp / "someproj"
            project_dir.mkdir()
            r = CLIRunner(home)
            rc = r.run(
                "install-skills",
                "--target", "project",
                "--project-dir", str(project_dir),
            )
            self.assertEqual(rc, 0, msg=r.last_stderr)
            installed = sorted(
                p.name for p in (project_dir / ".claude" / "skills").iterdir()
            )
            self.assertIn("knowledge-context", installed)


if __name__ == "__main__":
    unittest.main()
