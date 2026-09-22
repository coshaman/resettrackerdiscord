import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import reset_tracker


SAMPLE_HTML = """
<html><body>
  <section><h2>Reset scheduled</h2><p>Within about 19 hours By Wed, Sep 23, 06:59 UTC</p></section>
  <main>
    <p>Latest Codex limit reset 10 days ago</p>
    <div>Sep 12, 2026, 8:09 AM UTC</div>
  </main>
  <h2>Codex reset announcements</h2>
  <div>Sep 8, 2026, 1:56 AM UTC</div>
</body></html>
"""


class ParserTests(unittest.TestCase):
    def test_extract_latest_reset_is_anchored_to_marker(self):
        got = reset_tracker.extract_latest_reset(SAMPLE_HTML)
        self.assertEqual(got, datetime(2026, 9, 12, 8, 9, tzinfo=timezone.utc))

    def test_missing_marker_fails_closed(self):
        with self.assertRaises(ValueError):
            reset_tracker.extract_latest_reset("<p>Sep 12, 2026, 8:09 AM UTC</p>")


class DecisionTests(unittest.TestCase):
    def setUp(self):
        self.reset = datetime(2026, 9, 22, 10, 0, tzinfo=timezone.utc)

    def test_fresh_reset_notifies(self):
        state = {"last_notified_reset_utc": None}
        ok, reason, age = reset_tracker.should_notify(
            self.reset,
            state,
            now=self.reset + timedelta(minutes=30),
            max_age_minutes=50,
        )
        self.assertTrue(ok)
        self.assertEqual(reason, "fresh_reset")
        self.assertEqual(age, 30)

    def test_exactly_50_minutes_is_allowed(self):
        state = {"last_notified_reset_utc": None}
        ok, _, _ = reset_tracker.should_notify(
            self.reset,
            state,
            now=self.reset + timedelta(minutes=50),
            max_age_minutes=50,
        )
        self.assertTrue(ok)

    def test_older_than_50_minutes_is_ignored(self):
        state = {"last_notified_reset_utc": None}
        ok, reason, _ = reset_tracker.should_notify(
            self.reset,
            state,
            now=self.reset + timedelta(minutes=50, seconds=1),
            max_age_minutes=50,
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "too_old")

    def test_duplicate_is_ignored(self):
        state = {"last_notified_reset_utc": "2026-09-22T10:00:00Z"}
        ok, reason, _ = reset_tracker.should_notify(
            self.reset,
            state,
            now=self.reset + timedelta(minutes=10),
            max_age_minutes=50,
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "already_notified")

    def test_future_timestamp_is_ignored(self):
        state = {"last_notified_reset_utc": None}
        ok, reason, _ = reset_tracker.should_notify(
            self.reset,
            state,
            now=self.reset - timedelta(minutes=1),
            max_age_minutes=50,
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "future_timestamp")

    def test_state_round_trip(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "state.json"
            reset_tracker.save_state(self.reset, path)
            state = reset_tracker.load_state(path)
            self.assertEqual(state["last_notified_reset_utc"], "2026-09-22T10:00:00Z")


if __name__ == "__main__":
    unittest.main()
