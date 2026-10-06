import pytest

from scope.channel_config import (
    CHANNELS,
    ChannelConfig,
    axis_assignment,
    load_channel_configs,
    save_channel_configs,
)


# --- ChannelConfig ---------------------------------------------------------------
def test_default_config_is_neutral():
    cfg = ChannelConfig()
    assert cfg.label == "" and cfg.unit == "V" and cfg.factor == 1.0


def test_display_name_falls_back_to_channel():
    assert ChannelConfig().display_name("C1") == "C1"
    assert ChannelConfig(label="Vbat").display_name("C1") == "Vbat"


# --- load/save --------------------------------------------------------------------
def test_load_missing_file_returns_defaults(tmp_path):
    configs = load_channel_configs(tmp_path / "absent.json")
    assert set(configs) == set(CHANNELS)
    assert all(cfg == ChannelConfig() for cfg in configs.values())


def test_load_corrupted_file_returns_defaults(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{ceci n'est pas du json")
    configs = load_channel_configs(path)
    assert all(cfg == ChannelConfig() for cfg in configs.values())


def test_save_then_load_roundtrip(tmp_path):
    path = tmp_path / "channels_config.json"
    configs = {
        "C1": ChannelConfig(label="Vbat", unit="V", factor=1.0),
        "C2": ChannelConfig(label="Icharge", unit="A", factor=10.0),
    }
    save_channel_configs(configs, path)
    loaded = load_channel_configs(path)
    assert loaded["C1"] == configs["C1"]
    assert loaded["C2"] == configs["C2"]
    # Voies absentes du fichier sauvé -> défauts.
    assert loaded["C3"] == ChannelConfig()
    assert loaded["C4"] == ChannelConfig()


def test_load_partial_entry_fills_missing_fields(tmp_path):
    path = tmp_path / "partial.json"
    path.write_text('{"C1": {"label": "Vbat"}}')
    configs = load_channel_configs(path)
    assert configs["C1"] == ChannelConfig(label="Vbat", unit="V", factor=1.0)


# --- axis_assignment ---------------------------------------------------------------
def test_axis_assignment_no_active_channels():
    mapping, left, right = axis_assignment({"C1": ChannelConfig()}, [])
    assert mapping == {} and left is None and right is None


def test_axis_assignment_single_unit_goes_left_only():
    configs = {"C1": ChannelConfig(unit="V"), "C2": ChannelConfig(unit="V")}
    mapping, left, right = axis_assignment(configs, ["C1", "C2"])
    assert mapping == {"C1": "left", "C2": "left"}
    assert left == "V" and right is None


def test_axis_assignment_two_units_split_left_right():
    configs = {"C1": ChannelConfig(unit="V"), "C2": ChannelConfig(unit="A")}
    mapping, left, right = axis_assignment(configs, ["C1", "C2"])
    assert mapping == {"C1": "left", "C2": "right"}
    assert left == "V" and right == "A"


def test_axis_assignment_third_unit_falls_back_to_right():
    configs = {
        "C1": ChannelConfig(unit="V"),
        "C2": ChannelConfig(unit="A"),
        "C3": ChannelConfig(unit="W"),
    }
    mapping, left, right = axis_assignment(configs, ["C1", "C2", "C3"])
    assert mapping == {"C1": "left", "C2": "right", "C3": "right"}
    assert left == "V" and right == "A"


# --- réglages GUI mémorisés ------------------------------------------------------
from scope.channel_config import GUI_SETTINGS_DEFAULTS, load_gui_settings, save_gui_settings


def test_gui_settings_missing_file_returns_defaults(tmp_path):
    assert load_gui_settings(tmp_path / "absent.json") == GUI_SETTINGS_DEFAULTS


def test_gui_settings_corrupted_file_returns_defaults(tmp_path):
    path = tmp_path / "gui_settings.json"
    path.write_text("{pas du json", encoding="utf-8")
    assert load_gui_settings(path) == GUI_SETTINGS_DEFAULTS


def test_gui_settings_roundtrip(tmp_path):
    path = tmp_path / "gui_settings.json"
    settings = dict(GUI_SETTINGS_DEFAULTS, analysis_u="C1", analysis_i="C4", start_mode="now",
                    active_channels=["C2", "C3"], id_prefix="PEO-Ti", fiche={"operateur": "BDV"}, theme="sombre", series_rate="2")
    save_gui_settings(settings, path)
    assert load_gui_settings(path) == settings


def test_gui_settings_unknown_keys_ignored_missing_keys_defaulted(tmp_path):
    path = tmp_path / "gui_settings.json"
    path.write_text('{"analysis_u": "C4", "obsolete": 1}', encoding="utf-8")
    loaded = load_gui_settings(path)
    assert loaded["analysis_u"] == "C4"
    assert "obsolete" not in loaded
    assert loaded["analysis_i"] == GUI_SETTINGS_DEFAULTS["analysis_i"]


def test_gui_settings_wrong_type_falls_back_to_default(tmp_path):
    path = tmp_path / "gui_settings.json"
    path.write_text('{"active_channels": "C1", "png": "oui"}', encoding="utf-8")
    loaded = load_gui_settings(path)
    assert loaded["active_channels"] == GUI_SETTINGS_DEFAULTS["active_channels"]
    assert loaded["png"] == GUI_SETTINGS_DEFAULTS["png"]


def test_gui_settings_defaults_match_peo_setup():
    # départ au seuil ; analyse U = sonde HT (C2), I = courant (C3)
    assert GUI_SETTINGS_DEFAULTS["start_mode"] == "threshold"
    assert (GUI_SETTINGS_DEFAULTS["analysis_u"], GUI_SETTINGS_DEFAULTS["analysis_i"]) == ("C2", "C3")


def test_old_settings_file_gets_new_start_and_analysis_defaults_once(tmp_path):
    # ancien gui_settings.json (départ « now », U/I = C1/C2, seuil séparé) : ses clés
    # obsolètes sont ignorées -> nouveaux défauts au 1er lancement, puis mémorisés
    path = tmp_path / "gui_settings.json"
    path.write_text('{"series_mode": "now", "u_channel": "C1", "i_channel": "C2", '
                    '"thr_src": "C1", "thr_timeout": "45", "series_rate": "2"}', encoding="utf-8")
    loaded = load_gui_settings(path)
    assert loaded["start_mode"] == "threshold"
    assert (loaded["analysis_u"], loaded["analysis_i"]) == ("C2", "C3")
    assert loaded["series_rate"] == "2"  # les autres réglages sont conservés
    assert not {"series_mode", "u_channel", "i_channel", "thr_src", "thr_timeout"} & loaded.keys()
    save_gui_settings(dict(loaded, start_mode="now"), path)
    assert load_gui_settings(path)["start_mode"] == "now"  # ensuite : dernier choix repris


def test_fresh_install_records_the_analysis_channels():
    # sans réglage mémorisé, les voies enregistrées doivent contenir U et I, sinon
    # l'analyse des plateaux est désactivée (constaté sur une installation neuve)
    d = GUI_SETTINGS_DEFAULTS
    assert {d["analysis_u"], d["analysis_i"]} <= set(d["active_channels"])
