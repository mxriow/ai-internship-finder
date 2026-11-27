"""RFC 9309 robots.txt matching."""
import unittest

from finder.robots import Robots

AGENT = "ch-intern-finder"


class TestRobots(unittest.TestCase):
    def test_wildcards_and_anchors(self):
        r = Robots("User-agent: *\nDisallow: */iauth\nDisallow: /*.pdf$\nDisallow: /search?\n", AGENT)
        self.assertFalse(r.allowed("https://x/global/en/iauth"))
        self.assertFalse(r.allowed("https://x/docs/file.pdf"))
        self.assertTrue(r.allowed("https://x/docs/file.pdf?x=1"))      # $ anchors the end
        self.assertFalse(r.allowed("https://x/search?q=intern"))
        self.assertTrue(r.allowed("https://x/global/en/job/123/Marketing-Intern"))

    def test_longest_match_wins_and_allow_wins_ties(self):
        r = Robots("User-agent: *\nDisallow: /jobs/\nAllow: /jobs/public/\n", AGENT)
        self.assertFalse(r.allowed("https://x/jobs/private/1"))
        self.assertTrue(r.allowed("https://x/jobs/public/1"))
        r = Robots("User-agent: *\nDisallow: /page\nAllow: /page\n", AGENT)
        self.assertTrue(r.allowed("https://x/page"))

    def test_specific_group_overrides_star(self):
        text = "User-agent: *\nDisallow: /\n\nUser-agent: CH-Intern-Finder\nAllow: /jobs/\nDisallow: /\n"
        r = Robots(text, AGENT)
        self.assertTrue(r.allowed("https://x/jobs/1"))
        self.assertFalse(r.allowed("https://x/other"))
        self.assertFalse(Robots(text, "otherbot").allowed("https://x/jobs/1"))

    def test_grouped_agents_and_empty_disallow(self):
        r = Robots("User-agent: googlebot\nUser-agent: *\nDisallow:\n", AGENT)
        self.assertTrue(r.allowed("https://x/anything"))

    def test_smartrecruiters_style_disallow_all(self):
        r = Robots("User-agent: LinkedInBot\nAllow: /v1/companies/\nUser-agent: *\nDisallow: /\n", AGENT)
        self.assertFalse(r.allowed("https://api.smartrecruiters.com/v1/companies/x/postings"))

    def test_crawl_delay(self):
        self.assertEqual(Robots("User-agent: *\nCrawl-delay: 1\nAllow: /\n", AGENT).crawl_delay, 1.0)


if __name__ == "__main__":
    unittest.main()
