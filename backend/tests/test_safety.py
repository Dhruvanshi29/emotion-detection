"""Direct tests of the rule-based safety classifier."""
from __future__ import annotations

import pytest

from app.services.safety import classify


@pytest.mark.parametrize(
    "text",
    [
        "I want to kill myself",
        "I want to end my life tonight",
        "I've been thinking about suicide",
        "I don't want to live anymore",
        "planning to overdose",
    ],
)
def test_high_risk_detected(text):
    r = classify(text)
    assert r.level == "high"
    assert r.categories


@pytest.mark.parametrize(
    "text",
    [
        "I've been self-harming again",
        "I feel hopeless",
        "I had a panic attack today",
    ],
)
def test_medium_risk_detected(text):
    assert classify(text).level == "medium"


@pytest.mark.parametrize(
    "text",
    [
        "I'm feeling anxious about work",
        "I'm just so stressed",
        "I feel lonely",
    ],
)
def test_low_risk_detected(text):
    assert classify(text).level == "low"


@pytest.mark.parametrize(
    "text",
    [
        "",
        "Tell me a joke",
        "What is the weather like?",
    ],
)
def test_no_risk(text):
    assert classify(text).level == "none"
