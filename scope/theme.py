"""Charte graphique Materianova (reprise de l'app web inventaire_cibles) pour la GUI Qt.

Qt-free : palettes clair/sombre, feuille de style Qt (QSS) générée depuis la
palette, et logo SVG recoloré pour le fond sombre. ``gui.py`` applique le
résultat (``app.setStyleSheet``, fonds pyqtgraph).
"""

from __future__ import annotations

from pathlib import Path

LOGO_PATH = Path(__file__).resolve().parent / "assets" / "logo_materianova.svg"
_LOGO_INK = "#0d3755"  # bleu marine du texte du logo, illisible sur fond sombre

PALETTES = {
    "clair": {
        "bg1": "#FFFFFF", "bg2": "#F2F0E5", "ink": "#000000", "muted": "#6F6E69",
        "accent": "#879A39", "accent_light": "#a3b356", "charcoal": "#32373c",
        "blue": "#4385BE", "line": "#D1CFC6", "card": "#FFFFFF",
        "danger": "#cf2e2e", "warning": "#ff6900", "warning_bg": "#FFF1E6",
        "plot_bg": "#FFFFFF", "plot_fg": "#32373c",
    },
    "sombre": {
        "bg1": "#17191b", "bg2": "#22262a", "ink": "#e8e6df", "muted": "#9a9c96",
        "accent": "#a3b356", "accent_light": "#b8c76e", "charcoal": "#4a5157",
        "blue": "#5b9fd4", "line": "#34383c", "card": "#22262a",
        "danger": "#e5544f", "warning": "#ff8a3d", "warning_bg": "#3a2a1c",
        "plot_bg": "#000000", "plot_fg": "#e8e6df",
    },
}
THEMES = tuple(PALETTES)


def other_theme(name: str) -> str:
    return "sombre" if name == "clair" else "clair"


def qss(name: str) -> str:
    """Feuille de style Qt de la charte : cartes à bord fin, boutons « pilule »
    (anthracite par défaut, vert olive pour l'action principale, rouge pour
    arrêter), champ manquant en rouge pendant une manip, bandeau d'alerte orange."""
    p = PALETTES[name]
    return f"""
QWidget {{ background: {p['bg1']}; color: {p['ink']};
          font-family: "Segoe UI", Roboto, "Helvetica Neue", Arial; font-size: 10pt; }}
QMainWindow, QScrollArea, QScrollArea > QWidget > QWidget {{ background: {p['bg1']}; }}
QLabel, QCheckBox, QRadioButton {{ background: transparent; }}
QGroupBox > QWidget {{ background: transparent; }}
/* la règle ci-dessus (plus spécifique que QPushButton) rendrait les boutons d'un cadre
   transparents -- texte blanc sur fond blanc : on leur rend leur fond */
QGroupBox > QPushButton {{ background: {p['charcoal']}; }}
QGroupBox > QPushButton:hover {{ background: {p['blue']}; }}
QGroupBox > QPushButton:disabled {{ background: {p['line']}; color: {p['muted']}; }}
QFrame#header {{ background: {p['bg1']}; border-bottom: 1px solid {p['line']}; }}
QLabel#appTitle {{ font-size: 13pt; font-weight: 600; }}
QLabel#muted, QLabel[role="muted"] {{ color: {p['muted']}; }}
QLabel#seriesId {{ font-family: Consolas, "SF Mono", monospace; font-size: 12pt;
                  font-weight: 600; color: {p['accent']}; }}
QLabel#banner {{ background: {p['warning_bg']}; color: {p['ink']}; border: 1px solid {p['warning']};
                border-left: 6px solid {p['warning']}; border-radius: 8px; padding: 8px 12px;
                font-weight: 600; }}
QGroupBox {{ background: {p['card']}; border: 1px solid {p['line']}; border-radius: 8px;
            margin-top: 14px; padding: 10px 8px 8px 8px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px;
                   color: {p['accent']}; font-weight: 600; }}
QLineEdit, QPlainTextEdit, QComboBox, QSpinBox {{
    background: {p['bg1']}; border: 1px solid {p['line']}; border-radius: 6px; padding: 4px 6px;
    selection-background-color: {p['accent']}; }}
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus {{ border: 1px solid {p['accent']}; }}
QLineEdit:read-only {{ background: {p['bg2']}; color: {p['muted']}; }}
QLineEdit[missing="true"], QPlainTextEdit[missing="true"], QComboBox[missing="true"] {{
    border: 2px solid {p['danger']}; background: {p['warning_bg']}; }}
QComboBox QAbstractItemView {{ background: {p['card']}; border: 1px solid {p['line']};
                               selection-background-color: {p['accent']}; }}
QPushButton {{ background: {p['charcoal']}; color: #ffffff; border: none; border-radius: 14px;
              padding: 6px 16px; font-weight: 500; }}
QPushButton:hover {{ background: {p['blue']}; }}
QPushButton:disabled {{ background: {p['line']}; color: {p['muted']}; }}
QPushButton[kind="primary"] {{ background: {p['accent']}; font-weight: 600; }}
QPushButton[kind="primary"]:hover {{ background: {p['accent_light']}; }}
QPushButton[kind="danger"] {{ background: {p['danger']}; }}
QPushButton[kind="ghost"] {{ background: transparent; color: {p['ink']};
                            border: 1px solid {p['line']}; }}
QPushButton#browse {{ padding: 4px 6px; }}
QPushButton[kind="ghost"]:hover {{ border-color: {p['accent']}; background: {p['bg2']}; }}
QPushButton:disabled[kind] {{ background: {p['line']}; color: {p['muted']}; border: none; }}
QTabWidget::pane {{ border: 1px solid {p['line']}; border-radius: 8px; top: -1px; }}
QTabBar::tab {{ background: {p['bg2']}; color: {p['muted']}; padding: 7px 20px; border: 1px solid {p['line']};
               border-bottom: none; border-top-left-radius: 8px; border-top-right-radius: 8px;
               margin-right: 2px; }}
QTabBar::tab:selected {{ background: {p['bg1']}; color: {p['ink']};
                        border-top: 3px solid {p['accent']}; }}
QCheckBox::indicator:checked {{ background: {p['accent']}; border: 1px solid {p['accent']};
                               border-radius: 3px; }}
QCheckBox::indicator:unchecked {{ background: {p['bg1']}; border: 1px solid {p['line']};
                                 border-radius: 3px; }}
QRadioButton::indicator {{ width: 12px; height: 12px; border-radius: 7px; }}
QRadioButton::indicator:checked {{ background: {p['accent']}; border: 1px solid {p['accent']}; }}
QRadioButton::indicator:unchecked {{ background: {p['bg1']}; border: 1px solid {p['muted']}; }}
QSplitter::handle {{ background: {p['line']}; }}
QStatusBar {{ background: {p['bg2']}; color: {p['muted']}; border-top: 1px solid {p['line']}; }}
QHeaderView::section {{ background: {p['bg2']}; border: none; border-bottom: 1px solid {p['line']};
                       padding: 4px; font-weight: 600; }}
QTableWidget, QListWidget {{ background: {p['card']}; border: 1px solid {p['line']}; border-radius: 6px;
                            gridline-color: {p['line']}; }}
QToolTip {{ background: {p['card']}; color: {p['ink']}; border: 1px solid {p['line']}; }}
"""


def logo_svg(name: str) -> bytes:
    """SVG du logo pour le thème : texte éclairci sur fond sombre. Vide si absent."""
    try:
        svg = LOGO_PATH.read_text(encoding="utf-8")
    except OSError:
        return b""
    if name == "sombre":
        svg = svg.replace(_LOGO_INK, PALETTES["sombre"]["ink"])
    return svg.encode("utf-8")
