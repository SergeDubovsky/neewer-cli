import argparse
from pathlib import Path

import pytest

import neewer_cli


def make_args() -> argparse.Namespace:
    return neewer_cli.build_parser().parse_args([])


def test_get_app_version_returns_non_empty_string():
    assert isinstance(neewer_cli.get_app_version(), str)
    assert neewer_cli.get_app_version() != ""


def test_selector_to_addresses_group_and_mac():
    groups = {"studio": ["AA:AA:AA:AA:AA:AA", "BB:BB:BB:BB:BB:BB"]}
    resolved = neewer_cli.selector_to_addresses("group:studio,cc:cc:cc:cc:cc:cc", groups)
    assert resolved == {
        "AA:AA:AA:AA:AA:AA",
        "BB:BB:BB:BB:BB:BB",
        "CC:CC:CC:CC:CC:CC",
    }


def test_selector_to_addresses_all_returns_none():
    assert neewer_cli.selector_to_addresses("ALL", {}) is None
    assert neewer_cli.selector_to_addresses("*", {}) is None
    assert neewer_cli.selector_to_addresses("", {}) is None


def test_selector_to_addresses_unknown_group_raises():
    with pytest.raises(neewer_cli.ConfigError, match="Unknown group"):
        neewer_cli.selector_to_addresses("group:missing", {})


def test_apply_defaults_respects_cli_override():
    args = make_args()
    config = {"defaults": {"scan_attempts": 9, "debug": True, "parallel": 1}}
    neewer_cli.apply_defaults_from_config(args, config, ["--scan-attempts", "4"])

    # Should not override values explicitly present in argv.
    assert args.scan_attempts == 3
    # Should apply defaults for unset values.
    assert args.debug is True
    assert args.parallel == 1


def test_apply_preset_from_config_sets_per_light_and_light_selector():
    args = make_args()
    args.preset = "mixed"
    config = {
        "presets": {
            "mixed": {
                "per_light": {
                    "aa:bb:cc:dd:ee:ff": {"mode": "cct", "temp": 5600, "bri": 40},
                    "11:22:33:44:55:66": {"power": "OFF"},
                }
            }
        }
    }

    neewer_cli.apply_preset_from_config(args, config, [])
    assert args.light == "11:22:33:44:55:66,AA:BB:CC:DD:EE:FF"
    assert set(args._per_light_preset.keys()) == {
        "11:22:33:44:55:66",
        "AA:BB:CC:DD:EE:FF",
    }


def test_apply_preset_from_config_scene_aliases_map_to_extended_args():
    args = make_args()
    args.preset = "scene_adv"
    config = {
        "presets": {
            "scene_adv": {
                "mode": "SCENE",
                "effect": 13,
                "enable_extended_scene": True,
                "bright_min": 20,
                "bright_max": 80,
                "temp_min": 3200,
                "temp_max": 5600,
                "speed": 7,
            }
        }
    }

    neewer_cli.apply_preset_from_config(args, config, [])
    assert args.mode == "SCENE"
    assert args.scene == 13
    assert args.enable_extended_scene is True
    assert args.scene_bright_min == 20
    assert args.scene_bright_max == 80
    assert args.scene_temp_min == 3200
    assert args.scene_temp_max == 5600
    assert args.scene_speed == 7


def test_build_per_light_command_map_uses_overrides():
    args = make_args()
    args.mode = "CCT"
    args.temp = 32
    args.bri = 10
    args.gm = 0
    args.on = False
    args.off = False
    args._per_light_preset = {
        "AA:AA:AA:AA:AA:AA": {"mode": "CCT", "temp": 5600, "bri": 40, "gm": 0},
        "BB:BB:BB:BB:BB:BB": {"power": "OFF"},
    }

    command_map = neewer_cli.build_per_light_command_map(args)
    assert command_map["AA:AA:AA:AA:AA:AA"] == [120, 135, 2, 40, 56, 50]
    assert command_map["BB:BB:BB:BB:BB:BB"] == [120, 129, 1, 2]


def test_apply_command_overrides_scene_aliases():
    args = make_args()
    args.mode = "SCENE"
    args.enable_extended_scene = False
    neewer_cli.apply_command_overrides(
        args,
        {
            "effect": 12,
            "bright_min": 15,
            "bright_max": 65,
            "hue_min": 20,
            "hue_max": 220,
            "speed": 9,
            "special_options": 3,
        },
    )
    assert args.scene == 12
    assert args.scene_bright_min == 15
    assert args.scene_bright_max == 65
    assert args.scene_hue_min == 20
    assert args.scene_hue_max == 220
    assert args.scene_speed == 9
    assert args.scene_special == 3


def test_build_base_command_invalid_mode_raises_config_error():
    args = make_args()
    args.mode = "BADMODE"
    args.on = False
    args.off = False

    with pytest.raises(neewer_cli.ConfigError, match="Invalid command settings"):
        neewer_cli.build_base_command(args)


def test_build_per_light_command_map_invalid_override_raises_config_error():
    args = make_args()
    args._per_light_preset = {
        "AA:AA:AA:AA:AA:AA": {"mode": "BADMODE"},
    }

    with pytest.raises(neewer_cli.ConfigError, match="Invalid per-light preset"):
        neewer_cli.build_per_light_command_map(args)


def test_calculate_bytestring_cct_clamps_and_parses():
    args = argparse.Namespace(temp=10100, bri=150, gm=-60, hue=0, sat=0, scene=1)
    command = neewer_cli.calculate_bytestring("CCT", args)
    assert command == [120, 135, 2, 100, 100, 0]


def test_calculate_bytestring_scene_extended_payload_enabled():
    args = argparse.Namespace(
        temp=5600,
        bri=30,
        gm=0,
        hue=120,
        sat=70,
        scene=12,
        enable_extended_scene=True,
        scene_bright_min=10,
        scene_bright_max=90,
        scene_temp_min=3200,
        scene_temp_max=6500,
        scene_hue_min=30,
        scene_hue_max=180,
        scene_speed=6,
        scene_sparks=2,
        scene_special=1,
    )
    command = neewer_cli.calculate_bytestring("SCENE", args)
    assert command == [120, 136, 7, 12, 30, 30, 0, 180, 0, 6]


def test_build_payload_sequence_cct_only_splits_commands():
    light = neewer_cli.LightInfo(
        name="CCTOnly",
        realname="CCTOnly",
        address="AA:AA:AA:AA:AA:AA",
        rssi=-50,
        cct_only=True,
        infinity_mode=0,
        ble_device=None,
    )
    base = [120, 135, 2, 30, 56, 50]
    seq = neewer_cli.build_payload_sequence(light, base, power_with_response=True)

    assert len(seq) == 2
    assert seq[0] == (neewer_cli.tag_checksum([120, 130, 1, 30]), False, 0.05)
    assert seq[1] == (neewer_cli.tag_checksum([120, 131, 1, 56]), False, 0.0)


def test_build_payload_sequence_rejects_hsi_for_cct_only():
    light = neewer_cli.LightInfo(
        name="CCTOnly",
        realname="CCTOnly",
        address="AA:AA:AA:AA:AA:AA",
        rssi=-50,
        cct_only=True,
        infinity_mode=0,
        ble_device=None,
    )
    hsi = [120, 134, 4, 240, 0, 100, 50]

    with pytest.raises(neewer_cli.UnsupportedModeError):
        neewer_cli.build_payload_sequence(light, hsi, power_with_response=True)


def test_build_payload_sequence_non_infinity_cct_drops_gm():
    light = neewer_cli.LightInfo(
        name="FS150B",
        realname="FS150B",
        address="AA:AA:AA:AA:AA:AA",
        rssi=-50,
        cct_only=False,
        infinity_mode=0,
        ble_device=None,
    )
    base = [120, 135, 2, 40, 56, 80]
    seq = neewer_cli.build_payload_sequence(light, base, power_with_response=True)
    assert seq == [(neewer_cli.tag_checksum([120, 135, 2, 40, 56]), False, 0.0)]


def test_build_payload_sequence_rejects_extended_scene_on_unsupported_model():
    light = neewer_cli.LightInfo(
        name="FS150B",
        realname="FS150B",
        address="AA:AA:AA:AA:AA:AA",
        rssi=-50,
        cct_only=False,
        infinity_mode=0,
        ble_device=None,
    )
    extended_scene = [120, 136, 7, 12, 30, 30, 0, 180, 0, 6]

    with pytest.raises(neewer_cli.UnsupportedModeError, match="extended scene"):
        neewer_cli.build_payload_sequence(light, extended_scene, power_with_response=True)


def test_parse_status_payload_maps_power_and_channel():
    parsed = neewer_cli.parse_status_payload([120, 2, 1, 1], [120, 1, 1, 4])
    assert parsed["power"] == "ON"
    assert parsed["channel"] == 4
    assert parsed["power_raw"] == [120, 2, 1, 1]
    assert parsed["channel_raw"] == [120, 1, 1, 4]


def test_get_static_lights_from_config_includes_missing_addresses():
    lights_cfg = {
        "AA:AA:AA:AA:AA:AA": {"name": "Key", "infinity_mode": 0, "cct_only": False}
    }
    lights, missing = neewer_cli.get_static_lights_from_config(
        {"AA:AA:AA:AA:AA:AA", "BB:BB:BB:BB:BB:BB"}, lights_cfg
    )
    assert len(lights) == 2
    assert missing == ["BB:BB:BB:BB:BB:BB"]
    by_addr = {light.address: light for light in lights}
    assert by_addr["AA:AA:AA:AA:AA:AA"].name == "Key"
    assert by_addr["BB:BB:BB:BB:BB:BB"].name == "Configured Light"


def test_load_user_config_missing_default_path_returns_empty(monkeypatch, tmp_path: Path):
    missing_default = tmp_path / ".neewer-default"
    monkeypatch.setattr(neewer_cli, "DEFAULT_CONFIG_PATH", str(missing_default))
    assert neewer_cli.load_user_config(str(missing_default), debug=False) == {}


def test_load_user_config_normalizes_lights_and_groups(tmp_path: Path):
    cfg = tmp_path / "cfg.json"
    cfg.write_text(
        """
{
  "lights": [
    {"address": "aa:bb:cc:dd:ee:ff", "name": "Key"}
  ],
  "groups": {
    "studio": "aa:bb:cc:dd:ee:ff,11:22:33:44:55:66"
  },
  "presets": {},
  "defaults": {}
}
""".strip(),
        encoding="utf-8",
    )

    loaded = neewer_cli.load_user_config(str(cfg), debug=False)
    assert set(loaded["lights"].keys()) == {"AA:BB:CC:DD:EE:FF"}
    assert loaded["groups"]["studio"] == ["AA:BB:CC:DD:EE:FF", "11:22:33:44:55:66"]


def test_validate_runtime_args_status_requires_feature_flag():
    parser = neewer_cli.build_parser()
    args = parser.parse_args(["--status", "--light", "AA:AA:AA:AA:AA:AA"])
    with pytest.raises(neewer_cli.ConfigError, match="--status requires --enable-status-query"):
        neewer_cli.validate_runtime_args(args)


def test_validate_runtime_args_allows_status_when_enabled():
    parser = neewer_cli.build_parser()
    args = parser.parse_args(
        ["--status", "--enable-status-query", "--light", "AA:AA:AA:AA:AA:AA"]
    )
    neewer_cli.validate_runtime_args(args)


@pytest.mark.asyncio
async def test_query_light_status_once_rejects_unsupported_model():
    class FakeClient:
        is_connected = True

    light = neewer_cli.LightInfo(
        name="FS150B",
        realname="FS150B",
        address="AA:AA:AA:AA:AA:AA",
        rssi=-40,
        cct_only=False,
        infinity_mode=0,
        ble_device=None,
        client=FakeClient(),  # type: ignore[arg-type]
    )
    config = neewer_cli.AppConfig(
        debug=False,
        scan_timeout=1.0,
        scan_attempts=1,
        connect_timeout=1.0,
        connect_retries=1,
        write_retries=1,
        passes=1,
        parallel=1,
        settle_delay=0.0,
        power_with_response=True,
        enable_status_query=True,
    )

    ok, err, payload = await neewer_cli.query_light_status_once(light, config)
    assert ok is False
    assert "not supported" in err.lower()
    assert payload == {}


@pytest.mark.asyncio
async def test_send_command_once_writes_payload():
    class FakeClient:
        def __init__(self):
            self.is_connected = True
            self.calls = []

        async def write_gatt_char(self, uuid, data, response=False):
            self.calls.append((uuid, list(data), response))

    client = FakeClient()
    light = neewer_cli.LightInfo(
        name="Test",
        realname="Test",
        address="AA:AA:AA:AA:AA:AA",
        rssi=-40,
        cct_only=False,
        infinity_mode=0,
        ble_device=None,
        client=client,  # type: ignore[arg-type]
    )
    config = neewer_cli.AppConfig(
        debug=False,
        scan_timeout=1.0,
        scan_attempts=1,
        connect_timeout=1.0,
        connect_retries=1,
        write_retries=1,
        passes=1,
        parallel=1,
        settle_delay=0.0,
        power_with_response=True,
    )
    command = [120, 135, 2, 40, 56, 50]
    ok, err = await neewer_cli.send_command_once(light, command, config)

    assert ok is True
    assert err == ""
    assert len(client.calls) == 1
    assert client.calls[0][0] == neewer_cli.SET_LIGHT_UUID
