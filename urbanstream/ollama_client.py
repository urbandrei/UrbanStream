import httpx

from urbanstream.llm_config import (
    OLLAMA_BASE_URL, OLLAMA_FAST_MODEL, OLLAMA_BIG_MODEL, OLLAMA_EMBED_MODEL,
)


class OllamaClient:
    def __init__(self, base_url=None, fast_model=None, big_model=None,
                 embed_model=None):
        self.base_url = (base_url or OLLAMA_BASE_URL).rstrip("/")
        self.fast_model = fast_model or OLLAMA_FAST_MODEL
        self.big_model = big_model or OLLAMA_BIG_MODEL
        self.embed_model = embed_model or OLLAMA_EMBED_MODEL
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=120.0)

    # ── core methods (explicit model) ───────────────────

    async def generate(self, prompt, system=None, max_tokens=None, model=None):
        model = model or self.fast_model
        payload = {"model": model, "prompt": prompt, "stream": False}
        if system:
            payload["system"] = system
        if max_tokens:
            payload["options"] = {"num_predict": max_tokens}
        resp = await self._client.post("/api/generate", json=payload)
        resp.raise_for_status()
        return resp.json()["response"]

    async def chat(self, messages, max_tokens=None, model=None):
        model = model or self.fast_model
        payload = {"model": model, "messages": messages, "stream": False}
        if max_tokens:
            payload["options"] = {"num_predict": max_tokens}
        resp = await self._client.post("/api/chat", json=payload)
        resp.raise_for_status()
        return resp.json()["message"]["content"]

    # ── convenience wrappers ────────────────────────────

    async def generate_fast(self, prompt, **kwargs):
        return await self.generate(prompt, model=self.fast_model, **kwargs)

    async def generate_big(self, prompt, **kwargs):
        return await self.generate(prompt, model=self.big_model, **kwargs)

    async def chat_fast(self, messages, **kwargs):
        return await self.chat(messages, model=self.fast_model, **kwargs)

    async def chat_big(self, messages, **kwargs):
        return await self.chat(messages, model=self.big_model, **kwargs)

    # ── embeddings ──────────────────────────────────────

    async def embed(self, text):
        resp = await self._client.post(
            "/api/embed", json={"model": self.embed_model, "input": text}
        )
        resp.raise_for_status()
        return resp.json()["embeddings"][0]

    async def embed_batch(self, texts):
        resp = await self._client.post(
            "/api/embed", json={"model": self.embed_model, "input": texts}
        )
        resp.raise_for_status()
        return resp.json()["embeddings"]

    # ── health ──────────────────────────────────────────

    async def health_check(self):
        try:
            resp = await self._client.get("/api/tags")
            resp.raise_for_status()
            models = [m["name"] for m in resp.json().get("models", [])]
            return True, models
        except Exception as e:
            return False, str(e)

    async def close(self):
        await self._client.aclose()
