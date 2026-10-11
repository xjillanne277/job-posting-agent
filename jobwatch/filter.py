"""
deciding if a posting is worth pinging me about.

two steps:
  1. cheap check: is it even an internship? (meta has ~1000 postings and most
     are full time, no point spending llm calls on those)
  2. ask the llm to score how much the internship would help me grow as a
     product design engineer, based on profile.md
"""

import re

from .llm import ask_gemini, LLMError

INTERN_RE = re.compile(r"\b(intern|internship|co-?op|student)\b", re.I)

# only used if the llm is down, so i still hear about obvious ones
HARDWARE_RE = re.compile(
    r"mechanical|product design|hardware|enclosure|mechanism|thermal|reality labs"
    r"|wearable|ar/vr|prototyp|manufactur|test engineer|reliability",
    re.I,
)

PROMPT = """You are helping me screen Meta internship postings. Here is who I am and what I want:

{profile}

Here is a new posting:

TITLE: {title}
LOCATIONS: {locations}
DESCRIPTION:
{description}

Score this posting from 0 to 10 on how much it would help me grow as a product
design engineer in consumer hardware, given my background. 10 = exactly the kind
of mechanical/product design role on a real device I described, 0 = completely
unrelated. If it isn't actually an internship (or co-op) open to undergrads, score it 0.

Reply with only JSON in this shape:
{{"score": <int 0-10>, "why": "<1-2 sentences on what the role is and why it fits or doesnt>", "growth": "<1 sentence on the specific skill it would build for me, or empty string>"}}
"""


def looks_like_internship(job):
    if INTERN_RE.search(job.title):
        return True
    # some titles dont say intern but the first bit of the description does
    return "internship" in job.description[:600].lower()


def build_prompt(job, profile):
    return PROMPT.format(
        profile=profile.strip(),
        title=job.title,
        locations=", ".join(job.locations) or "not listed",
        description=job.description or "(no description found)",
    )


def keyword_judge(job):
    """backup plan when gemini isnt working"""
    hit = HARDWARE_RE.search(job.title + " " + job.description)
    return {
        "score": 6 if hit else 2,
        "why": "no llm this time (no key or it errored) so this is just a keyword match"
        + (f' (matched "{hit.group(0)}")' if hit else ""),
        "growth": "",
        "used_llm": False,
    }


def judge(job, profile, api_key=None, model="gemini-3.8-flash", session=None):
    if not api_key:
        return keyword_judge(job)
    try:
        out = ask_gemini(build_prompt(job, profile), api_key, model, session=session)
    except LLMError as e:
        # main decides what to do with this (usually: dont ping, retry next run)
        v = keyword_judge(job)
        v["llm_error"] = str(e)
        return v

    # dont fully trust the llm to follow the format
    try:
        score = max(0, min(10, int(out.get("score", 0))))
    except (TypeError, ValueError):
        score = 0
    return {
        "score": score,
        "why": str(out.get("why", "")).strip(),
        "growth": str(out.get("growth", "")).strip(),
        "used_llm": True,
    }
