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
import hashlib
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
EMAIL_DELIVERED = "EMAIL_DELIVERED"
EMAIL_SKIPPED_UNCONFIGURED = "EMAIL_SKIPPED_UNCONFIGURED"
EMAIL_FAILED = "EMAIL_FAILED"
DELIVERY_RECEIPT_FILENAME = "current-shadow-email-delivery-receipt.json"


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
    if nested.get("exact_create_reload_equality") is not True:
        raise CurrentShadowEmailError("provider receipt did not prove exact create/reload equality")
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
    legs = receipt.get("final_selected_legs")
    if not isinstance(legs, list) or not legs:
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
        confidence = leg.get("prediction_confidence", "?")
        line_text = "" if line is None else f" | line {line}"
        rows.append(f"{index}. {home} vs {away} | {market} | {outcome}{line_text} | prediction confidence {confidence} | fresh odds {odds}")
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


def _write_delivery_receipt(
    *, path: Path, status: str, source_receipt_sha256: str, failure_type: str | None = None,
) -> dict[str, Any]:
    value = {
        "schema_version": 1,
        "dataset_name": "athena-current-shadow-email-delivery-v1",
        "status": status,
        "observed_at": datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z"),
        "source_receipt_sha256": source_receipt_sha256,
        "smtp_successful_send": status == EMAIL_DELIVERED,
        "failure_type": failure_type,
        "secrets_recorded": False,
        "wager_placed": False,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    return value


def send_receipt_email(
    *, receipt_path: Path, delivery_receipt_path: Path | None = None,
) -> dict[str, Any]:
    receipt = _load_receipt(receipt_path)
    delivery_path = delivery_receipt_path or receipt_path.with_name(DELIVERY_RECEIPT_FILENAME)
    source_sha = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    plain = render_plain_text(receipt)
    html = render_html(receipt)

    sender = os.environ.get("GMAIL_ADDRESS", "").strip()
    password = os.environ.get("GMAIL_APP_PASSWORD", "")
    recipient = os.environ.get("RECIPIENT_EMAIL", "").strip()
    if not sender or not password or not recipient:
        return _write_delivery_receipt(
            path=delivery_path,
            status=EMAIL_SKIPPED_UNCONFIGURED,
            source_receipt_sha256=source_sha,
        )

    message = EmailMessage()
    message["Subject"] = _subject(receipt)
    message["From"] = sender
    message["To"] = recipient
    message.set_content(plain)
    message.add_alternative(html, subtype="html")

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
            server.starttls()
            server.login(sender, password)
            server.send_message(message)
    except Exception as exc:
        _write_delivery_receipt(
            path=delivery_path,
            status=EMAIL_FAILED,
            source_receipt_sha256=source_sha,
            failure_type=type(exc).__name__,
        )
        raise CurrentShadowEmailError("SMTP send failed; durable EMAIL_FAILED receipt written") from exc
    return _write_delivery_receipt(
        path=delivery_path,
        status=EMAIL_DELIVERED,
        source_receipt_sha256=source_sha,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--delivery-receipt", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = send_receipt_email(
        receipt_path=args.receipt,
        delivery_receipt_path=args.delivery_receipt,
    )
    print(f"ATHENA current Shadow email status: {result['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
