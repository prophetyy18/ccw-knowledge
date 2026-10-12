"""End-to-end: init, attach, detach lifecycle."""

import os
import unittest
from pathlib import Path

from tests.e2e._harness import CLIRunner, fresh_environment


class InitAttachTests(unittest.TestCase):
    def test_init_attaches_a_project_and_detaches(self):
        with fresh_environment() as (tmp, home, vault):
            project = tmp / "lp2"
            project.mkdir()

            r = CLIRunner(home)
            rc = r.run("init", "--vault", str(vault))
            self.assertEqual(rc, 0, msg=r.last_stderr)
            self.assertTrue((vault / "shared" / "sources").exists())
            self.assertTrue((vault / "shared" / "candidates").exists())
            self.assertTrue((vault / "shared" / "knowledge").exists())

            # attach
            os.chdir(project)
            rc = r.run("attach", "--project-id", "lp2")
            self.assertEqual(rc, 0, msg=r.last_stderr)
            self.assertTrue((project / ".ccw-knowledge.json").exists())
            self.assertTrue((vault / "projects" / "lp2" / "sources").exists())

            # second attach must be idempotent (same id)
            rc = r.run("attach", "--project-id", "lp2")
            self.assertEqual(rc, 0, msg=r.last_stderr)

            # detach
            rc = r.run("detach", "--project-id", "lp2")
            self.assertEqual(rc, 0, msg=r.last_stderr)
            self.assertFalse((project / ".ccw-knowledge.json").exists())
            # but project-knowledge in vault must remain untouched
            self.assertTrue((vault / "projects" / "lp2").exists())

    def test_init_is_idempotent(self):
        with fresh_environment() as (tmp, home, vault):
            r = CLIRunner(home)
            r.run("init", "--vault", str(vault))
            r2 = r.run("init", "--vault", str(vault))
            self.assertEqual(r2, 0)


if __name__ == "__main__":
    unittest.main()
