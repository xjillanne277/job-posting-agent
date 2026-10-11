import tempfile
import unittest
from pathlib import Path

from jobwatch.sitemap import parse_sitemap, job_id_from_url, fetch_job_ids
from jobwatch.state import load_seen, save_seen

FIX = Path(__file__).parent / "fixtures"


class FakeResp:
    def __init__(self, content):
        self.content = content

    def raise_for_status(self):
        pass


class FakeSession:
    """pretends to be requests.Session, serves files from fixtures/"""

    def __init__(self, pages):
        self.pages = pages

    def get(self, url, timeout=None):
        return FakeResp(self.pages[url])


class SitemapTests(unittest.TestCase):
    def test_parses_job_urls(self):
        jobs, children = parse_sitemap((FIX / "sitemap.xml").read_bytes())
        self.assertEqual(len(jobs), 3)
        self.assertEqual(children, [])

    def test_index_returns_children(self):
        jobs, children = parse_sitemap((FIX / "sitemap_index.xml").read_bytes())
        self.assertEqual(jobs, [])
        self.assertEqual(children, ["https://www.metacareers.com/jobsearch/sitemap-1.xml"])

    def test_job_id(self):
        url = "https://www.metacareers.com/profile/job_details/1288834486094873/"
        self.assertEqual(job_id_from_url(url), "1288834486094873")
        self.assertIsNone(job_id_from_url("https://www.metacareers.com/some/other/page/"))

    def test_fetch_follows_index(self):
        s = FakeSession({
            "https://index": (FIX / "sitemap_index.xml").read_bytes(),
            "https://www.metacareers.com/jobsearch/sitemap-1.xml": (FIX / "sitemap.xml").read_bytes(),
        })
        jobs = fetch_job_ids(s, "https://index")
        # the non-job link should get dropped
        self.assertEqual(set(jobs), {"1288834486094873", "998357492128826"})


class StateTests(unittest.TestCase):
    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "sub" / "seen.json"
            self.assertIsNone(load_seen(p))
            save_seen(p, {"123": "2026-10-11"})
            self.assertEqual(load_seen(p), {"123": "2026-10-11"})


if __name__ == "__main__":
    unittest.main()
