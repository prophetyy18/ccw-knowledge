"""CLI unit tests via direct invocation."""

import io
import json
import os
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from tempfile import TemporaryDirectory

from ccw_knowledge import cli
from ccw_knowledge import vault as vault_mod


class CLIParsingTests(unittest.TestCase):
    def test_help_exits_zero(self):
        import io, contextlib
        parser = cli.build_parser()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            with self.assertRaises(SystemExit) as cm:
                parser.parse_args(["--help"])
        self.assertEqual(cm.exception.code, 0)

    def test_invalid_subcommand(self):
        parser = cli.build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["badcommand"])


class CLIDispatchTests(unittest.TestCase):
    def _run_with_home(self, monkeypatch_method=None):
        """Run a CLI command against an isolated engine home."""
        from unittest import mock

        with TemporaryDirectory() as tmp:
            os.environ["CCW_HOME"] = str(Path(tmp) / "home")
            os.environ["CCW_CONFIG_DIR"] = str(Path(tmp) / "home" / ".ccw-knowledge")
            yield Path(tmp)

    def test_init_status_audit(self):
        import argparse
        gen = self._run_with_home()
        tmp = next(gen)
        try:
            v = tmp / "vault"
            cmd = argparse.Namespace(vault=str(v), force=False)
            rc = cli.cmd_init(cmd)
            self.assertEqual(rc, cli.EXIT_OK)
            s = argparse.Namespace(json=False, project=None)
            rc = cli.cmd_status(s)
            self.assertEqual(rc, cli.EXIT_OK)
            a = argparse.Namespace(project=None, scope=None, fix=False, json=False)
            rc = cli.cmd_audit(a)
            self.assertEqual(rc, cli.EXIT_OK)
        finally:
            try:
                next(gen)
            except StopIteration:
                pass


if __name__ == "__main__":
    unittest.main()
