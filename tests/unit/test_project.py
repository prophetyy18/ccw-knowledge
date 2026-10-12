"""Unit tests for the project module."""

import os
import unittest
from pathlib import Path


class ProjectIdentityTests(unittest.TestCase):
    def test_id_is_stable(self):
        from ccw_knowledge.pathutil import project_id_from_path, encode_project_path_for_storage
        p = Path("/tmp/sample-project")
        pid1 = project_id_from_path(p)
        pid2 = project_id_from_path(p)
        self.assertEqual(pid1, pid2)
        self.assertIn(encode_project_path_for_storage(p), pid1)

    def test_attach_writes_minimal_config(self):
        import tempfile

        from ccw_knowledge import vault as vault_mod, project as proj
        with tempfile.TemporaryDirectory() as tmp:
            proj_dir = Path(tmp) / "lp2"
            proj_dir.mkdir()
            vault_dir = Path(tmp) / "vault"
            vault_mod.init_vault(vault_dir)
            layout = vault_mod.resolve_vault()
            rec = proj.attach(
                project_root=proj_dir,
                vault=layout,
            )
            self.assertEqual(rec.project_root, str(proj_dir.resolve()))
            self.assertTrue((proj_dir / ".ccw-knowledge.json").exists())


class ProjectConfigYamlTests(unittest.TestCase):
    def test_roundtrip(self):
        import tempfile
        from ccw_knowledge import project as proj

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = proj.ProjectConfig(
                version=1,
                project_id="x",
                knowledge_enabled=True,
                scopes=["project:x", "shared"],
                default_depth="deep",
                context_budget=4000,
                capture_enabled=True,
                automatic_publication=False,
            )
            path = proj.write_local_config(root, cfg)
            text = path.read_text(encoding="utf-8")
            self.assertIn("project_id: x", text)
            self.assertIn("default_depth: deep", text)
            loaded = proj.load_local_config(root)
            assert loaded is not None
            self.assertEqual(loaded.project_id, "x")
            self.assertEqual(loaded.default_depth, "deep")
            self.assertEqual(loaded.scopes, ["project:x", "shared"])

    def test_attach_idempotent(self):
        import tempfile
        from ccw_knowledge import vault as vault_mod, project as proj

        with tempfile.TemporaryDirectory() as tmp:
            proj_dir = Path(tmp) / "lp3"
            proj_dir.mkdir()
            vault_dir = Path(tmp) / "vault"
            vault_mod.init_vault(vault_dir)
            layout = vault_mod.resolve_vault()
            rec1 = proj.attach(project_root=proj_dir, vault=layout)
            rec2 = proj.attach(project_root=proj_dir, vault=layout)
            self.assertEqual(rec1.project_id, rec2.project_id)


if __name__ == "__main__":
    unittest.main()
