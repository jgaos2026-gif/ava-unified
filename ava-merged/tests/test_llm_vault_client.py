"""Tests for services/llm_vault_client.py — offline, mocked network."""
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "services"))
import llm_vault_client  # noqa: E402


class TestVaultClient(unittest.TestCase):
    def setUp(self):
        for k in ("AVA_LLM_API_KEY", "AVA_LLM_MODEL"):
            os.environ.pop(k, None)

    def _fake_resp(self, body_dict):
        resp = mock.MagicMock()
        resp.read.return_value = json.dumps(body_dict).encode()
        resp.__enter__.return_value = resp
        return resp

    def test_no_model_defers_without_network(self):
        os.environ["AVA_LLM_API_KEY"] = "test-key-never-real"
        with mock.patch("llm_vault_client.urllib.request.urlopen") as u:
            r = llm_vault_client.propose("hello", model="")
            u.assert_not_called()
        self.assertEqual(r["reason"], "NO_MODEL_SET")

    def _patch_opener(self, body_dict):
        opener = mock.MagicMock()
        opener.open.return_value.__enter__.return_value = self._fake_resp(body_dict)
        # _fake_resp already is a context manager mock; simplify:
        fake = self._fake_resp(body_dict)
        opener.open.return_value = fake
        patcher = mock.patch("llm_vault_client.urllib.request.build_opener",
                             return_value=opener)
        patcher.start()
        self.addCleanup(patcher.stop)
        return opener

    def test_env_key_uses_x_goog_api_key_not_bearer(self):
        os.environ["AVA_LLM_API_KEY"] = "test-key-never-real"
        body = {"candidates": [{"content": {"parts": [{"text": "Hello."}]}}]}
        opener = self._patch_opener(body)
        r = llm_vault_client.propose("hello", model="gemini-test")
        sent = opener.open.call_args[0][0]
        self.assertEqual(sent.get_header("X-goog-api-key"), "test-key-never-real")
        self.assertIsNone(sent.get_header("Authorization"))
        self.assertEqual(r["status"], "PROPOSED")

    def test_tool_marker_defers(self):
        os.environ["AVA_LLM_API_KEY"] = "test-key-never-real"
        body = {"candidates": [{"content": {"parts": [{"text": "do tool_call now"}]}}]}
        self._patch_opener(body)
        with mock.patch("llm_vault_client.urllib.request.urlopen"):
            r = llm_vault_client.propose("hello", model="gemini-test")
        self.assertEqual(r["status"], "DEFERRED")
        self.assertEqual(r["text"], "")


if __name__ == "__main__":
    unittest.main()
