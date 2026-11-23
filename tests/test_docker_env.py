"""Env overrides used by the Docker image: bind host, allowed origins and data directory."""

import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from crunchyroll import server

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class OriginAllowedTests(unittest.TestCase):
    def test_localhost_only_by_default(self):
        with patch.dict(os.environ, {"CRUNCHYROLLER_ALLOWED_ORIGINS": ""}):
            self.assertTrue(server._origin_allowed("localhost"))
            self.assertTrue(server._origin_allowed("127.0.0.1"))
            self.assertFalse(server._origin_allowed("192.168.1.20"))
            self.assertFalse(server._origin_allowed(None))

    def test_extra_origins_from_env(self):
        with patch.dict(os.environ, {"CRUNCHYROLLER_ALLOWED_ORIGINS": "192.168.1.20, Crunchy.Example.org"}):
            self.assertTrue(server._origin_allowed("localhost"))
            self.assertTrue(server._origin_allowed("192.168.1.20"))
            self.assertTrue(server._origin_allowed("crunchy.example.org"))
            self.assertFalse(server._origin_allowed("evil.example.org"))


class BindHostTests(unittest.TestCase):
    def _bind_host(self, value):
        with patch.dict(os.environ, {"CRUNCHYROLLER_HOST": value}),              patch("crunchyroll.server.setup_logging"),              patch("crunchyroll.server.http.server.ThreadingHTTPServer", side_effect=OSError) as srv:
            with self.assertRaises(OSError):
                server.start_gui(use_browser=True)
        return srv.call_args[0][0][0]

    def test_empty_value_stays_on_localhost(self):
        self.assertEqual(self._bind_host(""), "127.0.0.1")

    def test_override(self):
        self.assertEqual(self._bind_host("0.0.0.0"), "0.0.0.0")


class DataDirTests(unittest.TestCase):
    def _state_dirs(self, value):
        code = (
            "import os; from crunchyroll import auth, watcher; from crunchyroll.state_store import StateStore; "
            "print('|'.join(os.path.dirname(p) for p in (auth.CONFIG_FILE, StateStore().state_path, watcher.MONITORED_FILE)))"
        )
        out = subprocess.check_output(
            [sys.executable, "-c", code], cwd=ROOT, text=True,
            env={**os.environ, "CRUNCHYROLLER_DATA_DIR": value},
        )
        return {os.path.normcase(d) for d in out.strip().splitlines()[-1].split("|")}

    def test_empty_value_keeps_project_root(self):
        self.assertEqual(self._state_dirs(""), {os.path.normcase(ROOT)})

    def test_all_state_files_follow_data_dir(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(self._state_dirs(d), {os.path.normcase(d)})


if __name__ == "__main__":
    unittest.main()
