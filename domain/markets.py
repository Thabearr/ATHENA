"""Canonical football market and selection definitions.

This module is the only place where legacy ATHENA verdict identifiers are
translated into canonical market/outcome pairs. Unknown identifiers fail
loudly; they are never converted to a default selection.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
import re
from typing import Any, Dict, Mapping, Optional, Tuple


class MarketRegistryError(ValueError):
    """Base class for canonical market validation errors."""


class UnknownMarketError(MarketRegistryError):
    """Raised when a market identifier is not registered."""


class UnknownOutcomeError(MarketRegistryError):
    """Raised when an outcome identifier is not registered."""


class UnknownSelectionError(MarketRegistryError):
    """Raised when a legacy verdict cannot be resolved."""


class InvalidSelectionError(MarketRegistryError):
    """Raised when a market/outcome/line combination is invalid."""


class MarketId(str, Enum):
    # Standard 1X2 is retained because prediction and audit payloads use it.
    MATCH_RESULT = "MATCH_RESULT"
    ASIAN_HANDICAP = "ASIAN_HANDICAP"
    TOTAL_GOALS = "TOTAL_GOALS"
    DRAW_OR_OVER_2_5 = "DRAW_OR_OVER_2_5"
    AWAY_OR_OVER_2_5 = "AWAY_OR_OVER_2_5"
    HOME_OR_OVER_2_5 = "HOME_OR_OVER_2_5"
    HOME_WIN_EITHER_HALF = "HOME_WIN_EITHER_HALF"
    AWAY_WIN_EITHER_HALF = "AWAY_WIN_EITHER_HALF"
    DOUBLE_CHANCE = "DOUBLE_CHANCE"
    BTTS = "BTTS"
    DRAW_NO_BET = "DRAW_NO_BET"
    HOME_WIN_TO_NIL = "HOME_WIN_TO_NIL"
    AWAY_WIN_TO_NIL = "AWAY_WIN_TO_NIL"
    MATCH_RESULT_1UP = "MATCH_RESULT_1UP"
    MATCH_RESULT_2UP = "MATCH_RESULT_2UP"


class OutcomeId(str, Enum):
    HOME = "HOME"
    DRAW = "DRAW"
    AWAY = "AWAY"
    YES = "YES"
    NO = "NO"
    OVER = "OVER"
    UNDER = "UNDER"
    HOME_OR_DRAW = "HOME_OR_DRAW"
    DRAW_OR_AWAY = "DRAW_OR_AWAY"
    HOME_OR_AWAY = "HOME_OR_AWAY"


class MarketFamily(str, Enum):
    MATCH_RESULT = "MATCH_RESULT"
    ASIAN_HANDICAP = "ASIAN_HANDICAP"
    TOTAL_GOALS = "TOTAL_GOALS"
    RESULT_OR_TOTALS = "RESULT_OR_TOTALS"
    WIN_EITHER_HALF = "WIN_EITHER_HALF"
    DOUBLE_CHANCE = "DOUBLE_CHANCE"
    BTTS = "BTTS"
    DRAW_NO_BET = "DRAW_NO_BET"
    WIN_TO_NIL = "WIN_TO_NIL"
    EARLY_PAYOUT = "EARLY_PAYOUT"


class DecisionStatus(str, Enum):
    ANALYTICAL_CANDIDATE = "ANALYTICAL_CANDIDATE"
    BET = "BET"
    NO_BET = "NO_BET"


@dataclass(frozen=True)
class MarketDefinition:
    market_id: MarketId
    family: MarketFamily
    display_name: str
    settlement_semantics: str
    supported_outcomes: Tuple[OutcomeId, ...]
    aliases: Tuple[str, ...] = ()
    line_required: bool = False


@dataclass(frozen=True)
class CanonicalSelection:
    market_id: MarketId
    outcome_id: OutcomeId
    display_label: str
    selection_display_name: str
    line: Optional[float] = None


MARKET_REGISTRY: Dict[MarketId, MarketDefinition] = {
    MarketId.MATCH_RESULT: MarketDefinition(
        market_id=MarketId.MATCH_RESULT,
        family=MarketFamily.MATCH_RESULT,
        display_name="1X2",
        settlement_semantics=(
            "Settles on the full-time result after regulation: home win, draw, "
            "or away win. Extra time and penalties are excluded."
        ),
        supported_outcomes=(OutcomeId.HOME, OutcomeId.DRAW, OutcomeId.AWAY),
        aliases=("1X2", "MATCH_RESULT_1X2", "FULL_TIME_RESULT"),
    ),
    MarketId.ASIAN_HANDICAP: MarketDefinition(
        market_id=MarketId.ASIAN_HANDICAP,
        family=MarketFamily.ASIAN_HANDICAP,
        display_name="Asian Handicap",
        settlement_semantics=(
            "Applies the stated handicap line to the selected team's full-time "
            "regulation score before comparison. Quarter lines may split stakes; "
            "this registry currently serializes the offered line without inventing it."
        ),
        supported_outcomes=(OutcomeId.HOME, OutcomeId.AWAY),
        aliases=("AH", "HANDICAP"),
        line_required=True,
    ),
    MarketId.TOTAL_GOALS: MarketDefinition(
        market_id=MarketId.TOTAL_GOALS,
        family=MarketFamily.TOTAL_GOALS,
        display_name="Over/Under Goals",
        settlement_semantics=(
            "Settles on whether total regulation-time goals are over or under "
            "the stated line."
        ),
        supported_outcomes=(OutcomeId.OVER, OutcomeId.UNDER),
        aliases=("OVER_UNDER", "OVER/UNDER", "TOTALS"),
        line_required=True,
    ),
    MarketId.DRAW_OR_OVER_2_5: MarketDefinition(
        market_id=MarketId.DRAW_OR_OVER_2_5,
        family=MarketFamily.RESULT_OR_TOTALS,
        display_name="Draw or Over 2.5",
        settlement_semantics=(
            "YES wins when the regulation-time result is a draw or total goals "
            "exceed 2.5; NO wins only when neither condition occurs."
        ),
        supported_outcomes=(OutcomeId.YES, OutcomeId.NO),
        aliases=("DRAW_OR_OVER_25",),
    ),
    MarketId.AWAY_OR_OVER_2_5: MarketDefinition(
        market_id=MarketId.AWAY_OR_OVER_2_5,
        family=MarketFamily.RESULT_OR_TOTALS,
        display_name="Away or Over 2.5",
        settlement_semantics=(
            "YES wins when the away team wins in regulation or total goals "
            "exceed 2.5; NO wins only when neither condition occurs."
        ),
        supported_outcomes=(OutcomeId.YES, OutcomeId.NO),
        aliases=("AWAY_OR_OVER_25",),
    ),
    MarketId.HOME_OR_OVER_2_5: MarketDefinition(
        market_id=MarketId.HOME_OR_OVER_2_5,
        family=MarketFamily.RESULT_OR_TOTALS,
        display_name="Home Team or Over 2.5",
        settlement_semantics=(
            "YES wins when the home team wins in regulation or total goals "
            "exceed 2.5; NO wins only when neither condition occurs."
        ),
        supported_outcomes=(OutcomeId.YES, OutcomeId.NO),
        aliases=("HOME_OR_OVER_25",),
    ),
    MarketId.HOME_WIN_EITHER_HALF: MarketDefinition(
        market_id=MarketId.HOME_WIN_EITHER_HALF,
        family=MarketFamily.WIN_EITHER_HALF,
        display_name="Home Team to Win Either Half",
        settlement_semantics=(
            "YES wins when the home team scores more goals than the away team "
            "in at least one individual half; NO wins otherwise."
        ),
        supported_outcomes=(OutcomeId.YES, OutcomeId.NO),
        aliases=(
            "WIN_EITHER_HALF_HOME",
            "HOME_WIN_EITHER_HALF",
            "HOME_TEAM_WIN_HALF",
        ),
    ),
    MarketId.AWAY_WIN_EITHER_HALF: MarketDefinition(
        market_id=MarketId.AWAY_WIN_EITHER_HALF,
        family=MarketFamily.WIN_EITHER_HALF,
        display_name="Away Team to Win Either Half",
        settlement_semantics=(
            "YES wins when the away team scores more goals than the home team "
            "in at least one individual half; NO wins otherwise."
        ),
        supported_outcomes=(OutcomeId.YES, OutcomeId.NO),
        aliases=(
            "WIN_EITHER_HALF_AWAY",
            "AWAY_WIN_EITHER_HALF",
            "AWAY_TEAM_WIN_HALF",
        ),
    ),
    MarketId.DOUBLE_CHANCE: MarketDefinition(
        market_id=MarketId.DOUBLE_CHANCE,
        family=MarketFamily.DOUBLE_CHANCE,
        display_name="Double Chance",
        settlement_semantics=(
            "Settles on two covered regulation-time results: 1X covers home or "
            "draw, X2 covers draw or away, and 12 covers home or away."
        ),
        supported_outcomes=(
            OutcomeId.HOME_OR_DRAW,
            OutcomeId.DRAW_OR_AWAY,
            OutcomeId.HOME_OR_AWAY,
        ),
        aliases=("DC",),
    ),
    MarketId.BTTS: MarketDefinition(
        market_id=MarketId.BTTS,
        family=MarketFamily.BTTS,
        display_name="GG/NG (BTTS)",
        settlement_semantics=(
            "YES wins when both teams score at least one regulation-time goal; "
            "NO wins when either team fails to score."
        ),
        supported_outcomes=(OutcomeId.YES, OutcomeId.NO),
        aliases=("GG_NG", "GG/NG", "BOTH_TEAMS_TO_SCORE"),
    ),
    MarketId.DRAW_NO_BET: MarketDefinition(
        market_id=MarketId.DRAW_NO_BET,
        family=MarketFamily.DRAW_NO_BET,
        display_name="Draw No Bet",
        settlement_semantics=(
            "The selected team must win in regulation; a draw voids the stake "
            "and a loss loses the stake."
        ),
        supported_outcomes=(OutcomeId.HOME, OutcomeId.AWAY),
        aliases=("DNB",),
    ),
    MarketId.HOME_WIN_TO_NIL: MarketDefinition(
        market_id=MarketId.HOME_WIN_TO_NIL,
        family=MarketFamily.WIN_TO_NIL,
        display_name="Home Team to Win to Nil",
        settlement_semantics=(
            "YES wins only when the home team wins in regulation and the away "
            "team scores zero; NO wins otherwise."
        ),
        supported_outcomes=(OutcomeId.YES, OutcomeId.NO),
        aliases=("HOME_TEAM_WIN_TO_NIL",),
    ),
    MarketId.AWAY_WIN_TO_NIL: MarketDefinition(
        market_id=MarketId.AWAY_WIN_TO_NIL,
        family=MarketFamily.WIN_TO_NIL,
        display_name="Away Team to Win to Nil",
        settlement_semantics=(
            "YES wins only when the away team wins in regulation and the home "
            "team scores zero; NO wins otherwise."
        ),
        supported_outcomes=(OutcomeId.YES, OutcomeId.NO),
        aliases=("AWAY_TEAM_WIN_TO_NIL",),
    ),
    MarketId.MATCH_RESULT_1UP: MarketDefinition(
        market_id=MarketId.MATCH_RESULT_1UP,
        family=MarketFamily.EARLY_PAYOUT,
        display_name="1X2 - 1UP",
        settlement_semantics=(
            "SportyBet Home/Away settles as won on an irreversible one-goal "
            "lead trigger or ordinary regulation-time victory; Draw settles "
            "from the regulation-time full-time result. The three selections "
            "are overlapping events."
        ),
        supported_outcomes=(OutcomeId.HOME, OutcomeId.DRAW, OutcomeId.AWAY),
        aliases=("1X2_1UP",),
    ),
    MarketId.MATCH_RESULT_2UP: MarketDefinition(
        market_id=MarketId.MATCH_RESULT_2UP,
        family=MarketFamily.EARLY_PAYOUT,
        display_name="1X2 - 2UP",
        settlement_semantics=(
            "SportyBet Home/Away settles as won on an irreversible two-goal "
            "lead trigger or ordinary regulation-time victory; Draw settles "
            "from the regulation-time full-time result. The three selections "
            "are overlapping events."
        ),
        supported_outcomes=(OutcomeId.HOME, OutcomeId.DRAW, OutcomeId.AWAY),
        aliases=("1X2_2UP",),
    ),
}


def _normalize_identifier(value: Any) -> str:
    if isinstance(value, Enum):
        value = value.value
    return re.sub(r"[^A-Z0-9]+", "_", str(value).strip().upper()).strip("_")


_MARKET_ALIASES: Dict[str, MarketId] = {}
for _market_id, _definition in MARKET_REGISTRY.items():
    for _alias in (
        _market_id.value,
        _definition.display_name,
        *_definition.aliases,
    ):
        _MARKET_ALIASES[_normalize_identifier(_alias)] = _market_id


_OUTCOME_ALIASES: Dict[str, OutcomeId] = {
    "HOME": OutcomeId.HOME,
    "HOME_WIN": OutcomeId.HOME,
    "1": OutcomeId.HOME,
    "DRAW": OutcomeId.DRAW,
    "X": OutcomeId.DRAW,
    "AWAY": OutcomeId.AWAY,
    "AWAY_WIN": OutcomeId.AWAY,
    "2": OutcomeId.AWAY,
    "YES": OutcomeId.YES,
    "Y": OutcomeId.YES,
    "NO": OutcomeId.NO,
    "N": OutcomeId.NO,
    "OVER": OutcomeId.OVER,
    "UNDER": OutcomeId.UNDER,
    "HOME_OR_DRAW": OutcomeId.HOME_OR_DRAW,
    "1X": OutcomeId.HOME_OR_DRAW,
    "DRAW_OR_AWAY": OutcomeId.DRAW_OR_AWAY,
    "X2": OutcomeId.DRAW_OR_AWAY,
    "HOME_OR_AWAY": OutcomeId.HOME_OR_AWAY,
    "12": OutcomeId.HOME_OR_AWAY,
}


def canonicalize_market_id(value: Any) -> MarketId:
    normalized = _normalize_identifier(value)
    try:
        return _MARKET_ALIASES[normalized]
    except KeyError as exc:
        raise UnknownMarketError(f"Unknown market identifier: {value!r}") from exc


def canonicalize_outcome_id(value: Any) -> OutcomeId:
    normalized = _normalize_identifier(value)
    try:
        return _OUTCOME_ALIASES[normalized]
    except KeyError as exc:
        raise UnknownOutcomeError(f"Unknown outcome identifier: {value!r}") from exc


def validate_selection(
    market_id: Any,
    outcome_id: Any,
    line: Optional[float] = None,
) -> Tuple[MarketId, OutcomeId, Optional[float]]:
    canonical_market = canonicalize_market_id(market_id)
    canonical_outcome = canonicalize_outcome_id(outcome_id)
    definition = MARKET_REGISTRY[canonical_market]

    if canonical_outcome not in definition.supported_outcomes:
        raise InvalidSelectionError(
            f"{canonical_outcome.value} is not valid for {canonical_market.value}"
        )

    if definition.line_required and line is None:
        raise InvalidSelectionError(
            f"{canonical_market.value} requires an explicit line"
        )
    if not definition.line_required and line is not None:
        raise InvalidSelectionError(
            f"{canonical_market.value} does not accept a separate line"
        )

    canonical_line = None
    if line is not None:
        if isinstance(line, bool):
            raise InvalidSelectionError("Selection line must be numeric")
        try:
            canonical_line = float(line)
        except (TypeError, ValueError) as exc:
            raise InvalidSelectionError("Selection line must be numeric") from exc
        if not math.isfinite(canonical_line):
            raise InvalidSelectionError("Selection line must be finite")

    return canonical_market, canonical_outcome, canonical_line


def _format_line(line: float) -> str:
    return f"{line:g}"


def _default_selection_names(
    market_id: MarketId,
    outcome_id: OutcomeId,
    line: Optional[float],
) -> Tuple[str, str]:
    if market_id == MarketId.MATCH_RESULT:
        label = {
            OutcomeId.HOME: "Home Win",
            OutcomeId.DRAW: "Draw",
            OutcomeId.AWAY: "Away Win",
        }[outcome_id]
        return label, label

    if market_id == MarketId.TOTAL_GOALS:
        label = f"{outcome_id.value.title()} {_format_line(line)}"
        return label, label

    if market_id == MarketId.ASIAN_HANDICAP:
        signed_line = f"{line:+g}"
        label = f"{outcome_id.value.title()} {signed_line}"
        return label, label

    if market_id == MarketId.DOUBLE_CHANCE:
        display_label = {
            OutcomeId.HOME_OR_DRAW: "Double Chance 1X",
            OutcomeId.DRAW_OR_AWAY: "Double Chance X2",
            OutcomeId.HOME_OR_AWAY: "Double Chance 12",
        }[outcome_id]
        selection_name = {
            OutcomeId.HOME_OR_DRAW: "Home or Draw",
            OutcomeId.DRAW_OR_AWAY: "Draw or Away",
            OutcomeId.HOME_OR_AWAY: "Home or Away",
        }[outcome_id]
        return display_label, selection_name

    if market_id == MarketId.BTTS:
        return f"BTTS {outcome_id.value.title()}", outcome_id.value.title()

    if market_id == MarketId.DRAW_NO_BET:
        label = f"Draw No Bet {outcome_id.value.title()}"
        return label, outcome_id.value.title()

    definition = MARKET_REGISTRY[market_id]
    if market_id in (MarketId.MATCH_RESULT_1UP, MarketId.MATCH_RESULT_2UP):
        return (
            f"{definition.display_name} {outcome_id.value.title()}",
            outcome_id.value.title(),
        )

    return (
        f"{definition.display_name} {outcome_id.value.title()}",
        outcome_id.value.title(),
    )


def make_selection(
    market_id: Any,
    outcome_id: Any,
    *,
    line: Optional[float] = None,
    display_label: Optional[str] = None,
    selection_display_name: Optional[str] = None,
) -> CanonicalSelection:
    market, outcome, canonical_line = validate_selection(
        market_id,
        outcome_id,
        line,
    )
    default_label, default_selection_name = _default_selection_names(
        market,
        outcome,
        canonical_line,
    )
    return CanonicalSelection(
        market_id=market,
        outcome_id=outcome,
        line=canonical_line,
        display_label=display_label or default_label,
        selection_display_name=(
            selection_display_name or default_selection_name
        ),
    )


_LEGACY_SELECTIONS: Dict[str, CanonicalSelection] = {}


def _register_legacy(
    selection: CanonicalSelection,
    *identifiers: str,
) -> None:
    for identifier in identifiers:
        _LEGACY_SELECTIONS[_normalize_identifier(identifier)] = selection


_register_legacy(
    make_selection(MarketId.MATCH_RESULT, OutcomeId.HOME),
    "HOME_WIN",
    "1X2_HOME",
)
_register_legacy(
    make_selection(MarketId.MATCH_RESULT, OutcomeId.DRAW),
    "DRAW",
    "1X2_DRAW",
)
_register_legacy(
    make_selection(MarketId.MATCH_RESULT, OutcomeId.AWAY),
    "AWAY_WIN",
    "1X2_AWAY",
)

_register_legacy(
    make_selection(MarketId.DOUBLE_CHANCE, OutcomeId.HOME_OR_DRAW),
    "DC_1X",
)
_register_legacy(
    make_selection(MarketId.DOUBLE_CHANCE, OutcomeId.DRAW_OR_AWAY),
    "DC_X2",
)
_register_legacy(
    make_selection(MarketId.DOUBLE_CHANCE, OutcomeId.HOME_OR_AWAY),
    "DC_12",
)

for _legacy_id, _outcome, _line in (
    ("AH_HOME_MINUS_05", OutcomeId.HOME, -0.5),
    ("AH_AWAY_PLUS_05", OutcomeId.AWAY, 0.5),
    ("AH_HOME_PLUS_05", OutcomeId.HOME, 0.5),
    ("AH_AWAY_MINUS_05", OutcomeId.AWAY, -0.5),
    ("AH_HOME_MINUS_15", OutcomeId.HOME, -1.5),
    ("AH_AWAY_PLUS_15", OutcomeId.AWAY, 1.5),
    ("AH_HOME_PLUS_15", OutcomeId.HOME, 1.5),
    ("AH_AWAY_MINUS_15", OutcomeId.AWAY, -1.5),
    ("AH_HOME_PLUS_25", OutcomeId.HOME, 2.5),
    ("AH_AWAY_PLUS_25", OutcomeId.AWAY, 2.5),
    ("AH_HOME_MINUS_25", OutcomeId.HOME, -2.5),
    ("AH_AWAY_MINUS_25", OutcomeId.AWAY, -2.5),
):
    _register_legacy(
        make_selection(MarketId.ASIAN_HANDICAP, _outcome, line=_line),
        _legacy_id,
    )

_register_legacy(
    make_selection(
        MarketId.ASIAN_HANDICAP,
        OutcomeId.HOME,
        line=1.5,
    ),
    "ASIAN_HANDICAP_HOME_PLUS_1_5",
)
_register_legacy(
    make_selection(MarketId.ASIAN_HANDICAP, OutcomeId.AWAY, line=1.5),
    "ASIAN_HANDICAP_AWAY_PLUS_1_5",
)

for _legacy_id, _outcome, _line in (
    ("OVER_05", OutcomeId.OVER, 0.5),
    ("OVER_15", OutcomeId.OVER, 1.5),
    ("OVER_25", OutcomeId.OVER, 2.5),
    ("UNDER_25", OutcomeId.UNDER, 2.5),
    ("UNDER_35", OutcomeId.UNDER, 3.5),
    ("UNDER_45", OutcomeId.UNDER, 4.5),
    ("UNDER_55", OutcomeId.UNDER, 5.5),
):
    _register_legacy(
        make_selection(MarketId.TOTAL_GOALS, _outcome, line=_line),
        _legacy_id,
    )

for _market_id, _legacy_id in (
    (MarketId.HOME_OR_OVER_2_5, "HOME_OR_OVER_25"),
    (MarketId.AWAY_OR_OVER_2_5, "AWAY_OR_OVER_25"),
    (MarketId.DRAW_OR_OVER_2_5, "DRAW_OR_OVER_25"),
):
    _register_legacy(
        make_selection(_market_id, OutcomeId.YES),
        _legacy_id,
    )

_home_half_yes = make_selection(
    MarketId.HOME_WIN_EITHER_HALF,
    OutcomeId.YES,
)
_register_legacy(
    _home_half_yes,
    "WIN_EITHER_HALF_HOME_YES",
    "HOME_WIN_EITHER_HALF",
    "HOME_TEAM_WIN_HALF",
    "HOME_TEAM_WIN_EITHER_HALF_YES",
)
_register_legacy(
    make_selection(MarketId.HOME_WIN_EITHER_HALF, OutcomeId.NO),
    "WIN_EITHER_HALF_HOME_NO",
    "HOME_TEAM_WIN_EITHER_HALF_NO",
)
_register_legacy(
    make_selection(MarketId.AWAY_WIN_EITHER_HALF, OutcomeId.YES),
    "WIN_EITHER_HALF_AWAY_YES",
    "AWAY_WIN_EITHER_HALF",
    "AWAY_TEAM_WIN_HALF",
    "AWAY_TEAM_WIN_EITHER_HALF_YES",
)
_register_legacy(
    make_selection(MarketId.AWAY_WIN_EITHER_HALF, OutcomeId.NO),
    "WIN_EITHER_HALF_AWAY_NO",
    "AWAY_TEAM_WIN_EITHER_HALF_NO",
)

_register_legacy(
    make_selection(MarketId.BTTS, OutcomeId.YES),
    "GG_YES",
    "BTTS_YES",
)
_register_legacy(
    make_selection(MarketId.BTTS, OutcomeId.NO),
    "GG_NO",
    "BTTS_NO",
)
_register_legacy(
    make_selection(MarketId.DRAW_NO_BET, OutcomeId.HOME),
    "DNB_HOME",
)
_register_legacy(
    make_selection(MarketId.DRAW_NO_BET, OutcomeId.AWAY),
    "DNB_AWAY",
)

for _market_id, _prefix in (
    (MarketId.HOME_WIN_TO_NIL, "HOME"),
    (MarketId.AWAY_WIN_TO_NIL, "AWAY"),
):
    _register_legacy(
        make_selection(_market_id, OutcomeId.YES),
        f"{_prefix}_WIN_TO_NIL_YES",
    )
    _register_legacy(
        make_selection(_market_id, OutcomeId.NO),
        f"{_prefix}_WIN_TO_NIL_NO",
    )

for _market_id, _prefix in (
    (MarketId.MATCH_RESULT_1UP, "1X2_1UP"),
    (MarketId.MATCH_RESULT_2UP, "1X2_2UP"),
):
    _register_legacy(
        make_selection(_market_id, OutcomeId.HOME),
        f"{_prefix}_HOME",
    )
    _register_legacy(
        make_selection(_market_id, OutcomeId.DRAW),
        f"{_prefix}_DRAW",
    )
    _register_legacy(
        make_selection(_market_id, OutcomeId.AWAY),
        f"{_prefix}_AWAY",
    )


def resolve_legacy_selection(identifier: Any) -> CanonicalSelection:
    normalized = _normalize_identifier(identifier)
    try:
        return _LEGACY_SELECTIONS[normalized]
    except KeyError as exc:
        raise UnknownSelectionError(
            f"Unknown legacy selection identifier: {identifier!r}"
        ) from exc


def serialize_selection(
    selection: CanonicalSelection,
    *,
    display_label: Optional[str] = None,
) -> Dict[str, Any]:
    market, outcome, line = validate_selection(
        selection.market_id,
        selection.outcome_id,
        selection.line,
    )
    definition = MARKET_REGISTRY[market]
    return {
        "market_id": market.value,
        "outcome_id": outcome.value,
        "line": line,
        "display_label": display_label or selection.display_label,
        "market_family": definition.family.value,
        "market_display_name": definition.display_name,
        "outcome_display_name": selection.selection_display_name,
        "settlement_semantics": definition.settlement_semantics,
    }


def serialize_leg(leg: Mapping[str, Any]) -> Dict[str, Any]:
    """Validate and serialize one leg without changing its selection identity."""
    if not isinstance(leg, Mapping):
        raise InvalidSelectionError("A slip leg must be a mapping")
    if not leg.get("fixture_id") and not leg.get("fixture"):
        raise InvalidSelectionError(
            "A slip leg requires fixture_id or fixture text"
        )

    has_market_id = leg.get("market_id") is not None
    has_outcome_id = leg.get("outcome_id") is not None
    if has_market_id != has_outcome_id:
        raise InvalidSelectionError(
            "Canonical market_id and outcome_id must be provided together"
        )

    if has_market_id and has_outcome_id:
        selection = make_selection(
            leg["market_id"],
            leg["outcome_id"],
            line=leg.get("line"),
            display_label=leg.get("display_label"),
            selection_display_name=leg.get("outcome_display_name")
            or leg.get("selection"),
        )
        if leg.get("verdict"):
            legacy_selection = resolve_legacy_selection(leg["verdict"])
            canonical_identity = (
                selection.market_id,
                selection.outcome_id,
                selection.line,
            )
            legacy_identity = (
                legacy_selection.market_id,
                legacy_selection.outcome_id,
                legacy_selection.line,
            )
            if canonical_identity != legacy_identity:
                raise InvalidSelectionError(
                    "Canonical selection conflicts with legacy verdict "
                    f"{leg['verdict']!r}"
                )
    elif leg.get("verdict"):
        selection = resolve_legacy_selection(leg["verdict"])
    else:
        raise InvalidSelectionError(
            "A slip leg requires canonical market_id/outcome_id fields "
            "or a registered legacy verdict"
        )

    serialized = dict(leg)
    serialized.update(
        serialize_selection(
            selection,
            display_label=leg.get("display_label"),
        )
    )
    return serialized


__all__ = [
    "CanonicalSelection",
    "DecisionStatus",
    "InvalidSelectionError",
    "MARKET_REGISTRY",
    "MarketDefinition",
    "MarketFamily",
    "MarketId",
    "MarketRegistryError",
    "OutcomeId",
    "UnknownMarketError",
    "UnknownOutcomeError",
    "UnknownSelectionError",
    "canonicalize_market_id",
    "canonicalize_outcome_id",
    "make_selection",
    "resolve_legacy_selection",
    "serialize_leg",
    "serialize_selection",
    "validate_selection",
]
