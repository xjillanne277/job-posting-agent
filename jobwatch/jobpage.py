"""
pulling the useful stuff (title, description, location) out of a single job page.

meta's job pages are mostly react, so i try a few things in order of how
reliable they are:
  1. json-ld JobPosting data (structured, best case)
  2. og:title / og:description meta tags (always seem to be there)
  3. whatever visible text is in the html as a last resort
"""

import html
import json
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser

from .fetch import get

SKIP_TAGS = {"style", "noscript", "svg"}
MAX_DESC_CHARS = 6000  # dont need to send the llm a novel


@dataclass
class Job:
    id: str
    url: str
    title: str = ""
    description: str = ""
    locations: list = field(default_factory=list)


class _PageReader(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta = {}
        self.ld_blobs = []
        self.text = []
        self._in_ld = False
        self._ld_buf = []
        self._skip = 0  # >0 means im inside a script/style tag

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "meta":
            key = a.get("property") or a.get("name")
            if key and a.get("content") and key not in self.meta:
                self.meta[key] = a["content"]
        elif tag == "script":
            if (a.get("type") or "").lower() == "application/ld+json":
                self._in_ld = True
                self._ld_buf = []
            else:
                self._skip += 1
        elif tag in SKIP_TAGS:
            self._skip += 1

    def handle_endtag(self, tag):
        if tag == "script":
            if self._in_ld:
                self.ld_blobs.append("".join(self._ld_buf))
                self._in_ld = False
            elif self._skip:
                self._skip -= 1
        elif tag in SKIP_TAGS and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if self._in_ld:
            self._ld_buf.append(data)
        elif not self._skip:
            t = data.strip()
            if t:
                self.text.append(t)


def strip_html(s):
    """job descriptions in json-ld are html, turn them into plain text"""
    s = re.sub(r"<br\s*/?>|</p>|</li>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in s.splitlines()]
    return "\n".join(line for line in lines if line)


def _find_jobposting(blob):
    """json-ld can be a dict, a list, or have an @graph... dig for the JobPosting"""
    if isinstance(blob, list):
        for item in blob:
            found = _find_jobposting(item)
            if found:
                return found
    elif isinstance(blob, dict):
        t = blob.get("@type")
        if t == "JobPosting" or (isinstance(t, list) and "JobPosting" in t):
            return blob
        if "@graph" in blob:
            return _find_jobposting(blob["@graph"])
    return None


def _locations_from_ld(jp):
    locs = jp.get("jobLocation") or []
    if isinstance(locs, dict):
        locs = [locs]
    out = []
    for loc in locs:
        addr = loc.get("address", {}) if isinstance(loc, dict) else {}
        if isinstance(addr, str):
            out.append(addr)
            continue
        parts = [addr.get(k) for k in ("addressLocality", "addressRegion", "addressCountry")]
        # addressCountry is sometimes {"name": "US"} instead of just "US"
        parts = [p.get("name") if isinstance(p, dict) else p for p in parts]
        parts = [p for p in parts if p]
        if parts:
            out.append(", ".join(parts))
    return out


def clean_title(t):
    t = html.unescape(t or "").strip()
    return re.sub(r"\s*[|\-–]\s*Meta Careers\s*$", "", t, flags=re.I)


def parse_job_page(job_id, url, page_html):
    r = _PageReader()
    r.feed(page_html)
    job = Job(id=job_id, url=url)

    # 1. structured data
    for blob in r.ld_blobs:
        try:
            jp = _find_jobposting(json.loads(blob))
        except json.JSONDecodeError:
            continue
        if jp:
            job.title = clean_title(jp.get("title", ""))
            job.description = strip_html(jp.get("description", ""))
            job.locations = _locations_from_ld(jp)
            break

    # 2. meta tags
    if not job.title:
        job.title = clean_title(r.meta.get("og:title") or r.meta.get("twitter:title") or "")
    if not job.description:
        job.description = html.unescape(
            r.meta.get("og:description") or r.meta.get("description") or ""
        ).strip()

    # 3. if the description is basically empty, throw in the page text so the
    # llm at least has something to go off of
    if len(job.description) < 200 and r.text:
        job.description = (job.description + "\n" + "\n".join(r.text)).strip()

    job.description = job.description[:MAX_DESC_CHARS]
    return job


def fetch_job(session, job_id, url):
    resp = get(session, url)
    resp.raise_for_status()
    return parse_job_page(job_id, url, resp.text)
