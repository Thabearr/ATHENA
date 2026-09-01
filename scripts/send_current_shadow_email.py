#!/usr/bin/env python3
"""Email one durable current ATHENA Shadow run receipt.

A SportyBet share code is rendered only when the durable runner receipt and its
nested provider receipt both prove an exact verified terminal state.  Mail is a
delivery surface only: it cannot promote authority, repair a failed run, or turn
a no-code state into a code.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from email.message import EmailMessage
from html import escape
import json
import os
from pathlib import Path
import smtplib
from typing import Any, Mapping


EXPECTED_DATASET = "athena-current-shadow-all-market-runner-v1"
VERIFIED_STATUSES = frozenset(
    {
        "RESEARCH_SHADOW_CODE_VERIFIED",
        "RESEARCH_SHADOW_CODE_VERIFIED_WITH_SHORTFALL",
    }
)
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587


class CurrentShadowEmailError(ValueError):
    pass


def _load_receipt(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise CurrentShadowEmailError("current Shadow run receipt is unavailable")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CurrentShadowEmailError("current Shadow run receipt is invalid JSON") from exc
    if type(value) is not dict:
        raise CurrentShadowEmailError("current Shadow run receipt must be an object")
    return value


def _require_false(value: Mapping[str, Any], key: str) -> None:
    if value.get(key) is not False:
        raise CurrentShadowEmailError(f"receipt safety flag {key} is not exactly false")


def _verified_code(receipt: Mapping[str, Any]) -> tuple[str, str] | None:
    if receipt.get("dataset_name") != EXPECTED_DATASET:
        raise CurrentShadowEmailError("unexpected current Shadow dataset identity")
    for key in (
        "sportybet_login_used",
        "sportybet_cookie_used",
        "sportybet_wallet_used",
        "stake_submitted",
        "wager_placed",
    ):
        _require_false(receipt, key)

    status = receipt.get("status")
    code = receipt.get("shareCode")
    url = receipt.get("shareURL")
    nested = receipt.get("share_code_receipt")

    if status not in VERIFIED_STATUSES:
        if code is not None or url is not None:
            raise CurrentShadowEmailError("unverified terminal state exposed a share code")
        return None

    if type(code) is not str or not code.strip() or type(url) is not str or not url.strip():
        raise CurrentShadowEmailError("verified terminal state omitted share-code identity")
    if type(nested) is not dict or nested.get("code_verified") is not True:
        raise CurrentShadowEmailError("provider receipt did not prove code_verified=true")
    if nested.get("status") != status:
        raise CurrentShadowEmailError("provider receipt terminal status differs from runner")
    if nested.get("shareCode") != code or nested.get("shareURL") != url:
        raise CurrentShadowEmailError("provider and runner share-code identities differ")
    for key in (
        "sportybet_login_used",
        "sportybet_cookie_used",
        "sportybet_wallet_used",
        "stake_submitted",
        "wager_placed",
    ):
        _require_false(nested, key)
    return code, url


def _selected_leg_lines(receipt: Mapping[str, Any]) -> list[str]:
    portfolio = receipt.get("portfolio")
    if type(portfolio) is not dict:
        return []
    legs = portfolio.get("selected_legs")
    if type(legs) is not list:
        return []
    rows: list[str] = []
    for index, leg in enumerate(legs, start=1):
        if type(leg) is not dict:
            continue
        home = leg.get("home_team", "?")
        away = leg.get("away_team", "?")
        market = leg.get("market_id", "?")
        outcome = leg.get("provider_outcome_name") or leg.get("outcome_id", "?")
        line = leg.get("line")
        odds = leg.get("decimal_odds", "?")
        line_text = "" if line is None else f" | line {line}"
        rows.append(f"{index}. {home} vs {away} | {market} | {outcome}{line_text} | odds {odds}")
    return rows


def render_plain_text(receipt: Mapping[str, Any]) -> str:
    verified = _verified_code(receipt)
    status = str(receipt.get("status", "UNKNOWN"))
    target = receipt.get("requested_target_size", "?")
    selected = receipt.get("selected_leg_count", 0)
    shortfall = receipt.get("shortfall", "?")
    lines = [
        "ATHENA CURRENT SHADOW — RESEARCH ONLY",
        f"Status: {status}",
        f"Requested target: {target}",
        f"Selected legs: {selected}",
        f"Shortfall: {shortfall}",
    ]
    if verified is not None:
        code, url = verified
        lines.extend([f"Verified SportyBet share code: {code}", f"Share URL: {url}"])
    else:
        reasons = receipt.get("reasons")
        if type(reasons) is list and reasons:
            lines.append("Reasons: " + "; ".join(str(item) for item in reasons))
        lines.append("No verified SportyBet share code was released for this run.")

    leg_lines = _selected_leg_lines(receipt)
    if leg_lines:
        lines.extend(["", "Selected legs:", *leg_lines])
    lines.extend(
        [
            "",
            "No login, wallet, stake, or wager action is authorized by this email.",
            "wager_placed=false",
        ]
    )
    return "\n".join(lines) + "\n"


def render_html(receipt: Mapping[str, Any]) -> str:
    text = render_plain_text(receipt)
    return (
        "<html><body style=\"font-family:Arial,sans-serif\">"
        "<h2>ATHENA Current Shadow</h2>"
        "<p><strong>Research-only verified delivery surface.</strong></p>"
        f"<pre style=\"white-space:pre-wrap\">{escape(text)}</pre>"
        "</body></html>"
    )


def _subject(receipt: Mapping[str, Any]) -> str:
    status = str(receipt.get("status", "UNKNOWN"))
    target = receipt.get("requested_target_size", "?")
    observed = receipt.get("observed_at")
    date_text = datetime.now(timezone.utc).date().isoformat()
    if type(observed) is str and len(observed) >= 10:
        date_text = observed[:10]
    return f"ATHENA Shadow {date_text} — target {target} — {status}"


def send_receipt_email(*, receipt_path: Path) -> None:
    receipt = _load_receipt(receipt_path)
    plain = render_plain_text(receipt)
    html = render_html(receipt)

    sender = os.environ.get("GMAIL_ADDRESS", "").strip()
    password = os.environ.get("GMAIL_APP_PASSWORD", "")
    recipient = os.environ.get("RECIPIENT_EMAIL", "").strip()
    if not sender or not password or not recipient:
        raise CurrentShadowEmailError(
            "GMAIL_ADDRESS, GMAIL_APP_PASSWORD, and RECIPIENT_EMAIL are required"
        )

    message = EmailMessage()
    message["Subject"] = _subject(receipt)
    message["From"] = sender
    message["To"] = recipient
    message.set_content(plain)
    message.add_alternative(html, subtype="html")

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
        server.starttls()
        server.login(sender, password)
        server.send_message(message)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    send_receipt_email(receipt_path=args.receipt)
    print("ATHENA current Shadow email delivered.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
