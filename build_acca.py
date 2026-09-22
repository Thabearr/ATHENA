"""Thin command-line transport for canonical ATHENA run requests."""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Sequence

import typer
from rich.console import Console

from domain.run_contracts import RunReceipt, RunRequest, canonical_json_bytes
from services.athena_run_request_parser import (
    AthenaRunRequestParseError,
    CLI_TIMEZONE_ID,
    parse_explicit_request,
    parse_shorthand_request,
)
from services.athena_run_service import AthenaRunService, AthenaRunServiceError


app = typer.Typer(help="ATHENA canonical run request interface", no_args_is_help=True)
console = Console()
_ACCA_SHORTHAND_HINT = re.compile(r"^[0-9]+acca$", re.ASCII)


@app.callback()
def cli_root() -> None:
    """Submit a canonical ATHENA run request."""


def _render_request_summary(request: RunRequest, manifest) -> None:
    capabilities = manifest.to_dict()["capabilities"]
    console.print("Resolved ATHENA request (before execution):")
    console.print(f"  timezone: {CLI_TIMEZONE_ID}")
    console.print(f"  dates: {', '.join(item.isoformat() for item in request.dates)}")
    console.print(f"  target_legs: {request.target_legs}")
    console.print(f"  target_total_odds: {request.target_total_odds}")
    console.print(f"  bookie: {request.bookie}")
    console.print(f"  mode: {request.mode}")
    console.print(f"  authority_profile: {request.authority_profile}")
    console.print(f"  create_share_code: {request.create_share_code}")
    console.print(f"  place_wager: {request.place_wager}")
    for name in (
        "provider_acquisition",
        "share_code_generation",
        "login",
        "cookies",
        "wallet",
        "staking",
        "wager",
    ):
        console.print(f"  {name}: {capabilities[name]}")


def render_receipt(receipt: RunReceipt) -> None:
    """Render only the exact canonical receipt payload; do not recalculate it."""
    if type(receipt) is not RunReceipt:
        raise TypeError("renderer requires exact RunReceipt")
    console.print(canonical_json_bytes(receipt).decode("utf-8"), markup=False)


def execute_request(
    request: RunRequest,
    *,
    output_root: Path,
    service: AthenaRunService | None = None,
) -> RunReceipt:
    if type(request) is not RunRequest:
        raise TypeError("CLI requires exact RunRequest")
    selected_service = service if service is not None else AthenaRunService()
    manifest = selected_service.authority_manifest_for(request)
    _render_request_summary(request, manifest)
    receipt = selected_service.run(request, output_root=output_root)
    render_receipt(receipt)
    return receipt


@app.command("run")
def run_command(
    days: str = typer.Option(..., "--days", help="Comma-separated Lagos dates or relative day names"),
    target_legs: int = typer.Option(..., "--target-legs", min=1, max=50),
    bookie: str = typer.Option("sportybet", "--bookie"),
    profile: str = typer.Option(..., "--profile", help="Explicit execution profile: main or shadow"),
    target_total_odds: str | None = typer.Option(None, "--target-total-odds"),
    output_dir: Path = typer.Option(Path("artifacts/athena-runs"), "--output-dir"),
) -> None:
    """Resolve an explicit request and pass it to AthenaRunService."""
    try:
        request = parse_explicit_request(
            days=days,
            target_legs=target_legs,
            bookie=bookie,
            profile=profile,
            target_total_odds=target_total_odds,
        )
        execute_request(request, output_root=output_dir)
    except (AthenaRunRequestParseError, AthenaRunServiceError) as exc:
        console.print(f"Request stopped: {exc}", style="red")
        raise typer.Exit(code=2) from exc


def _is_shorthand_candidate(args: Sequence[str]) -> bool:
    if len(args) != 3 or args[0] in {"run", "--help", "-h"}:
        return False
    return (
        _ACCA_SHORTHAND_HINT.fullmatch(args[1]) is not None
        or "acca" in args[1].lower()
        or args[2].lower() == "sportybet"
    )


def main(argv: Sequence[str] | None = None) -> None:
    """Console entrypoint supporting both explicit syntax and legacy shorthand."""
    args = list(sys.argv[1:] if argv is None else argv)
    if _is_shorthand_candidate(args):
        try:
            request = parse_shorthand_request(
                date_scope=args[0],
                acca_token=args[1],
                bookie=args[2],
            )
            execute_request(
                request,
                output_root=Path("artifacts/athena-runs"),
            )
        except (AthenaRunRequestParseError, AthenaRunServiceError) as exc:
            console.print(f"Request stopped: {exc}", style="red")
            raise typer.Exit(code=2) from exc
        return
    app(args=args, prog_name="athena")


if __name__ == "__main__":
    main()
