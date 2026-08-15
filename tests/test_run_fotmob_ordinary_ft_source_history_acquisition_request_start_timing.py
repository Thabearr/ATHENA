from __future__ import annotations

import datetime
from pathlib import Path
from types import SimpleNamespace

import domain.fotmob_ordinary_ft_source_history_acquisition_runner as runner_domain
import scripts.run_fotmob_ordinary_ft_source_history_acquisition as module
from domain.fotmob_ordinary_ft_source_history_acquisition_runner import CampaignSlot


UTC = datetime.timezone.utc
T0 = datetime.datetime(2026, 8, 15, 10, 0, tzinfo=UTC)


class _Clock:
    def __init__(self) -> None:
        self.value = T0
        self.sleeps: list[float] = []

    def __call__(self) -> datetime.datetime:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += datetime.timedelta(seconds=seconds)

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.advance(seconds)


def test_inter_request_spacing_uses_actual_post_marker_request_start(
    tmp_path: Path,
    monkeypatch,
) -> None:
    plan = (
        CampaignSlot(1, "20200801", "A"),
        CampaignSlot(2, "20200802", "A"),
    )
    monkeypatch.setattr(runner_domain, "campaign_slots", lambda: plan)

    clock = _Clock()
    actual_request_starts: list[datetime.datetime] = []
    responses: dict[Path, SimpleNamespace] = {}
    calls = 0

    original_create = module._create_inflight_intent
    marker_latencies = iter((0.80, 0.05))

    def create_with_variable_durable_latency(*args, **kwargs):
        intent = original_create(*args, **kwargs)
        clock.advance(next(marker_latencies))
        return intent

    monkeypatch.setattr(module, "_create_inflight_intent", create_with_variable_durable_latency)

    def fetch(**kwargs):
        nonlocal calls
        calls += 1
        actual_request_starts.append(clock())
        clock.advance(0.05)
        return SimpleNamespace(
            network_acquisition_performed=True,
            observed_at=clock(),
        )

    def write(response, *, request_date, timezone, ccode3, repository_root):
        capture = Path(repository_root) / f"{calls:024x}"
        responses[capture] = response
        return capture, None

    def verify(*, capture_directory, request_date, repository_root):
        response = responses[Path(capture_directory)]
        return (
            SimpleNamespace(
                request_date=request_date,
                timezone="UTC",
                ccode3="NGA",
                observed_at=response.observed_at,
                raw_sha256=f"{calls % 10}" * 64,
                raw_size=100 + calls,
            ),
            f"{(calls + 1) % 10}" * 64,
        )

    progress = module.execute_campaign(
        execute_live_network=True,
        repository_root=tmp_path,
        max_successful_slots=2,
        fetcher=fetch,
        writer=write,
        verifier=verify,
        clock=clock,
        sleeper=clock.sleep,
    )

    assert progress.complete is True
    assert len(actual_request_starts) == 2
    actual_separation = (
        actual_request_starts[1] - actual_request_starts[0]
    ).total_seconds()
    assert actual_separation >= 1.0
    assert clock.sleeps == [0.95]
