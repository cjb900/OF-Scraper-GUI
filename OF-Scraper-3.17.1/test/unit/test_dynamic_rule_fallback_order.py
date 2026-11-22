"""When the chosen dynamic rule source fails, the others are tried in the
order OF-Scraper-Community uses (digitalcriminals, rafa, xagler; riley was
dropped), skipping the source already tried."""

import types

import pytest

import ofscraper.utils.auth.request as request

RULE = ("rule", "1234", "checksum")
NAMES = ["digitalcriminals", "riley", "datawhores", "xagler", "rafa"]


@pytest.fixture
def sources(monkeypatch):
    calls = []
    answers = {}

    def make(name):
        def fetch():
            calls.append(name)
            answer = answers.get(name, RuntimeError(f"{name} down"))
            if isinstance(answer, Exception):
                raise answer
            return answer

        return fetch

    for name in NAMES:
        monkeypatch.setattr(request, f"get_request_auth_{name}", make(name))
    monkeypatch.setattr(request, "curr_auth", None)
    monkeypatch.setattr(request, "last_check", None)
    monkeypatch.setattr(request.cache, "set", lambda *a, **k: None)

    def choose(name):
        monkeypatch.setattr(
            request.settings, "get_settings", lambda: types.SimpleNamespace(dynamic_rules=name)
        )

    return calls, answers, choose


def test_all_down_tries_the_three_fallbacks_in_order(sources):
    calls, _, choose = sources
    choose("datawhores")
    with pytest.raises(request.DynamicRuleUnavailable) as err:
        request.get_request_auth()
    assert calls == ["datawhores", "digitalcriminals", "rafa", "xagler"]
    assert [name for name, _ in err.value.failures] == calls


def test_the_chosen_source_is_not_tried_twice(sources):
    calls, _, choose = sources
    choose("rafa")
    with pytest.raises(request.DynamicRuleUnavailable):
        request.get_request_auth()
    assert calls == ["rafa", "digitalcriminals", "xagler"]


def test_first_working_fallback_is_used(sources):
    calls, answers, choose = sources
    answers["rafa"] = RULE
    choose("riley")
    assert request.get_request_auth() == RULE
    assert calls == ["riley", "digitalcriminals", "rafa"]
