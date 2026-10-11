# job-posting-agent

checks meta careers for new internship postings and pings me on discord when one
actually fits what i want to do (product design engineering on consumer hardware).
the goal is to apply in the first few hours instead of finding out a week later 🫠

## how it works

```
meta careers sitemap  ->  any job ids i haven't seen?  ->  open those job pages
   ->  is it an internship?  ->  gemini scores it 0-10 against profile.md
   ->  score >= 6  ->  discord ping (shows up on my phone)
```

- **finding new postings:** the metacareers search page is all javascript, but they
  publish a sitemap with every job link in it. i diff that against a list of ids
  i've already seen.
- **filtering:** most of meta's postings are full time, so a quick regex check
  for intern/co-op first, then the llm only looks at internships. it gets
  [`profile.md`](profile.md) (my background + what i want to grow in) and scores how much the
  role would actually help me grow. if gemini is down it falls back to keyword
  matching so i don't miss anything obvious.
- **pings:** discord webhook with the title, link, score, and why it's a fit.
- **scheduling:** github actions runs it every 3 hours. the seen-jobs list is kept
  in the actions cache so nothing gets committed back to the repo.

```
jobwatch/
  sitemap.py   get every job id off the sitemap
  jobpage.py   pull title / description / location out of a job page
  filter.py    internship check + llm scoring
  llm.py       gemini api call
  notify.py    discord webhook
  state.py     remember what i've seen
  __main__.py  ties it all together
profile.md     what i'm looking for (edit this!)
```

## setup

1. **discord webhook:** in a server you own, go to channel settings -> integrations ->
   webhooks -> new webhook -> copy url. set that channel's notifications to
   "all messages" so your phone actually buzzes.
2. **gemini key:** make one at [aistudio.google.com](https://aistudio.google.com/apikey).
   the free tier is plenty for this.
3. **repo secrets:** settings -> secrets and variables -> actions -> add
   `DISCORD_WEBHOOK_URL` and `GEMINI_API_KEY`.
   optional *variables* (not secrets): `MIN_SCORE` (default 6), `GEMINI_MODEL`
   (default `gemini-3.8-flash`, it switches to another flash model on its own if that one's gone or overloaded).
4. **test it:** actions tab -> "check meta internships" -> run workflow -> tick
   `test_ping`. you should get a discord message.
5. **first real run:** run it again with nothing ticked. the first run just remembers
   everything that's already posted (so i don't get 1000 pings), and every run after
   that only looks at new stuff.
6. **backfill (optional):** run it with `backfill` ticked to go back through the
   postings that were already up. it does 150 pages per run and keeps going on the
   scheduled runs until it's done, then messages you that it finished.

## running locally

```bash
pip install -r requirements.txt
export DISCORD_WEBHOOK_URL=...   # optional, prints instead if missing
export GEMINI_API_KEY=...        # optional, uses keywords instead if missing
python -m jobwatch --dry-run     # see what it would ping without sending anything
python -m unittest               # tests use saved fake pages, they don't hit meta
```

## notes / things i learned

- github turns off scheduled workflows on public repos after 60 days with no
  commits, so if pings stop coming that's probably why (just re-enable it in the actions tab).
- if meta changes their sitemap or page layout this will break. the run fails loudly
  if the sitemap comes back empty, and logs it if a page has no title.
- it waits 1s between page loads and caps how many it opens per run so it's not
  hammering their site.

stuff that helped me figure out how to build this: a bunch of open source job
scraper projects on github, anthropic's agent demos, and the clawdbot creator's
talk at yc startup school.
