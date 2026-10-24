from decimal import Decimal as D

from arcelikSalesHelper.domain.products import (
    ProductDraft,
    name_key,
    normalize_draft,
    validate_draft,
)


def test_name_key_collapses_whitespace_and_casefolds() -> None:
    assert name_key("  Arçelik   Fridge ") == "arçelik fridge"


def test_name_key_is_unicode_normalisation_insensitive() -> None:
    assert name_key("Ar\u00e7elik") == name_key(
        "Arc\u0327elik"
    )  # composed vs decomposed ç


def test_normalize_draft_blanks_become_none() -> None:
    d = normalize_draft(ProductDraft("  A  B ", D(1), D(1), "   ", "\n"))
    assert d.name == "A B"
    assert d.default_gift_name is None
    assert d.notes is None


def test_validate_draft_collects_all_errors() -> None:
    errs = validate_draft(ProductDraft("", D(-1), D("NaN")))
    assert {e.code for e in errs} == {
        "name_required",
        "regular_price_invalid",
        "website_price_invalid",
    }


def test_validate_draft_accepts_zero_prices() -> None:
    assert validate_draft(ProductDraft("Free", D(0), D(0))) == ()
