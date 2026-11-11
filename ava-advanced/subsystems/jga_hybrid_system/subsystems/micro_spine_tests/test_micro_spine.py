"""Tests for the Hardened MicroSpine Core (Option 1)."""
import os
import socket
import struct
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from micro_spine import (IntegrityError, MicroSpine, SecretError,
                         load_secret, run_selftest, run_socket_server,
                         MAX_PAYLOAD)

SECRET = b"test-secret-at-least-16-bytes!"


def make_spine(td):
    return MicroSpine(Path(td) / "spine.bin", SECRET)


class TestCore(unittest.TestCase):
    def test_genesis_only_verifies(self):
        with tempfile.TemporaryDirectory() as td:
            spine = make_spine(td)
            self.assertEqual(spine.record_count, 0)
            head, count = spine.verify_integrity()
            self.assertEqual(count, 0)

    def test_append_and_verify(self):
        with tempfile.TemporaryDirectory() as td:
            spine = make_spine(td)
            ok, head = spine.append(b"hello")
            self.assertTrue(ok)
            self.assertEqual(spine.record_count, 1)
            self.assertEqual(spine.verify_integrity()[0].hex(), head)
            # Remount with the same secret verifies too.
            spine2 = MicroSpine(Path(td) / "spine.bin", SECRET)
            self.assertEqual(spine2.record_count, 1)

    def test_tampered_payload_refuses_mount(self):
        with tempfile.TemporaryDirectory() as td:
            spine = make_spine(td)
            spine.append(b"hello world")
            p = Path(td) / "spine.bin"
            data = bytearray(p.read_bytes())
            data[-1] ^= 0x01  # flip one payload bit
            p.write_bytes(data)
            with self.assertRaises(IntegrityError):
                MicroSpine(p, SECRET)

    def test_tampered_hash_refuses_mount(self):
        with tempfile.TemporaryDirectory() as td:
            spine = make_spine(td)
            spine.append(b"hello")
            p = Path(td) / "spine.bin"
            data = bytearray(p.read_bytes())
            # First record header starts after genesis (44 bytes); hash field at +12
            data[44 + 12] ^= 0x01
            p.write_bytes(data)
            with self.assertRaises(IntegrityError):
                MicroSpine(p, SECRET)

    def test_truncated_file_refuses_mount(self):
        with tempfile.TemporaryDirectory() as td:
            spine = make_spine(td)
            spine.append(b"hello world, this is longer")
            p = Path(td) / "spine.bin"
            data = p.read_bytes()
            p.write_bytes(data[:-3])
            with self.assertRaises(IntegrityError):
                MicroSpine(p, SECRET)

    def test_trailing_garbage_refuses_mount(self):
        with tempfile.TemporaryDirectory() as td:
            spine = make_spine(td)
            spine.append(b"hello")
            p = Path(td) / "spine.bin"
            with open(p, "ab") as f:
                f.write(b"junk")
            with self.assertRaises(IntegrityError):
                MicroSpine(p, SECRET)

    def test_wrong_secret_refuses_mount(self):
        with tempfile.TemporaryDirectory() as td:
            spine = make_spine(td)
            spine.append(b"hello")
            with self.assertRaises(IntegrityError):
                MicroSpine(Path(td) / "spine.bin", b"a-different-secret-16+!")

    def test_empty_and_oversize_refused(self):
        with tempfile.TemporaryDirectory() as td:
            spine = make_spine(td)
            self.assertEqual(spine.append(b"")[0], False)
            self.assertEqual(spine.append(b"x" * (MAX_PAYLOAD + 1))[0], False)
            self.assertEqual(spine.record_count, 0)


class TestSecret(unittest.TestCase):
    def setUp(self):
        self._env = dict(os.environ)
        os.environ.pop("BCT_SECRET", None)
        os.environ.pop("BCT_SECRET_FILE", None)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env)

    def test_missing_secret_refused(self):
        with self.assertRaises(SecretError):
            load_secret()

    def test_short_secret_refused(self):
        os.environ["BCT_SECRET"] = "short"
        with self.assertRaises(SecretError):
            load_secret()

    def test_keyfile_0600_accepted(self):
        with tempfile.TemporaryDirectory() as td:
            kf = Path(td) / "key"
            kf.write_bytes(b"keyfile-secret-at-least-16")
            os.chmod(kf, 0o600)
            os.environ["BCT_SECRET_FILE"] = str(kf)
            self.assertEqual(load_secret(), b"keyfile-secret-at-least-16")

    def test_keyfile_group_readable_refused(self):
        if os.name != "posix":
            self.skipTest("POSIX permission check only")
        with tempfile.TemporaryDirectory() as td:
            kf = Path(td) / "key"
            kf.write_bytes(b"keyfile-secret-at-least-16")
            os.chmod(kf, 0o640)
            os.environ["BCT_SECRET_FILE"] = str(kf)
            with self.assertRaises(SecretError):
                load_secret()


class TestSelftestIsolation(unittest.TestCase):
    def test_selftest_does_not_touch_persistent_file(self):
        with tempfile.TemporaryDirectory() as td:
            spine = make_spine(td)
            spine.append(b"real record")
            p = Path(td) / "spine.bin"
            before = p.read_bytes()
            # run_selftest needs a secret in env
            os.environ["BCT_SECRET"] = SECRET.decode()
            try:
                self.assertTrue(run_selftest())
            finally:
                os.environ.pop("BCT_SECRET", None)
            self.assertEqual(p.read_bytes(), before)


class TestSocket(unittest.TestCase):
    def test_socket_roundtrip_and_oversize_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            spine = make_spine(td)
            sock_path = Path(td) / "bct_ipc.sock"
            thread = threading.Thread(target=run_socket_server,
                                      args=(spine, sock_path), daemon=True)
            thread.start()
            for _ in range(50):
                if sock_path.exists():
                    break
                import time; time.sleep(0.05)
            def send(payload):
                s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                s.settimeout(5)
                s.connect(str(sock_path))
                s.sendall(struct.pack(">I", len(payload)) + payload)
                resp = s.recv(128)
                s.close()
                return resp
            self.assertTrue(send(b"socket record").startswith(b"OK:"))
            self.assertEqual(spine.record_count, 1)
            # Oversize length prefix: server must reject, not append.
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(5)
            s.connect(str(sock_path))
            s.sendall(struct.pack(">I", MAX_PAYLOAD + 1))
            resp = s.recv(128)
            s.close()
            self.assertTrue(resp.startswith(b"FAIL:"))
            self.assertEqual(spine.record_count, 1)


if __name__ == "__main__":
    unittest.main()
