import unittest
from unittest import mock

import requests

from finder.http import PoliteClient


def resp(code, text=""):
    r = mock.Mock(); r.status_code = code; r.text = text
    return r


class TestRobots(unittest.TestCase):
    def client(self, *responses):
        c = PoliteClient("test-agent/1.0", max_rps_per_host=1000)
        c.session.get = mock.Mock(side_effect=list(responses))
        return c

    @mock.patch("finder.http.time.sleep")
    def test_one_retry_after_server_error(self, _sleep):
        c = self.client(resp(503), resp(200, "User-agent: *\nDisallow: /private/"))
        self.assertTrue(c.allowed("https://x.example/jobs"))
        self.assertFalse(c.allowed("https://x.example/private/a"))

    @mock.patch("finder.http.time.sleep")
    def test_two_failures_mean_disallow_all(self, _sleep):
        c = self.client(resp(503), requests.ConnectionError("down"))
        self.assertFalse(c.allowed("https://x.example/jobs"))

    def test_4xx_means_allow_all(self):
        c = self.client(resp(404))
        self.assertTrue(c.allowed("https://x.example/anything"))

    def test_disallow_all_is_respected(self):
        c = self.client(resp(200, "User-agent: *\nDisallow: /"))
        self.assertFalse(c.allowed("https://x.example/jobs"))


if __name__ == "__main__":
    unittest.main()
