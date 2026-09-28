import time

from openai import OpenAI

from ..config import settings

_client: OpenAI | None = None
_probe: OpenAI | None = None
_last_check = 0.0
_last_result = False


def client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(base_url=settings.llm_base_url, api_key=settings.llm_api_key, timeout=120, max_retries=0)
    return _client


def _probe_client() -> OpenAI:
    global _probe
    if _probe is None:
        # short timeout + no proxy/env detection - the probe must never hang requests.
        # (trust_env moved into the httpx client: the OpenAI 3.x SDK dropped the kwarg)
        import httpx

        _probe = OpenAI(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            max_retries=0,
            http_client=httpx.Client(timeout=2.0, trust_env=False),
        )
    return _probe


def available() -> bool:
    global _last_check, _last_result
    now = time.time()
    if now - _last_check < 60:
        return _last_result
    try:
        _probe_client().models.list()
        _last_result = True
    except Exception:
        _last_result = False
    _last_check = now
    return _last_result


def chat(prompt: str, system: str = "You are an assistant for Coal India Limited (CMPDI) geological and mining reporting.", max_tokens: int = 1024) -> str:
    # Qwen3 thinking-mode soft switch: keep answers direct and low-latency
    # (extraction JSON, cited RAG answers, report summaries). Harmless for other models.
    if "/no_think" not in prompt:
        prompt = prompt + " /no_think"
    resp = client().chat.completions.create(
        model=settings.llm_model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        max_tokens=max_tokens,
        temperature=0.2,
    )
    return resp.choices[0].message.content or ""


def chat_stream(prompt: str, system: str = "You are an assistant for Coal India Limited (CMPDI) geological and mining reporting.", max_tokens: int = 1024):
    """Yield answer text incrementally (SSE-friendly). Same switch + params as chat()."""
    if "/no_think" not in prompt:
        prompt = prompt + " /no_think"
    stream = client().chat.completions.create(
        model=settings.llm_model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        max_tokens=max_tokens,
        temperature=0.2,
        stream=True,
    )
    for chunk in stream:
        delta = chunk.choices[0].delta.content if chunk.choices else None
        if delta:
            yield delta
