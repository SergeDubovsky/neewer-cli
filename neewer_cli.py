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
import shlex
import sys
import time
from importlib import metadata as importlib_metadata
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

_BLEAK_IMPORT_ERROR: Optional[Exception] = None
try:
    from bleak import BleakClient, BleakScanner
except ModuleNotFoundError as exc:
    # Keep module importable for unit tests and non-BLE code paths.
    BleakClient = None  # type: ignore[assignment,misc]
    BleakScanner = None  # type: ignore[assignment,misc]
    _BLEAK_IMPORT_ERROR = exc


SET_LIGHT_UUID = "69400002-B5A3-F393-E0A9-E50E24DCCA99"
NEEWER_SERVICE_UUID = "69400001-B5A3-F393-E0A9-E50E24DCCA99"
NOTIFY_LIGHT_UUID = "69400003-B5A3-F393-E0A9-E50E24DCCA99"
STATUS_QUERY_POWER = [120, 133, 0, 253]
STATUS_QUERY_CHANNEL = [120, 132, 0, 252]
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
    supports_status_query: Optional[bool] = None
    supports_extended_scene: Optional[bool] = None


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
    resolve_timeout: float = 2.0
    enable_status_query: bool = False
    enable_extended_scene: bool = False
    status_timeout: float = 1.0


class UnsupportedModeError(RuntimeError):
    pass


class ConfigError(RuntimeError):
    pass


def get_app_version() -> str:
    try:
        return importlib_metadata.version("neewer-cli")
    except importlib_metadata.PackageNotFoundError:
        # Running from source checkout without package installation.
        return "dev"


def ensure_bleak_available() -> None:
    if BleakClient is None or BleakScanner is None:
        raise ConfigError(
            "Missing dependency: bleak (install with: pip install bleak)"
        )


def log(msg: str, debug: bool = False, enabled: bool = True) -> None:
    if debug and not enabled:
        return
    timestamp = time.strftime("%H:%M:%S")
    print(f"[{timestamp}] {msg}")


def normalize_address(addr: str) -> str:
    return addr.strip().upper()


def validate_mac_address(mac_address: str, context: str = "MAC address") -> str:
    normalized = normalize_address(mac_address)
    parts = normalized.split(":")
    if len(parts) != 6:
        raise ConfigError(f"Invalid {context} '{mac_address}': expected 6 octets")
    for part in parts:
        if len(part) != 2:
            raise ConfigError(f"Invalid {context} '{mac_address}': octets must be 2 hex chars")
        try:
            int(part, 16)
        except ValueError as exc:
            raise ConfigError(f"Invalid {context} '{mac_address}': non-hex octet '{part}'") from exc
    return normalized


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
                raise ConfigError(
                    f"'lights.{key}' must be an object with metadata fields (for example: name)"
                )
            normalized[validate_mac_address(str(key), context="light address key")] = value
        return normalized
    if isinstance(raw_lights, list):
        normalized = {}
        for idx, row in enumerate(raw_lights):
            if not isinstance(row, dict):
                raise ConfigError(f"'lights[{idx}]' must be an object")
            address = row.get("address")
            if not address:
                raise ConfigError(f"'lights[{idx}]' is missing required field 'address'")
            row_copy = dict(row)
            row_copy.pop("address", None)
            normalized[
                validate_mac_address(str(address), context=f"lights[{idx}].address")
            ] = row_copy
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
            raise ConfigError(f"'groups.{key}' must be a list or comma-separated string")
        parsed_members: List[str] = []
        for idx, member in enumerate(members):
            text = str(member).strip()
            if not text:
                raise ConfigError(f"'groups.{key}[{idx}]' must not be empty")
            parsed_members.append(
                validate_mac_address(text, context=f"groups.{key}[{idx}]")
            )
        normalized[key] = parsed_members
    return normalized


def _load_config_file(path: str) -> Dict[str, Any]:
    ext = os.path.splitext(path)[1].lower()
    try:
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        raise ConfigError(f"Unable to read config file '{path}': {exc}") from exc

    if ext in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore
        except ModuleNotFoundError as exc:
            raise ConfigError(
                "YAML config requires PyYAML (pip install pyyaml) or use JSON config."
            ) from exc
        try:
            parsed = yaml.safe_load(text)
        except Exception as exc:
            raise ConfigError(f"Invalid YAML config '{path}': {exc}") from exc
    else:
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ConfigError(f"Invalid JSON config '{path}': {exc.msg} at line {exc.lineno}") from exc

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
) -> Optional[Set[str]]:
    if selector.strip() == "" or selector.upper() in {"ALL", "*"}:
        return None

    resolved: Set[str] = set()
    for token in [x.strip() for x in selector.split(",") if x.strip()]:
        if token.lower().startswith("group:"):
            group_name = token.split(":", 1)[1]
            if group_name not in groups:
                raise ConfigError(f"Unknown group '{group_name}' in light selector")
            resolved.update(groups[group_name])
        else:
            resolved.add(validate_mac_address(token, context="light selector address"))
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
        "bright_min": "scene_bright_min",
        "bright_max": "scene_bright_max",
        "temp_min": "scene_temp_min",
        "temp_max": "scene_temp_max",
        "hue_min": "scene_hue_min",
        "hue_max": "scene_hue_max",
        "speed": "scene_speed",
        "sparks": "scene_sparks",
        "special_options": "scene_special",
        "specialoptions": "scene_special",
    }

    for raw_key, value in preset.items():
        if raw_key == "per_light":
            continue
        raw_key_text = str(raw_key)
        key = alias_map.get(raw_key_text, raw_key_text).replace("-", "_")
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
                normalized_power = value.strip().upper()
                args.on = normalized_power in {"ON", "1", "TRUE"}
                args.off = normalized_power in {"OFF", "0", "FALSE"}
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
    target_addresses: Optional[Set[str]],
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
    unconfigured: List[str] = []

    for address in addresses:
        meta = lights_cfg.get(address)
        if meta is None:
            unconfigured.append(address)
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
        supports_status_query_raw = meta.get("supports_status_query")
        supports_extended_scene_raw = meta.get("supports_extended_scene")
        supports_status_query = (
            _to_bool(supports_status_query_raw, False)
            if supports_status_query_raw is not None
            else None
        )
        supports_extended_scene = (
            _to_bool(supports_extended_scene_raw, False)
            if supports_extended_scene_raw is not None
            else None
        )

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
                supports_status_query=supports_status_query,
                supports_extended_scene=supports_extended_scene,
            )
        )

    return lights, unconfigured


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
        if "supports_status_query" in meta:
            light.supports_status_query = _to_bool(meta["supports_status_query"], False)
        if "supports_extended_scene" in meta:
            light.supports_extended_scene = _to_bool(meta["supports_extended_scene"], False)


def get_corrected_name(light_name: str) -> str:
    if not light_name:
        return "Unknown"
    for needle, corrected in NEW_LIGHT_NAMES:
        if needle in light_name:
            return corrected
    return light_name


def _find_light_specs_entry(light_name: str) -> Optional[Tuple[str, int, int, bool, int]]:
    for entry in reversed(MASTER_LIGHT_SPECS):
        if entry[0] in light_name:
            return entry
    return None


def get_light_specs(light_name: str) -> Tuple[List[int], bool, int]:
    cct_bounds = [3200, 5600]
    cct_only = False
    infinity_mode = 0

    entry = _find_light_specs_entry(light_name)
    if entry is not None:
        cct_bounds = [entry[1], entry[2]]
        cct_only = entry[3]
        infinity_mode = entry[4]
    return cct_bounds, cct_only, infinity_mode


def is_neewer_device(name: Optional[str]) -> bool:
    if not name:
        return False
    upper_name = name.upper()
    return any(upper_name.startswith(prefix) for prefix in ACCEPTED_NAME_PREFIXES)


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
    if temp >= 1000:
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


def _split_hue(hue_value: int) -> Tuple[int, int]:
    hue = clamp(int(hue_value), 0, 360)
    return hue & 0xFF, (hue & 0xFF00) >> 8


def model_supports_status_query(light: LightInfo) -> bool:
    if light.supports_status_query is not None:
        return light.supports_status_query

    name_upper = (light.name or "").upper()
    if not name_upper:
        return False

    # Status query notify flow is known to work primarily on older panel/ring RGB/CCT models.
    unsupported_prefixes = (
        "FS",
        "CB",
        "MS",
        "AS",
        "APOLLO",
        "HB",
        "HS",
        "TL120",
        "PL",
    )
    if any(name_upper.startswith(prefix) for prefix in unsupported_prefixes):
        return False

    supported_prefixes = (
        "SL",
        "SNL",
        "RGB",
        "GL",
        "NL",
        "SRP",
        "WRP",
        "ZRP",
        "CL124",
        "ZK-RY",
        "TL60",
    )
    return any(name_upper.startswith(prefix) for prefix in supported_prefixes)


def model_supports_extended_scene(light: LightInfo) -> bool:
    if light.supports_extended_scene is not None:
        return light.supports_extended_scene
    return light.infinity_mode in (1, 2) and not light.cct_only


def calculate_extended_scene_bytestring(effect: int, args: argparse.Namespace) -> List[int]:
    brightness = clamp(int(args.bri), 0, 100)
    bright_min = clamp(int(args.scene_bright_min), 0, 100)
    bright_max = clamp(int(args.scene_bright_max), 0, 100)
    temp = clamp(parse_temp_value(int(args.temp)), 25, 100)
    temp_min = clamp(parse_temp_value(int(args.scene_temp_min)), 25, 100)
    temp_max = clamp(parse_temp_value(int(args.scene_temp_max)), 25, 100)
    gm = clamp(int(args.gm) + 50, 0, 100)
    hue_low, hue_high = _split_hue(int(args.hue))
    hue_min_low, hue_min_high = _split_hue(int(args.scene_hue_min))
    hue_max_low, hue_max_high = _split_hue(int(args.scene_hue_max))
    sat = clamp(int(args.sat), 0, 100)
    speed = clamp(int(args.scene_speed), 1, 10)
    sparks = clamp(int(args.scene_sparks), 0, 10)
    special = clamp(int(args.scene_special), 0, 10)

    payload = [effect]

    if effect == 1:
        payload.extend([brightness, temp, speed])
    elif effect in {2, 3, 6, 8}:
        payload.extend([brightness, temp, gm, speed])
    elif effect == 4:
        payload.extend([brightness, temp, gm, speed, sparks])
    elif effect == 5:
        payload.extend([bright_min, bright_max, temp, gm, speed])
    elif effect in {7, 9}:
        payload.extend([brightness, hue_low, hue_high, sat, speed])
    elif effect == 10:
        payload.extend([brightness, special, speed])
    elif effect == 11:
        payload.extend([bright_min, bright_max, temp, gm, speed, sparks])
    elif effect == 12:
        payload.extend([brightness, hue_min_low, hue_min_high, hue_max_low, hue_max_high, speed])
    elif effect == 13:
        payload.extend([brightness, temp_min, temp_max, speed])
    elif effect == 14:
        payload = [14, 0, bright_min, bright_max, 0, 0, temp, speed]
    elif effect == 15:
        payload = [14, 1, bright_min, bright_max, hue_low, hue_high, 0, speed]
    elif effect == 16:
        payload = [15, bright_min, bright_max, temp, gm, speed]
    elif effect == 17:
        payload = [16, brightness, special, speed, sparks]
    elif effect == 18:
        payload = [17, brightness, special, speed]
    elif effect == 21:
        payload.extend([brightness, 2, 5])
    elif effect == 22:
        payload.extend([brightness, 75, 50, 5])
    elif effect == 23:
        payload.extend([brightness, 0, 0, 55, 0, 10])
    elif effect == 24:
        payload.extend([brightness, 49, 0, 20, 1, 8])
    elif effect == 25:
        payload.extend([brightness, 1, 10])
    elif effect == 26:
        payload.extend([2, brightness, 32, 50, 10, 4])
    elif effect == 27:
        payload.extend([brightness, 75, 10])
    elif effect == 28:
        payload.extend([brightness, 75, 50, 10])
    elif effect == 29:
        payload.extend([2, brightness, 75, 50, 10])
    else:
        payload.extend([brightness])

    return [120, 136, len(payload), *payload]


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
        if bool(getattr(args, "enable_extended_scene", False)):
            return calculate_extended_scene_bytestring(effect, args)
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
            is_power_on = int(base_command[3]) == 1
            hw_mac = get_hw_mac_for_light(light)
            payload = tag_checksum(get_infinity_power_bytestring(is_power_on, hw_mac))
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
        is_extended_scene = len(base_command) > 5
        if is_extended_scene and not model_supports_extended_scene(light):
            raise UnsupportedModeError(
                f"{light.name} does not support extended scene arguments."
            )

        if light.infinity_mode == 1:
            hw_mac = get_hw_mac_for_light(light)
            payload = [120, 145, 6 + (len(base_command) - 2)]
            payload.extend(split_mac_address(hw_mac))
            payload.extend([139, convert_fx_index(1, int(base_command[3]))])
            payload.extend(base_command[4:])

            power_off = tag_checksum(get_infinity_power_bytestring(False, hw_mac))
            power_on_packet = tag_checksum(get_infinity_power_bytestring(True, hw_mac))
            return [
                (power_off, False, 0.05),
                (power_on_packet, False, 0.05),
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


def validate_base_command_for_light(light: LightInfo, base_command: Sequence[int]) -> None:
    mode = int(base_command[1])
    if mode != 135:
        return

    entry = _find_light_specs_entry(light.name)
    if entry is None:
        return

    min_temp = clamp(parse_temp_value(entry[1]), 25, 100)
    max_temp = clamp(parse_temp_value(entry[2]), 25, 100)
    if max_temp < min_temp:
        min_temp, max_temp = max_temp, min_temp

    temp = int(base_command[4])
    if min_temp <= temp <= max_temp:
        return

    if min_temp == max_temp:
        supported = f"{min_temp}00K"
    else:
        supported = f"{min_temp}00K-{max_temp}00K"

    raise UnsupportedModeError(
        f"{light.name} supports CCT {supported}, got {temp}00K."
    )


async def discover_devices(
    scan_timeout: float, target_addresses: Optional[Set[str]], debug: bool
) -> Dict[str, LightInfo]:
    ensure_bleak_available()
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
    config: AppConfig, target_addresses: Optional[Set[str]], collect_all: bool = False
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
            if collected and not collect_all:
                break

    if target_addresses is not None:
        missing = sorted(addr for addr in target_addresses if addr not in collected)
    return list(collected.values()), missing


async def resolve_static_ble_devices(lights: Sequence[LightInfo], config: AppConfig) -> None:
    if not lights or config.resolve_timeout <= 0:
        return

    target_addresses = {light.address for light in lights}
    log(
        "Resolving BLE handles for configured lights "
        f"(timeout={config.resolve_timeout:.1f}s)...",
        debug=True,
        enabled=config.debug,
    )
    found = await discover_devices(config.resolve_timeout, target_addresses, config.debug)

    resolved = 0
    for light in lights:
        match = found.get(light.address)
        if match is None or match.ble_device is None:
            continue
        light.ble_device = match.ble_device
        light.rssi = match.rssi
        light.realname = match.realname
        if light.name in {"Configured Light", "Unknown", ""}:
            light.name = match.name
        resolved += 1

    if config.debug:
        unresolved = len(lights) - resolved
        log(
            f"Resolved BLE handles for {resolved}/{len(lights)} configured light(s). "
            f"Unresolved: {unresolved} (fallback to direct address connect).",
            debug=True,
            enabled=True,
        )


async def connect_light(light: LightInfo, config: AppConfig) -> Tuple[bool, str]:
    ensure_bleak_available()
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
            client_kwargs: Dict[str, Any] = {"timeout": config.connect_timeout}
            if light.ble_device is not None:
                client_kwargs["services"] = [NEEWER_SERVICE_UUID]
            client = BleakClient(target, **client_kwargs)
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
        validate_base_command_for_light(light, base_command)
        payload_sequence = build_payload_sequence(
            light, base_command, power_with_response=config.power_with_response
        )
    except UnsupportedModeError as exc:
        return False, str(exc)
    except ValueError as exc:
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


def parse_status_payload(power_payload: Optional[Sequence[int]], channel_payload: Optional[Sequence[int]]) -> Dict[str, Any]:
    power = "UNKNOWN"
    channel: Any = "---"

    if power_payload and len(power_payload) > 3:
        if int(power_payload[3]) == 1:
            power = "ON"
        elif int(power_payload[3]) == 2:
            power = "STBY"

    if channel_payload and len(channel_payload) > 3:
        channel = int(channel_payload[3])

    return {
        "power": power,
        "channel": channel,
        "power_raw": list(power_payload) if power_payload else [],
        "channel_raw": list(channel_payload) if channel_payload else [],
    }


async def query_notify_payload(
    client: BleakClient,
    command: Sequence[int],
    expected_type: int,
    timeout: float,
    retries: int,
) -> Optional[List[int]]:
    seen: List[List[int]] = []

    def _notify_callback(_sender: Any, data: bytearray) -> None:
        try:
            seen.append(list(data))
        except Exception:
            pass

    await client.start_notify(NOTIFY_LIGHT_UUID, _notify_callback)
    try:
        loop = asyncio.get_running_loop()
        for attempt in range(1, retries + 1):
            base_idx = len(seen)
            await client.write_gatt_char(SET_LIGHT_UUID, bytearray(command), response=False)

            deadline = loop.time() + timeout
            while loop.time() < deadline:
                for payload in seen[base_idx:]:
                    if len(payload) > 1 and int(payload[1]) == expected_type:
                        return payload
                await asyncio.sleep(0.05)

            await asyncio.sleep(min(0.05 * attempt, 0.2))
    finally:
        try:
            await client.stop_notify(NOTIFY_LIGHT_UUID)
        except Exception:
            pass

    return None


async def query_light_status_once(
    light: LightInfo, config: AppConfig
) -> Tuple[bool, str, Dict[str, Any]]:
    if light.client is None or not light.client.is_connected:
        return False, "not connected", {}
    if not config.enable_status_query:
        return False, "status query feature is disabled", {}
    if not model_supports_status_query(light):
        return False, "status query not supported by this model", {}

    try:
        power_payload = await query_notify_payload(
            light.client,
            STATUS_QUERY_POWER,
            expected_type=2,
            timeout=config.status_timeout,
            retries=config.write_retries,
        )
        channel_payload = await query_notify_payload(
            light.client,
            STATUS_QUERY_CHANNEL,
            expected_type=1,
            timeout=config.status_timeout,
            retries=config.write_retries,
        )
    except Exception as exc:  # pragma: no cover - runtime BLE dependent
        return False, str(exc), {}

    if power_payload is None and channel_payload is None:
        return False, "status query timed out (no notify response)", {}

    return True, "", parse_status_payload(power_payload, channel_payload)


def is_light_connected(light: LightInfo) -> bool:
    return light.client is not None and light.client.is_connected


async def connect_targets(
    lights: Sequence[LightInfo], config: AppConfig
) -> Tuple[List[LightInfo], Dict[str, str]]:
    to_connect = [light for light in lights if not is_light_connected(light)]
    connect_failures: Dict[str, str] = {}

    if to_connect:
        connection_results = await run_bounded(
            to_connect, config.parallel, lambda light: connect_light(light, config)
        )
        for light, (ok, err) in zip(to_connect, connection_results):
            if not ok:
                connect_failures[light.address] = f"{light.name}: {err or 'unknown connect error'}"

    ready = [light for light in lights if is_light_connected(light)]
    return ready, connect_failures


async def send_command_adaptive(
    lights: Sequence[LightInfo],
    base_command: Sequence[int],
    per_light_commands: Dict[str, List[int]],
    config: AppConfig,
) -> Dict[str, str]:
    pending: Dict[str, LightInfo] = {light.address: light for light in lights}
    failures: Dict[str, str] = {}

    for attempt in range(1, config.passes + 1):
        if not pending:
            break

        current_targets = list(pending.values())
        ready, connect_failures = await connect_targets(current_targets, config)

        retry_next: Dict[str, LightInfo] = {}
        for address, reason in connect_failures.items():
            failures[address] = reason
            light = pending.get(address)
            if light is not None:
                retry_next[address] = light

        if ready:
            log(f"Sending attempt {attempt}/{config.passes} to {len(ready)} light(s)...")
            send_results = await run_bounded(
                ready,
                config.parallel,
                lambda light: send_command_once(
                    light, per_light_commands.get(light.address, base_command), config
                ),
            )
            for light, (ok, err) in zip(ready, send_results):
                if ok:
                    failures.pop(light.address, None)
                    if config.debug:
                        current_command = per_light_commands.get(light.address, base_command)
                        log(
                            f"WRITE OK {light.name} ({light.address}) :: "
                            f"{format_status_command(current_command)}",
                            debug=True,
                            enabled=True,
                        )
                else:
                    failures[light.address] = f"{light.name}: {err or 'write failed'}"
                    retry_next[light.address] = light

        pending = retry_next

    return failures


async def query_status_adaptive(
    lights: Sequence[LightInfo],
    config: AppConfig,
) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, str]]:
    pending: Dict[str, LightInfo] = {light.address: light for light in lights}
    failures: Dict[str, str] = {}
    statuses: Dict[str, Dict[str, Any]] = {}

    for attempt in range(1, config.passes + 1):
        if not pending:
            break

        current_targets = list(pending.values())
        ready, connect_failures = await connect_targets(current_targets, config)

        retry_next: Dict[str, LightInfo] = {}
        for address, reason in connect_failures.items():
            failures[address] = reason
            light = pending.get(address)
            if light is not None:
                retry_next[address] = light

        if ready:
            log(
                f"Querying status attempt {attempt}/{config.passes} "
                f"for {len(ready)} light(s)..."
            )
            query_results = await run_bounded(
                ready,
                config.parallel,
                lambda light: query_light_status_once(light, config),
            )

            for light, (ok, err, status_info) in zip(ready, query_results):
                if ok:
                    failures.pop(light.address, None)
                    statuses[light.address] = status_info
                    if config.debug:
                        log(
                            f"STATUS OK {light.name} ({light.address}) :: "
                            f"power={status_info.get('power')} channel={status_info.get('channel')}",
                            debug=True,
                            enabled=True,
                        )
                else:
                    failures[light.address] = f"{light.name}: {err or 'status query failed'}"
                    if "not supported" not in (err or "").lower():
                        retry_next[light.address] = light

        pending = retry_next

    return statuses, failures


def print_status_table(lights: Sequence[LightInfo], status_map: Dict[str, Dict[str, Any]]) -> None:
    if not status_map:
        print("No status responses received.")
        return

    print("ADDRESS              NAME               POWER  CHANNEL")
    print("-------------------  -----------------  -----  -------")
    by_address = {light.address: light for light in lights}
    for address in sorted(status_map.keys()):
        status = status_map[address]
        light = by_address.get(address)
        name = (light.name if light else address)[:17]
        power = str(status.get("power", "UNKNOWN"))
        channel = str(status.get("channel", "---"))
        print(f"{address:<19}  {name:<17}  {power:<5}  {channel:<7}")


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


def parse_addresses(light_arg: str, groups: Dict[str, List[str]]) -> Optional[Set[str]]:
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
        resolve_timeout=max(0.0, float(args.resolve_timeout)),
        enable_status_query=bool(args.enable_status_query),
        enable_extended_scene=bool(args.enable_extended_scene),
        status_timeout=max(0.1, float(args.status_timeout)),
    )


def build_base_command(args: argparse.Namespace) -> List[int]:
    try:
        if args.on:
            return set_power_bytestring(True)
        if args.off:
            return set_power_bytestring(False)
        return calculate_bytestring(args.mode, args)
    except ValueError as exc:
        raise ConfigError(f"Invalid command settings: {exc}") from exc


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
        "bright_min": "scene_bright_min",
        "bright_max": "scene_bright_max",
        "temp_min": "scene_temp_min",
        "temp_max": "scene_temp_max",
        "hue_min": "scene_hue_min",
        "hue_max": "scene_hue_max",
        "speed": "scene_speed",
        "sparks": "scene_sparks",
        "special_options": "scene_special",
        "specialoptions": "scene_special",
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
        try:
            command_map[address] = build_base_command(temp_args)
        except ConfigError as exc:
            raise ConfigError(f"Invalid per-light preset for {address}: {exc}") from exc
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


def build_serve_command(
    line: str,
    base_args: argparse.Namespace,
    config_data: Dict[str, Any],
    groups_cfg: Dict[str, List[str]],
) -> Tuple[Optional[Set[str]], List[int], Dict[str, List[int]], str]:
    tokens = shlex.split(line)
    if not tokens:
        raise ConfigError("Empty command.")

    cmd = tokens[0].lower()

    if cmd == "preset":
        if len(tokens) != 2:
            raise ConfigError("Usage: preset <name>")
        temp_args = argparse.Namespace(**vars(base_args))
        temp_args.on = False
        temp_args.off = False
        temp_args.preset = tokens[1]
        temp_args._per_light_preset = {}
        apply_preset_from_config(temp_args, config_data, [])
        if temp_args.mode:
            temp_args.mode = str(temp_args.mode).upper()
        base_command = build_base_command(temp_args)
        per_light_commands = build_per_light_command_map(temp_args)
        target_addresses = parse_addresses(temp_args.light, groups_cfg)
        description = f"Preset '{tokens[1]}'"
        return target_addresses, base_command, per_light_commands, description

    temp_args = argparse.Namespace(**vars(base_args))
    temp_args._per_light_preset = {}
    temp_args.preset = ""

    if cmd == "on":
        if len(tokens) != 1:
            raise ConfigError("Usage: on")
        temp_args.on = True
        temp_args.off = False
        base_command = build_base_command(temp_args)
        return None, base_command, {}, "Power ON"

    if cmd == "off":
        if len(tokens) != 1:
            raise ConfigError("Usage: off")
        temp_args.on = False
        temp_args.off = True
        base_command = build_base_command(temp_args)
        return None, base_command, {}, "Power OFF"

    if cmd == "cct":
        if len(tokens) not in {3, 4}:
            raise ConfigError("Usage: cct <temp> <bri> [gm]")
        temp_args.on = False
        temp_args.off = False
        temp_args.mode = "CCT"
        temp_args.temp = _to_int(tokens[1], temp_args.temp)
        temp_args.bri = _to_int(tokens[2], temp_args.bri)
        temp_args.gm = _to_int(tokens[3], 0) if len(tokens) == 4 else 0
        base_command = build_base_command(temp_args)
        return None, base_command, {}, format_status_command(base_command)

    if cmd == "hsi":
        if len(tokens) != 4:
            raise ConfigError("Usage: hsi <hue> <sat> <bri>")
        temp_args.on = False
        temp_args.off = False
        temp_args.mode = "HSI"
        temp_args.hue = _to_int(tokens[1], temp_args.hue)
        temp_args.sat = _to_int(tokens[2], temp_args.sat)
        temp_args.bri = _to_int(tokens[3], temp_args.bri)
        base_command = build_base_command(temp_args)
        return None, base_command, {}, format_status_command(base_command)

    if cmd in {"scene", "anm"}:
        if len(tokens) != 3:
            raise ConfigError("Usage: scene <effect> <bri>")
        temp_args.on = False
        temp_args.off = False
        temp_args.mode = "SCENE"
        temp_args.scene = _to_int(tokens[1], temp_args.scene)
        temp_args.bri = _to_int(tokens[2], temp_args.bri)
        base_command = build_base_command(temp_args)
        return None, base_command, {}, format_status_command(base_command)

    raise ConfigError(
        "Unknown serve command. Supported: on, off, cct, hsi, scene, preset, help, exit."
    )


def select_session_lights(
    session_lights: Sequence[LightInfo], target_addresses: Optional[Set[str]]
) -> Tuple[List[LightInfo], List[str]]:
    if target_addresses is None:
        return list(session_lights), []

    by_address = {light.address: light for light in session_lights}
    selected: List[LightInfo] = []
    missing: List[str] = []
    for address in sorted(target_addresses):
        light = by_address.get(address)
        if light is None:
            missing.append(address)
        else:
            selected.append(light)
    return selected, missing


async def run_serve_mode(
    session_lights: Sequence[LightInfo],
    base_args: argparse.Namespace,
    config: AppConfig,
    config_data: Dict[str, Any],
    groups_cfg: Dict[str, List[str]],
) -> int:
    ready, connect_failures = await connect_targets(session_lights, config)
    exit_code = 0
    if connect_failures:
        exit_code = 2
        log("Failed to connect to some lights:")
        for address, reason in connect_failures.items():
            print(f"- {address} :: {reason}")
    if not ready:
        return 2

    names = ", ".join(f"{light.name}({light.address})" for light in ready)
    log(f"Serve mode ready. Connected lights: {names}")
    print(
        "Commands: on | off | cct <temp> <bri> [gm] | hsi <hue> <sat> <bri> | "
        "scene <fx> <bri> | preset <name> | help | exit"
    )

    try:
        while True:
            try:
                line = await asyncio.to_thread(input, "neewer> ")
            except EOFError:
                break

            command = line.strip()
            if not command:
                continue

            lower = command.lower()
            if lower in {"exit", "quit"}:
                break
            if lower in {"help", "?"}:
                print(
                    "Commands: on | off | cct <temp> <bri> [gm] | hsi <hue> <sat> <bri> | "
                    "scene <fx> <bri> | preset <name> | help | exit"
                )
                continue

            try:
                target_addresses, base_command, per_light_commands, description = (
                    build_serve_command(command, base_args, config_data, groups_cfg)
                )
            except ConfigError as exc:
                print(f"[ERROR] {exc}")
                continue

            target_lights, target_missing = select_session_lights(
                session_lights, target_addresses
            )
            if target_missing:
                log("Command references lights not in this serve session:")
                for address in target_missing:
                    print(f"- {address}")
            if not target_lights:
                continue

            if per_light_commands:
                log(
                    f"{description} defines per-light commands for "
                    f"{len(per_light_commands)} light(s)."
                )
            else:
                log(f"Command: {description}")

            send_failures = await send_command_adaptive(
                target_lights, base_command, per_light_commands, config
            )
            if send_failures:
                exit_code = 2
                log("Command failed for some lights:")
                for address, reason in send_failures.items():
                    print(f"- {address} :: {reason}")
            else:
                names = ", ".join(
                    f"{light.name}({light.address})" for light in target_lights
                )
                log(
                    f"Command sent successfully to {len(target_lights)} light(s): {names}"
                )
    finally:
        connected = [light for light in session_lights if is_light_connected(light)]
        if connected:
            await run_bounded(
                connected, config.parallel, lambda light: disconnect_light(light, config)
            )

    return exit_code


async def async_main(args: argparse.Namespace, argv: Sequence[str]) -> int:
    config_data = load_user_config(args.config, args.debug)
    apply_defaults_from_config(args, config_data, argv)
    apply_preset_from_config(args, config_data, argv)

    if args.mode:
        args.mode = str(args.mode).upper()

    validate_runtime_args(args)
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

    missing: List[str] = []
    unconfigured: List[str] = []
    if use_skip_discovery:
        lights, unconfigured = get_static_lights_from_config(target_addresses, lights_cfg)
        log(
            f"Skipping BLE discovery. Using configured addresses only ({len(lights)} light(s)).",
            debug=True,
            enabled=config.debug,
        )
        await resolve_static_ble_devices(lights, config)
    else:
        lights, missing = await discover_with_retries(
            config, target_addresses, collect_all=bool(args.list)
        )
        if lights_cfg:
            merge_light_metadata_from_config(lights, lights_cfg)

    if args.list:
        print_device_table(sorted(lights, key=lambda d: d.rssi, reverse=True))
        if missing:
            print("\nMissing target address(es):")
            for addr in missing:
                print(f"- {addr}")
            return 2
        if unconfigured:
            print("\nAddress(es) missing config metadata (using generic defaults):")
            for addr in unconfigured:
                print(f"- {addr}")
        return 0 if lights else 1

    if not lights:
        log("No target lights discovered.")
        return 1

    if unconfigured:
        log("Some target addresses are missing config metadata; using generic defaults:")
        for addr in unconfigured:
            print(f"- {addr}")

    if missing:
        log("Some requested lights were not found:")
        for addr in missing:
            print(f"- {addr}")

    if args.status:
        status_map, status_failures = await query_status_adaptive(lights, config)
        connected = [light for light in lights if is_light_connected(light)]
        if connected:
            await run_bounded(
                connected, config.parallel, lambda light: disconnect_light(light, config)
            )

        print_status_table(lights, status_map)
        if status_failures:
            log("Status query failed for some lights:")
            for address, reason in status_failures.items():
                print(f"- {address} :: {reason}")
            return 2
        return 0 if not missing else 2

    if args.serve:
        return await run_serve_mode(lights, args, config, config_data, groups_cfg)

    base_command = build_base_command(args)
    per_light_commands = build_per_light_command_map(args)
    if per_light_commands:
        log(
            f"Preset '{args.preset}' defines per-light commands for "
            f"{len(per_light_commands)} light(s)."
        )
    else:
        log(f"Command: {format_status_command(base_command)}")

    send_failures = await send_command_adaptive(lights, base_command, per_light_commands, config)
    connected = [light for light in lights if is_light_connected(light)]
    if connected:
        await run_bounded(
            connected, config.parallel, lambda light: disconnect_light(light, config)
        )

    if send_failures:
        log("Command failed for some lights:")
        for address, reason in send_failures.items():
            print(f"- {address} :: {reason}")

    status_code = 0
    if missing or send_failures:
        status_code = 2

    names = ", ".join(f"{light.name}({light.address})" for light in connected)
    if status_code == 0:
        log(f"Command sent successfully to {len(connected)} light(s): {names}")
    else:
        log(
            f"Command sent to {len(connected)} connected light(s) with warnings/errors: {names}"
        )
    return status_code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Standalone Neewer BLE CLI utility (no GUI)."
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {get_app_version()}",
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
    parser.add_argument(
        "--status",
        action="store_true",
        help="Query power/channel status instead of sending a control command",
    )
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Keep BLE connections open and accept live commands from stdin",
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
    parser.add_argument(
        "--scene-bright-min",
        default=0,
        type=int,
        help="Extended scene: minimum brightness (0-100)",
    )
    parser.add_argument(
        "--scene-bright-max",
        default=100,
        type=int,
        help="Extended scene: maximum brightness (0-100)",
    )
    parser.add_argument(
        "--scene-temp-min",
        default=3200,
        type=int,
        help="Extended scene: minimum CCT (for example 3200 or 32)",
    )
    parser.add_argument(
        "--scene-temp-max",
        default=5600,
        type=int,
        help="Extended scene: maximum CCT (for example 5600 or 56)",
    )
    parser.add_argument(
        "--scene-hue-min",
        default=0,
        type=int,
        help="Extended scene: minimum hue (0-360)",
    )
    parser.add_argument(
        "--scene-hue-max",
        default=360,
        type=int,
        help="Extended scene: maximum hue (0-360)",
    )
    parser.add_argument(
        "--scene-speed",
        default=5,
        type=int,
        help="Extended scene: speed parameter (1-10)",
    )
    parser.add_argument(
        "--scene-sparks",
        default=0,
        type=int,
        help="Extended scene: sparks parameter (0-10)",
    )
    parser.add_argument(
        "--scene-special",
        default=1,
        type=int,
        help="Extended scene: special option parameter (0-10)",
    )

    parser.add_argument("--scan-timeout", default=8.0, type=float)
    parser.add_argument("--scan-attempts", default=3, type=int)
    parser.add_argument(
        "--resolve-timeout",
        default=2.0,
        type=float,
        help="Short scan timeout used to resolve BLE handles for --skip-discovery",
    )
    parser.add_argument(
        "--status-timeout",
        default=1.0,
        type=float,
        help="Timeout (seconds) waiting for status-query notify responses",
    )
    parser.add_argument("--connect-timeout", default=12.0, type=float)
    parser.add_argument("--connect-retries", default=3, type=int)
    parser.add_argument("--write-retries", default=2, type=int)
    parser.add_argument(
        "--passes",
        default=2,
        type=int,
        help="Max adaptive send attempts (retries only failed lights)",
    )
    parser.add_argument(
        "--parallel", default=2, type=int, help="Max concurrent connect/write operations"
    )
    parser.add_argument("--settle-ms", default=50, type=int, help="Delay between BLE writes")
    parser.add_argument(
        "--no-response",
        action="store_true",
        help="Use write-without-response for power commands (faster, less reliable)",
    )
    parser.add_argument(
        "--enable-status-query",
        action="store_true",
        help="Enable experimental status query protocol commands",
    )
    parser.add_argument(
        "--enable-extended-scene",
        action="store_true",
        help="Enable experimental extended scene argument payloads on supported models",
    )
    parser.add_argument("--debug", action="store_true", help="Verbose debug output")

    return parser


def validate_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if args.on and args.off:
        parser.error("--on and --off are mutually exclusive")
    if args.mode:
        args.mode = str(args.mode).upper()


def validate_runtime_args(args: argparse.Namespace) -> None:
    if args.on and args.off:
        raise ConfigError("--on and --off are mutually exclusive")
    if args.status and args.serve:
        raise ConfigError("--status and --serve are mutually exclusive")
    if args.status and (args.on or args.off):
        raise ConfigError("--status cannot be combined with --on/--off")
    if args.status and not args.enable_status_query:
        raise ConfigError("--status requires --enable-status-query")


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    validate_args(parser, args)
    try:
        return asyncio.run(async_main(args, sys.argv[1:]))
    except ConfigError as exc:
        print(f"[ERROR] {exc}")
        return 2
    except KeyboardInterrupt:
        log("Interrupted by user.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
