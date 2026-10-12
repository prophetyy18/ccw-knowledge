"""Unit tests for the vault module."""

import os
import unittest
from pathlib import Path

from ccw_knowledge import vault as vault_mod


class VaultInitTests(unittest.TestCase):
    def test_init_creates_layout(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "vault"
            layout = vault_mod.init_vault(target)
            self.assertTrue(layout.shared_sources.exists())
            self.assertTrue(layout.shared_candidates.exists())
            self.assertTrue(layout.shared_knowledge.exists())
            self.assertTrue(layout.projects_root.exists())
            for d in (layout.shared_sources, layout.shared_candidates,
                      layout.shared_knowledge):
                self.assertTrue((d / "_meta.json").exists())

    def test_init_idempotent(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "vault"
            vault_mod.init_vault(target)
            # second call must succeed without --force
            vault_mod.init_vault(target)
            self.assertTrue(target.exists())

    def test_resolve_requires_init(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "vault"
            target.mkdir()
            vault_mod.init_vault(target)
            layout = vault_mod.resolve_vault()
            self.assertEqual(layout.root, target.resolve())

    def test_find_scope_for_path(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "vault"
            vault_mod.init_vault(target)
            layout = vault_mod.resolve_vault()
            sample = layout.shared_knowledge / "foo.md"
            sample.parent.mkdir(parents=True, exist_ok=True)
            sample.write_text("# x")
            info = vault_mod.find_scope_for_path(layout, sample)
            self.assertIsNotNone(info)
            self.assertEqual(info["scope"], "shared")
            self.assertEqual(info["bucket"], "knowledge")


if __name__ == "__main__":
    unittest.main()
