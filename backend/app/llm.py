"""Unified 3-Tier LLM Client with Automated Resilient Failover.

Tier 1: Google Gemini (gemini-2.5-flash) via google-genai
Tier 2: Groq (openai/gpt-oss-120b) via OpenAI-compatible REST endpoint
Tier 3: OpenRouter (google/gemma-4-31b-it:free) via OpenAI-compatible REST endpoint
"""

import json
import asyncio
from typing import Callable, Coroutine, List, Dict, Any, Optional
import httpx
from google import genai
from google.genai import types

from .settings import settings


class LLMChatSession:
    """Manages multi-turn conversation state with automatic failover across 3 zero-cost tiers."""

    def __init__(
        self,
        system_instruction: str,
        temperature: float = 0.1,
        max_tokens: int = 4096
    ):
        self.system_instruction = system_instruction
        self.temperature = temperature
        self.max_tokens = max_tokens
        # Unified message history for OpenAI-compatible endpoints: [{"role": "...", "content": "..."}]
        self.messages: List[Dict[str, str]] = [
            {"role": "system", "content": self.system_instruction}
        ]
        # Active Gemini client and chat objects
        self._gemini_client: Optional[genai.Client] = None
        self._gemini_chat = None
        self._gemini_models = ["gemini-3.6-flash", "gemini-3.7-flash", "gemini-3.5-flash", "gemini-flash-latest"]
        self._current_model_idx = 0
        self._init_gemini_chat()

    def _init_gemini_chat(self, model_override: Optional[str] = None):
        """Initializes and holds a persistent reference to the Gemini API Client and Async Chat."""
        if settings.GEMINI_API_KEY:
            try:
                self._gemini_client = genai.Client(api_key=settings.GEMINI_API_KEY)
                model_name = model_override or self._gemini_models[self._current_model_idx % len(self._gemini_models)]
                self._gemini_chat = self._gemini_client.aio.chats.create(
                    model=model_name,
                    config=types.GenerateContentConfig(
                        system_instruction=self.system_instruction,
                        temperature=self.temperature,
                        max_output_tokens=self.max_tokens,
                    )
                )
            except Exception as e:
                print(f"[LLM Router] Failed to initialize Gemini chat: {e}")
                self._gemini_client = None
                self._gemini_chat = None

    async def _call_gemini(self, prompt: str) -> str:
        """Tier 1: Google Gemini API with intra-model fallback, lifecycle recovery, and retry."""
        if not settings.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY is not configured.")
        
        last_err = None
        for attempt in range(1, 4):
            if not self._gemini_chat or not self._gemini_client:
                self._init_gemini_chat()
                if not self._gemini_chat:
                    raise ValueError("Failed to initialize Gemini chat client.")

            try:
                response = await self._gemini_chat.send_message(prompt)
                text = response.text or ""
                if not text.strip():
                    raise RuntimeError("Gemini returned empty response.")
                return text
            except Exception as e:
                last_err = e
                err_str = str(e).lower()
                
                # If client was closed, recreate chat session immediately
                if "client has been closed" in err_str:
                    print(f"[LLM Router] Gemini client connection was closed. Recreating (attempt {attempt}/3)...")
                    self._init_gemini_chat()
                    continue

                # If quota exhausted (429) or demand spike (503), switch to another model in Gemini family
                if "429" in err_str or "quota" in err_str or "503" in err_str or "unavailable" in err_str:
                    self._current_model_idx = (self._current_model_idx + 1) % len(self._gemini_models)
                    next_model = self._gemini_models[self._current_model_idx]
                    print(f"[LLM Router] Gemini model failover ({e}) -> Trying intra-Gemini model '{next_model}' (attempt {attempt}/3)...")
                    self._init_gemini_chat(model_override=next_model)
                    await asyncio.sleep(1.0)
                    continue
                
                # For other errors, raise to allow fallback tiers
                raise e

        if last_err:
            raise last_err
        raise RuntimeError("Gemini request failed after 3 attempts.")

    async def _call_openai_compatible(
        self,
        base_url: str,
        api_key: str,
        model: str,
        headers_extra: Optional[Dict[str, str]] = None
    ) -> str:
        """Helper for Tier 2 (Groq) and Tier 3 (OpenRouter)."""
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        if headers_extra:
            headers.update(headers_extra)

        payload = {
            "model": model,
            "messages": self.messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers=headers,
                json=payload
            )
            if resp.status_code != 200:
                raise RuntimeError(
                    f"Provider {base_url} returned HTTP {resp.status_code}: {resp.text}"
                )
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            if not content:
                raise RuntimeError(f"Provider {base_url} returned empty content.")
            return content

    async def _call_groq(self) -> str:
        """Tier 2: Groq Clean Models (openai/gpt-oss-120b)."""
        if not settings.GROQ_API_KEY:
            raise ValueError("GROQ_API_KEY is not configured.")
        
        model = settings.GROQ_MODEL or "openai/gpt-oss-120b"
        return await self._call_openai_compatible(
            base_url="https://api.groq.com/openai/v1",
            api_key=settings.GROQ_API_KEY,
            model=model
        )

    async def _call_openrouter(self) -> str:
        """Tier 3: OpenRouter Free Tier (google/gemma-4-31b-it:free)."""
        if not settings.OPENROUTER_API_KEY:
            raise ValueError("OPENROUTER_API_KEY is not configured.")
        
        model = settings.OPENROUTER_MODEL or "cohere/north-mini-code:free"
        headers_extra = {
            "HTTP-Referer": "https://nimbusagent.vercel.app",
            "X-Title": "Nimbus Cloud Agent",
        }
        return await self._call_openai_compatible(
            base_url="https://openrouter.ai/api/v1",
            api_key=settings.OPENROUTER_API_KEY,
            model=model,
            headers_extra=headers_extra
        )

    async def send_message(
        self,
        prompt: str,
        on_fallback: Optional[Callable[[str], Coroutine[Any, Any, None]]] = None
    ) -> str:
        """Sends a message across the 3-tier fallback hierarchy with automatic failover."""
        # Append user turn to universal message log
        self.messages.append({"role": "user", "content": prompt})

        errors: List[str] = []

        # --- TIER 1: Google Gemini ---
        try:
            response_text = await self._call_gemini(prompt)
            self.messages.append({"role": "assistant", "content": response_text})
            return response_text
        except Exception as e:
            err_msg = f"Tier 1 (Gemini: {settings.GEMINI_MODEL}) failed: {e}"
            errors.append(err_msg)
            if on_fallback:
                await on_fallback(f"⚠️ {err_msg} -> Failing over to Tier 2 (Groq)...")

        # --- TIER 2: Groq (openai/gpt-oss-120b) ---
        try:
            response_text = await self._call_groq()
            self.messages.append({"role": "assistant", "content": response_text})
            return response_text
        except Exception as e:
            err_msg = f"Tier 2 (Groq: {settings.GROQ_MODEL}) failed: {e}"
            errors.append(err_msg)
            if on_fallback:
                await on_fallback(f"⚠️ {err_msg} -> Failing over to Tier 3 (OpenRouter)...")

        # --- TIER 3: OpenRouter Free Tier (google/gemma-4-31b-it:free) ---
        try:
            response_text = await self._call_openrouter()
            self.messages.append({"role": "assistant", "content": response_text})
            return response_text
        except Exception as e:
            err_msg = f"Tier 3 (OpenRouter: {settings.OPENROUTER_MODEL}) failed: {e}"
            errors.append(err_msg)

        # All tiers exhausted
        all_errs = "\n - ".join(errors)
        raise RuntimeError(f"All LLM tiers in fallback stack exhausted:\n - {all_errs}")
