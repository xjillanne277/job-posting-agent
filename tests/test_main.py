"""end to end-ish test with a fake meta site so i dont hit the real one"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from jobwatch.__main__ import parse_args, run
from jobwatch.state import load_seen, save_seen

FIX = Path(__file__).parent / "fixtures"
SITEMAP = "https://www.metacareers.com/jobsearch/sitemap.xml"
JOB_A = "https://www.metacareers.com/profile/job_details/1288834486094873/"  # building engineer
JOB_B = "https://www.metacareers.com/profile/job_details/998357492128826/"   # pde intern


class Resp:
    def __init__(self, body, status=200):
        self.content = body if isinstance(body, bytes) else body.encode()
        self.text = self.content.decode()
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(response=self)


class FakeMeta:
    def __init__(self):
        self.headers = {}
        self.pages = {
            SITEMAP: (FIX / "sitemap.xml").read_bytes(),
            JOB_A: (FIX / "job_ogonly.html").read_text(),
            JOB_B: (FIX / "job_ldjson.html").read_text(),
        }
        self.opened = []
        self.posts = []

    def get(self, url, timeout=None, headers=None):
        self.opened.append(url)
        return Resp(self.pages[url])

    def post(self, url, **kw):
        self.posts.append((url, kw))
        return Resp(b"", 204)


class MainTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name) / "seen.json"
        env = {"DISCORD_WEBHOOK_URL": "https://hook", "GEMINI_API_KEY": "", "MIN_SCORE": "6"}
        self.env = mock.patch.dict(os.environ, env)
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def args(self, *extra):
        return parse_args(["--state", str(self.state), "--delay", "0", *extra])

    def test_first_run_just_remembers_everything(self):
        site = FakeMeta()
        stats = run(self.args(), session=site)
        self.assertEqual(stats["seeded"], 2)
        self.assertEqual(set(load_seen(self.state)), {"1288834486094873", "998357492128826"})
        self.assertEqual(site.opened, [SITEMAP])  # didnt open any job pages
        self.assertEqual(len(site.posts), 1)       # just the "im set up" message

    def test_new_internship_gets_pinged(self):
        save_seen(self.state, {"1288834486094873": "x"})  # only the building engineer seen
        site = FakeMeta()
        stats = run(self.args(), session=site)
        self.assertEqual(stats["new"], 1)
        self.assertEqual(stats["pinged"], 1)
        embed = site.posts[0][1]["json"]["embeds"][0]
        self.assertEqual(embed["title"], "Product Design Engineer Intern")
        self.assertIn("998357492128826", load_seen(self.state))

    def test_nothing_new_nothing_pinged(self):
        save_seen(self.state, {"1288834486094873": "x", "998357492128826": "x"})
        site = FakeMeta()
        stats = run(self.args(), session=site)
        self.assertEqual(stats["pinged"], 0)
        self.assertEqual(site.posts, [])

    def test_backfill_checks_existing(self):
        site = FakeMeta()
        stats = run(self.args("--backfill"), session=site)
        self.assertEqual(stats["opened"], 2)
        self.assertEqual(stats["internships"], 1)
        self.assertEqual(stats["pinged"], 1)

    def test_failed_page_retried_next_time(self):
        save_seen(self.state, {"1288834486094873": "x"})
        site = FakeMeta()
        site.get = lambda url, timeout=None, headers=None: Resp(site.pages[SITEMAP]) if url == SITEMAP else Resp(b"", 500)
        stats = run(self.args(), session=site)
        self.assertEqual(stats["errors"], 1)
        self.assertNotIn("998357492128826", load_seen(self.state))

    def test_dry_run_doesnt_post(self):
        save_seen(self.state, {"1288834486094873": "x"})
        site = FakeMeta()
        stats = run(self.args("--dry-run"), session=site)
        self.assertEqual(stats["pinged"], 1)
        self.assertEqual(site.posts, [])


if __name__ == "__main__":
    unittest.main()
