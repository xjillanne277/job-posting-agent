"""
remembering which postings ive already looked at (just a json file).
format is {job_id: "when i first saw it"}
"""

import json
import os
from pathlib import Path


def load_seen(path):
    """returns None if theres no file yet (aka first run) so main can tell
    the difference between 'never ran' and 'ran but saw nothing'"""
    p = Path(path)
    if not p.exists():
        return None
    with p.open() as f:
        return json.load(f)


def save_seen(path, seen):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    # write to a temp file then swap it in so a crash halfway through
    # doesnt leave me with a broken json file and a ton of duplicate pings
    tmp = p.with_suffix(".tmp")
    with tmp.open("w") as f:
        json.dump(seen, f, indent=1, sort_keys=True)
    os.replace(tmp, p)
