"""Application-wide Material theme and persisted readability settings."""

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication
from qt_material import apply_stylesheet

MATERIAL_THEME = "light_blue.xml"
FONT_SCALE_KEY = "ui/font_scale_percent"
FONT_SCALE_CHOICES = (100, 110, 120, 130, 140, 150)
DEFAULT_FONT_SCALE = 120


def load_font_scale(settings: QSettings) -> int:
    """Return the saved scale, falling back when its stored value is invalid."""
    value = settings.value(FONT_SCALE_KEY, DEFAULT_FONT_SCALE, type=int)
    return value if value in FONT_SCALE_CHOICES else DEFAULT_FONT_SCALE


def readability_styles(font_scale_percent: int) -> str:
    scale = font_scale_percent / 100
    caption_size = 12 * scale
    amount_size = 28 * scale
    missing_size = 15 * scale
    emphasized_size = 13 * scale
    return f"""
QFrame#posHero {{
    background-color: #eaf2ff;
    border: 1px solid #9bb9e3;
    border-radius: 10px;
}}
QLabel#posCaption {{
    color: #25364a;
    font-size: {caption_size}pt;
    font-weight: 600;
}}
QLabel#posAmount {{
    color: #102c55;
    font-size: {amount_size}pt;
    font-weight: 700;
    padding: 5px 0;
}}
QLabel#discountAmount {{
    color: #163a66;
    font-size: {emphasized_size}pt;
    font-weight: 600;
    padding: 3px 0;
}}
QLabel#posAmount[missing="true"] {{
    color: #7a3e00;
    font-size: {missing_size}pt;
}}
QGroupBox[visualRole="option"] {{
    border: 1px solid #b6c8df;
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 8px;
}}
QLabel[amountRole="emphasis"] {{
    color: #163a66;
    font-size: {emphasized_size}pt;
    font-weight: 600;
}}
QTableView#productsTable {{
    alternate-background-color: #f4f8fe;
    selection-background-color: #c7dcf7;
    selection-color: #102c55;
    gridline-color: #d6e0ed;
}}
QHeaderView::section {{
    color: #25364a;
    font-weight: 600;
    padding: 8px 10px;
}}
QTableView#productsTable::item {{
    padding: 6px 8px;
}}
QGroupBox {{
    color: #26384a;
    text-transform: none;
}}
QGroupBox::title {{
    color: #26384a;
    font-weight: 600;
}}
QTabBar::tab {{
    color: #334155;
    font-weight: 600;
    text-transform: none;
}}
QPushButton {{
    text-transform: none;
}}
"""


def install_material_theme(
    app: QApplication, font_scale_percent: int = DEFAULT_FONT_SCALE
) -> None:
    """Apply the selected Qt Material theme and scaled readability styles."""
    if font_scale_percent not in FONT_SCALE_CHOICES:
        font_scale_percent = DEFAULT_FONT_SCALE
    app.setProperty("fontScalePercent", font_scale_percent)
    scale = font_scale_percent / 100
    font_size = f"{13 * scale:g}px"
    apply_stylesheet(
        app,
        theme=MATERIAL_THEME,
        invert_secondary=True,
        extra={"font_size": font_size, "line_height": font_size},
    )
    app.setStyleSheet(app.styleSheet() + readability_styles(font_scale_percent))
