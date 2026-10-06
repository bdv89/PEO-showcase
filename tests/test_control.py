"""Tests du pilotage : on vérifie les commandes SCPI émises (scope mocké)."""

import pytest

from scope import control


class FakeScope:
    def __init__(self, responses=None):
        self.written = []
        self._responses = responses or {}

    def write(self, cmd):
        self.written.append(cmd)

    def query(self, cmd):
        self.written.append(cmd)
        return self._responses[cmd]


def test_set_timebase():
    s = FakeScope()
    control.set_timebase(s, "1MS")
    assert s.written == ["TDIV 1MS"]


def test_set_vdiv_and_offset():
    s = FakeScope()
    control.set_vdiv(s, "C2", "50MV")
    control.set_offset(s, "C2", "-1.5V")
    assert s.written == ["C2:VDIV 50MV", "C2:OFST -1.5V"]


def test_set_coupling_validates():
    s = FakeScope()
    control.set_coupling(s, "C1", "d1m")  # casse insensible
    assert s.written == ["C1:CPL D1M"]
    with pytest.raises(ValueError):
        control.set_coupling(s, "C1", "XYZ")


def test_enable_channel():
    s = FakeScope()
    control.enable_channel(s, "C3", on=False)
    control.enable_channel(s, "C3", on=True)
    assert s.written == ["C3:TRA OFF", "C3:TRA ON"]


def test_trigger_slope_validates():
    s = FakeScope()
    control.set_trigger_slope(s, "C1", "pos")
    assert s.written == ["C1:TRSL POS"]
    with pytest.raises(ValueError):
        control.set_trigger_slope(s, "C1", "sideways")


def test_run_stop_autoset():
    s = FakeScope()
    control.run(s)
    control.stop(s)
    control.autoset(s)
    assert s.written == ["ARM", "STOP", "ASET"]


def test_set_waveform_points():
    s = FakeScope()
    control.set_waveform_points(s, 1400)
    assert s.written == ["WFSU SP,1,NP,1400,FP,0"]
    with pytest.raises(ValueError):
        control.set_waveform_points(s, 0)


def test_set_trigger_mode_validates():
    s = FakeScope()
    control.set_trigger_mode(s, "single")  # casse insensible
    assert s.written == ["TRMD SINGLE"]
    with pytest.raises(ValueError):
        control.set_trigger_mode(s, "BOGUS")


def test_active_channels_filters_on():
    s = FakeScope(
        {
            "C1:TRA?": "C1:TRA ON",
            "C2:TRA?": "C2:TRA OFF",
            "C3:TRA?": "C3:TRA ON",
            "C4:TRA?": "C4:TRA OFF",
        }
    )
    assert control.active_channels(s) == ["C1", "C3"]


def test_autoscale_computes_offset_and_vdiv():
    # vpp = 2.0 - (-1.0) = 3.0 ; v0 = -1.0 + 1.5 = 0.5 -> OFST -0.5
    # VDIV = 3.0 / 7.5 = 0.4
    s = FakeScope(
        {
            "C1:PAVA? MIN": "C1:PAVA MIN,-1.00E+00V",
            "C1:PAVA? MAX": "C1:PAVA MAX,2.00E+00V",
        }
    )
    control.autoscale(s, "C1")
    ofst_cmds = [c for c in s.written if c.startswith("C1:OFST")]
    vdiv_cmds = [c for c in s.written if c.startswith("C1:VDIV")]
    assert len(ofst_cmds) == 2  # 2 itérations (défaut)
    assert len(vdiv_cmds) == 2
    assert ofst_cmds[0] == "C1:OFST -0.50000V"
    assert vdiv_cmds[0] == "C1:VDIV 0.40000V"


def test_autoscale_custom_iterations():
    s = FakeScope(
        {
            "C1:PAVA? MIN": "C1:PAVA MIN,-1.00E+00V",
            "C1:PAVA? MAX": "C1:PAVA MAX,1.00E+00V",
        }
    )
    control.autoscale(s, "C1", iterations=1)
    assert len([c for c in s.written if c.startswith("C1:OFST")]) == 1


def test_autoscale_no_signal_raises():
    s = FakeScope(
        {
            "C1:PAVA? MIN": "C1:PAVA MIN,****V",
            "C1:PAVA? MAX": "C1:PAVA MAX,****V",
        }
    )
    with pytest.raises(ValueError):
        control.autoscale(s, "C1")
