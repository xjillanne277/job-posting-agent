"""
the actual loop:  python -m jobwatch

  sitemap -> new job ids -> fetch each page -> is it an internship?
  -> llm scores it -> ping me on discord if its a good fit

settings come from env vars so i can keep secrets out of the repo:
  DISCORD_WEBHOOK_URL   where pings go (if missing it just prints)
  GEMINI_API_KEY        for scoring (if missing it falls back to keywords)
  GEMINI_MODEL          default gemini-2.5-flash
  MIN_SCORE             only ping at or above this, default 6
"""

import argparse
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from .filter import judge, looks_like_internship
from .jobpage import fetch_job
from .notify import send_job, send_text
from .sitemap import fetch_job_ids
from .state import load_seen, save_seen

ROOT = Path(__file__).resolve().parent.parent

def parse_args(argv=None):
    p = argparse.ArgumentParser(description="ping me about relevant meta internships")
    p.add_argument("--state", default=str(ROOT / "data" / "seen.json"))
    p.add_argument("--profile", default=str(ROOT / "profile.md"))
    p.add_argument("--backfill", action="store_true",
                   help="also go back through postings that were already up. it does --max-pages per "
                        "run and keeps going on the scheduled runs until its checked everything")
    p.add_argument("--max-pages", type=int, default=150,
                   help="max job pages to open per run so i dont hammer their site")
    p.add_argument("--max-llm", type=int, default=40, help="max llm calls per run (free tier limits)")
    p.add_argument("--delay", type=float, default=1.0, help="seconds between page requests")
    p.add_argument("--llm-delay", type=float, default=4.0,
                   help="seconds between llm calls, free tier only allows a few per minute")
    p.add_argument("--dry-run", action="store_true", help="print instead of sending to discord")
    p.add_argument("--test-ping", action="store_true", help="just send a test message to discord and quit")
    return p.parse_args(argv)


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run(args, session=None):
    # headers are handled per request in fetch.py
    s = session or requests.Session()

    webhook = None if args.dry_run else os.environ.get("DISCORD_WEBHOOK_URL")
    api_key = os.environ.get("GEMINI_API_KEY")
    model = os.environ.get("GEMINI_MODEL") or "gemini-2.5-flash"
    min_score = int(os.environ.get("MIN_SCORE") or 6)

    def say(msg):
        print(msg)
        if webhook:
            send_text(s, webhook, msg)

    if args.test_ping:
        if not webhook:
            sys.exit("no DISCORD_WEBHOOK_URL set, nothing to ping")
        send_text(s, webhook, "test ping from job-posting-agent 👋 if you see this its working")
        return {"pinged": 0}

    if not api_key:
        print("no GEMINI_API_KEY, using keyword matching instead of the llm")

    profile = Path(args.profile).read_text()
    current = fetch_job_ids(s)
    if not current:
        # if this happens meta probably changed their sitemap and i need to fix stuff
        raise SystemExit("sitemap had 0 jobs in it?? something changed on meta's end")
    print(f"{len(current)} postings on the sitemap")

    state_dir = Path(args.state).parent
    checked_path = state_dir / "checked.json"      # ids whose page i actually opened + judged
    backfill_flag = state_dir / "backfill_pending"  # exists while a backfill is still going

    seen = load_seen(args.state)
    first_run = seen is None
    seen = seen or {}
    checked = load_seen(checked_path) or {}

    if args.backfill and not backfill_flag.exists():
        state_dir.mkdir(parents=True, exist_ok=True)
        backfill_flag.touch()
        say(f"starting a backfill, going through postings that were already up "
            f"({args.max_pages} per run, so it'll take a few runs) 🔍")
    backfilling = backfill_flag.exists()

    # first run: theres ~1000 postings already up and i dont want 1000 pings,
    # so just remember them all. from then on only new ones get checked
    if first_run and not backfilling:
        stamp = now()
        for jid in current:
            seen[jid] = stamp
        save_seen(args.state, seen)
        say(f"job-posting-agent is set up 👀 watching {len(current)} meta postings, "
            f"i'll ping you when a relevant internship goes up")
        return {"pinged": 0, "new": 0, "seeded": len(current)}

    new_ids = [jid for jid in current if jid not in seen]
    print(f"{len(new_ids)} new since last time")

    # new stuff goes first, then the old postings ive never actually looked at
    queue = list(new_ids)
    if backfilling:
        old_unchecked = [jid for jid in current if jid in seen and jid not in checked]
        print(f"backfill: {len(old_unchecked)} older postings left to check")
        queue += old_unchecked

    stats = {"new": len(new_ids), "queued": len(queue), "opened": 0, "internships": 0, "judged": 0, "pinged": 0, "errors": 0}
    llm_calls = 0

    try:
        for jid in queue:
            if stats["opened"] >= args.max_pages:
                print("hit --max-pages, the rest will get checked next run")
                break

            url = current[jid]
            try:
                job = fetch_job(s, jid, url)
            except requests.HTTPError as e:
                if e.response is not None and e.response.status_code == 404:
                    seen[jid] = checked[jid] = now()  # posting already gone, skip it forever
                else:
                    print(f"  couldnt load {url}: {e}")  # try again next run
                    stats["errors"] += 1
                continue
            except requests.RequestException as e:
                print(f"  couldnt load {url}: {e}")
                stats["errors"] += 1
                continue
            finally:
                stats["opened"] += 1
                time.sleep(args.delay)

            if not job.title:
                print(f"  no title found for {url}, page layout might have changed")

            if not looks_like_internship(job):
                seen[jid] = checked[jid] = now()
                continue
            stats["internships"] += 1

            if api_key and llm_calls >= args.max_llm:
                # dont mark as seen, itll get judged next run
                print("hit --max-llm, leaving the rest for next run")
                break

            verdict = judge(job, profile, api_key=api_key, model=model, session=s)
            if verdict.get("used_llm"):
                llm_calls += 1
                time.sleep(args.llm_delay)
            stats["judged"] += 1
            print(f"  [{verdict['score']}/10] {job.title} -- {verdict['why']}")

            if verdict["score"] >= min_score:
                if webhook:
                    send_job(s, webhook, job, verdict)
                else:
                    print(f"  >>> would ping: {job.title} {job.url}")
                stats["pinged"] += 1

            seen[jid] = checked[jid] = now()
    finally:
        # save even if something crashes so i dont get double pinged next run
        save_seen(args.state, seen)
        save_seen(checked_path, checked)

    if backfilling and all(jid in checked for jid in current):
        backfill_flag.unlink()
        say("backfill done ✅ went through every posting that was already up, "
            "back to just checking new ones")

    print("done:", ", ".join(f"{k}={v}" for k, v in stats.items()))
    return stats


def main(argv=None):
    run(parse_args(argv))


if __name__ == "__main__":
    main()
