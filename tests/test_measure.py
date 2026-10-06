"""Tests des mesures automatiques (SCPI PAVA?) — exécutables sans matériel."""

import pytest

from scope.measure import VALID_PARAMS, measure, measure_all, parse_pava, parse_pava_all


class FakeScope:
    def __init__(self, responses=None):
        self.written = []
        self._responses = responses or {}

    def write(self, cmd):
        self.written.append(cmd)

    def query(self, cmd):
        self.written.append(cmd)
        return self._responses[cmd]


# --- parse_pava ------------------------------------------------------------------
@pytest.mark.parametrize(
    "response, param, expected",
    [
        ("C1:PAVA PKPK,1.23E+00V", "PKPK", 1.23),
        ("C1:PAVA FREQ,1.00E+03Hz", "FREQ", 1000.0),
        ("C1:PAVA MEAN,-5.00E-02V", "MEAN", -0.05),
        ("C2:PAVA DUTY,5.00E+01%", "DUTY", 50.0),
    ],
)
def test_parse_pava_nominal(response, param, expected):
    assert parse_pava(response, param) == pytest.approx(expected)


def test_parse_pava_unavailable():
    """'****' = mesure indisponible (pas de signal / hors écran) -> None."""
    assert parse_pava("C1:PAVA PKPK,****V", "PKPK") is None


def test_parse_pava_unavailable_no_unit():
    assert parse_pava("C1:PAVA FREQ,*****", "FREQ") is None


# --- parse_pava_all --------------------------------------------------------------
def test_parse_pava_all():
    response = "C1:PAVA ALL,PKPK,1.00E+00V,FREQ,1.00E+03Hz,MEAN,****V"
    result = parse_pava_all(response)
    assert result["PKPK"] == pytest.approx(1.0)
    assert result["FREQ"] == pytest.approx(1000.0)
    assert result["MEAN"] is None


def test_parse_pava_all_without_literal_all_prefix():
    """Format observé sur matériel réel (SDS1204X-E) : pas de token 'ALL,'
    littéral avant la liste, contrairement à l'hypothèse initiale."""
    response = "C1:PAVA PKPK,3.30E+00V,MIN,-2.60E+00V,MAX,2.60E+00V"
    result = parse_pava_all(response)
    assert result["PKPK"] == pytest.approx(3.30)
    assert result["MIN"] == pytest.approx(-2.60)
    assert result["MAX"] == pytest.approx(2.60)


def test_parse_pava_all_disambiguates_substring_params():
    """WID/DUTY sont des suffixes de PWID/NWID/NDUTY : ne pas s'y confondre."""
    response = "C1:PAVA PWID,1.00E-03S,NWID,2.00E-03S,WID,3.00E-03S,DUTY,5.00E+01%,NDUTY,4.00E+01%"
    result = parse_pava_all(response)
    assert result["PWID"] == pytest.approx(1e-3)
    assert result["NWID"] == pytest.approx(2e-3)
    assert result["WID"] == pytest.approx(3e-3)
    assert result["DUTY"] == pytest.approx(50.0)
    assert result["NDUTY"] == pytest.approx(40.0)


# --- measure -----------------------------------------------------------------
def test_measure_queries_and_parses():
    s = FakeScope({"C1:PAVA? PKPK": "C1:PAVA PKPK,2.50E+00V"})
    assert measure(s, "C1", "PKPK") == pytest.approx(2.5)
    assert s.written == ["C1:PAVA? PKPK"]


def test_measure_unavailable_returns_none():
    s = FakeScope({"C1:PAVA? FREQ": "C1:PAVA FREQ,****Hz"})
    assert measure(s, "C1", "FREQ") is None


def test_measure_invalid_param():
    s = FakeScope()
    with pytest.raises(ValueError):
        measure(s, "C1", "BOGUS")


def test_measure_param_case_insensitive():
    s = FakeScope({"C1:PAVA? PKPK": "C1:PAVA PKPK,1.00E+00V"})
    assert measure(s, "C1", "pkpk") == pytest.approx(1.0)


def test_all_valid_params_accepted():
    # Sanity : chaque paramètre documenté est accepté par measure() sans lever.
    s = FakeScope({f"C1:PAVA? {p}": f"C1:PAVA {p},1.00E+00V" for p in VALID_PARAMS})
    for p in VALID_PARAMS:
        measure(s, "C1", p)


# --- measure_all ---------------------------------------------------------------
def test_measure_all_queries_and_parses():
    s = FakeScope(
        {"C1:PAVA? ALL": "C1:PAVA ALL,PKPK,1.00E+00V,FREQ,1.00E+03Hz,MEAN,****V"}
    )
    result = measure_all(s, "C1")
    assert result["PKPK"] == pytest.approx(1.0)
    assert result["FREQ"] == pytest.approx(1000.0)
    assert result["MEAN"] is None
    assert s.written == ["C1:PAVA? ALL"]
