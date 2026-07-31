"""Deterministic Win Either Half labels for offline research only.

This module derives post-match labels from explicit full-time and half-time
scores. It does not calculate probabilities, value, stakes, or market
eligibility for production recommendations.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Iterable, Optional, Tuple

from domain.half_time_data import (
    HalfTimeObservation,
    HalfTimeValidationStatus,
    ScoreProvenance,
    select_one_observation_per_fixture,
)


DEFAULT_TRAIN_SEASONS = ("2020-21", "2021-22", "2022-23", "2023-24")
DEFAULT_VALIDATION_SEASONS = ("2024-25",)
DEFAULT_TEST_SEASONS = ("2025-26",)
_FOOTBALL_SEASON_PATTERN = re.compile(
    r"^(?P<start>[0-9]{4})-(?P<end>[0-9]{2})$"
)


class ResearchLabelError(ValueError):
    """Raised when deterministic label or split requirements are violated."""


class ResearchSplit(str, Enum):
    TRAIN = "TRAIN"
    VALIDATION = "VALIDATION"
    TEST = "TEST"


class HalfOutcome(str, Enum):
    HOME = "HOME"
    DRAW = "DRAW"
    AWAY = "AWAY"


def parse_football_season(season: str) -> int:
    """Validate ``YYYY-YY`` and return its chronological starting year.

    The ending component must be the two-digit representation of the year
    immediately following the four-digit starting year. Raw strings are
    validated rather than ordered lexicographically.
    """
    if not isinstance(season, str):
        raise ResearchLabelError(
            "Football season must use YYYY-YY, for example 2025-26"
        )
    match = _FOOTBALL_SEASON_PATTERN.fullmatch(season)
    if match is None:
        raise ResearchLabelError(
            f"Football season must use YYYY-YY: {season!r}"
        )
    start_year = int(match.group("start"))
    end_year = int(match.group("end"))
    expected_end = (start_year + 1) % 100
    if end_year != expected_end:
        raise ResearchLabelError(
            "Football season ending year must immediately follow its "
            f"starting year: {season!r}"
        )
    return start_year


class LabelExclusionReason(str, Enum):
    MISSING_HALF_TIME_SCORE = "MISSING_HALF_TIME_SCORE"
    INVALID_SCORE_EVIDENCE = "INVALID_SCORE_EVIDENCE"
    INVALID_OBSERVATION = "INVALID_OBSERVATION"
    UNOBSERVED_PROVENANCE = "UNOBSERVED_PROVENANCE"
    SOURCE_CONFLICT = "SOURCE_CONFLICT"
    MISSING_FIXTURE_IDENTITY = "MISSING_FIXTURE_IDENTITY"
    MISSING_KICKOFF = "MISSING_KICKOFF"
    MISSING_LEAGUE = "MISSING_LEAGUE"
    MISSING_SEASON = "MISSING_SEASON"
    MISSING_TEAM_IDENTITY = "MISSING_TEAM_IDENTITY"
    NEGATIVE_SECOND_HALF_SCORE = "NEGATIVE_SECOND_HALF_SCORE"


_EXCLUSION_EXPLANATIONS = {
    LabelExclusionReason.MISSING_HALF_TIME_SCORE: (
        "An explicit pair of observed half-time scores is unavailable."
    ),
    LabelExclusionReason.INVALID_SCORE_EVIDENCE: (
        "The stored full-time or half-time score evidence is invalid."
    ),
    LabelExclusionReason.INVALID_OBSERVATION: (
        "The selected observation is not VALID for a non-score reason."
    ),
    LabelExclusionReason.UNOBSERVED_PROVENANCE: (
        "Half-time score provenance is not OBSERVED."
    ),
    LabelExclusionReason.SOURCE_CONFLICT: (
        "The selected observation has an unresolved source conflict."
    ),
    LabelExclusionReason.MISSING_FIXTURE_IDENTITY: (
        "Fixture identity is missing."
    ),
    LabelExclusionReason.MISSING_KICKOFF: "Kickoff time is missing.",
    LabelExclusionReason.MISSING_LEAGUE: "League metadata is missing.",
    LabelExclusionReason.MISSING_SEASON: "Season metadata is missing.",
    LabelExclusionReason.MISSING_TEAM_IDENTITY: (
        "Home or away team identity is missing."
    ),
    LabelExclusionReason.NEGATIVE_SECOND_HALF_SCORE: (
        "Full-time minus half-time produced a negative second-half score."
    ),
}


@dataclass(frozen=True)
class TemporalSplitConfig:
    train_seasons: Tuple[str, ...] = DEFAULT_TRAIN_SEASONS
    validation_seasons: Tuple[str, ...] = DEFAULT_VALIDATION_SEASONS
    test_seasons: Tuple[str, ...] = DEFAULT_TEST_SEASONS

    def __post_init__(self) -> None:
        normalized = {}
        for field_name in (
            "train_seasons",
            "validation_seasons",
            "test_seasons",
        ):
            values = tuple(getattr(self, field_name))
            if not values:
                split_name = field_name.removesuffix("_seasons").upper()
                raise ResearchLabelError(
                    f"{split_name} must contain at least one season"
                )
            chronological = tuple(
                (parse_football_season(value), value) for value in values
            )
            if len(set(values)) != len(values):
                raise ResearchLabelError(
                    f"Duplicate season in {field_name.replace('_', ' ')}"
                )
            ordered = tuple(
                value for _, value in sorted(chronological)
            )
            normalized[field_name] = ordered
            object.__setattr__(self, field_name, ordered)

        memberships = {}
        for split, field_name in (
            (ResearchSplit.TRAIN, "train_seasons"),
            (ResearchSplit.VALIDATION, "validation_seasons"),
            (ResearchSplit.TEST, "test_seasons"),
        ):
            for season in normalized[field_name]:
                memberships.setdefault(season, []).append(split)
        overlaps = sorted(
            season for season, splits in memberships.items() if len(splits) > 1
        )
        if overlaps:
            raise ResearchLabelError(
                "Season split definitions overlap: " + ", ".join(overlaps)
            )

        train_keys = tuple(
            parse_football_season(value)
            for value in normalized["train_seasons"]
        )
        validation_keys = tuple(
            parse_football_season(value)
            for value in normalized["validation_seasons"]
        )
        test_keys = tuple(
            parse_football_season(value)
            for value in normalized["test_seasons"]
        )
        if not (
            max(train_keys) < min(validation_keys)
            and max(validation_keys) < min(test_keys)
        ):
            raise ResearchLabelError(
                "Temporal splits must be chronological and non-interleaved: "
                "every TRAIN season must precede every VALIDATION season, "
                "and every VALIDATION season must precede every TEST season"
            )

    def split_for(self, season: str) -> ResearchSplit:
        if season in self.train_seasons:
            return ResearchSplit.TRAIN
        if season in self.validation_seasons:
            return ResearchSplit.VALIDATION
        if season in self.test_seasons:
            return ResearchSplit.TEST
        raise ResearchLabelError(
            f"Eligible season is not assigned to a temporal split: {season}"
        )

    def to_dict(self) -> dict:
        return {
            "train": list(self.train_seasons),
            "validation": list(self.validation_seasons),
            "test": list(self.test_seasons),
        }


@dataclass(frozen=True)
class WinEitherHalfLabel:
    fixture_identity: str
    home_team: str
    away_team: str
    kickoff_utc: str
    league: str
    season: str
    split: ResearchSplit
    source: str
    source_fixture_id: Optional[str]
    score_provenance: str
    full_time_home_goals: int
    full_time_away_goals: int
    half_time_home_goals: int
    half_time_away_goals: int
    second_half_home_goals: int
    second_half_away_goals: int
    first_half_outcome: HalfOutcome
    second_half_outcome: HalfOutcome
    home_win_first_half: int
    away_win_first_half: int
    home_win_second_half: int
    away_win_second_half: int
    home_win_either_half_yes: int
    away_win_either_half_yes: int
    both_teams_won_a_half: int


@dataclass(frozen=True)
class LabelExclusion:
    fixture_identity: str
    league: Optional[str]
    season: Optional[str]
    source: str
    validation_status: str
    provenance: str
    reason_codes: Tuple[LabelExclusionReason, ...]
    explanation: str


@dataclass(frozen=True)
class WinEitherHalfLabelDataset:
    selected_fixtures: int
    labels: Tuple[WinEitherHalfLabel, ...]
    exclusions: Tuple[LabelExclusion, ...]
    split_config: TemporalSplitConfig


def _enum_value(value) -> str:
    return getattr(value, "value", str(value))


def _normalized_utc(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(
        timespec="microseconds"
    ).replace("+00:00", "Z")


def _is_non_negative_integer(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _outcome(home_goals: int, away_goals: int) -> HalfOutcome:
    if home_goals > away_goals:
        return HalfOutcome.HOME
    if away_goals > home_goals:
        return HalfOutcome.AWAY
    return HalfOutcome.DRAW


def label_exclusion_reasons(
    observation: HalfTimeObservation,
) -> Tuple[LabelExclusionReason, ...]:
    reasons = set()
    if not str(observation.fixture_identity or "").strip():
        reasons.add(LabelExclusionReason.MISSING_FIXTURE_IDENTITY)
    if not str(observation.home_team or "").strip() or not str(
        observation.away_team or ""
    ).strip():
        reasons.add(LabelExclusionReason.MISSING_TEAM_IDENTITY)
    if observation.kickoff_time is None:
        reasons.add(LabelExclusionReason.MISSING_KICKOFF)
    if not str(observation.league or "").strip():
        reasons.add(LabelExclusionReason.MISSING_LEAGUE)
    if not str(observation.season or "").strip():
        reasons.add(LabelExclusionReason.MISSING_SEASON)
    if observation.conflict_status:
        reasons.add(LabelExclusionReason.SOURCE_CONFLICT)

    provenance = observation.half_time_score_provenance
    if provenance != ScoreProvenance.OBSERVED:
        reasons.add(LabelExclusionReason.UNOBSERVED_PROVENANCE)

    half_time_scores = (
        observation.half_time_home_goals,
        observation.half_time_away_goals,
    )
    if any(value is None for value in half_time_scores):
        reasons.add(LabelExclusionReason.MISSING_HALF_TIME_SCORE)

    all_scores = (
        observation.full_time_home_goals,
        observation.full_time_away_goals,
        observation.half_time_home_goals,
        observation.half_time_away_goals,
    )
    present_scores_are_valid = all(
        value is None or _is_non_negative_integer(value)
        for value in all_scores
    )
    score_evidence_invalid = (
        not present_scores_are_valid
        or observation.full_time_home_goals is None
        or observation.full_time_away_goals is None
        or (
            (observation.half_time_home_goals is None)
            != (observation.half_time_away_goals is None)
        )
    )
    if (
        observation.authoritative_full_time_source
        and (
            (
                observation.stored_full_time_home_goals is not None
                and observation.stored_full_time_home_goals
                != observation.full_time_home_goals
            )
            or (
                observation.stored_full_time_away_goals is not None
                and observation.stored_full_time_away_goals
                != observation.full_time_away_goals
            )
        )
    ):
        score_evidence_invalid = True
    if score_evidence_invalid:
        reasons.add(LabelExclusionReason.INVALID_SCORE_EVIDENCE)

    if all(_is_non_negative_integer(value) for value in all_scores):
        second_home = (
            observation.full_time_home_goals
            - observation.half_time_home_goals
        )
        second_away = (
            observation.full_time_away_goals
            - observation.half_time_away_goals
        )
        if second_home < 0 or second_away < 0:
            reasons.add(LabelExclusionReason.NEGATIVE_SECOND_HALF_SCORE)

    if (
        observation.validation_status == HalfTimeValidationStatus.INVALID
        and not reasons
    ):
        reasons.add(LabelExclusionReason.INVALID_OBSERVATION)

    return tuple(sorted(reasons, key=lambda item: item.value))


def _build_exclusion(
    observation: HalfTimeObservation,
    reasons: Tuple[LabelExclusionReason, ...],
) -> LabelExclusion:
    explanation = " ".join(_EXCLUSION_EXPLANATIONS[reason] for reason in reasons)
    return LabelExclusion(
        fixture_identity=str(observation.fixture_identity or "").strip(),
        league=(str(observation.league).strip() if observation.league else None),
        season=(str(observation.season).strip() if observation.season else None),
        source=str(observation.source or "").strip(),
        validation_status=_enum_value(observation.validation_status),
        provenance=_enum_value(observation.half_time_score_provenance),
        reason_codes=reasons,
        explanation=explanation[:500],
    )


def derive_win_either_half_label(
    observation: HalfTimeObservation,
    *,
    split: ResearchSplit,
) -> WinEitherHalfLabel:
    """Derive exact post-match labels from one eligible observation."""
    reasons = label_exclusion_reasons(observation)
    if reasons:
        raise ResearchLabelError(
            "Observation is not label-eligible: "
            + ", ".join(reason.value for reason in reasons)
        )

    first_home = observation.half_time_home_goals
    first_away = observation.half_time_away_goals
    second_home = observation.full_time_home_goals - first_home
    second_away = observation.full_time_away_goals - first_away
    home_first = int(first_home > first_away)
    away_first = int(first_away > first_home)
    home_second = int(second_home > second_away)
    away_second = int(second_away > second_home)
    home_yes = int(bool(home_first or home_second))
    away_yes = int(bool(away_first or away_second))

    return WinEitherHalfLabel(
        fixture_identity=observation.fixture_identity,
        home_team=str(observation.home_team).strip(),
        away_team=str(observation.away_team).strip(),
        kickoff_utc=_normalized_utc(observation.kickoff_time),
        league=str(observation.league).strip(),
        season=str(observation.season).strip(),
        split=split,
        source=observation.source,
        source_fixture_id=observation.source_fixture_id,
        score_provenance=_enum_value(
            observation.half_time_score_provenance
        ),
        full_time_home_goals=observation.full_time_home_goals,
        full_time_away_goals=observation.full_time_away_goals,
        half_time_home_goals=first_home,
        half_time_away_goals=first_away,
        second_half_home_goals=second_home,
        second_half_away_goals=second_away,
        first_half_outcome=_outcome(first_home, first_away),
        second_half_outcome=_outcome(second_home, second_away),
        home_win_first_half=home_first,
        away_win_first_half=away_first,
        home_win_second_half=home_second,
        away_win_second_half=away_second,
        home_win_either_half_yes=home_yes,
        away_win_either_half_yes=away_yes,
        both_teams_won_a_half=int(bool(home_yes and away_yes)),
    )


def build_win_either_half_labels(
    observations: Iterable[HalfTimeObservation],
    *,
    split_config: TemporalSplitConfig = TemporalSplitConfig(),
) -> WinEitherHalfLabelDataset:
    """Select one fixture record, label eligible rows and retain exclusions."""
    selected = select_one_observation_per_fixture(observations)
    labels = []
    exclusions = []
    for observation in selected:
        reasons = label_exclusion_reasons(observation)
        if reasons:
            exclusions.append(_build_exclusion(observation, reasons))
            continue
        season = str(observation.season).strip()
        split = split_config.split_for(season)
        labels.append(
            derive_win_either_half_label(observation, split=split)
        )

    labels.sort(key=lambda item: (item.kickoff_utc, item.fixture_identity))
    exclusions.sort(
        key=lambda item: (
            item.fixture_identity,
            tuple(reason.value for reason in item.reason_codes),
        )
    )
    if len(labels) + len(exclusions) != len(selected):
        raise ResearchLabelError("Selected fixture accounting is inconsistent")
    return WinEitherHalfLabelDataset(
        selected_fixtures=len(selected),
        labels=tuple(labels),
        exclusions=tuple(exclusions),
        split_config=split_config,
    )


__all__ = [
    "DEFAULT_TEST_SEASONS",
    "DEFAULT_TRAIN_SEASONS",
    "DEFAULT_VALIDATION_SEASONS",
    "HalfOutcome",
    "LabelExclusion",
    "LabelExclusionReason",
    "ResearchLabelError",
    "ResearchSplit",
    "TemporalSplitConfig",
    "WinEitherHalfLabel",
    "WinEitherHalfLabelDataset",
    "build_win_either_half_labels",
    "derive_win_either_half_label",
    "label_exclusion_reasons",
    "parse_football_season",
]
