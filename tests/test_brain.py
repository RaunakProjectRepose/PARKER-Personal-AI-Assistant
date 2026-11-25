"""Tests for backend.brain.

These never contact a real Ollama server: ``requests.post`` is replaced with a
fake, so the tests run in a second, offline, on any machine.
"""

from unittest.mock import Mock

import pytest
import requests

from backend import brain


def fake_response(status=200, json_data=None, text=""):
    resp = Mock()
    resp.status_code = status
    resp.ok = 200 <= status < 300
    resp.text = text
    if isinstance(json_data, Exception):
        resp.json.side_effect = json_data
    else:
        resp.json.return_value = json_data
    return resp


@pytest.fixture
def post(monkeypatch):
    """Replace requests.post and give the test control over its result."""
    mock = Mock(return_value=fake_response(json_data={"message": {"content": " Hello. "}}))
    monkeypatch.setattr(brain.requests, "post", mock)
    return mock


# ---- build_messages ---------------------------------------------------------

def test_system_prompt_comes_first_and_user_message_last():
    msgs = brain.build_messages("  Hi  ")
    assert msgs[0] == {"role": "system", "content": brain.SYSTEM_PROMPT}
    assert msgs[-1] == {"role": "user", "content": "Hi"}


def test_history_sits_between_system_prompt_and_new_message():
    history = [
        {"role": "user", "content": "My name is Raunak."},
        {"role": "assistant", "content": "Nice to meet you."},
    ]
    msgs = brain.build_messages("What is my name?", history)
    assert msgs[1:3] == history
    assert len(msgs) == 4


def test_history_is_not_modified():
    history = [{"role": "user", "content": "Earlier"}]
    brain.build_messages("Now", history)
    assert history == [{"role": "user", "content": "Earlier"}]


@pytest.mark.parametrize("bad", ["", "   ", None])
def test_empty_message_is_rejected(bad):
    with pytest.raises(ValueError):
        brain.build_messages(bad)


def test_system_prompt_names_parker_and_the_real_model():
    # Without this, Qwen once claimed to be "trained by Google".
    assert "PARKER" in brain.SYSTEM_PROMPT
    assert "Qwen" in brain.SYSTEM_PROMPT


# ---- generate_response: success ---------------------------------------------

def test_returns_reply_text_stripped(post):
    assert brain.generate_response("Hello") == "Hello."


def test_sends_correct_request_to_ollama(post):
    brain.generate_response("Hello", model="test-model", base_url="http://host:1234")
    url = post.call_args.args[0]
    payload = post.call_args.kwargs["json"]
    assert url == "http://host:1234/api/chat"
    assert payload["model"] == "test-model"
    assert payload["stream"] is False
    assert payload["think"] is False
    assert payload["messages"][-1] == {"role": "user", "content": "Hello"}
    assert post.call_args.kwargs["timeout"] > 0


# ---- generate_response: failures --------------------------------------------

def test_ollama_not_running(post):
    post.side_effect = requests.ConnectionError()
    with pytest.raises(brain.BrainError, match="Is the Ollama app running"):
        brain.generate_response("Hello")


def test_timeout(post):
    post.side_effect = requests.Timeout()
    with pytest.raises(brain.BrainError, match="did not reply"):
        brain.generate_response("Hello", timeout=5)


def test_model_not_downloaded(post):
    post.return_value = fake_response(status=404, text='{"error":"model not found"}')
    with pytest.raises(brain.BrainError, match="ollama pull"):
        brain.generate_response("Hello", model="missing:1b")


def test_server_error(post):
    post.return_value = fake_response(status=500, text="boom")
    with pytest.raises(brain.BrainError, match="HTTP 500"):
        brain.generate_response("Hello")


@pytest.mark.parametrize(
    "json_data",
    [ValueError("not json"), {}, {"message": None}, {"message": {"role": "assistant"}}],
)
def test_unexpected_reply_format(post, json_data):
    post.return_value = fake_response(json_data=json_data)
    with pytest.raises(brain.BrainError, match="unexpected format"):
        brain.generate_response("Hello")


def test_empty_reply(post):
    post.return_value = fake_response(json_data={"message": {"content": "   "}})
    with pytest.raises(brain.BrainError, match="empty reply"):
        brain.generate_response("Hello")
