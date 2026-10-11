"""
talking to gemini. using it because the free tier is enough for this
(a run only ever judges a handful of postings).

calling the rest api directly with requests instead of the google sdk, one less
dependency and the sdk keeps changing names lol
"""

import json
import os
import re
import time

import requests

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
MODELS_URL = "https://generativelanguage.googleapis.com/v1beta/models"

# google retires models pretty often (gemini-2.5-flash started 404ing on me) and
# the free tier sometimes 503s when its busy. so if the model i asked for is gone
# or overloaded, i ask the api what flash models exist and move down the list.
_resolved = {}   # model i asked for -> model that actually worked
_ranked = None   # cached list of available flash models, best first


class LLMError(Exception):
    pass


class _Unavailable(Exception):
    """this model is gone (404) or overloaded (429/503) -> try a different one"""


def rank_models(available):
    """from model names (like "models/gemini-3-flash"), return the flash ones
    best first: regular flash before lite, stable before preview, newer before older"""
    names = [n.split("/", 1)[-1] for n in available]
    flash = [n for n in names if "flash" in n and not any(
        bad in n for bad in ("image", "tts", "live", "audio", "embedding"))]

    def rank(n):
        nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", n)]
        return ("lite" not in n, "preview" not in n and "exp" not in n, nums)

    return sorted(flash, key=rank, reverse=True)


def pick_model(available):
    ranked = rank_models(available)
    return ranked[0] if ranked else None


def list_models(api_key, session):
    r = session.get(MODELS_URL, headers={"x-goog-api-key": api_key},
                    params={"pageSize": 1000}, timeout=30)
    if not r.ok:
        raise LLMError(f"couldnt list models: {r.status_code} {' '.join(r.text.split())[:200]}")
    return [m["name"] for m in r.json().get("models", [])
            if "generateContent" in m.get("supportedGenerationMethods", [])]


def _notice(msg):
    print(f"::notice::{msg}" if os.environ.get("GITHUB_ACTIONS") == "true" else f"  {msg}")


def _call(prompt, api_key, model, session, retries):
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",  # makes it actually return json
            "temperature": 0.2,
        },
    }
    # key goes in a header not the url so it doesnt end up in logs
    headers = {"x-goog-api-key": api_key}

    err = None
    for attempt in range(retries):
        try:
            r = session.post(GEMINI_URL.format(model=model), json=body, headers=headers, timeout=60)
        except requests.RequestException as e:
            err = e
        else:
            if r.status_code == 404:
                raise _Unavailable(f"{model} 404")
            # 429 = free tier rate limit, 5xx = google having a moment. wait and retry
            if r.status_code == 429 or r.status_code >= 500:
                err = f"{r.status_code}"
            elif not r.ok:
                raise LLMError(f"gemini {r.status_code} on {model}: {' '.join(r.text.split())[:300]}")
            else:
                try:
                    text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                    return json.loads(text)
                except (KeyError, IndexError, ValueError) as e:
                    raise LLMError(f"couldnt read gemini response: {e}") from e
        if attempt < retries - 1:
            time.sleep(5 * (attempt + 1))
    raise _Unavailable(f"{model} kept failing ({err})")


def ask_gemini(prompt, api_key, model, session=None, retries=3, max_models=3):
    """sends the prompt, expects json back, returns it as a dict"""
    global _ranked
    s = session or requests.Session()
    current = _resolved.get(model, model)
    tried = []

    while True:
        try:
            out = _call(prompt, api_key, current, s, retries)
            if current != model and _resolved.get(model) != current:
                _notice(f"using {current} instead of {model}")
            _resolved[model] = current
            return out
        except _Unavailable as e:
            tried.append(current)
            if len(tried) >= max_models:
                raise LLMError(f"tried {', '.join(tried)} and none worked (last: {e})")
            if _ranked is None:
                _ranked = rank_models(list_models(api_key, s))
            options = [m for m in _ranked if m not in tried]
            if not options:
                raise LLMError(f"{e} and no other flash model to try")
            _notice(f"{e}, trying {options[0]}")
            current = options[0]
