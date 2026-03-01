import argparse
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import neewer_config_cli


def test_prompt_text_escape_raises(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "\x1b")
    with pytest.raises(neewer_config_cli.WizardBack):
        neewer_config_cli.prompt_text("Name")


def test_prompt_choice_ignores_escape_when_back_disabled(monkeypatch):
    values = iter(["\x1b", "1"])
    monkeypatch.setattr("builtins.input", lambda _: next(values))
    picked = neewer_config_cli.prompt_choice("Pick", ["Only"], allow_back=False)
    assert picked == 0


def test_prompt_temp_kelvin_accepts_protocol_shorthand(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "56")
    value = neewer_config_cli.prompt_temp_kelvin("Temperature (Kelvin)", 5600)
    assert value == 5600


def test_prompt_text_propagates_keyboard_interrupt(monkeypatch):
    def fake_read(_prompt):
        raise KeyboardInterrupt

    monkeypatch.setattr(neewer_config_cli, "_read_user_input", fake_read)
    with pytest.raises(KeyboardInterrupt):
        neewer_config_cli.prompt_text("Any")


def test_ensure_config_shape_normalizes_blocks():
    cfg = {
        "lights": [{"address": "aa:bb:cc:dd:ee:ff", "name": "Key"}],
        "groups": {"studio": "aa:bb:cc:dd:ee:ff"},
        "presets": {},
        "defaults": {},
    }
    shaped = neewer_config_cli.ensure_config_shape(cfg)
    assert set(shaped["lights"].keys()) == {"AA:BB:CC:DD:EE:FF"}
    assert shaped["groups"]["studio"] == ["AA:BB:CC:DD:EE:FF"]


def test_update_preset_membership_adds_and_removes_from_group_selector():
    cfg = {
        "lights": {
            "AA:AA:AA:AA:AA:AA": {"name": "Key"},
            "BB:BB:BB:BB:BB:BB": {"name": "Fill"},
        },
        "groups": {"studio": ["AA:AA:AA:AA:AA:AA"]},
        "presets": {"all_on": {"lights": "group:studio", "power": "ON"}},
        "defaults": {},
    }

    result_add = neewer_config_cli.update_preset_membership(
        cfg, "all_on", "bb:bb:bb:bb:bb:bb", add=True
    )
    assert "added to group:studio" in result_add
    assert cfg["groups"]["studio"] == ["AA:AA:AA:AA:AA:AA", "BB:BB:BB:BB:BB:BB"]

    result_remove = neewer_config_cli.update_preset_membership(
        cfg, "all_on", "AA:AA:AA:AA:AA:AA", add=False
    )
    assert "removed from group:studio" in result_remove
    assert cfg["groups"]["studio"] == ["BB:BB:BB:BB:BB:BB"]


def test_update_preset_membership_handles_explicit_members_and_per_light():
    cfg = {
        "lights": {
            "AA:AA:AA:AA:AA:AA": {"name": "Key"},
            "BB:BB:BB:BB:BB:BB": {"name": "Fill"},
        },
        "groups": {},
        "presets": {
            "setup": {
                "lights": "AA:AA:AA:AA:AA:AA",
                "mode": "CCT",
                "per_light": {"AA:AA:AA:AA:AA:AA": {"mode": "CCT", "temp": 5600, "bri": 30}},
            }
        },
        "defaults": {},
    }

    neewer_config_cli.update_preset_membership(cfg, "setup", "BB:BB:BB:BB:BB:BB", add=True)
    assert cfg["presets"]["setup"]["lights"] == "AA:AA:AA:AA:AA:AA,BB:BB:BB:BB:BB:BB"
    assert "BB:BB:BB:BB:BB:BB" in cfg["presets"]["setup"]["per_light"]

    neewer_config_cli.update_preset_membership(cfg, "setup", "AA:AA:AA:AA:AA:AA", add=False)
    assert cfg["presets"]["setup"]["lights"] == "BB:BB:BB:BB:BB:BB"
    assert "AA:AA:AA:AA:AA:AA" not in cfg["presets"]["setup"]["per_light"]


def test_parse_selection_supports_ranges_and_all():
    valid = {1, 2, 3, 4, 5}
    assert neewer_config_cli.parse_selection("2,4-5", valid) == [2, 4, 5]
    assert neewer_config_cli.parse_selection("all", valid) == [1, 2, 3, 4, 5]
    assert neewer_config_cli.parse_selection("none", valid) == []


def test_apply_light_cct_override_to_preset_creates_per_light_entry():
    preset = {"lights": "group:studio", "mode": "CCT", "temp": 5600, "bri": 30, "gm": 0}
    neewer_config_cli.apply_light_cct_override_to_preset(
        preset, "aa:aa:aa:aa:aa:aa", 4300, 45, -10
    )
    entry = preset["per_light"]["AA:AA:AA:AA:AA:AA"]
    assert entry["mode"] == "CCT"
    assert entry["temp"] == 4300
    assert entry["bri"] == 45
    assert entry["gm"] == -10


def test_edit_preset_cct_for_light_updates_selected_light(monkeypatch):
    cfg = {
        "lights": {
            "AA:AA:AA:AA:AA:AA": {"name": "Key"},
            "BB:BB:BB:BB:BB:BB": {"name": "Fill"},
        },
        "groups": {"studio": ["AA:AA:AA:AA:AA:AA", "BB:BB:BB:BB:BB:BB"]},
        "presets": {"scene_setup": {"lights": "group:studio", "mode": "CCT", "temp": 5600, "bri": 30}},
        "defaults": {},
    }

    monkeypatch.setattr(neewer_config_cli, "prompt_select_preset_detailed", lambda *_a, **_k: "scene_setup")
    monkeypatch.setattr(
        neewer_config_cli,
        "prompt_select_address_from_list",
        lambda *_a, **_k: "BB:BB:BB:BB:BB:BB",
    )
    monkeypatch.setattr(neewer_config_cli, "prompt_temp_kelvin", lambda *_a, **_k: 5000)
    values = iter([40, 5])
    monkeypatch.setattr(neewer_config_cli, "prompt_int", lambda *_a, **_k: next(values))

    changed = neewer_config_cli.edit_preset_cct_for_light(cfg)
    assert changed is True
    override = cfg["presets"]["scene_setup"]["per_light"]["BB:BB:BB:BB:BB:BB"]
    assert override["temp"] == 5000
    assert override["bri"] == 40
    assert override["gm"] == 5


def test_edit_preset_cct_for_light_declines_power_preset_conversion(monkeypatch):
    cfg = {
        "lights": {"AA:AA:AA:AA:AA:AA": {"name": "Key"}},
        "groups": {"studio": ["AA:AA:AA:AA:AA:AA"]},
        "presets": {"all_on": {"lights": "group:studio", "power": "ON"}},
        "defaults": {},
    }

    monkeypatch.setattr(neewer_config_cli, "prompt_select_preset_detailed", lambda *_a, **_k: "all_on")
    monkeypatch.setattr(
        neewer_config_cli,
        "prompt_select_address_from_list",
        lambda *_a, **_k: "AA:AA:AA:AA:AA:AA",
    )
    monkeypatch.setattr(neewer_config_cli, "prompt_yes_no", lambda *_a, **_k: False)

    changed = neewer_config_cli.edit_preset_cct_for_light(cfg)
    assert changed is False
    assert cfg["presets"]["all_on"] == {"lights": "group:studio", "power": "ON"}


def test_edit_preset_cct_for_light_back_from_temp_returns_to_light_selection(monkeypatch):
    cfg = {
        "lights": {
            "AA:AA:AA:AA:AA:AA": {"name": "Key"},
            "BB:BB:BB:BB:BB:BB": {"name": "Fill"},
        },
        "groups": {"studio": ["AA:AA:AA:AA:AA:AA", "BB:BB:BB:BB:BB:BB"]},
        "presets": {
            "studio_default": {"lights": "group:studio", "mode": "CCT", "temp": 5600, "bri": 30}
        },
        "defaults": {},
    }

    monkeypatch.setattr(
        neewer_config_cli, "prompt_select_preset_detailed", lambda *_a, **_k: "studio_default"
    )
    addresses = iter(["AA:AA:AA:AA:AA:AA", "BB:BB:BB:BB:BB:BB"])
    monkeypatch.setattr(
        neewer_config_cli,
        "prompt_select_address_from_list",
        lambda *_a, **_k: next(addresses),
    )
    temp_values = iter([neewer_config_cli.WizardBack("Back requested"), 5100])

    def next_temp(*_args, **_kwargs):
        value = next(temp_values)
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(neewer_config_cli, "prompt_temp_kelvin", next_temp)
    values = iter([65, 0])
    monkeypatch.setattr(neewer_config_cli, "prompt_int", lambda *_a, **_k: next(values))

    changed = neewer_config_cli.edit_preset_cct_for_light(cfg)
    assert changed is True
    per_light = cfg["presets"]["studio_default"]["per_light"]
    assert "AA:AA:AA:AA:AA:AA" not in per_light
    assert per_light["BB:BB:BB:BB:BB:BB"]["temp"] == 5100


def test_base_cct_defaults_expand_compact_temp_values():
    temp, bri, gm = neewer_config_cli._base_cct_defaults_for_preset({"temp": 56}, None)
    assert temp == 5600
    assert bri == 30
    assert gm == 0


@pytest.mark.asyncio
async def test_run_detailed_scan_uses_cli_overrides_and_targets_configured(monkeypatch):
    calls = []

    async def fake_discover_with_retries(config, target_addresses, collect_all=False):
        calls.append((config.scan_timeout, config.scan_attempts, target_addresses, collect_all))
        return [], []

    monkeypatch.setattr(
        neewer_config_cli.core,
        "discover_with_retries",
        fake_discover_with_retries,
    )

    args = argparse.Namespace(scan_timeout=9.0, scan_attempts=4, debug=False)
    config_data = {
        "defaults": {"scan_timeout": 3.0, "scan_attempts": 2},
        "lights": {"AA:AA:AA:AA:AA:AA": {"name": "Key"}},
    }

    lights = await neewer_config_cli.run_detailed_scan(config_data, args)
    assert lights == []
    assert len(calls) == 2
    first_timeout, first_attempts, first_targets, first_collect_all = calls[0]
    second_timeout, second_attempts, second_targets, second_collect_all = calls[1]
    assert first_timeout == 9.0
    assert first_attempts == 4
    assert first_targets is None
    assert first_collect_all is True
    assert second_timeout == 9.0
    assert second_attempts == 4
    assert second_targets == {"AA:AA:AA:AA:AA:AA"}
    assert second_collect_all is True


def test_update_lights_metadata_backtracks_to_previous_light(monkeypatch):
    discovered = [
        neewer_config_cli.core.LightInfo(
            name="Key",
            realname="Key",
            address="AA:AA:AA:AA:AA:AA",
            rssi=-50,
            cct_only=False,
            infinity_mode=0,
            ble_device=None,
        ),
        neewer_config_cli.core.LightInfo(
            name="Fill",
            realname="Fill",
            address="BB:BB:BB:BB:BB:BB",
            rssi=-55,
            cct_only=False,
            infinity_mode=0,
            ble_device=None,
        ),
    ]
    cfg = {
        "lights": {},
        "groups": {},
        "presets": {},
        "defaults": {},
    }

    text_values = iter(
        [
            "Key v1",
            neewer_config_cli.WizardBack("Back requested"),
            "Key v2",
            "Fill v1",
        ]
    )
    bool_values = iter([False, True, False])
    int_values = iter([0, 1, 0])

    def next_text(*_args, **_kwargs):
        value = next(text_values)
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(neewer_config_cli, "prompt_text", next_text)
    monkeypatch.setattr(neewer_config_cli, "prompt_yes_no", lambda *_a, **_k: next(bool_values))
    monkeypatch.setattr(neewer_config_cli, "prompt_int", lambda *_a, **_k: next(int_values))

    changed = neewer_config_cli.update_lights_metadata(
        cfg,
        discovered,
        ["AA:AA:AA:AA:AA:AA", "BB:BB:BB:BB:BB:BB"],
    )

    assert changed == 2
    assert cfg["lights"]["AA:AA:AA:AA:AA:AA"]["name"] == "Key v2"
    assert cfg["lights"]["AA:AA:AA:AA:AA:AA"]["infinity_mode"] == 1
    assert cfg["lights"]["BB:BB:BB:BB:BB:BB"]["name"] == "Fill v1"
