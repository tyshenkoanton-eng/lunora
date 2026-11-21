"""G17-S2: минимальный контракт результата движка (решение Антона №5, 2026-11-21).

Каждая величина движка — `Result`: значение, правило (`rule_id` + версия), `stability`,
либо `not_computed` с причиной из ENGINE-SPEC §1.2. Полный `Signal` с голосованием — S4.
"""

import pytest

from lunora.engines import NOT_COMPUTED_REASONS, STABILITY_TAGS, Result, Rule


def test_reason_and_stability_vocabularies_match_spec():
    # ENGINE-SPEC §1.2: причины not_computed; ARCHITECTURE §4.5 + convention
    assert {
        "no_birth_time",
        "no_place",
        "no_sex",
        "not_applicable_latitude",
        "rule_not_formalized",
        "out_of_v1",
        "table_not_verified",
    } == NOT_COMPUTED_REASONS
    assert {"stable", "range", "undetermined", "convention"} == STABILITY_TAGS


def test_computed_result_carries_rule_and_stability():
    r = Result.computed(Rule("num.life_path", "0.1.0"), 8)
    assert r.value == 8
    assert r.rule.id == "num.life_path" and r.rule.version == "0.1.0"
    assert r.stability == "stable"
    assert r.not_computed is None
    assert r.is_computed


def test_not_computed_result_has_reason_and_no_value():
    r = Result.missing(Rule("num.psychomatrix", "0.1.0"), "rule_not_formalized")
    assert r.value is None
    assert r.not_computed == "rule_not_formalized"
    assert not r.is_computed


def test_unknown_reason_rejected():
    with pytest.raises(ValueError):
        Result.missing(Rule("x", "0.1.0"), "guessed")


def test_unknown_stability_rejected():
    with pytest.raises(ValueError):
        Result.computed(Rule("x", "0.1.0"), 1, stability="maybe")


def test_value_and_reason_are_exclusive():
    with pytest.raises(ValueError):
        Result(rule=Rule("x", "0.1.0"), value=1, not_computed="out_of_v1")


def test_rule_version_is_semver():
    with pytest.raises(ValueError):
        Rule("x", "v1")


def test_result_is_immutable():
    r = Result.computed(Rule("x", "0.1.0"), 1)
    with pytest.raises(AttributeError):
        r.value = 2  # type: ignore[misc]
