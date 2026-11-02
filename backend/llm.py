"""Model access (any OpenAI-compatible /chat/completions endpoint). Never logs or returns the API key."""
import httpx
from . import config


class LLMError(Exception):
    """A user-presentable failure from the model provider."""


def complete(system: str, user: str, temperature: float = 0.0, json_mode: bool = False) -> str:
    s = config.llm_settings()
    if not (s["base_url"] and s["model"]):
        raise LLMError("No model configured. Set LLM_BASE_URL and LLM_MODEL (and LLM_API_KEY if your provider needs one) in .env.")
    payload = {
        "model": s["model"], "temperature": temperature, "max_tokens": s["max_tokens"],
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    headers = {"Authorization": "Bearer " + s["api_key"]} if s["api_key"] else {}
    last = "unknown error"
    for _ in range(config.LLM_RETRIES + 1):
        try:
            r = httpx.post(s["base_url"] + "/chat/completions", headers=headers, json=payload, timeout=config.LLM_TIMEOUT_SECONDS)
            if r.status_code >= 400:
                last = f"provider returned HTTP {r.status_code}"
                if r.status_code < 500 and r.status_code != 429:
                    break
                continue
            return r.json()["choices"][0]["message"]["content"].strip()
        except httpx.TimeoutException:
            last = f"request timed out after {config.LLM_TIMEOUT_SECONDS}s"
        except httpx.HTTPError as exc:
            last = f"network error ({type(exc).__name__}); is the model server running at {s['base_url']}?"
        except (KeyError, IndexError, ValueError):
            last = "unexpected response shape from provider"
            break
    raise LLMError(f"LLM call failed: {last}")
