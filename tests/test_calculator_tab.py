from decimal import Decimal as D
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QBoxLayout, QGroupBox, QLabel

from arcelikSalesHelper.application.calculator import TransactionEvaluation
from arcelikSalesHelper.ui.calculator_tab import CalculatorTab
from arcelikSalesHelper.ui.theme import (
    DEFAULT_FONT_SCALE,
    MATERIAL_THEME,
    install_material_theme,
    readability_styles,
)

from .test_ui import add_product


def fill(
    row: Any,
    name: str,
    regular: str,
    website: str,
    qty: int = 1,
    gift: str | None = None,
    manager: str | None = None,
    total_mode: bool = False,
) -> None:
    line = row.line
    line.name_edit.setText(name)
    line.regular_edit.setText(regular)
    line.website_edit.setText(website)
    line.quantity_spin.setValue(qty)
    if gift is not None:
        line.gift_check.setChecked(True)
        line.gift_name_edit.setText(gift)
    if manager is not None:
        line.manager_edit.setText(manager)
    if total_mode:
        line.line_radio.setChecked(True)


def fill_two(tab: CalculatorTab) -> None:
    tab.add_line()
    fill(tab.rows[0], "Fridge", "5.000,00", "4.000,00", manager="3.000,00")
    fill(
        tab.rows[1],
        "Washer",
        "6.000,00",
        "5.000,00",
        qty=3,
        gift="Vacuum",
        manager="4.500,00",
    )


def titles(tab: CalculatorTab) -> list[str]:
    return [b.title() for b in tab.panel.findChildren(QGroupBox)]


def layout_order(tab: CalculatorTab) -> list[Any]:
    return [tab._rows_layout.itemAt(i).widget() for i in range(len(tab.rows))]


def pos_total(tab: CalculatorTab) -> D | None:
    assert tab.evaluation.result is not None
    return tab.evaluation.result.totals.pos.value


# ---- lines ----------------------------------------------------------------


def test_fresh_calculator_has_one_incomplete_line_and_no_save(
    qtbot, repo
) -> None:  # type: ignore[no-untyped-def]
    tab = CalculatorTab(repo)
    qtbot.addWidget(tab)
    assert len(tab.rows) == 1
    assert not tab.save_button.isEnabled()
    assert not tab.rows[0].remove_button.isEnabled()
    assert titles(tab) == ["Satır 1"]
    assert all(b.error_text == "" for b in tab.rows[0].line.blocks.values())


def test_add_and_remove_lines_keep_at_least_one(qtbot, repo) -> None:  # type: ignore[no-untyped-def]
    tab = CalculatorTab(repo)
    qtbot.addWidget(tab)
    tab.add_button.click()
    assert len(tab.rows) == 2
    assert [r.title() for r in tab.rows] == ["Satır 1", "Satır 2"]
    assert tab.rows[0].remove_button.isEnabled()
    tab.rows[1].remove_button.click()
    assert len(tab.rows) == 1
    tab.remove_line(tab.rows[0])  # ignored: the last line stays
    assert len(tab.rows) == 1


def test_move_buttons_are_disabled_at_the_ends(qtbot, repo) -> None:  # type: ignore[no-untyped-def]
    tab = CalculatorTab(repo)
    qtbot.addWidget(tab)
    tab.add_line()
    assert (
        not tab.rows[0].up_button.isEnabled()
        and tab.rows[0].down_button.isEnabled()
    )
    assert (
        tab.rows[1].up_button.isEnabled()
        and not tab.rows[1].down_button.isEnabled()
    )


# ---- totals and independence ----------------------------------------------


def test_mixed_gift_and_no_gift_lines_give_the_expected_totals(
    qtbot, repo
) -> None:  # type: ignore[no-untyped-def]
    tab = CalculatorTab(repo)
    qtbot.addWidget(tab)
    fill_two(tab)
    assert tab.evaluation.valid and tab.save_button.isEnabled()
    result = tab.evaluation.result
    assert result is not None
    assert result.totals.regular.value == D(23000)
    assert result.totals.ten_pct.value == D(19800)
    assert pos_total(tab) == D(20500)
    assert not tab.rows[
        0
    ].line.gift_check.isChecked()  # gift state is per line
    assert tab.rows[1].line.gift_check.isChecked()


def test_removing_a_line_recomputes_totals(qtbot, repo) -> None:  # type: ignore[no-untyped-def]
    tab = CalculatorTab(repo)
    qtbot.addWidget(tab)
    fill_two(tab)
    tab.rows[0].remove_button.click()
    assert len(tab.rows) == 1 and tab.rows[0].line.name_edit.text() == "Washer"
    assert pos_total(tab) == D(16500)


def test_reordering_moves_the_state_with_the_line(qtbot, repo) -> None:  # type: ignore[no-untyped-def]
    tab = CalculatorTab(repo)
    qtbot.addWidget(tab)
    fill_two(tab)
    before = tab.evaluation.result
    assert before is not None

    tab.rows[1].up_button.click()
    assert layout_order(tab) == tab.rows
    first = tab.rows[0].line
    assert first.name_edit.text() == "Washer"
    assert first.quantity_spin.value() == 3
    assert (
        first.gift_check.isChecked()
        and first.gift_name_edit.text() == "Vacuum"
    )
    assert first.manager_edit.text() == "4.500,00"
    assert [r.title() for r in tab.rows] == ["Satır 1", "Satır 2"]
    after = tab.evaluation.result
    assert after is not None and after.totals == before.totals

    tab.rows[0].down_button.click()  # and back again
    assert tab.rows[0].line.name_edit.text() == "Fridge"


def test_invalid_line_hides_totals_but_keeps_the_valid_card(
    qtbot, repo
) -> None:  # type: ignore[no-untyped-def]
    tab = CalculatorTab(repo)
    qtbot.addWidget(tab)
    fill_two(tab)
    tab.rows[1].line.website_edit.setText("invalid")
    assert not tab.evaluation.valid and not tab.save_button.isEnabled()
    assert tab.rows[1].line.blocks["website_discounted_price"].error_text != ""
    shown = titles(tab)
    assert "Satır 1: Fridge" in shown
    assert "POS hesaplama ayrıntıları" not in shown
    line_pos = tab.panel.findChildren(QLabel, "posAmount")
    assert len(line_pos) == 1 and line_pos[0].text() == "4.000,00 TL"
    assert "İşlem toplamları" not in shown
    assert any(
        "Tamamlanacak veya düzeltilecek satırlar: 2" in lb.text()
        for lb in tab.panel.findChildren(QLabel)
    )

    tab.rows[1].line.website_edit.setText("5.000,00")
    assert tab.evaluation.valid and "İşlem toplamları" in titles(tab)


# ---- comparison -----------------------------------------------------------


def test_options_are_side_by_side_only_for_lines_with_a_gift(
    qtbot, repo
) -> None:  # type: ignore[no-untyped-def]
    tab = CalculatorTab(repo)
    qtbot.addWidget(tab)
    fill(tab.rows[0], "Fridge", "5.000,00", "4.000,00")
    shown = titles(tab)
    assert (
        shown.count("Web sitesi indirim seçeneği") == 1
        and "Hediye seçeneği" not in shown
    )

    tab.add_line()
    fill(tab.rows[1], "Washer", "6.000,00", "5.000,00", gift="Vacuum")
    shown = titles(tab)
    assert (
        shown.count("Web sitesi indirim seçeneği") == 2
        and shown.count("Hediye seçeneği") == 1
    )


def test_panel_never_recommends_an_option(qtbot, repo) -> None:  # type: ignore[no-untyped-def]
    tab = CalculatorTab(repo)
    qtbot.addWidget(tab)
    fill_two(tab)
    text = " ".join(lb.text() for lb in tab.panel.findChildren(QLabel)).lower()
    assert (
        "recommend" not in text and "best" not in text and "winner" not in text
    )


def test_pos_result_is_prominent_selectable_and_first(qtbot, repo) -> None:  # type: ignore[no-untyped-def]
    tab = CalculatorTab(repo)
    qtbot.addWidget(tab)
    fill(tab.rows[0], "Fridge", "5.000,00", "4.000,00", manager="3.000,00")

    amount = tab.panel.findChild(QLabel, "posAmount")
    assert amount is not None and amount.text() == "4.000,00 TL"
    assert amount.textInteractionFlags() & Qt.TextInteractionFlag.TextSelectableByMouse
    assert tab.panel._totals.itemAt(0).widget().objectName() == "posHero"
    discount_label = tab.panel.findChild(QLabel, "discountAmountLabel")
    discount_value = tab.panel.findChild(QLabel, "discountAmountValue")
    assert discount_label is not None and discount_label.text() == "İndirim tutarı"
    assert discount_value is not None and discount_value.text() == "1.000,00 TL"
    assert discount_label.parentWidget().title() == "Web sitesi indirim seçeneği"
    assert discount_value.parentWidget().title() == "Web sitesi indirim seçeneği"

    result_card = tab.panel.findChild(QGroupBox, "lineResultCard")
    assert result_card is not None and result_card.title() == "Satır 1: Fridge"
    assert tab.panel.findChild(QLabel, "lineQuantityLabel").text() == "Adet"
    assert tab.panel.findChild(QLabel, "lineQuantityValue").text() == "1"


def test_transaction_pos_total_precedes_multi_line_details(qtbot, repo) -> None:  # type: ignore[no-untyped-def]
    tab = CalculatorTab(repo)
    qtbot.addWidget(tab)
    fill_two(tab)

    amounts = [label.text() for label in tab.panel.findChildren(QLabel, "posAmount")]
    assert amounts == ["20.500,00 TL", "4.000,00 TL", "16.500,00 TL"]
    discounts = [label.text() for label in tab.panel.findChildren(QLabel, "discountAmountValue")]
    assert discounts == ["1.000,00 TL", "3.000,00 TL"]
    labels = " ".join(label.text() for label in tab.panel.findChildren(QLabel))
    assert "%10 bazı" not in labels
    assert "Her satır kendi" not in labels
    assert "bilgilendirme amaçlıdır" not in labels
    assert "Bu nasıl hesaplandı" not in labels
    assert tab.panel._totals.itemAt(0).widget().objectName() == "posHero"


def test_option_cards_stack_at_narrow_width_and_return_to_columns(qtbot, repo) -> None:  # type: ignore[no-untyped-def]
    app = QApplication.instance()
    assert app is not None
    install_material_theme(app, DEFAULT_FONT_SCALE)
    tab = CalculatorTab(repo)
    qtbot.addWidget(tab)
    fill(tab.rows[0], "Washer", "6.000,00", "5.000,00", gift="Vacuum")
    tab.panel.resize(700, 900)
    tab.panel._update_option_directions()
    assert tab.panel._option_layouts[0].direction() == QBoxLayout.Direction.TopToBottom

    tab.panel.resize(900, 900)
    tab.panel._update_option_directions()
    assert tab.panel._option_layouts[0].direction() == QBoxLayout.Direction.LeftToRight

    install_material_theme(app, 150)
    tab.panel.resize(900, 900)
    tab.panel._update_option_directions()
    assert tab.panel._option_layouts[0].direction() == QBoxLayout.Direction.TopToBottom

    install_material_theme(app, 100)
    tab.panel.resize(700, 900)
    tab.panel._update_option_directions()
    assert tab.panel._option_layouts[0].direction() == QBoxLayout.Direction.LeftToRight
    install_material_theme(app, DEFAULT_FONT_SCALE)


def test_light_blue_material_theme_and_result_styles_are_installed(qtbot) -> None:  # type: ignore[no-untyped-def]
    app = QApplication.instance()
    assert app is not None
    install_material_theme(app)
    assert MATERIAL_THEME == "light_blue.xml"
    assert "QFrame#posHero" in app.styleSheet()
    assert "QLabel#posAmount" in app.styleSheet()
    assert "QGroupBox#lineResultCard::title" in app.styleSheet()
    assert "QLabel#lineQuantityValue" in app.styleSheet()
    assert "QLabel#discountAmountLabel" in app.styleSheet()
    assert "font-size: 24pt" in readability_styles(100)
    assert "font-size: 13pt;\n    font-weight: 700" in readability_styles(100)
    assert "QGroupBox::title" in app.styleSheet()
    assert "color: #26384a" in app.styleSheet()


# ---- products and save ----------------------------------------------------


def test_selecting_a_saved_product_copies_values_and_never_writes_back(
    qtbot, repo
) -> None:  # type: ignore[no-untyped-def]
    product = add_product(repo, gift="Vacuum")
    tab = CalculatorTab(repo)
    qtbot.addWidget(tab)
    line = tab.rows[0].line
    line.product_combo.setCurrentIndex(1)
    assert line.name_edit.text() == "Fridge" and line.name_edit.isReadOnly()
    assert (
        line.regular_edit.text() == "5.000,00"
        and line.gift_name_edit.text() == "Vacuum"
    )
    assert tab.evaluation.valid

    line.gift_name_edit.setText("Toaster")
    line.manager_edit.setText("3.000,00")
    assert repo.get(product.id) == product


def test_refresh_updates_every_row_and_keeps_entered_values(
    qtbot, repo
) -> None:  # type: ignore[no-untyped-def]
    product = add_product(repo)
    tab = CalculatorTab(repo)
    qtbot.addWidget(tab)
    tab.add_line()
    for row in tab.rows:
        row.line.product_combo.setCurrentIndex(1)
    assert all(r.line.selected_product() is not None for r in tab.rows)

    repo.archive(product.id)
    add_product(repo, "Washer")
    tab.refresh_products()
    for row in tab.rows:
        assert row.line.product_combo.count() == 2  # one-off + Washer
        assert row.line.product_combo.currentIndex() == 0
        assert row.line.regular_edit.text() == "5.000,00"
    assert tab.evaluation.valid


def test_ambiguous_price_shows_a_hint(qtbot, repo) -> None:  # type: ignore[no-untyped-def]
    tab = CalculatorTab(repo)
    qtbot.addWidget(tab)
    tab.rows[0].line.regular_edit.setText("5.000")
    assert "5.000,00 TL" in tab.rows[0].line.blocks["regular_price"].hint_text


def test_save_emits_the_transaction_evaluation_with_entered_text(
    qtbot, repo
) -> None:  # type: ignore[no-untyped-def]
    tab = CalculatorTab(repo)
    qtbot.addWidget(tab)
    fill_two(tab)
    with qtbot.waitSignal(tab.save_requested) as blocker:
        tab.save_button.click()
    sent = blocker.args[0]
    assert isinstance(sent, TransactionEvaluation) and sent.valid
    assert [f.product_name for f in sent.forms] == ["Fridge", "Washer"]
    assert sent.forms[1].manager_value == "4.500,00"
