"""
getting the list of every posting on meta careers.

the search page on metacareers is all javascript (graphql calls with tokens that
change), so scraping it is a pain. BUT they publish a sitemap with a link to every
job page, which is way more stable. so the plan is: grab the sitemap, pull out the
job ids, and anything i havent seen before is a new posting.
"""

import re
import xml.etree.ElementTree as ET

from .fetch import get

SITEMAP_URL = "https://www.metacareers.com/jobsearch/sitemap.xml"

# job links look like .../profile/job_details/1288834486094873/
JOB_ID_RE = re.compile(r"/job_details/(\d+)")


def _tag(el):
    # xml tags come back with the namespace stuck on the front, ex
    # {http://www.sitemaps.org/schemas/sitemap/0.9}loc  -> just want "loc"
    return el.tag.rsplit("}", 1)[-1]


def parse_sitemap(xml_bytes):
    """returns (job_urls, child_sitemap_urls)

    a sitemap can either be a normal list of pages OR an index that points to
    more sitemaps. right now meta's is a normal one but i handle both in case
    they split it up later when there are more jobs
    """
    root = ET.fromstring(xml_bytes)
    locs = [el.text.strip() for el in root.iter() if _tag(el) == "loc" and el.text]

    if _tag(root) == "sitemapindex":
        return [], locs
    return locs, []


def job_id_from_url(url):
    m = JOB_ID_RE.search(url)
    return m.group(1) if m else None


def fetch_job_ids(session, url=SITEMAP_URL, _depth=0):
    """{job_id: job_url} for every posting currently listed"""
    resp = get(session, url)
    resp.raise_for_status()

    job_urls, children = parse_sitemap(resp.content)

    jobs = {}
    for u in job_urls:
        jid = job_id_from_url(u)
        if jid:
            jobs[jid] = u

    # only go a couple levels deep, dont want to accidentally loop forever
    if _depth < 2:
        for child in children:
            jobs.update(fetch_job_ids(session, child, _depth + 1))

    return jobs
