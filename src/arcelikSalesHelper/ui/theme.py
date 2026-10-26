"""Application-wide Material theme setup and readability accents."""

from PySide6.QtWidgets import QApplication
from qt_material import apply_stylesheet

MATERIAL_THEME = "light_blue.xml"

_READABILITY_STYLES = """
QFrame#posHero {
    background-color: #eaf2ff;
    border: 1px solid #9bb9e3;
    border-radius: 10px;
}
QLabel#posCaption {
    color: #25364a;
    font-size: 12pt;
    font-weight: 600;
}
QLabel#posAmount {
    color: #102c55;
    font-size: 28pt;
    font-weight: 700;
    padding: 5px 0;
}
QLabel#posAmount[missing="true"] {
    color: #7a3e00;
    font-size: 15pt;
}
QGroupBox[visualRole="option"] {
    border: 1px solid #b6c8df;
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 8px;
}
QLabel[amountRole="emphasis"] {
    color: #163a66;
    font-size: 13pt;
    font-weight: 600;
}
QTableView#productsTable {
    alternate-background-color: #f4f8fe;
    selection-background-color: #c7dcf7;
    selection-color: #102c55;
    gridline-color: #d6e0ed;
}
QHeaderView::section {
    color: #25364a;
    font-weight: 600;
    padding: 8px 10px;
}
QTableView#productsTable::item {
    padding: 6px 8px;
}
QPushButton, QTabBar::tab, QGroupBox::title {
    text-transform: none;
}
"""


def install_material_theme(app: QApplication) -> None:
    """Apply the selected Qt Material theme and result-panel accents."""
    apply_stylesheet(app, theme=MATERIAL_THEME, invert_secondary=True)
    app.setStyleSheet(app.styleSheet() + _READABILITY_STYLES)
