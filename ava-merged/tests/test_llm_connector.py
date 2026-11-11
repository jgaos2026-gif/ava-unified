"""Tests for llm_connector.py — offline, no key, no network on the defer paths."""
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import llm_connector  # noqa: E402


class TestLLMConnector(unittest.TestCase):
    def setUp(self):
        for k in ("AVA_LLM_API_KEY", "AVA_LLM_MODEL", "AVA_LLM_PROVIDER"):
            os.environ.pop(k, None)

    def test_no_key_is_not_connected_and_propose_defers_without_network(self):
        st = llm_connector.status()
        self.assertFalse(st["llm_connected"])
        self.assertEqual(st["reason"], "NO_API_KEY")
        self.assertNotIn("AVA_LLM_API_KEY", json.dumps(st))
        with mock.patch("llm_connector.urllib.request.urlopen") as u:
            r = llm_connector.propose("hello")
            u.assert_not_called()
        self.assertEqual(r["status"], "DEFERRED")

    def test_no_model_is_not_connected(self):
        os.environ["AVA_LLM_API_KEY"] = "test-key-never-real"
        st = llm_connector.status()
        self.assertFalse(st["llm_connected"])
        self.assertEqual(st["reason"], "NO_MODEL_SET")

    def test_unsupported_provider(self):
        os.environ["AVA_LLM_PROVIDER"] = "made-up-provider"
        st = llm_connector.status()
        self.assertFalse(st["llm_connected"])
        self.assertEqual(st["reason"], "UNSUPPORTED_PROVIDER")

    def test_tool_marker_response_is_deferred_not_executed(self):
        os.environ["AVA_LLM_API_KEY"] = "test-key-never-real"
        os.environ["AVA_LLM_MODEL"] = "test-model"
        fake_body = json.dumps({"output_text": "do this tool_call now"}).encode()
        resp = mock.MagicMock()
        resp.read.return_value = fake_body
        resp.__enter__.return_value = resp
        with mock.patch("llm_connector.urllib.request.urlopen", return_value=resp):
            r = llm_connector.propose("hello")
        self.assertEqual(r["status"], "DEFERRED")
        self.assertEqual(r["reason"], "TOOL_MARKER_IN_RESPONSE")
        self.assertEqual(r["text"], "")

    def test_gemini_response_uses_x_goog_api_key_header_not_bearer(self):
        os.environ["AVA_LLM_PROVIDER"] = "gemini"
        os.environ["AVA_LLM_API_KEY"] = "test-key-never-real"
        os.environ["AVA_LLM_MODEL"] = "gemini-test-model"
        fake_body = json.dumps(
            {"candidates": [{"content": {"parts": [{"text": "Hello, John."}]}}]}).encode()
        resp = mock.MagicMock()
        resp.read.return_value = fake_body
        resp.__enter__.return_value = resp
        with mock.patch("llm_connector.urllib.request.urlopen", return_value=resp) as u:
            r = llm_connector.propose("hello")
            sent = u.call_args[0][0]
            self.assertIn("gemini-test-model", sent.full_url)
            self.assertEqual(sent.get_header("X-goog-api-key"), "test-key-never-real")
            self.assertIsNone(sent.get_header("Authorization"))
        self.assertEqual(r["status"], "PROPOSED")
        self.assertEqual(r["text"], "Hello, John.")

    def test_clean_response_is_proposal_only(self):
        os.environ["AVA_LLM_PROVIDER"] = "openai-responses"
        os.environ["AVA_LLM_API_KEY"] = "test-key-never-real"
        os.environ["AVA_LLM_MODEL"] = "test-model"
        fake_body = json.dumps({"output_text": "Hello, John."}).encode()
        resp = mock.MagicMock()
        resp.read.return_value = fake_body
        resp.__enter__.return_value = resp
        with mock.patch("llm_connector.urllib.request.urlopen", return_value=resp) as u:
            r = llm_connector.propose("hello")
            # Key travels only in the Authorization header of that one call.
            sent = u.call_args[0][0]
            self.assertEqual(sent.get_header("Authorization"), "Bearer test-key-never-real")
        self.assertEqual(r["status"], "PROPOSED")
        self.assertEqual(r["text"], "Hello, John.")


if __name__ == "__main__":
    unittest.main()
