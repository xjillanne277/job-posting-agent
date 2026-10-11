import unittest
from pathlib import Path

from jobwatch.jobpage import parse_job_page, clean_title, strip_html

FIX = Path(__file__).parent / "fixtures"


class JobPageTests(unittest.TestCase):
    def test_ldjson(self):
        job = parse_job_page("1", "u", (FIX / "job_ldjson.html").read_text())
        self.assertEqual(job.title, "Product Design Engineer Intern")
        self.assertIn("Design mechanisms and enclosures", job.description)
        self.assertNotIn("<li>", job.description)
        self.assertEqual(job.locations, ["Burlingame, CA, US", "Redmond, WA"])
        # react junk shouldnt leak in
        self.assertNotIn("react stuff", job.description)

    def test_og_fallback_plus_page_text(self):
        job = parse_job_page("2", "u", (FIX / "job_ogonly.html").read_text())
        self.assertEqual(job.title, "Lead Building Engineer")
        self.assertIn("Short blurb.", job.description)
        self.assertIn("HVAC", job.description)
        self.assertNotIn("shouldNotShowUp", job.description)
        self.assertNotIn("color:red", job.description)

    def test_clean_title(self):
        self.assertEqual(clean_title("Mechanical Engineer Intern | Meta Careers"), "Mechanical Engineer Intern")
        self.assertEqual(clean_title("AR/VR Intern"), "AR/VR Intern")

    def test_strip_html(self):
        self.assertEqual(strip_html("<p>a &amp; b</p><p>c</p>"), "a & b\nc")


if __name__ == "__main__":
    unittest.main()
