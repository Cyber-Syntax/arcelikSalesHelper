from arcelikSalesHelper.application.calculator import (
    LineForm,
    evaluate_line,
    evaluate_transaction,
)
from arcelikSalesHelper.domain.models import ManagerMode, POS_LABEL


def form(**kwargs: object) -> LineForm:
    values: dict[str, object] = {
        "product_name": "Fridge",
        "regular_price": "5.000,00",
        "website_price": "4.000,00",
    }
    values.update(kwargs)
    return LineForm(**values)  # type: ignore[arg-type]


def row_values(evaluation):
    return {
        row.label: row.value
        for section in evaluation.totals_sections
        for row in section.rows
    }


def test_transaction_totals_and_pos_are_presented() -> None:
    evaluation = evaluate_transaction(
        [
            form(manager_value="3.000,00"),
            form(
                product_name="Washer",
                quantity=3,
                regular_price="6.000,00",
                website_price="5.000,00",
                gift_selected=True,
                gift_name="Vacuum",
                manager_value="4.500,00",
            ),
        ]
    )
    assert evaluation.valid
    values = row_values(evaluation)
    assert values["Regular total"] == "23.000,00 TL"
    assert values["Standard 10% scenario total"] == "19.800,00 TL"
    assert values["POS-entry total"] == "20.500,00 TL"
    assert POS_LABEL in [
        section.title for section in evaluation.totals_sections
    ]


def test_invalid_and_empty_transactions_have_pending_reasons() -> None:
    assert evaluate_transaction([]).pending_reason == (
        "Add at least one product line."
    )
    evaluation = evaluate_transaction(
        [form(manager_value="3.000,00"), form(coupon="9.000,00")]
    )
    assert not evaluation.valid
    assert "2" in (evaluation.pending_reason or "")
    assert evaluation.lines[0].valid
    assert not evaluation.lines[1].valid


def test_missing_manager_values_are_explicit() -> None:
    evaluation = evaluate_transaction([form(), form()])
    values = row_values(evaluation)
    assert values["Manager-provided total"] == (
        "n/a: missing manager value on lines 1, 2"
    )
    assert values["POS-entry total"] == (
        "n/a: missing manager value on lines 1, 2"
    )


def test_options_show_comparison_and_keep_manager_on_one_side() -> None:
    evaluation = evaluate_transaction(
        [form(gift_name="Vacuum", manager_value="3.000,00")]
    )
    view = evaluation.lines[0].view
    assert view is not None and view.card.gift_option is not None
    assert any(
        row.label == "Manager line total"
        for row in view.card.website_option.rows
    )
    assert any(
        row.label == "Manager-provided value"
        for row in view.card.gift_option.rows
    )
    assert "not selected" in (view.card.gift_option.note or "")


def test_line_index_and_total_manager_mode_are_preserved() -> None:
    result = evaluate_line(
        form(
            manager_value="4.500,00",
            manager_mode=ManagerMode.LINE,
        ),
        4,
    ).result
    assert result is not None
    assert [warning.line_index for warning in result.warnings] == [4]
    view = evaluate_line(
        form(
            quantity=3,
            manager_value="4.500,00",
            manager_mode=ManagerMode.LINE,
        )
    ).view
    assert view is not None
    assert any(
        row.label == "Manager value mode" and row.value == "Total line price"
        for row in view.card.website_option.rows
    )
