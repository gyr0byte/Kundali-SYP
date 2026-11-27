"""Offline gazetteer coverage and deterministic ranking."""

import pytest

from app.geo.nepal import RESULT_LIMIT, resolve_birthplace, search_birthplaces


@pytest.mark.parametrize(
    ("query", "ident"),
    [
        ("Kathmandu", 1283240),
        ("Katmandu", 1283240),
        ("काठमाडौं", 1283240),
        ("पोखरा", 1282898),
        ("Pokhara", 1282898),
        ("Waling", 1282616),
        ("Wāliṅ", 1282616),
    ],
)
def test_search_matches_source_names_and_aliases(query: str, ident: int) -> None:
    result = search_birthplaces(query)
    assert result[0] == resolve_birthplace(ident)
    assert result[0].timezone == "Asia/Kathmandu"
    assert result[0].context


def test_duplicate_names_and_bounded_repeatable_order() -> None:
    results = search_birthplaces("Rampur")
    duplicates = [place for place in results if place.name == "Rāmpur"]
    assert len(duplicates) > 1
    assert len({(place.context, place.latitude, place.longitude) for place in duplicates}) > 1
    assert len(results) <= RESULT_LIMIT
    assert results == search_birthplaces("  RAMPUR ")
    assert search_birthplaces("Rampur Udayapur")[0].id == 1282875
    assert search_birthplaces("zqqqqqqq") == []
    assert resolve_birthplace(1) is None


@pytest.mark.parametrize("query", ["", " ", "a", "123", "??", "\nKathmandu", "a" * 81])
def test_rejects_invalid_search_queries(query: str) -> None:
    with pytest.raises(ValueError, match="2 to 80"):
        search_birthplaces(query)
