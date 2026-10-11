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

# google renames/retires models pretty often (gemini-2.5-flash started 404ing on me),
# so if the configured one isnt found i ask the api what models exist and pick a flash one
_resolved = {}


class LLMError(Exception):
    pass


def pick_model(available):
    """from a list of model names (like "models/gemini-3-flash"), pick the best
    flash model for this. prefers regular flash over lite, and newer over older"""
    names = [n.split("/", 1)[-1] for n in available]
    flash = [n for n in names if "flash" in n and "image" not in n and "tts" not in n
             and "live" not in n and "audio" not in n]
    if not flash:
        return None
    # non-lite first, then non-preview, then highest version number
    def rank(n):
        nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", n)]
        return ("lite" not in n, "preview" not in n and "exp" not in n, nums)
    return max(flash, key=rank)


def list_models(api_key, session):
    r = session.get(MODELS_URL, headers={"x-goog-api-key": api_key},
                    params={"pageSize": 1000}, timeout=30)
    if not r.ok:
        raise LLMError(f"couldnt list models: {r.status_code} {r.text[:200]}")
    return [m["name"] for m in r.json().get("models", [])
            if "generateContent" in m.get("supportedGenerationMethods", [])]


def ask_gemini(prompt, api_key, model, session=None, retries=3):
    """sends the prompt, expects json back, returns it as a dict"""
    s = session or requests.Session()
    model = _resolved.get(model, model)
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",  # makes it actually return json
            "temperature": 0.2,
        },
    }
    # key goes in a header not the url so it doesnt end up in logs
    headers = {"x-goog-api-key": api_key}

    for attempt in range(retries):
        try:
            r = s.post(GEMINI_URL.format(model=model), json=body, headers=headers, timeout=60)
        except requests.RequestException as e:
            err = e
        else:
            # 429 = free tier rate limit, 5xx = google having a moment. wait and retry
            if r.status_code == 429 or r.status_code >= 500:
                err = LLMError(f"gemini {r.status_code}")
            elif r.status_code == 404 and model not in _resolved.values():
                new = pick_model(list_models(api_key, s))
                if not new or new == model:
                    raise LLMError(f"model {model} not found and no flash model to switch to")
                msg = f"{model} isnt available anymore, switching to {new}"
                print(f"::notice::{msg}" if os.environ.get("GITHUB_ACTIONS") == "true" else f"  {msg}")
                _resolved[model] = new
                return ask_gemini(prompt, api_key, model, session=s, retries=retries)
            elif not r.ok:
                raise LLMError(f"gemini {r.status_code} on {model}: {' '.join(r.text.split())[:300]}")
            else:
                try:
                    text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                    return json.loads(text)
                except (KeyError, IndexError, ValueError) as e:
                    raise LLMError(f"couldnt read gemini response: {e}") from e
        time.sleep(5 * (attempt + 1))

    raise LLMError(f"gave up after {retries} tries ({err})")
