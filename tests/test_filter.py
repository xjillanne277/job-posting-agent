import json
import unittest
from unittest import mock

from jobwatch import filter as f
from jobwatch.jobpage import Job
from jobwatch.llm import LLMError


def job(title, desc=""):
    return Job(id="1", url="u", title=title, description=desc, locations=["Burlingame, CA"])


class FakeResp:
    def __init__(self, status, payload):
        self.status_code = status
        self.ok = status < 400
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


def gemini_says(obj):
    return FakeResp(200, {"candidates": [{"content": {"parts": [{"text": json.dumps(obj)}]}}]})


class FilterTests(unittest.TestCase):
    def test_internship_check(self):
        self.assertTrue(f.looks_like_internship(job("Mechanical Engineer Intern")))
        self.assertTrue(f.looks_like_internship(job("Product Design Engineer, Co-op")))
        self.assertTrue(f.looks_like_internship(job("Hardware Engineer", "This is a 12 week internship")))
        self.assertFalse(f.looks_like_internship(job("Lead Building Engineer", "facilities")))
        # "international" shouldnt count as intern lol
        self.assertFalse(f.looks_like_internship(job("International Tax Manager")))

    def test_prompt_has_everything(self):
        p = f.build_prompt(job("PDE Intern", "design hinges"), "i like hinges")
        self.assertIn("i like hinges", p)
        self.assertIn("PDE Intern", p)
        self.assertIn("design hinges", p)
        self.assertIn("Burlingame", p)

    def test_no_key_uses_keywords(self):
        v = f.judge(job("Mechanical Engineer Intern"), "profile", api_key=None)
        self.assertEqual(v["score"], 6)
        self.assertFalse(v["used_llm"])
        v = f.judge(job("Marketing Intern"), "profile", api_key=None)
        self.assertEqual(v["score"], 2)

    def test_llm_answer_gets_clamped(self):
        s = mock.Mock()
        s.post.return_value = gemini_says({"score": 42, "why": "great fit", "growth": "dfm"})
        v = f.judge(job("PDE Intern"), "profile", api_key="k", session=s)
        self.assertEqual(v["score"], 10)
        self.assertEqual(v["why"], "great fit")
        self.assertTrue(v["used_llm"])
        # make sure the key went in the header, not the url
        _, kwargs = s.post.call_args
        self.assertEqual(kwargs["headers"]["x-goog-api-key"], "k")

    def test_pick_model(self):
        from jobwatch.llm import pick_model
        models = ["models/gemini-2.0-flash", "models/gemini-3-flash", "models/gemini-3-flash-lite",
                  "models/gemini-3-pro", "models/gemini-3-flash-image", "models/gemini-3.5-flash-preview"]
        self.assertEqual(pick_model(models), "gemini-3-flash")
        self.assertIsNone(pick_model(["models/gemini-3-pro"]))

    def test_404_switches_model(self):
        from jobwatch import llm
        llm._resolved.clear()
        s = mock.Mock()
        s.post.side_effect = [FakeResp(404, {"error": "not found"}), gemini_says({"score": 8, "why": "ok", "growth": ""})]
        s.get.return_value = FakeResp(200, {"models": [
            {"name": "models/gemini-3-flash", "supportedGenerationMethods": ["generateContent"]}]})
        v = f.judge(job("PDE Intern"), "profile", api_key="k", model="gemini-2.5-flash", session=s)
        self.assertEqual(v["score"], 8)
        self.assertIn("gemini-3-flash:generateContent", s.post.call_args[0][0])
        llm._resolved.clear()

    def test_llm_failure_falls_back(self):
        with mock.patch.object(f, "ask_gemini", side_effect=LLMError("nope")):
            v = f.judge(job("Mechanical Engineer Intern"), "profile", api_key="k")
        self.assertFalse(v["used_llm"])
        self.assertEqual(v["score"], 6)


if __name__ == "__main__":
    unittest.main()
