import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.llm import LLMChatSession


@pytest.mark.asyncio
async def test_llm_session_tier1_success():
    with patch("app.llm.settings.GEMINI_API_KEY", "test_gemini_key"), \
         patch("app.llm.genai.Client") as mock_client:
        
        mock_chat = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.text = "```json\n{\"command\": \"git status\"}\n```"
        mock_chat.send_message.return_value = mock_resp
        mock_client.return_value.aio.chats.create.return_value = mock_chat

        session = LLMChatSession(system_instruction="You are Nimbus agent.")
        output = await session.send_message("Please inspect files.")

        assert output == "```json\n{\"command\": \"git status\"}\n```"
        assert len(session.messages) == 3
        assert session.messages[0]["role"] == "system"
        assert session.messages[1]["role"] == "user"
        assert session.messages[2]["role"] == "assistant"


@pytest.mark.asyncio
async def test_llm_session_failover_to_tier2_groq():
    with patch("app.llm.settings.GEMINI_API_KEY", "test_gemini_key"), \
         patch("app.llm.settings.GROQ_API_KEY", "gsk_test_key"), \
         patch("app.llm.genai.Client") as mock_client, \
         patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        
        # Tier 1 fails with 429
        mock_chat = AsyncMock()
        mock_chat.send_message.side_effect = RuntimeError("429 ResourceExhausted")
        mock_client.return_value.aio.chats.create.return_value = mock_chat

        # Tier 2 (Groq) succeeds
        mock_groq_resp = MagicMock()
        mock_groq_resp.status_code = 200
        mock_groq_resp.json.return_value = {
            "choices": [{"message": {"content": "```json\n{\"command\": \"pytest\"}\n```"}}]
        }
        mock_post.return_value = mock_groq_resp

        fallback_logs = []
        async def on_fallback(msg: str):
            fallback_logs.append(msg)

        session = LLMChatSession(system_instruction="You are Nimbus agent.")
        output = await session.send_message("Run tests", on_fallback=on_fallback)

        assert output == "```json\n{\"command\": \"pytest\"}\n```"
        assert len(fallback_logs) >= 1
        assert "Tier 1" in fallback_logs[0]
        assert "Failing over to Tier 2 (Groq)" in fallback_logs[0]


@pytest.mark.asyncio
async def test_llm_session_failover_to_tier3_openrouter():
    with patch("app.llm.settings.GEMINI_API_KEY", None), \
         patch("app.llm.settings.GROQ_API_KEY", "gsk_test_key"), \
         patch("app.llm.settings.OPENROUTER_API_KEY", "sk-or-test"), \
         patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        
        # Tier 2 fails with 500 error
        mock_groq_fail = MagicMock()
        mock_groq_fail.status_code = 500
        mock_groq_fail.text = "Internal Server Error"

        # Tier 3 (OpenRouter) succeeds
        mock_or_success = MagicMock()
        mock_or_success.status_code = 200
        mock_or_success.json.return_value = {
            "choices": [{"message": {"content": "Task completed successfully."}}]
        }

        # First post call is Groq (fails), second post call is OpenRouter (succeeds)
        mock_post.side_effect = [mock_groq_fail, mock_or_success]

        fallback_logs = []
        async def on_fallback(msg: str):
            fallback_logs.append(msg)

        session = LLMChatSession(system_instruction="You are Nimbus agent.")
        output = await session.send_message("Summarize results", on_fallback=on_fallback)

        assert output == "Task completed successfully."
        assert any("Tier 3 (OpenRouter)" in log for log in fallback_logs)


@pytest.mark.asyncio
async def test_llm_session_all_tiers_exhausted():
    with patch("app.llm.settings.GEMINI_API_KEY", None), \
         patch("app.llm.settings.GROQ_API_KEY", None), \
         patch("app.llm.settings.OPENROUTER_API_KEY", None):
        
        session = LLMChatSession(system_instruction="You are Nimbus agent.")
        with pytest.raises(RuntimeError) as exc_info:
            await session.send_message("Hello")
        
        assert "All LLM tiers in fallback stack exhausted" in str(exc_info.value)
