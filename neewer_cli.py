#!/usr/bin/env python3
"""
Standalone Neewer BLE CLI utility.

This script intentionally avoids all GUI/threading code from NeewerLite-Python.py
and focuses on fast + reliable command delivery over BLE.

Attribution:
- Based on NeewerLite-Python by Zach Glenwright:
  https://github.com/taburineagle/NeewerLite-Python
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

try:
    from bleak import BleakClient, BleakScanner
except ModuleNotFoundError:
    print("Missing dependency: bleak")
    print("Install with: pip install bleak")
    sys.exit(1)


SET_LIGHT_UUID = "69400002-B5A3-F393-E0A9-E50E24DCCA99"
DEFAULT_CONFIG_PATH = os.path.expanduser("~/.neewer")

# (needle in raw device name, corrected model name)
NEW_LIGHT_NAMES = [
    ("20200015", "RGB1"),
    ("20200037", "SL90"),
    ("20200049", "RGB1200"),
    ("20210006", "Apollo 150D"),
    ("20210007", "RGB C80"),
    ("20210012", "CB60 RGB"),
    ("20210018", "BH-30S RGB"),
    ("20210034", "MS60B"),
    ("20210035", "MS60C"),
    ("20210036", "TL60 RGB"),
    ("20210037", "CB200B"),
    ("20220014", "CB60B"),
    ("20220016", "PL60C"),
    ("20220035", "MS150B"),
    ("20220041", "AS600B"),
    ("20220043", "FS150B"),
    ("20220046", "RP19C"),
    ("20220051", "CB100C"),
    ("20220055", "CB300B"),
    ("20220057", "SL90 Pro"),
    ("20230021", "BH-30S RGB"),
    ("20230022", "HS60B"),
    ("20230025", "RGB1200"),
    ("20230031", "TL120C"),
    ("20230050", "FS230 5600K"),
    ("20230051", "FS230B"),
    ("20230052", "FS150 5600K"),
    ("20230064", "TL60 RGB"),
    ("20230080", "MS60C"),
    ("20230092", "RGB1200"),
    ("20230108", "HB80C"),
]

# NAME, CCT TEMP MIN, CCT TEMP MAX, CCT-ONLY, INFINITY MODE
# INFINITY MODE:
# 0: classic command path
# 1: Infinity command path
# 2: Infinity protocol, but not full Infinity light behavior
MASTER_LIGHT_SPECS = [
    ("Apollo", 5600, 5600, True, 0),
    ("BH-30S RGB", 2500, 10000, False, 1),
    ("CB60 RGB", 2500, 6500, False, 1),
    ("CL124", 2500, 10000, False, 2),
    ("GL1", 2900, 7000, True, 0),
    ("GL1C", 2900, 7000, False, 1),
    ("HB80C", 2500, 7500, False, 1),
    ("MS60B", 2700, 6500, True, 1),
    ("NL140", 3200, 5600, True, 0),
    ("RGB C80", 2500, 10000, False, 1),
    ("RGB CB60", 2500, 10000, False, 1),
    ("RGB1", 3200, 5600, False, 1),
    ("RGB1000", 2500, 10000, False, 1),
    ("RGB1200", 2500, 10000, False, 1),
    ("RGB140", 2500, 10000, False, 1),
    ("RGB168", 2500, 8500, False, 2),
    ("RGB176", 3200, 5600, False, 0),
    ("RGB176 A1", 2500, 10000, False, 0),
    ("RGB18", 3200, 5600, False, 0),
    ("RGB190", 3200, 5600, False, 0),
    ("RGB450", 3200, 5600, False, 0),
    ("RGB480", 3200, 5600, False, 0),
    ("RGB512", 2500, 10000, False, 1),
    ("RGB530", 3200, 5600, False, 0),
    ("RGB530PRO", 3200, 5600, False, 0),
    ("RGB650", 3200, 5600, False, 0),
    ("RGB660", 3200, 5600, False, 0),
    ("RGB660PRO", 3200, 5600, False, 0),
    ("RGB800", 2500, 10000, False, 1),
    ("RGB960", 3200, 5600, False, 0),
    ("RGB-P200", 3200, 5600, False, 0),
    ("RGB-P280", 3200, 5600, False, 0),
    ("SL70", 3200, 8500, False, 0),
    ("SL80", 3200, 8500, False, 0),
    ("SL90", 2500, 10000, False, 1),
    ("SL90 Pro", 2500, 10000, False, 1),
    ("SNL1320", 3200, 5600, True, 0),
    ("SNL1920", 3200, 5600, True, 0),
    ("SNL480", 3200, 5600, True, 0),
    ("SNL530", 3200, 5600, True, 0),
    ("SNL660", 3200, 5600, True, 0),
    ("SNL960", 3200, 5600, True, 0),
    ("SRP16", 3200, 5600, True, 0),
    ("SRP18", 3200, 5600, True, 0),
    ("TL60", 2500, 10000, False, 1),
    ("WRP18", 3200, 5600, True, 0),
    ("ZK-RY", 5600, 5600, False, 0),
    ("ZRP16", 3200, 5600, True, 0),
]

ACCEPTED_NAME_PREFIXES = ("NEEWER", "NW-", "SL", "NWR")


@dataclass
class LightInfo:
    name: str
    realname: str
    address: str
    rssi: int
    cct_only: bool
    infinity_mode: int
    ble_device: Any
    hw_mac: Optional[str] = None
    client: Optional[BleakClient] = None


@dataclass
class AppConfig:
    debug: bool
    scan_timeout: float
    scan_attempts: int
    connect_timeout: float
    connect_retries: int
    write_retries: int
    passes: int
    parallel: int
    settle_delay: float
    power_with_response: bool


class UnsupportedModeError(RuntimeError):
    pass


class ConfigError(RuntimeError):
    pass


def log(msg: str, debug: bool = False, enabled: bool = True) -> None:
    if debug and not enabled:
        return
    timestamp = time.strftime("%H:%M:%S")
    print(f"[{timestamp}] {msg}")


def normalize_address(addr: str) -> str:
    return addr.strip().upper()


def _to_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lower = value.strip().lower()
        if lower in {"1", "true", "yes", "on"}:
            return True
        if lower in {"0", "false", "no", "off"}:
            return False
    return default


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _arg_present(argv: Sequence[str], arg_name: str) -> bool:
    flag = f"--{arg_name.replace('_', '-')}"
    for token in argv:
        if token == flag or token.startswith(flag + "="):
            return True
    return False


def _normalize_lights_block(raw_lights: Any) -> Dict[str, Dict[str, Any]]:
    if raw_lights is None:
        return {}
    if isinstance(raw_lights, dict):
        normalized: Dict[str, Dict[str, Any]] = {}
        for key, value in raw_lights.items():
            if not isinstance(value, dict):
                value = {}
            normalized[normalize_address(str(key))] = value
        return normalized
    if isinstance(raw_lights, list):
        normalized = {}
        for row in raw_lights:
            if not isinstance(row, dict):
                continue
            address = row.get("address")
            if not address:
                continue
            row_copy = dict(row)
            row_copy.pop("address", None)
            normalized[normalize_address(str(address))] = row_copy
        return normalized
    raise ConfigError("'lights' must be an object or array")


def _normalize_groups_block(raw_groups: Any) -> Dict[str, List[str]]:
    if raw_groups is None:
        return {}
    if not isinstance(raw_groups, dict):
        raise ConfigError("'groups' must be an object")
    normalized: Dict[str, List[str]] = {}
    for group_name, members in raw_groups.items():
        key = str(group_name)
        if isinstance(members, str):
            members = [x.strip() for x in members.split(",") if x.strip()]
        if not isinstance(members, list):
            continue
        normalized[key] = [normalize_address(str(m)) for m in members if str(m).strip()]
    return normalized


def _load_config_file(path: str) -> Dict[str, Any]:
    ext = os.path.splitext(path)[1].lower()
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()

    if ext in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore
        except ModuleNotFoundError as exc:
            raise ConfigError(
                "YAML config requires PyYAML (pip install pyyaml) or use JSON config."
            ) from exc
        parsed = yaml.safe_load(text)
    else:
        parsed = json.loads(text)

    if parsed is None:
        return {}
    if not isinstance(parsed, dict):
        raise ConfigError("Config root must be a JSON/YAML object.")
    return parsed


def load_user_config(path: str, debug: bool) -> Dict[str, Any]:
    if not path:
        return {}
    expanded_path = os.path.expanduser(path)
    if not os.path.exists(expanded_path):
        if os.path.abspath(expanded_path) == os.path.abspath(DEFAULT_CONFIG_PATH):
            # Optional default config file.
            return {}
        raise ConfigError(f"Config file not found: {path}")

    parsed = _load_config_file(expanded_path)
    parsed["lights"] = _normalize_lights_block(parsed.get("lights"))
    parsed["groups"] = _normalize_groups_block(parsed.get("groups"))

    if "presets" in parsed and not isinstance(parsed["presets"], dict):
        raise ConfigError("'presets' must be an object")
    if "defaults" in parsed and not isinstance(parsed["defaults"], dict):
        raise ConfigError("'defaults' must be an object")

    if debug:
        log(
            f"Loaded config '{expanded_path}' (lights={len(parsed['lights'])}, "
            f"groups={len(parsed['groups'])}, presets={len(parsed.get('presets', {}))})"
        )
    return parsed


def selector_to_addresses(
    selector: str, groups: Dict[str, List[str]]
) -> Optional[set]:
    if selector.strip() == "" or selector.upper() in {"ALL", "*"}:
        return None

    resolved: set = set()
    for token in [x.strip() for x in selector.split(",") if x.strip()]:
        if token.lower().startswith("group:"):
            group_name = token.split(":", 1)[1]
            if group_name not in groups:
                raise ConfigError(f"Unknown group '{group_name}' in light selector")
            resolved.update(groups[group_name])
        else:
            resolved.add(normalize_address(token))
    return resolved


def apply_defaults_from_config(
    args: argparse.Namespace,
    config_data: Dict[str, Any],
    argv: Sequence[str],
) -> None:
    defaults = config_data.get("defaults", {})
    if not isinstance(defaults, dict):
        return

    for key, value in defaults.items():
        attr = key.replace("-", "_")
        if not hasattr(args, attr):
            continue
        if _arg_present(argv, attr):
            continue
        current = getattr(args, attr)
        if isinstance(current, bool):
            setattr(args, attr, _to_bool(value, current))
        elif isinstance(current, int):
            setattr(args, attr, _to_int(value, current))
        elif isinstance(current, float):
            setattr(args, attr, _to_float(value, current))
        else:
            setattr(args, attr, value)


def apply_preset_from_config(
    args: argparse.Namespace,
    config_data: Dict[str, Any],
    argv: Sequence[str],
) -> None:
    args._per_light_preset = {}

    if not args.preset:
        return
    presets = config_data.get("presets", {})
    if not isinstance(presets, dict):
        raise ConfigError("Config 'presets' must be an object")
    if args.preset not in presets:
        raise ConfigError(f"Preset '{args.preset}' not found in config")

    preset = presets[args.preset]
    if not isinstance(preset, dict):
        raise ConfigError(f"Preset '{args.preset}' must be an object")

    if "per_light" in preset:
        per_light = preset["per_light"]
        if not isinstance(per_light, dict):
            raise ConfigError(f"Preset '{args.preset}'.per_light must be an object")
        normalized: Dict[str, Dict[str, Any]] = {}
        for address, command_info in per_light.items():
            if not isinstance(command_info, dict):
                raise ConfigError(
                    f"Preset '{args.preset}'.per_light[{address}] must be an object"
                )
            normalized[normalize_address(str(address))] = dict(command_info)
        args._per_light_preset = normalized
        if not _arg_present(argv, "light") and normalized:
            args.light = ",".join(sorted(normalized.keys()))

    alias_map = {
        "brightness": "bri",
        "saturation": "sat",
        "temperature": "temp",
        "effect": "scene",
        "power": "on",
    }

    for raw_key, value in preset.items():
        if raw_key == "per_light":
            continue
        key = alias_map.get(raw_key, raw_key).replace("-", "_")
        if key == "lights":
            if _arg_present(argv, "light"):
                continue
            if isinstance(value, list):
                args.light = ",".join(str(x) for x in value)
            else:
                args.light = str(value)
            continue

        if key == "on":
            if _arg_present(argv, "on") or _arg_present(argv, "off"):
                continue
            if isinstance(value, str):
                normalized = value.strip().upper()
                args.on = normalized in {"ON", "1", "TRUE"}
                args.off = normalized in {"OFF", "0", "FALSE"}
            else:
                args.on = _to_bool(value, False)
                args.off = not args.on
            continue

        if not hasattr(args, key):
            continue
        if _arg_present(argv, key):
            continue

        current = getattr(args, key)
        if isinstance(current, bool):
            setattr(args, key, _to_bool(value, current))
        elif isinstance(current, int):
            setattr(args, key, _to_int(value, current))
        elif isinstance(current, float):
            setattr(args, key, _to_float(value, current))
        else:
            setattr(args, key, value)


def get_static_lights_from_config(
    target_addresses: Optional[set],
    lights_cfg: Dict[str, Dict[str, Any]],
) -> Tuple[List[LightInfo], List[str]]:
    if target_addresses is None:
        if not lights_cfg:
            raise ConfigError(
                "--skip-discovery with --light ALL requires configured lights in the config file."
            )
        addresses = sorted(lights_cfg.keys())
    else:
        addresses = sorted(target_addresses)

    lights: List[LightInfo] = []
    missing: List[str] = []

    for address in addresses:
        meta = lights_cfg.get(address)
        if meta is None:
            missing.append(address)
            meta = {}

        name = str(meta.get("name") or "Configured Light")
        _, inferred_cct_only, inferred_infinity_mode = get_light_specs(name)
        cct_only = _to_bool(meta.get("cct_only"), inferred_cct_only)
        infinity_mode = _to_int(meta.get("infinity_mode"), inferred_infinity_mode)
        hw_mac = meta.get("hw_mac")
        if isinstance(hw_mac, str):
            hw_mac = normalize_address(hw_mac)
        else:
            hw_mac = None

        lights.append(
            LightInfo(
                name=name,
                realname=name,
                address=address,
                rssi=_to_int(meta.get("rssi"), -127),
                cct_only=cct_only,
                infinity_mode=infinity_mode,
                ble_device=None,
                hw_mac=hw_mac,
            )
        )

    return lights, missing


def merge_light_metadata_from_config(
    lights: Sequence[LightInfo], lights_cfg: Dict[str, Dict[str, Any]]
) -> None:
    for light in lights:
        meta = lights_cfg.get(light.address)
        if not meta:
            continue
        if "name" in meta and str(meta["name"]).strip():
            light.name = str(meta["name"]).strip()
            light.realname = light.name
        if "cct_only" in meta:
            light.cct_only = _to_bool(meta["cct_only"], light.cct_only)
        if "infinity_mode" in meta:
            light.infinity_mode = _to_int(meta["infinity_mode"], light.infinity_mode)
        if "hw_mac" in meta and isinstance(meta["hw_mac"], str) and meta["hw_mac"].strip():
            light.hw_mac = normalize_address(meta["hw_mac"])


def get_corrected_name(light_name: str) -> str:
    if not light_name:
        return "Unknown"
    for needle, corrected in NEW_LIGHT_NAMES:
        if needle in light_name:
            return corrected
    return light_name


def get_light_specs(light_name: str) -> Tuple[List[int], bool, int]:
    cct_bounds = [3200, 5600]
    cct_only = False
    infinity_mode = 0

    for entry in reversed(MASTER_LIGHT_SPECS):
        if entry[0] in light_name:
            cct_bounds = [entry[1], entry[2]]
            cct_only = entry[3]
            infinity_mode = entry[4]
            break
    return cct_bounds, cct_only, infinity_mode


def is_neewer_device(name: Optional[str]) -> bool:
    if not name:
        return False
    upper_name = name.upper()
    return any(prefix in upper_name for prefix in ACCEPTED_NAME_PREFIXES)


def split_mac_address(mac_address: str) -> List[int]:
    parts = mac_address.split(":")
    if len(parts) != 6:
        raise ValueError(f"Expected MAC address with 6 octets, got: {mac_address}")
    return [int(part, 16) for part in parts]


def tag_checksum(payload: Sequence[int]) -> List[int]:
    checksum = 0
    tagged = []
    for value in payload:
        checksum += (value + 256) if value < 0 else value
        tagged.append(value)
    tagged.append(checksum & 0xFF)
    return tagged


def clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def parse_temp_value(temp_raw: int) -> int:
    temp = int(temp_raw)
    if temp >= 100:
        # Accept values like 5600 and convert to 56 to match protocol payload.
        temp = int(round(temp / 100.0))
    return temp


def convert_fx_index(infinity_mode: int, effect_num: int) -> int:
    if infinity_mode > 0:
        if effect_num > 20:
            return {
                21: 10,
                22: 8,
                23: 12,
                24: 12,
                25: 17,
                26: 11,
                27: 1,
                28: 2,
                29: 15,
            }.get(effect_num, effect_num)
        return effect_num

    if effect_num < 20:
        return {
            10: 1,
            16: 4,
            17: 5,
            11: 6,
            1: 7,
            2: 8,
            15: 9,
        }.get(effect_num, 10)
    return effect_num - 20


def calculate_bytestring(color_mode: str, args: argparse.Namespace) -> List[int]:
    mode = color_mode.upper()
    if mode == "CCT":
        temp = clamp(parse_temp_value(args.temp), 25, 100)
        bri = clamp(int(args.bri), 0, 100)
        gm = clamp(int(args.gm) + 50, 0, 100)
        return [120, 135, 2, bri, temp, gm]

    if mode == "HSI":
        hue = clamp(int(args.hue), 0, 360)
        sat = clamp(int(args.sat), 0, 100)
        bri = clamp(int(args.bri), 0, 100)
        return [120, 134, 4, hue & 0xFF, (hue & 0xFF00) >> 8, sat, bri]

    if mode in ("ANM", "SCENE"):
        effect = clamp(int(args.scene), 1, 29)
        bri = clamp(int(args.bri), 0, 100)
        return [120, 136, 2, effect, bri]

    raise ValueError(f"Unsupported mode: {color_mode}")


def set_power_bytestring(power_on: bool) -> List[int]:
    return [120, 129, 1, 1 if power_on else 2]


def get_infinity_power_bytestring(power_on: bool, light_mac_address: str) -> List[int]:
    payload = [120, 141, 8]
    payload.extend(split_mac_address(light_mac_address))
    payload.extend([129, 1 if power_on else 0])
    return payload


def cct_split_bytestrings(command: Sequence[int]) -> List[List[int]]:
    bri_only = [120, 130, 1, int(command[3])]
    temp_only = [120, 131, 1, int(command[4])]
    return [bri_only, temp_only]


def get_hw_mac_for_light(light: LightInfo) -> str:
    if light.hw_mac:
        return light.hw_mac
    if light.address.count(":") == 5:
        return light.address
    raise ValueError(
        f"Infinity command requires a MAC address but device address is '{light.address}'."
    )


def build_payload_sequence(
    light: LightInfo, base_command: Sequence[int], power_with_response: bool
) -> List[Tuple[List[int], bool, float]]:
    mode = int(base_command[1])

    if light.cct_only and mode in (134, 136):
        raise UnsupportedModeError(f"{light.name} only supports CCT mode.")

    if mode == 129:
        if light.infinity_mode == 1:
            power_on = int(base_command[3]) == 1
            hw_mac = get_hw_mac_for_light(light)
            payload = tag_checksum(get_infinity_power_bytestring(power_on, hw_mac))
            return [(payload, power_with_response, 0.0)]
        payload = tag_checksum(list(base_command))
        return [(payload, power_with_response, 0.0)]

    if mode == 135:
        if light.cct_only:
            split_values = cct_split_bytestrings(base_command)
            return [
                (tag_checksum(split_values[0]), False, 0.05),
                (tag_checksum(split_values[1]), False, 0.0),
            ]

        if light.infinity_mode == 1:
            hw_mac = get_hw_mac_for_light(light)
            payload = [120, 144, 11]
            payload.extend(split_mac_address(hw_mac))
            payload.extend([135, base_command[3], base_command[4], base_command[5], 4])
            return [(tag_checksum(payload), False, 0.0)]

        if light.infinity_mode == 2:
            payload = list(base_command)
            payload[2] = 3
            return [(tag_checksum(payload), False, 0.0)]

        # Classic non-Infinity lights ignore GM in CCT.
        return [(tag_checksum(list(base_command[:5])), False, 0.0)]

    if mode == 134:
        if light.infinity_mode == 1:
            hw_mac = get_hw_mac_for_light(light)
            payload = [120, 143, 11]
            payload.extend(split_mac_address(hw_mac))
            payload.extend(
                [
                    134,
                    base_command[3],
                    base_command[4],
                    base_command[5],
                    base_command[6],
                ]
            )
            return [(tag_checksum(payload), False, 0.0)]
        return [(tag_checksum(list(base_command)), False, 0.0)]

    if mode == 136:
        if light.infinity_mode == 1:
            hw_mac = get_hw_mac_for_light(light)
            payload = [120, 145, 6 + (len(base_command) - 2)]
            payload.extend(split_mac_address(hw_mac))
            payload.extend([139, convert_fx_index(1, int(base_command[3]))])
            payload.extend(base_command[4:])

            power_off = tag_checksum(get_infinity_power_bytestring(False, hw_mac))
            power_on = tag_checksum(get_infinity_power_bytestring(True, hw_mac))
            return [
                (power_off, False, 0.05),
                (power_on, False, 0.05),
                (tag_checksum(payload), False, 0.0),
            ]

        if light.infinity_mode == 2:
            payload = list(base_command)
            payload[1] = 139
            payload[2] = len(payload) - 3
            return [(tag_checksum(payload), False, 0.0)]

        payload = list(base_command[:5])
        current_effect = payload[3]
        payload[3] = payload[4]
        payload[4] = convert_fx_index(0, int(current_effect))
        return [(tag_checksum(payload), False, 0.0)]

    raise ValueError(f"Unsupported command mode byte: {mode}")


async def discover_devices(
    scan_timeout: float, target_addresses: Optional[set], debug: bool
) -> Dict[str, LightInfo]:
    discovered: Dict[str, LightInfo] = {}

    try:
        device_scan = await BleakScanner.discover(timeout=scan_timeout, return_adv=True)
        iterable: Iterable[Tuple[Any, Any]] = device_scan.values()
    except TypeError:
        # Older bleak fallback without return_adv support.
        raw_scan = await BleakScanner.discover(timeout=scan_timeout)
        iterable = [(dev, type("Adv", (), {"rssi": getattr(dev, "rssi", -127)})()) for dev in raw_scan]

    for device, adv_data in iterable:
        address = normalize_address(device.address)
        raw_name = device.name or ""

        if target_addresses is not None:
            if address not in target_addresses:
                continue
        elif not is_neewer_device(raw_name):
            continue

        corrected_name = get_corrected_name(raw_name)
        _, cct_only, infinity_mode = get_light_specs(corrected_name)
        rssi = int(getattr(adv_data, "rssi", -127))
        existing = discovered.get(address)

        # Keep the strongest RSSI record when duplicates appear.
        if existing is None or rssi > existing.rssi:
            discovered[address] = LightInfo(
                name=corrected_name or "Unknown",
                realname=raw_name or corrected_name or "Unknown",
                address=address,
                rssi=rssi,
                cct_only=cct_only,
                infinity_mode=infinity_mode,
                ble_device=device,
            )

    if debug:
        log(f"Discovery returned {len(discovered)} matching device(s).")
    return discovered


async def discover_with_retries(
    config: AppConfig, target_addresses: Optional[set]
) -> Tuple[List[LightInfo], List[str]]:
    collected: Dict[str, LightInfo] = {}
    missing: List[str] = []

    for attempt in range(1, config.scan_attempts + 1):
        log(
            f"Scanning for BLE devices (attempt {attempt}/{config.scan_attempts}, "
            f"timeout={config.scan_timeout:.1f}s)..."
        )
        found = await discover_devices(config.scan_timeout, target_addresses, config.debug)
        collected.update(found)

        if target_addresses is not None:
            missing = sorted(addr for addr in target_addresses if addr not in collected)
            if not missing:
                break
            if attempt < config.scan_attempts:
                log(f"Still missing {len(missing)} target device(s), retrying...", enabled=True)
        else:
            if collected:
                break

    if target_addresses is not None:
        missing = sorted(addr for addr in target_addresses if addr not in collected)
    return list(collected.values()), missing


async def connect_light(light: LightInfo, config: AppConfig) -> Tuple[bool, str]:
    last_error = ""
    target = light.ble_device if light.ble_device is not None else light.address

    for attempt in range(1, config.connect_retries + 1):
        client: Optional[BleakClient] = None
        try:
            log(
                f"Connecting to {light.address} [{light.name}] "
                f"(attempt {attempt}/{config.connect_retries})...",
                debug=True,
                enabled=config.debug,
            )
            client = BleakClient(target, timeout=config.connect_timeout)
            await client.connect()
            if not client.is_connected:
                raise RuntimeError("connect() completed but client is not connected")
            light.client = client
            if light.infinity_mode == 1 and light.address.count(":") == 5:
                light.hw_mac = light.address
            return True, ""
        except Exception as exc:  # pragma: no cover - runtime BLE dependent
            last_error = str(exc)
            if client is not None:
                try:
                    await client.disconnect()
                except Exception:
                    pass
            await asyncio.sleep(min(0.2 * attempt, 1.0))

    return False, last_error


async def disconnect_light(light: LightInfo, config: AppConfig) -> None:
    if light.client is None:
        return
    try:
        if light.client.is_connected:
            await light.client.disconnect()
            log(
                f"Disconnected {light.address} [{light.name}]",
                debug=True,
                enabled=config.debug,
            )
    except Exception as exc:  # pragma: no cover - runtime BLE dependent
        log(f"Disconnect failed for {light.address}: {exc}", enabled=True)
    finally:
        light.client = None


async def run_bounded(
    items: Sequence[LightInfo],
    parallel: int,
    fn,
) -> List[Any]:
    sem = asyncio.Semaphore(max(1, parallel))

    async def _runner(item: LightInfo):
        async with sem:
            return await fn(item)

    return list(await asyncio.gather(*(_runner(item) for item in items)))


async def write_payload(
    client: BleakClient,
    payload: Sequence[int],
    response: bool,
    retries: int,
    debug: bool,
) -> Tuple[bool, str]:
    last_error = ""
    for attempt in range(1, retries + 1):
        try:
            await client.write_gatt_char(SET_LIGHT_UUID, bytearray(payload), response=response)
            return True, ""
        except Exception as exc:  # pragma: no cover - runtime BLE dependent
            last_error = str(exc)
            if debug:
                log(
                    f"write_gatt_char failed (attempt {attempt}/{retries}): {exc}",
                    debug=True,
                    enabled=True,
                )
            await asyncio.sleep(min(0.1 * attempt, 0.5))
    return False, last_error


async def send_command_once(
    light: LightInfo, base_command: Sequence[int], config: AppConfig
) -> Tuple[bool, str]:
    if light.client is None or not light.client.is_connected:
        return False, "not connected"

    try:
        payload_sequence = build_payload_sequence(
            light, base_command, power_with_response=config.power_with_response
        )
    except UnsupportedModeError as exc:
        return False, str(exc)
    except Exception as exc:
        return False, str(exc)

    for payload, response, extra_delay in payload_sequence:
        ok, err = await write_payload(
            light.client, payload, response, config.write_retries, config.debug
        )
        if not ok:
            return False, err

        delay = max(config.settle_delay, extra_delay)
        if delay > 0:
            await asyncio.sleep(delay)

    return True, ""


def format_status_command(base_command: Sequence[int]) -> str:
    mode = base_command[1]
    if mode == 129:
        return "Power ON" if base_command[3] == 1 else "Power OFF"
    if mode == 135:
        return f"CCT temp={base_command[4]}00K bri={base_command[3]} gm={base_command[5]-50}"
    if mode == 134:
        hue = base_command[3] + (256 * base_command[4])
        return f"HSI hue={hue} sat={base_command[5]} bri={base_command[6]}"
    if mode == 136:
        return f"SCENE effect={base_command[3]} bri={base_command[4]}"
    return f"RAW {list(base_command)}"


def parse_addresses(light_arg: str, groups: Dict[str, List[str]]) -> Optional[set]:
    return selector_to_addresses(light_arg, groups)


def build_config(args: argparse.Namespace) -> AppConfig:
    return AppConfig(
        debug=bool(args.debug),
        scan_timeout=float(args.scan_timeout),
        scan_attempts=max(1, int(args.scan_attempts)),
        connect_timeout=float(args.connect_timeout),
        connect_retries=max(1, int(args.connect_retries)),
        write_retries=max(1, int(args.write_retries)),
        passes=max(1, int(args.passes)),
        parallel=max(1, int(args.parallel)),
        settle_delay=max(0.0, float(args.settle_ms) / 1000.0),
        power_with_response=not bool(args.no_response),
    )


def build_base_command(args: argparse.Namespace) -> List[int]:
    if args.on:
        return set_power_bytestring(True)
    if args.off:
        return set_power_bytestring(False)
    return calculate_bytestring(args.mode, args)


def apply_command_overrides(
    namespace: argparse.Namespace,
    overrides: Dict[str, Any],
) -> None:
    alias_map = {
        "brightness": "bri",
        "saturation": "sat",
        "temperature": "temp",
        "effect": "scene",
        "power": "on",
    }

    for raw_key, raw_value in overrides.items():
        key = alias_map.get(raw_key, raw_key).replace("-", "_")
        if key == "on":
            if isinstance(raw_value, str):
                normalized = raw_value.strip().upper()
                namespace.on = normalized in {"ON", "1", "TRUE"}
                namespace.off = normalized in {"OFF", "0", "FALSE"}
            else:
                namespace.on = _to_bool(raw_value, False)
                namespace.off = not namespace.on
            continue

        if not hasattr(namespace, key):
            continue
        current = getattr(namespace, key)
        if isinstance(current, bool):
            setattr(namespace, key, _to_bool(raw_value, current))
        elif isinstance(current, int):
            setattr(namespace, key, _to_int(raw_value, current))
        elif isinstance(current, float):
            setattr(namespace, key, _to_float(raw_value, current))
        else:
            setattr(namespace, key, raw_value)

    if hasattr(namespace, "mode") and namespace.mode:
        namespace.mode = str(namespace.mode).upper()


def build_per_light_command_map(args: argparse.Namespace) -> Dict[str, List[int]]:
    per_light = getattr(args, "_per_light_preset", {})
    if not per_light:
        return {}

    command_map: Dict[str, List[int]] = {}
    for address, command_info in per_light.items():
        temp_args = argparse.Namespace(**vars(args))
        apply_command_overrides(temp_args, command_info)
        command_map[address] = build_base_command(temp_args)
    return command_map


def print_device_table(lights: Sequence[LightInfo]) -> None:
    if not lights:
        print("No matching Neewer lights found.")
        return

    print(f"Found {len(lights)} light(s):")
    print("ID  RSSI  ADDRESS              NAME               TYPE               PROTO  CCT_ONLY")
    print("--  ----  -------------------  -----------------  -----------------  -----  --------")
    for idx, light in enumerate(lights, start=1):
        light_type = light.realname if light.realname else light.name
        print(
            f"{idx:>2}  {light.rssi:>4}  {light.address:<19}  "
            f"{light.name[:17]:<17}  {light_type[:17]:<17}  "
            f"{light.infinity_mode:^5}  {str(light.cct_only):<8}"
        )


async def async_main(args: argparse.Namespace) -> int:
    config_data = load_user_config(args.config, args.debug)
    apply_defaults_from_config(args, config_data, sys.argv[1:])
    apply_preset_from_config(args, config_data, sys.argv[1:])

    if args.mode:
        args.mode = str(args.mode).upper()

    if args.on and args.off:
        raise ConfigError("--on and --off are mutually exclusive")
    if not args.list and not args.light:
        raise ConfigError("--light is required unless using --list or a preset sets lights")

    config = build_config(args)
    groups_cfg = config_data.get("groups", {})
    lights_cfg = config_data.get("lights", {})
    target_addresses = parse_addresses(args.light, groups_cfg)

    use_skip_discovery = bool(args.skip_discovery)
    if use_skip_discovery and not lights_cfg and target_addresses is None:
        # Keep --list usable even when skip-discovery is configured by default.
        use_skip_discovery = False
        log(
            "skip-discovery requested but no configured lights exist; falling back to BLE scan.",
            debug=True,
            enabled=config.debug,
        )

    if use_skip_discovery:
        lights, missing = get_static_lights_from_config(target_addresses, lights_cfg)
        log(
            f"Skipping BLE discovery. Using configured addresses only ({len(lights)} light(s)).",
            debug=True,
            enabled=config.debug,
        )
    else:
        lights, missing = await discover_with_retries(config, target_addresses)
        if lights_cfg:
            merge_light_metadata_from_config(lights, lights_cfg)

    if args.list:
        print_device_table(sorted(lights, key=lambda d: d.rssi, reverse=True))
        if missing:
            print("\nMissing target address(es):")
            for addr in missing:
                print(f"- {addr}")
            return 2
        return 0 if lights else 1

    if not lights:
        log("No target lights discovered.")
        return 1

    if missing:
        log("Some requested lights were not found:")
        for addr in missing:
            print(f"- {addr}")

    base_command = build_base_command(args)
    per_light_commands = build_per_light_command_map(args)
    if per_light_commands:
        log(
            f"Preset '{args.preset}' defines per-light commands for "
            f"{len(per_light_commands)} light(s)."
        )
    else:
        log(f"Command: {format_status_command(base_command)}")

    connection_results = await run_bounded(
        lights, config.parallel, lambda light: connect_light(light, config)
    )

    connected: List[LightInfo] = []
    connect_failures: List[Tuple[LightInfo, str]] = []

    for light, (ok, err) in zip(lights, connection_results):
        if ok:
            connected.append(light)
        else:
            connect_failures.append((light, err))

    if connect_failures:
        log("Failed to connect to some lights:")
        for light, err in connect_failures:
            print(f"- {light.address} [{light.name}] :: {err or 'unknown connect error'}")

    if not connected:
        return 1

    send_failures: Dict[str, str] = {}
    for current_pass in range(1, config.passes + 1):
        log(f"Sending pass {current_pass}/{config.passes}...")
        send_results = await run_bounded(
            connected,
            config.parallel,
            lambda light: send_command_once(
                light, per_light_commands.get(light.address, base_command), config
            ),
        )
        for light, (ok, err) in zip(connected, send_results):
            if not ok:
                send_failures[light.address] = f"{light.name}: {err or 'write failed'}"
            elif config.debug:
                current_command = per_light_commands.get(light.address, base_command)
                log(
                    f"WRITE OK {light.name} ({light.address}) :: "
                    f"{format_status_command(current_command)}",
                    debug=True,
                    enabled=True,
                )

    await run_bounded(connected, config.parallel, lambda light: disconnect_light(light, config))

    if send_failures:
        log("Command failed for some lights:")
        for address, reason in send_failures.items():
            print(f"- {address} :: {reason}")
        return 2

    names = ", ".join(f"{light.name}({light.address})" for light in connected)
    log(f"Command sent successfully to {len(connected)} light(s): {names}")
    return 0 if not missing else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Standalone Neewer BLE CLI utility (no GUI)."
    )
    parser.add_argument(
        "--config",
        default=DEFAULT_CONFIG_PATH,
        help="Config file path (.json, .yaml, .yml). Default: ~/.neewer",
    )
    parser.add_argument("--preset", default="", help="Preset name from config file")
    parser.add_argument("--list", action="store_true", help="Scan and list detected lights")
    parser.add_argument(
        "--light",
        default="",
        help="Comma-separated MAC addresses, ALL/*, or group:<name> from config",
    )
    parser.add_argument(
        "--skip-discovery",
        action="store_true",
        help="Skip BLE scan and connect directly to configured MAC addresses",
    )
    parser.add_argument("--on", action="store_true", help="Turn light(s) on")
    parser.add_argument("--off", action="store_true", help="Turn light(s) off")
    parser.add_argument(
        "--mode",
        default="CCT",
        choices=["CCT", "HSI", "ANM", "SCENE", "cct", "hsi", "anm", "scene"],
        help="Color mode when not using --on/--off",
    )

    parser.add_argument("--temp", default=56, type=int, help="CCT temperature (56 or 5600)")
    parser.add_argument("--hue", default=240, type=int, help="HSI hue (0-360)")
    parser.add_argument("--sat", default=100, type=int, help="HSI saturation (0-100)")
    parser.add_argument("--bri", default=100, type=int, help="Brightness (0-100)")
    parser.add_argument(
        "--gm",
        default=0,
        type=int,
        help="GM compensation (-50 to 50); internally shifted by +50",
    )
    parser.add_argument("--scene", default=1, type=int, help="Scene/effect index (1-29)")

    parser.add_argument("--scan-timeout", default=8.0, type=float)
    parser.add_argument("--scan-attempts", default=3, type=int)
    parser.add_argument("--connect-timeout", default=12.0, type=float)
    parser.add_argument("--connect-retries", default=3, type=int)
    parser.add_argument("--write-retries", default=2, type=int)
    parser.add_argument("--passes", default=2, type=int, help="How many send passes to run")
    parser.add_argument(
        "--parallel", default=2, type=int, help="Max concurrent connect/write operations"
    )
    parser.add_argument("--settle-ms", default=50, type=int, help="Delay between BLE writes")
    parser.add_argument(
        "--no-response",
        action="store_true",
        help="Use write-without-response for power commands (faster, less reliable)",
    )
    parser.add_argument("--debug", action="store_true", help="Verbose debug output")

    return parser


def validate_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if args.on and args.off:
        parser.error("--on and --off are mutually exclusive")
    if args.mode:
        args.mode = str(args.mode).upper()


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    validate_args(parser, args)
    try:
        return asyncio.run(async_main(args))
    except ConfigError as exc:
        print(f"[ERROR] {exc}")
        return 2
    except KeyboardInterrupt:
        log("Interrupted by user.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
