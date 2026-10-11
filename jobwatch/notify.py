"""
discord pings. a webhook is just a url you POST json to, no bot setup needed.
if the discord app is on my phone i get a push notification too
"""

import time

META_BLUE = 0x0866FF


def _post(session, webhook, payload):
    r = session.post(webhook, json=payload, timeout=20)
    if r.status_code == 429:
        # discord tells you how long to chill for
        try:
            wait = float(r.json().get("retry_after", 2))
        except ValueError:
            wait = 2
        time.sleep(min(wait, 30))
        r = session.post(webhook, json=payload, timeout=20)
    r.raise_for_status()


def send_text(session, webhook, message):
    _post(session, webhook, {"content": message[:2000]})


def build_job_message(job, verdict):
    fields = [{"name": "score", "value": f"{verdict['score']}/10", "inline": True}]
    if job.locations:
        fields.append({"name": "where", "value": ", ".join(job.locations)[:1000], "inline": True})
    # discord rejects empty field values so only add this if theres something
    if verdict.get("growth"):
        fields.append({"name": "what i'd learn", "value": verdict["growth"][:1000]})

    embed = {
        "title": (job.title or "untitled posting")[:256],
        "url": job.url,
        "description": (verdict.get("why") or "")[:2000],
        "color": META_BLUE,
        "fields": fields,
    }
    return {"content": "🚨 new meta internship that looks relevant, go apply!!", "embeds": [embed]}


def send_job(session, webhook, job, verdict):
    _post(session, webhook, build_job_message(job, verdict))
