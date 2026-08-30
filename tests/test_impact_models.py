from __future__ import annotations

import pytest
from pydantic import ValidationError

from contextforge.impact import (
    ImpactedSymbol,
    ImpactReport,
    ImpactSeed,
    ImpactStep,
    RiskLevel,
)
from contextforge.models import EdgeType


def _seed() -> ImpactSeed:
    return ImpactSeed(
        unit_id="function:app/routing.py:join_path",
        qualname="app.routing.join_path",
        path="app/routing.py",
        start_line=4,
        end_line=6,
    )


def _symbol() -> ImpactedSymbol:
    return ImpactedSymbol(
        unit_id="method:app/routing.py:Mount.resolve",
        qualname="app.routing.Mount.resolve",
        path="app/routing.py",
        start_line=12,
        end_line=14,
        distance=1,
        path_confidence=0.72,
        relationship_path=(
            ImpactStep(
                source_id="method:app/routing.py:Mount.resolve",
                target_id="function:app/routing.py:join_path",
                edge_type=EdgeType.CALLS,
                confidence=0.72,
            ),
        ),
        community=0,
    )


def _report(**overrides: object) -> ImpactReport:
    values: dict[str, object] = {
        "repository": "sample",
        "mode": "symbol",
        "target": "app.routing.join_path",
        "max_depth": 3,
        "limit": 200,
        "seeds": (_seed(),),
        "impacted": (_symbol(),),
        "related_tests": (),
        "impacted_files": ("app/routing.py",),
        "changed_files": (),
        "communities": (0,),
        "unresolved": (),
        "risk_level": RiskLevel.LOW,
        "risk_reasons": ("1 impacted production symbol",),
        "truncated": False,
    }
    values.update(overrides)
    return ImpactReport.model_validate(values)


def test_impact_report_serializes_stable_public_schema() -> None:
    report = _report()

    payload = report.model_dump(mode="json")

    assert payload["risk_level"] == "low"
    assert payload["impacted"][0]["relationship_path"][0]["edge_type"] == "CALLS"
    assert report.impacted_files == ("app/routing.py",)
    assert report.communities == (0,)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("max_depth", 4),
        ("limit", 0),
    ],
)
def test_impact_report_rejects_out_of_bounds_limits(field: str, value: int) -> None:
    with pytest.raises(ValidationError):
        _report(**{field: value})


def test_impacted_symbol_rejects_invalid_distance_and_confidence() -> None:
    values = _symbol().model_dump()
    values["distance"] = 0
    values["path_confidence"] = 1.1

    with pytest.raises(ValidationError):
        ImpactedSymbol.model_validate(values)
