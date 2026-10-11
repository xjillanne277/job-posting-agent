import unittest
from unittest import mock

from jobwatch.jobpage import Job
from jobwatch.notify import build_job_message, send_job


class NotifyTests(unittest.TestCase):
    def test_message_shape(self):
        j = Job(id="1", url="https://x", title="PDE Intern", locations=["Burlingame, CA"])
        msg = build_job_message(j, {"score": 9, "why": "hinges!!", "growth": "dfm"})
        e = msg["embeds"][0]
        self.assertEqual(e["title"], "PDE Intern")
        self.assertEqual(e["url"], "https://x")
        self.assertEqual([fld["name"] for fld in e["fields"]], ["score", "where", "what i'd learn"])

    def test_skips_empty_fields(self):
        j = Job(id="1", url="https://x", title="PDE Intern")
        msg = build_job_message(j, {"score": 7, "why": "", "growth": ""})
        self.assertEqual([fld["name"] for fld in msg["embeds"][0]["fields"]], ["score"])

    def test_retries_on_rate_limit(self):
        limited = mock.Mock(status_code=429)
        limited.json.return_value = {"retry_after": 0}
        fine = mock.Mock(status_code=204)
        s = mock.Mock()
        s.post.side_effect = [limited, fine]
        send_job(s, "https://hook", Job(id="1", url="u", title="t"), {"score": 7})
        self.assertEqual(s.post.call_count, 2)


if __name__ == "__main__":
    unittest.main()
