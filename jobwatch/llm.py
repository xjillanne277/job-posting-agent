"""
talking to gemini. using it because the free tier is enough for this
(a run only ever judges a handful of postings).

calling the rest api directly with requests instead of the google sdk, one less
dependency and the sdk keeps changing names lol
"""

import json
import time

import requests

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class LLMError(Exception):
    pass


def ask_gemini(prompt, api_key, model, session=None, retries=3):
    """sends the prompt, expects json back, returns it as a dict"""
    s = session or requests.Session()
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
            elif not r.ok:
                raise LLMError(f"gemini {r.status_code}: {r.text[:300]}")
            else:
                try:
                    text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                    return json.loads(text)
                except (KeyError, IndexError, ValueError) as e:
                    raise LLMError(f"couldnt read gemini response: {e}") from e
        time.sleep(5 * (attempt + 1))

    raise LLMError(f"gave up after {retries} tries ({err})")
