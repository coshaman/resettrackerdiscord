#!/usr/bin/env python3
"""Reset Sentinel: watch codex-resets.com and notify one Discord webhook."""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

TRACKER_URL = os.environ.get("TRACKER_URL", "https://codex-resets.com/")
STATE_FILE = Path(os.environ.get("STATE_FILE", "data/state.json"))
MAX_AGE_MINUTES = int(os.environ.get("MAX_AGE_MINUTES", "50"))
BOT_NAME = os.environ.get("BOT_NAME", "Reset Sentinel")
USER_AGENT = os.environ.get(
    "USER_AGENT",
    "Mozilla/5.0 (compatible; ResetSentinel/1.0; +https://github.com/coshaman/resettrackdiscord)",
)

DATE_RE = re.compile(
    r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+"
    r"\d{1,2},\s+\d{4},\s+\d{1,2}:\d{2}\s+(?:AM|PM)\s+UTC\b",
    re.IGNORECASE,
)
MARKER = "Latest Codex limit reset"


class _VisibleTextParser(HTMLParser):
    """Extract text from HTML while ignoring tags."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        data = data.strip()
        if data:
            self.parts.append(data)


def html_to_text(raw_html: str) -> str:
    parser = _VisibleTextParser()
    parser.feed(raw_html)
    return " ".join(parser.parts)


def parse_reset_datetime(value: str) -> datetime:
    # Normalize whitespace/case but keep English month abbreviations.
    normalized = " ".join(value.split())
    # strptime accepts case-insensitive AM/PM/month names in the C locale used by GitHub runners.
    dt = datetime.strptime(normalized, "%b %d, %Y, %I:%M %p UTC")
    return dt.replace(tzinfo=timezone.utc)


def extract_latest_reset(raw_html: str) -> datetime:
    """Extract the timestamp shown under 'Latest Codex limit reset'.

    The tracker currently renders a human-readable timestamp such as:
      Sep 12, 2026, 8:09 AM UTC

    We deliberately anchor the search to the 'Latest Codex limit reset' marker so a
    future scheduled reset or older history entry cannot be mistaken for the latest reset.
    """

    text = html.unescape(html_to_text(raw_html))
    marker_index = text.lower().find(MARKER.lower())
    if marker_index == -1:
        raise ValueError(f"Could not find marker: {MARKER!r}")

    # The timestamp is immediately after the marker. Keep the window bounded so we do
    # not accidentally match a history item much later on the page if the layout changes.
    nearby = text[marker_index : marker_index + 500]
    match = DATE_RE.search(nearby)
    if not match:
        raise ValueError("Could not find a UTC reset timestamp near the latest-reset marker")

    return parse_reset_datetime(match.group(0))


def fetch_tracker_page(url: str = TRACKER_URL) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "no-cache",
        },
    )
    try:
        with urlopen(request, timeout=25) as response:
            if response.status != 200:
                raise RuntimeError(f"Tracker returned HTTP {response.status}")
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset, errors="replace")
    except HTTPError as exc:
        raise RuntimeError(f"Tracker request failed with HTTP {exc.code}") from exc
    except URLError as exc:
        raise RuntimeError(f"Tracker request failed: {exc.reason}") from exc


def load_state(path: Path = STATE_FILE) -> dict[str, Any]:
    if not path.exists():
        return {"last_notified_reset_utc": None}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise RuntimeError(f"Could not read state file {path}") from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"Invalid state format in {path}")
    data.setdefault("last_notified_reset_utc", None)
    return data


def save_state(reset_time: datetime, path: Path = STATE_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "last_notified_reset_utc": reset_time.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def state_matches(state: dict[str, Any], reset_time: datetime) -> bool:
    expected = reset_time.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return state.get("last_notified_reset_utc") == expected


def reset_age_minutes(reset_time: datetime, now: datetime | None = None) -> float:
    if now is None:
        now = datetime.now(timezone.utc)
    return (now - reset_time).total_seconds() / 60.0


def should_notify(
    reset_time: datetime,
    state: dict[str, Any],
    *,
    now: datetime | None = None,
    max_age_minutes: int = MAX_AGE_MINUTES,
) -> tuple[bool, str, float]:
    age = reset_age_minutes(reset_time, now)

    if state_matches(state, reset_time):
        return False, "already_notified", age
    if age < 0:
        return False, "future_timestamp", age
    if age > max_age_minutes:
        return False, "too_old", age
    return True, "fresh_reset", age


def _post_json(url: str, payload: dict[str, Any]) -> int:
    body = json.dumps(payload).encode("utf-8")
    request = Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urlopen(request, timeout=20) as response:
            return response.status
    except HTTPError as exc:
        # Do not include the webhook URL in logs; it is a secret credential.
        raise RuntimeError(f"Discord webhook failed with HTTP {exc.code}") from exc
    except URLError as exc:
        raise RuntimeError(f"Discord webhook network failure: {exc.reason}") from exc


def send_reset_notification(webhook_url: str, reset_time: datetime, age_minutes: float) -> None:
    unix_ts = int(reset_time.timestamp())
    payload = {
        "username": BOT_NAME,
        "allowed_mentions": {"parse": []},
        "content": (
            "🚨 **Codex Reset 감지**\n"
            "Codex 사용량 리셋이 감지됐어요.\n"
            f"• 리셋 시각: <t:{unix_ts}:F> (<t:{unix_ts}:R>)\n"
            f"• 감지 지연: 약 {max(0, round(age_minutes))}분\n"
            f"• 출처: <{TRACKER_URL}>"
        ),
    }
    status = _post_json(webhook_url, payload)
    if status not in (200, 204):
        raise RuntimeError(f"Discord webhook returned unexpected HTTP {status}")


def send_test_notification(webhook_url: str) -> None:
    payload = {
        "username": BOT_NAME,
        "allowed_mentions": {"parse": []},
        "content": (
            "✅ **Reset Sentinel 테스트 성공**\n"
            "이 메시지가 보이면 Discord Webhook 연결이 정상입니다.\n"
            "실제 알림은 codex-resets.com의 최신 리셋이 0~50분 이내일 때만 전송됩니다."
        ),
    }
    status = _post_json(webhook_url, payload)
    if status not in (200, 204):
        raise RuntimeError(f"Discord webhook returned unexpected HTTP {status}")


def require_webhook() -> str:
    value = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    if not value:
        raise RuntimeError("DISCORD_WEBHOOK_URL is not set")
    if not value.startswith("https://discord.com/api/webhooks/") and not value.startswith(
        "https://discordapp.com/api/webhooks/"
    ):
        raise RuntimeError("DISCORD_WEBHOOK_URL does not look like a Discord webhook URL")
    return value


def run_check() -> int:
    state = load_state()
    page = fetch_tracker_page()
    reset_time = extract_latest_reset(page)
    notify, reason, age = should_notify(reset_time, state)

    print(f"Latest reset (UTC): {reset_time.isoformat()}")
    print(f"Reset age: {age:.1f} minutes")
    print(f"Decision: {reason}")

    if not notify:
        return 0

    webhook_url = require_webhook()
    send_reset_notification(webhook_url, reset_time, age)

    # Persist only after Discord accepted the message. If delivery fails, the state remains
    # unchanged so the next scheduled run can retry.
    save_state(reset_time)
    print("Discord notification sent; state updated.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Codex reset -> Discord notifier")
    parser.add_argument(
        "--test-webhook",
        action="store_true",
        help="Send a test message to the configured Discord webhook without touching state.",
    )
    args = parser.parse_args(argv)

    try:
        if args.test_webhook:
            send_test_notification(require_webhook())
            print("Discord test notification sent.")
            return 0
        return run_check()
    except Exception as exc:  # deliberate top-level boundary for useful Actions logs
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
