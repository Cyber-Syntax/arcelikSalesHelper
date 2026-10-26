from decimal import Decimal as D

from arcelikSalesHelper import strings as T
from arcelikSalesHelper.application.calculator import (
    LineForm,
    Section,
    TransactionEvaluation,
    evaluate_line,
    evaluate_transaction,
)
from arcelikSalesHelper.domain.models import POS_LABEL, ManagerMode


def form(**kw: object) -> LineForm:
    base: dict[str, object] = dict(
        product_name="Fridge",
        regular_price="5.000,00",
        website_discounted_price="4.000,00",
    )
    base.update(kw)
    return LineForm(**base)  # type: ignore[arg-type]


def two_forms() -> list[LineForm]:
    return [
        form(manager_value="3.000,00"),
        form(
            product_name="Washer", quantity=3, regular_price="6.000,00",
            website_discounted_price="5.000,00", gift_selected=True, gift_name="Vacuum",
            manager_value="4.500,00",
        ),
    ]  # fmt: skip


def totals(ev: TransactionEvaluation) -> dict[str, str]:
    return {r.label: r.value for s in ev.totals_sections for r in s.rows}


def val(section: Section, label: str) -> str:
    return next(r.value for r in section.rows if r.label == label)


def test_mixed_gift_and_no_gift_totals_are_formatted() -> None:
    ev = evaluate_transaction(two_forms())
    assert ev.valid
    t = totals(ev)
    assert t[T.LBL_TOTAL_DISCOUNT] == "4.000,00 TL"
    assert t[T.LBL_TOTAL_POS] == "20.500,00 TL"
    assert POS_LABEL in [s.title for s in ev.totals_sections]
    assert ev.result is not None
    assert [r.discount_amount for r in ev.result.lines] == [D(1000), D(3000)]
    assert ev.result.totals.discount_amount.value == D(4000)


def test_missing_manager_value_gives_explicit_na_with_line_numbers() -> None:
    forms = two_forms()
    forms.append(
        form(
            product_name="Dryer",
            regular_price="2.000,00",
            website_discounted_price="1.500,00",
        )
    )
    t = totals(evaluate_transaction(forms))
    assert (
        t[T.LBL_TOTAL_DISCOUNT] == "4.500,00 TL"
    )
    assert t[T.LBL_TOTAL_POS] == "Yok: yönetici değeri eksik (satır 3)"


def test_zero_website_price_has_no_discount_in_transaction_pos():
    line = form(
        regular_price="38.299,00",
        website_discounted_price="0,00",
        manager_value="32.000,00",
    )
    ev = evaluate_transaction([line])
    assert ev.result is not None
    assert ev.result.totals.discount_amount.value == D("0")
    assert ev.result.totals.pos.value == D("32000")
    assert totals(ev)[T.LBL_TOTAL_DISCOUNT] == "0,00 TL"
    assert totals(ev)[T.LBL_TOTAL_POS] == "32.000,00 TL"


def test_na_lists_every_missing_line() -> None:
    forms = [form(), form(manager_value="3.000,00"), form()]
    assert totals(evaluate_transaction(forms))[T.LBL_TOTAL_POS] == (
        "Yok: yönetici değeri eksik (satırlar 1, 3)"
    )


def test_an_invalid_line_blocks_totals_but_not_the_other_cards() -> None:
    ev = evaluate_transaction(
        [form(manager_value="3.000,00"), form(website_discounted_price="bad")]
    )
    assert not ev.valid and ev.totals_sections == ()
    assert ev.lines[0].valid and not ev.lines[1].valid
    assert ev.pending_reason is not None and "2" in ev.pending_reason


def test_empty_transaction_has_a_reason_and_no_totals() -> None:
    ev = evaluate_transaction([])
    assert (
        not ev.valid and ev.pending_reason == "En az bir ürün satırı ekleyin."
    )


def test_forms_are_kept_for_the_snapshot() -> None:
    forms = two_forms()
    assert evaluate_transaction(forms).forms == tuple(forms)


def test_warning_carries_its_line_index() -> None:
    result = evaluate_line(form(manager_value="4.500,00"), 4).result
    assert result is not None and [w.line_index for w in result.warnings] == [
        4
    ]


# ---- options --------------------------------------------------------------


def test_no_gift_line_shows_only_final_website_offer_amounts() -> (
    None
):
    ev = evaluate_transaction([form(manager_value="3.000,00")])
    assert ev.lines[0].view is not None
    card = ev.lines[0].view.card
    assert card.gift_option is None
    assert val(card.website_option, "Web sitesi indirimli toplam") == "4.000,00 TL"
    assert val(card.website_option, T.LBL_WEBSITE_OFFER_TOTAL) == "3.600,00 TL"
    assert val(card.website_option, T.LBL_DISCOUNT_AMOUNT) == "1.000,00 TL"
    assert val(card.prices, "Yönetici toplamı") == "3.000,00 TL"
    assert [row.label for row in card.pos.rows] == [T.LBL_POS_AMOUNT]
    assert all("baz" not in row.label.lower() for row in card.website_option.rows)


def test_gift_line_compares_both_final_offer_amounts() -> (
    None
):
    ev = evaluate_transaction(two_forms())
    view = ev.lines[1].view
    assert view is not None and view.card.gift_option is not None
    site, gift = view.card.website_option, view.card.gift_option
    assert val(gift, "Hediye") == "Vacuum"
    assert val(gift, "Normal fiyat toplamı") == "18.000,00 TL"
    assert val(gift, T.LBL_FIRST_PRICE_TEN_PERCENT) == "16.200,00 TL"
    assert val(site, "Web sitesi indirimli toplam") == "15.000,00 TL"
    assert val(site, T.LBL_WEBSITE_OFFER_TOTAL) == "13.500,00 TL"
    assert val(site, T.LBL_DISCOUNT_AMOUNT) == "3.000,00 TL"
    assert val(view.card.prices, "Yönetici toplamı") == "13.500,00 TL"
    assert [row.label for row in site.rows] == [
        T.LBL_WEBSITE_DISCOUNTED_TOTAL,
        T.LBL_DISCOUNT_AMOUNT,
        T.LBL_WEBSITE_OFFER_TOTAL,
    ]
    assert [row.label for row in gift.rows] == [
        T.LBL_GIFT,
        T.LBL_REGULAR_TOTAL,
        T.LBL_FIRST_PRICE_TEN_PERCENT,
    ]
    assert all(row.label != T.LBL_DISCOUNT_AMOUNT for row in gift.rows)


def test_named_but_unselected_gift_shows_only_final_amounts() -> None:
    ev = evaluate_transaction(
        [form(gift_name="Vacuum", manager_value="3.000,00")]
    )
    view = ev.lines[0].view
    assert view is not None and view.card.gift_option is not None
    assert val(view.card.gift_option, T.LBL_FIRST_PRICE_TEN_PERCENT) == "4.500,00 TL"
    assert val(view.card.prices, "Yönetici toplamı") == "3.000,00 TL"
    assert view.card.gift_option.note is None


def test_total_line_mode_shows_the_final_manager_total_only() -> None:
    ev = evaluate_transaction(
        [
            form(
                quantity=3,
                manager_value="12.000,00",
                manager_mode=ManagerMode.LINE,
            )
        ]
    )
    view = ev.lines[0].view
    assert view is not None
    assert val(view.card.prices, "Yönetici toplamı") == "12.000,00 TL"


def test_option_panels_never_rank_or_recommend() -> None:
    ev = evaluate_transaction(two_forms())
    for line_eval in ev.lines:
        assert line_eval.view is not None
        text = repr(line_eval.view.card).lower()
        assert (
            "recommend" not in text
            and "best" not in text
            and "winner" not in text
        )
    assert D(0) == 0  # keeps the Decimal import used for type clarity
