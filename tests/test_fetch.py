import unittest
from unittest import mock

from jobwatch import fetch


class R:
    def __init__(self, code):
        self.status_code = code


class FetchTests(unittest.TestCase):
    def setUp(self):
        fetch._working = None

    def test_falls_through_to_next_profile(self):
        s = mock.Mock()
        s.get.side_effect = [R(400), R(200)]
        self.assertEqual(fetch.get(s, "u").status_code, 200)
        # second call should go straight to the profile that worked
        s.get.side_effect = [R(200)]
        fetch.get(s, "u2")
        _, kw = s.get.call_args
        self.assertEqual(kw["headers"], fetch.PROFILES[1][1])

    def test_404_isnt_retried(self):
        s = mock.Mock()
        s.get.return_value = R(404)
        self.assertEqual(fetch.get(s, "u").status_code, 404)
        self.assertEqual(s.get.call_count, 1)

    def test_all_fail_returns_last(self):
        s = mock.Mock()
        s.get.return_value = R(400)
        self.assertEqual(fetch.get(s, "u").status_code, 400)
        self.assertEqual(s.get.call_count, len(fetch.PROFILES))


if __name__ == "__main__":
    unittest.main()
