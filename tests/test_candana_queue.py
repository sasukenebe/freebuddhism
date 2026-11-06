import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/buddhist_canon_pipeline"))
from candana_queue import (  # noqa: E402
    SourceLinks, checked_url, retry_seconds, step, add_jobs, priority, process_discovery,
)


class QueueTests(unittest.TestCase):
    def state(self):
        return {"interval_seconds": 120, "next_request_at": 0, "halt_reason": None,
                "consecutive_failures": 0, "robots": {"www.mindreleased.com": {"text": "User-agent: *\nAllow: /"}},
                "jobs": [{"url": "https://www.mindreleased.com/s/example.pdf", "current_url": "https://www.mindreleased.com/s/example.pdf",
                          "state": "PENDING", "attempts": 0, "redirects": 0}]}

    def tick(self, state, now, response):
        requests = []
        saved = []
        def requester(url):
            requests.append(url)
            return response
        result = step(state, now, requester, lambda value: saved.append(copy.deepcopy(value)))
        return result, requests, saved

    def test_retry_after_seconds_and_dates(self):
        self.assertEqual(retry_seconds("3600", 0), 3600)
        self.assertEqual(retry_seconds("Thu, 01 Jan 1970 01:00:00 GMT", 100), 3500)
        self.assertEqual(retry_seconds("invalid", 0), 0)

    def test_429_cools_down_the_entire_queue_and_survives_reload(self):
        state = self.state()
        result, requests, saved = self.tick(state, 100, (429, {"Retry-After": "3600"}, b""))
        self.assertEqual(len(requests), 1)
        self.assertAlmostEqual(state["next_request_at"], 3700, places=1)
        result, requests, _ = self.tick(copy.deepcopy(saved[-1]), 200, (200, {}, b""))
        self.assertEqual(result["status"], "WAIT")
        self.assertEqual(requests, [])

    def test_unauthorized_and_forbidden_halt_without_retry(self):
        for status in (401, 403):
            state = self.state()
            self.tick(state, 100, (status, {}, b""))
            result, requests, _ = self.tick(state, 100000, (200, {}, b""))
            self.assertEqual(result["status"], "HALTED")
            self.assertEqual(requests, [])

    def test_redirects_are_deferred_not_followed_in_a_burst(self):
        state = self.state()
        result, requests, saved = self.tick(state, 100, (302, {"Location": "https://static1.squarespace.com/book.pdf"}, b""))
        self.assertEqual(len(requests), 1)
        self.assertEqual(state["jobs"][0]["current_url"], "https://static1.squarespace.com/book.pdf")
        self.assertEqual(saved[0]["next_request_at"], 220)
        result, requests, _ = self.tick(state, 101, (200, {}, b""))
        self.assertEqual(result["status"], "WAIT")
        self.assertEqual(requests, [])

    def test_robots_is_fetched_before_content_and_delay_is_respected(self):
        state = self.state()
        state["robots"] = {}
        _, requests, _ = self.tick(state, 100, (200, {}, b"User-agent: *\nDisallow: /s/\nCrawl-delay: 600\n"))
        self.assertEqual(requests, ["https://www.mindreleased.com/robots.txt"])
        self.assertAlmostEqual(state["next_request_at"], 700, places=1)
        result, requests, _ = self.tick(state, 701, (200, {}, b""))
        self.assertEqual(result["status"], "ROBOTS_DISALLOWED")
        self.assertEqual(requests, [])

    def test_discovery_prefers_real_text_sources_and_rejects_other_hosts(self):
        parser = SourceLinks("https://www.mindreleased.com/pali-suttas")
        parser.feed('<a href="/s/text.txt">Text</a><a href="/s/text.docx">Document</a>'
                    '<a href="/s/text.pdf">PDF</a><a href="https://example.org/file.pdf">Other host</a>')
        self.assertEqual(len(parser.urls), 3)
        for value in ("file:///etc/passwd", "http://www.mindreleased.com/s/file", "https://www.mindreleased.com@evil.test/file"):
            with self.assertRaises(ValueError):
                checked_url(value)
        state = self.state()
        add_jobs(state, ["https://example.org/unrelated.pdf", "https://www.mindreleased.com/s/source.txt"])
        self.assertEqual(len(state["jobs"]), 2)
        self.assertTrue(sorted(state["jobs"], key=priority)[0]["url"].endswith(".txt"))

    def test_completed_queue_makes_no_requests(self):
        state = self.state()
        state["jobs"][0]["state"] = "COLLECTED"
        result, requests, _ = self.tick(state, 100, (200, {}, b""))
        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(requests, [])

    def test_legacy_http_sitemap_links_are_collected_over_https_only(self):
        state = self.state()
        job = {"url": "https://www.mindreleased.com/sitemap.xml"}
        process_discovery(state, job, b'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>http://www.mindreleased.com/native-texts</loc></url></urlset>')
        self.assertTrue(job["discovery_parsed"])
        self.assertEqual(state["jobs"][-1]["url"], "https://www.mindreleased.com/native-texts")

    def test_cached_text_conversion_can_continue_without_network_during_cooldown(self):
        state = self.state()
        state["next_request_at"] = 1000
        state["jobs"][0].update(state="COLLECTED", cache="build/candana-audit/fixture.pdf")
        with patch("candana_queue.stage_text") as stage:
            result, requests, _ = self.tick(state, 100, (200, {}, b""))
        self.assertEqual(result["status"], "STAGED_TEXT_DRAFT")
        self.assertEqual(requests, [])
        stage.assert_called_once_with(state["jobs"][0])
        state["next_request_at"] = 0
        with patch("candana_queue.stage_text") as stage:
            result, requests, _ = self.tick(state, 100, (200, {}, b""))
        self.assertEqual(result["status"], "STAGED_TEXT_DRAFT")
        self.assertEqual(requests, [])
