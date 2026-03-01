from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import neewer_config_tui


def test_parse_temp_kelvin_accepts_kelvin_and_shorthand():
    assert neewer_config_tui.parse_temp_kelvin("5600") == 5600
    assert neewer_config_tui.parse_temp_kelvin("56") == 5600


def test_parse_temp_kelvin_rejects_out_of_range():
    with pytest.raises(ValueError, match="Temperature must be between"):
        neewer_config_tui.parse_temp_kelvin("10")
    with pytest.raises(ValueError, match="Temperature must be between"):
        neewer_config_tui.parse_temp_kelvin("12000")


def test_parse_brightness_and_gm_ranges():
    assert neewer_config_tui.parse_brightness("0") == 0
    assert neewer_config_tui.parse_brightness("100") == 100
    assert neewer_config_tui.parse_gm("-50") == -50
    assert neewer_config_tui.parse_gm("50") == 50
    with pytest.raises(ValueError, match="Brightness must be between"):
        neewer_config_tui.parse_brightness("120")
    with pytest.raises(ValueError, match="GM must be between"):
        neewer_config_tui.parse_gm("-70")


def test_resolve_candidate_lights_for_preset_prefers_preset_members():
    config_data = {
        "lights": {
            "AA:AA:AA:AA:AA:AA": {"name": "Key"},
            "BB:BB:BB:BB:BB:BB": {"name": "Fill"},
        },
        "groups": {"studio": ["AA:AA:AA:AA:AA:AA"]},
        "presets": {"p1": {"lights": "group:studio", "mode": "CCT"}},
        "defaults": {},
    }
    result = neewer_config_tui.resolve_candidate_lights_for_preset(config_data, "p1")
    assert result == ["AA:AA:AA:AA:AA:AA"]


def test_resolve_candidate_lights_for_preset_falls_back_to_all_configured():
    config_data = {
        "lights": {
            "AA:AA:AA:AA:AA:AA": {"name": "Key"},
            "BB:BB:BB:BB:BB:BB": {"name": "Fill"},
        },
        "groups": {},
        "presets": {"p1": {"lights": "group:missing", "mode": "CCT"}},
        "defaults": {},
    }
    result = neewer_config_tui.resolve_candidate_lights_for_preset(config_data, "p1")
    assert result == ["AA:AA:AA:AA:AA:AA", "BB:BB:BB:BB:BB:BB"]


def test_format_preset_option_includes_kind():
    config_data = {
        "lights": {},
        "groups": {},
        "presets": {
            "on": {"lights": "group:studio", "power": "ON"},
            "cct": {"lights": "group:studio", "mode": "CCT"},
        },
        "defaults": {},
    }
    assert "[POWER ON]" in neewer_config_tui.format_preset_option(config_data, "on")
    assert "[CCT]" in neewer_config_tui.format_preset_option(config_data, "cct")


@pytest.mark.skipif(
    not neewer_config_tui._TEXTUAL_AVAILABLE,
    reason="Textual not installed in test environment",
)
@pytest.mark.asyncio
async def test_tui_app_mounts_and_loads_config(tmp_path):
    cfg_path = tmp_path / "cfg.json"
    cfg_path.write_text(
        '{"lights":{"AA:AA:AA:AA:AA:AA":{"name":"Key"}},"groups":{"studio":["AA:AA:AA:AA:AA:AA"]},"presets":{"p1":{"lights":"group:studio","mode":"CCT","temp":5600,"bri":40}},"defaults":{}}',
        encoding="utf-8",
    )

    app = neewer_config_tui.NeewerConfigTui(str(cfg_path))
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.query_one("#config_tree") is not None
        assert app.query_one("#scan_results") is not None
        assert app.current_preset == "p1"
        assert app.current_light == "AA:AA:AA:AA:AA:AA"
