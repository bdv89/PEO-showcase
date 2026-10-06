"""Charte Materianova (``scope.theme``) : palettes, QSS, logo -- sans Qt."""

import pytest

from scope import theme


@pytest.mark.parametrize("name", theme.THEMES)
def test_qss_uses_palette_colours(name):
    css = theme.qss(name)
    p = theme.PALETTES[name]
    for key in ("bg1", "accent", "danger", "warning"):
        assert p[key] in css
    assert 'QLineEdit[missing="true"]' in css and "QLabel#banner" in css


def test_palettes_define_the_same_keys():
    assert theme.PALETTES["clair"].keys() == theme.PALETTES["sombre"].keys()


def test_other_theme():
    assert theme.other_theme("clair") == "sombre" and theme.other_theme("sombre") == "clair"


def test_logo_recoloured_for_dark_theme():
    light, dark = theme.logo_svg("clair"), theme.logo_svg("sombre")
    assert b"<svg" in light and b"#0d3755" in light
    assert b"#0d3755" not in dark and theme.PALETTES["sombre"]["ink"].encode() in dark
