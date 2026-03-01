"""Interactive configuration wizard for neewer-cli."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

import neewer_cli as core


class WizardBack(RuntimeError):
    """Raised when user requests to navigate one step back in wizard."""


def _is_back_input(raw: str) -> bool:
    text = raw.strip().lower()
    return raw == "\x1b" or text in {"esc", "escape", "back", "b", ".."}


def _read_user_input(prompt: str) -> Tuple[str, bool]:
    if os.name == "nt" and sys.stdin.isatty() and "PYTEST_CURRENT_TEST" not in os.environ:
        try:
            import msvcrt
        except Exception:
            pass
        else:
            buffer: List[str] = []
            print(prompt, end="", flush=True)
            while True:
                char = msvcrt.getwch()
                if char in {"\r", "\n"}:
                    print()
                    return "".join(buffer), False
                if char == "\x03":
                    raise KeyboardInterrupt
                if char == "\x1b":
                    print()
                    return "", True
                if char in {"\x00", "\xe0"}:
                    _ = msvcrt.getwch()
                    continue
                if char in {"\x08", "\x7f"}:
                    if buffer:
                        buffer.pop()
                        print("\b \b", end="", flush=True)
                    continue
                buffer.append(char)
                print(char, end="", flush=True)
    return input(prompt), False


def _ensure_mapping(value: Any, key_name: str) -> Dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise core.ConfigError(f"'{key_name}' must be an object")
    return value


def ensure_config_shape(config_data: Dict[str, Any]) -> Dict[str, Any]:
    shaped = dict(config_data)
    shaped["lights"] = core._normalize_lights_block(shaped.get("lights"))
    shaped["groups"] = core._normalize_groups_block(shaped.get("groups"))
    shaped["presets"] = _ensure_mapping(shaped.get("presets"), "presets")
    shaped["defaults"] = _ensure_mapping(shaped.get("defaults"), "defaults")
    return shaped


def _now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _default_output_format(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext in {".yml", ".yaml"}:
        return "yaml"
    return "json"


def write_config_file(path: str, config_data: Dict[str, Any]) -> Optional[str]:
    expanded = os.path.abspath(os.path.expanduser(path))
    parent_dir = os.path.dirname(expanded)
    os.makedirs(parent_dir, exist_ok=True)

    backup_path: Optional[str] = None
    if os.path.exists(expanded):
        backup_path = f"{expanded}.{_now_stamp()}.bak"
        with open(expanded, "rb") as src, open(backup_path, "wb") as dst:
            dst.write(src.read())

    fmt = _default_output_format(expanded)
    if fmt == "yaml":
        try:
            import yaml  # type: ignore
        except ModuleNotFoundError as exc:
            raise core.ConfigError(
                "YAML config requires PyYAML (pip install pyyaml) or use JSON config."
            ) from exc
        body = yaml.safe_dump(config_data, sort_keys=False, allow_unicode=False)
    else:
        body = json.dumps(config_data, indent=2, ensure_ascii=True)

    temp_fd, temp_path = tempfile.mkstemp(prefix=".neewer-tmp-", dir=parent_dir)
    try:
        with os.fdopen(temp_fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(body)
            fh.write("\n")
        os.replace(temp_path, expanded)
    except Exception:
        try:
            os.remove(temp_path)
        except OSError:
            pass
        raise

    return backup_path


def prompt_text(
    message: str,
    default: Optional[str] = None,
    allow_empty: bool = False,
    allow_back: bool = True,
) -> str:
    while True:
        suffix = f" [{default}]" if default not in {None, ""} else ""
        hint = " (ESC to go back)" if allow_back else ""
        raw, esc_pressed = _read_user_input(f"{message}{suffix}{hint}: ")
        if allow_back and (esc_pressed or _is_back_input(raw)):
            raise WizardBack("Back requested")
        if not allow_back and (esc_pressed or _is_back_input(raw)):
            print("Back is not available here.")
            continue
        text = raw.strip()
        if text:
            return text
        if default is not None:
            return str(default)
        if allow_empty:
            return ""
        print("Value is required.")


def prompt_yes_no(message: str, default: bool = True, allow_back: bool = True) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"
    while True:
        hint = " (ESC to go back)" if allow_back else ""
        raw = input(f"{message} {suffix}{hint}: ")
        if allow_back and _is_back_input(raw):
            raise WizardBack("Back requested")
        text = raw.strip().lower()
        if not text:
            return default
        if text in {"y", "yes"}:
            return True
        if text in {"n", "no"}:
            return False
        print("Enter 'y' or 'n'.")


def prompt_int(
    message: str,
    default: int,
    minimum: Optional[int] = None,
    maximum: Optional[int] = None,
    allow_back: bool = True,
) -> int:
    while True:
        raw = prompt_text(message, str(default), allow_back=allow_back)
        if not raw:
            return default
        try:
            value = int(raw)
        except ValueError:
            print("Enter a valid integer.")
            continue
        if minimum is not None and value < minimum:
            print(f"Value must be >= {minimum}.")
            continue
        if maximum is not None and value > maximum:
            print(f"Value must be <= {maximum}.")
            continue
        return value


def _normalize_temp_to_kelvin(raw_temp: Any, fallback_kelvin: int = 5600) -> int:
    temp = core._to_int(raw_temp, fallback_kelvin)
    if 25 <= temp <= 100:
        return temp * 100
    return temp


def prompt_temp_kelvin(
    message: str,
    default_kelvin: int,
    minimum: int = 2500,
    maximum: int = 10000,
    allow_back: bool = True,
) -> int:
    normalized_default = _normalize_temp_to_kelvin(default_kelvin, 5600)
    while True:
        raw = prompt_text(message, str(normalized_default), allow_back=allow_back)
        try:
            value = int(raw)
        except ValueError:
            print("Enter a valid integer (example: 5600 or 56).")
            continue

        if 25 <= value <= 100:
            value *= 100

        if value < minimum:
            print(f"Value must be >= {minimum} (or shorthand {minimum // 100}).")
            continue
        if value > maximum:
            print(f"Value must be <= {maximum} (or shorthand {maximum // 100}).")
            continue
        return value


def prompt_choice(
    message: str,
    options: Sequence[str],
    default_index: int = 0,
    allow_back: bool = True,
) -> int:
    if not options:
        raise core.ConfigError("No options available")
    print(f"\n{message}")
    for idx, option in enumerate(options, start=1):
        print(f"{idx}. {option}")
    default_num = default_index + 1
    while True:
        raw = prompt_text("Choose option number", str(default_num), allow_back=allow_back)
        try:
            picked = int(raw)
        except ValueError:
            print("Enter a valid option number.")
            continue
        if 1 <= picked <= len(options):
            return picked - 1
        print("Option out of range.")


def parse_selection(raw: str, valid_ids: Set[int]) -> List[int]:
    text = raw.strip().lower()
    if text == "all":
        return sorted(valid_ids)
    if text in {"none", ""}:
        return []
    selected: Set[int] = set()
    for part in [p.strip() for p in raw.split(",") if p.strip()]:
        if "-" in part:
            bounds = [x.strip() for x in part.split("-", 1)]
            if len(bounds) != 2 or not bounds[0].isdigit() or not bounds[1].isdigit():
                raise ValueError(f"Invalid range '{part}'")
            start = int(bounds[0])
            end = int(bounds[1])
            if start > end:
                start, end = end, start
            for number in range(start, end + 1):
                if number in valid_ids:
                    selected.add(number)
            continue
        if not part.isdigit():
            raise ValueError(f"Invalid number '{part}'")
        number = int(part)
        if number not in valid_ids:
            raise ValueError(f"Unknown id '{number}'")
        selected.add(number)
    return sorted(selected)


def extract_preset_addresses(
    preset: Dict[str, Any],
    groups: Dict[str, List[str]],
) -> Tuple[Set[str], bool]:
    members: Set[str] = set()
    unresolved = False
    lights_value = preset.get("lights")

    if lights_value is None:
        pass
    elif isinstance(lights_value, list):
        tokens = [str(x).strip() for x in lights_value if str(x).strip()]
        for token in tokens:
            if token.lower().startswith("group:"):
                group_name = token.split(":", 1)[1]
                if group_name in groups:
                    members.update(groups[group_name])
                else:
                    unresolved = True
            elif token.upper() in {"ALL", "*"}:
                unresolved = True
            else:
                members.add(core.validate_mac_address(token, context="preset lights"))
    else:
        raw = str(lights_value).strip()
        if raw:
            for token in [x.strip() for x in raw.split(",") if x.strip()]:
                if token.lower().startswith("group:"):
                    group_name = token.split(":", 1)[1]
                    if group_name in groups:
                        members.update(groups[group_name])
                    else:
                        unresolved = True
                elif token.upper() in {"ALL", "*"}:
                    unresolved = True
                else:
                    members.add(core.validate_mac_address(token, context="preset lights"))

    per_light = preset.get("per_light")
    if isinstance(per_light, dict):
        members.update(core.normalize_address(addr) for addr in per_light.keys())

    return members, unresolved


def _extract_single_group_selector(lights_value: Any) -> Optional[str]:
    if isinstance(lights_value, str):
        raw = lights_value.strip()
        if raw.lower().startswith("group:") and "," not in raw and raw.count(":") == 1:
            return raw.split(":", 1)[1]
    return None


def _upsert_group_members(group_members: Iterable[str], address: str, add: bool) -> List[str]:
    members = {core.normalize_address(x) for x in group_members}
    normalized = core.validate_mac_address(address, context="preset member address")
    if add:
        members.add(normalized)
    else:
        members.discard(normalized)
    return sorted(members)


def _to_explicit_lights_value(addresses: Set[str]) -> str:
    return ",".join(sorted(addresses))


def update_preset_membership(
    config_data: Dict[str, Any],
    preset_name: str,
    address: str,
    add: bool,
) -> str:
    presets = config_data["presets"]
    if preset_name not in presets:
        raise core.ConfigError(f"Preset '{preset_name}' not found")
    preset = presets[preset_name]
    if not isinstance(preset, dict):
        raise core.ConfigError(f"Preset '{preset_name}' must be an object")

    normalized_address = core.validate_mac_address(address, context="light address")
    groups = config_data["groups"]

    group_name = _extract_single_group_selector(preset.get("lights"))
    if group_name is not None:
        if group_name not in groups:
            raise core.ConfigError(
                f"Preset '{preset_name}' references missing group '{group_name}'"
            )
        groups[group_name] = _upsert_group_members(groups[group_name], normalized_address, add)
        changed = "added to" if add else "removed from"
        return f"{normalized_address} {changed} group:{group_name}"

    members, unresolved = extract_preset_addresses(preset, groups)
    if unresolved:
        raise core.ConfigError(
            f"Preset '{preset_name}' uses complex selectors (groups/ALL). Edit it manually or convert to a single group selector."
        )

    if add:
        members.add(normalized_address)
    else:
        members.discard(normalized_address)
    preset["lights"] = _to_explicit_lights_value(members)

    per_light = preset.get("per_light")
    if isinstance(per_light, dict):
        if add and normalized_address not in per_light:
            per_light[normalized_address] = {}
        if not add:
            per_light.pop(normalized_address, None)

    changed = "added to" if add else "removed from"
    return f"{normalized_address} {changed} preset:{preset_name}"


def create_or_replace_preset(
    config_data: Dict[str, Any],
    preset_name: str,
    preset_body: Dict[str, Any],
    overwrite: bool,
) -> bool:
    presets = config_data["presets"]
    exists = preset_name in presets
    if exists and not overwrite:
        return False
    presets[preset_name] = preset_body
    return True


def choose_light_addresses(
    discovered: Sequence[core.LightInfo],
    configured_lights: Dict[str, Dict[str, Any]],
) -> List[str]:
    print("\nDiscovered lights:")
    print("ID  RSSI  ADDRESS              NAME               STATUS")
    print("--  ----  -------------------  -----------------  ---------")
    indexed: Dict[int, str] = {}
    for idx, light in enumerate(discovered, start=1):
        status = "configured" if light.address in configured_lights else "new"
        print(
            f"{idx:>2}  {light.rssi:>4}  {light.address:<19}  "
            f"{light.name[:17]:<17}  {status}"
        )
        indexed[idx] = light.address

    default_select = "all"
    if any(addr not in configured_lights for addr in indexed.values()):
        new_ids = [idx for idx, addr in indexed.items() if addr not in configured_lights]
        default_select = ",".join(str(x) for x in new_ids) if new_ids else "all"

    while True:
        raw = prompt_text(
            "Select IDs to configure (example: 1,3-5, all, none)",
            default_select,
            allow_empty=True,
        )
        try:
            picked_ids = parse_selection(raw, set(indexed.keys()))
        except ValueError as exc:
            print(f"Invalid selection: {exc}")
            continue
        return [indexed[idx] for idx in picked_ids]


def choose_or_create_group(
    config_data: Dict[str, Any],
    addresses: Sequence[str],
) -> str:
    groups = config_data["groups"]
    if not addresses:
        raise core.ConfigError("No addresses selected")
    if not prompt_yes_no("Create/update a group for these lights?", True):
        return ",".join(sorted(set(addresses)))

    known_groups = sorted(groups.keys())
    group_name_default = "studio" if "studio" not in groups else (known_groups[0] if known_groups else "studio")
    group_name = prompt_text("Group name", group_name_default)
    current = groups.get(group_name, [])

    merge_mode = True
    if current:
        merge_mode = prompt_yes_no(
            f"Group '{group_name}' already has {len(current)} light(s). Merge selected lights?",
            True,
        )
    if merge_mode:
        members = set(current)
        members.update(addresses)
        groups[group_name] = sorted(core.validate_mac_address(x, context="group member") for x in members)
    else:
        groups[group_name] = sorted(core.validate_mac_address(x, context="group member") for x in addresses)
    return f"group:{group_name}"


def _collect_cct_for_address(address: str, default_temp: int, default_bri: int) -> Dict[str, Any]:
    temp = prompt_temp_kelvin(f"{address} temperature (Kelvin, e.g. 5600)", default_temp)
    bri = prompt_int(f"{address} brightness (0-100)", default_bri, 0, 100)
    gm = prompt_int(f"{address} GM compensation (-50 to 50)", 0, -50, 50)
    return {"mode": "CCT", "temp": temp, "bri": bri, "gm": gm}


def configure_cct_setup_preset(
    config_data: Dict[str, Any],
    preset_name: str,
    selector: str,
    addresses: Sequence[str],
) -> bool:
    same_for_all = prompt_yes_no("Use the same CCT settings for all lights?", True)
    if same_for_all:
        temp = prompt_temp_kelvin("Temperature (Kelvin, e.g. 5600)", 5600)
        bri = prompt_int("Brightness (0-100)", 30, 0, 100)
        gm = prompt_int("GM compensation (-50 to 50)", 0, -50, 50)
        body: Dict[str, Any] = {
            "lights": selector,
            "mode": "CCT",
            "temp": temp,
            "bri": bri,
            "gm": gm,
            "power_on_first": True,
        }
    else:
        per_light: Dict[str, Dict[str, Any]] = {}
        index = 0
        while index < len(addresses):
            address = addresses[index]
            try:
                per_light[address] = _collect_cct_for_address(address, 5600, 30)
            except WizardBack:
                if index == 0:
                    raise
                prev_index = index - 1
                prev_address = addresses[prev_index]
                per_light.pop(prev_address, None)
                index = prev_index
                print(f"Going back to previous light setup: {prev_address}")
                continue
            index += 1
        body = {
            "lights": selector,
            "mode": "CCT",
            "power_on_first": True,
            "per_light": per_light,
        }

    exists = preset_name in config_data["presets"]
    overwrite = True
    if exists:
        overwrite = prompt_yes_no(f"Preset '{preset_name}' exists. Overwrite?", False)
    return create_or_replace_preset(config_data, preset_name, body, overwrite)


def configure_on_off_presets(config_data: Dict[str, Any], selector: str) -> int:
    if not prompt_yes_no("Create/update ON/OFF presets for this light set?", True):
        return 0

    on_name = prompt_text("ON preset name", "all_on")
    off_name = prompt_text("OFF preset name", "all_off")

    changed = 0
    for preset_name, power in ((on_name, "ON"), (off_name, "OFF")):
        overwrite = True
        if preset_name in config_data["presets"]:
            overwrite = prompt_yes_no(f"Preset '{preset_name}' exists. Overwrite?", False)
        ok = create_or_replace_preset(
            config_data,
            preset_name,
            {"lights": selector, "power": power},
            overwrite=overwrite,
        )
        if ok:
            changed += 1
    return changed


def update_lights_metadata(
    config_data: Dict[str, Any],
    discovered: Sequence[core.LightInfo],
    selected_addresses: Sequence[str],
) -> int:
    lights_cfg = config_data["lights"]
    by_address = {light.address: light for light in discovered}
    changed_addresses: Set[str] = set()
    index = 0

    while index < len(selected_addresses):
        address = selected_addresses[index]
        light = by_address[address]
        existing = dict(lights_cfg.get(address, {}))
        default_name = str(existing.get("name") or light.name)
        default_cct_only = bool(existing.get("cct_only", light.cct_only))
        default_infinity = int(existing.get("infinity_mode", light.infinity_mode))

        print(f"\nConfigure {address} ({light.name})")
        try:
            name = prompt_text("Name", default_name)
            cct_only = prompt_yes_no("CCT-only model?", default_cct_only)
            infinity_mode = prompt_int(
                "Protocol mode (0=classic, 1=infinity, 2=hybrid)",
                default_infinity,
                0,
                2,
            )
        except WizardBack:
            if index == 0:
                raise
            index -= 1
            prev_address = selected_addresses[index]
            print(f"Going back to previous light: {prev_address}")
            continue

        record = dict(existing)
        record["name"] = name
        record["cct_only"] = cct_only
        record["infinity_mode"] = infinity_mode
        lights_cfg[address] = record
        changed_addresses.add(address)
        index += 1
    return len(changed_addresses)


def prompt_select_preset(config_data: Dict[str, Any], message: str = "Select preset") -> Optional[str]:
    presets = sorted(config_data["presets"].keys())
    if not presets:
        return None
    idx = prompt_choice(message, presets, 0)
    return presets[idx]


def prompt_select_address(config_data: Dict[str, Any], message: str = "Select light") -> Optional[str]:
    addresses = sorted(config_data["lights"].keys())
    if not addresses:
        return None
    options = [f"{addr} ({config_data['lights'][addr].get('name', 'Configured Light')})" for addr in addresses]
    idx = prompt_choice(message, options, 0)
    return addresses[idx]


def prompt_select_address_from_list(
    config_data: Dict[str, Any],
    addresses: Sequence[str],
    message: str = "Select light",
) -> Optional[str]:
    if not addresses:
        return None
    sorted_addresses = sorted(set(addresses))
    options = [
        f"{addr} ({config_data['lights'].get(addr, {}).get('name', 'Configured Light')})"
        for addr in sorted_addresses
    ]
    idx = prompt_choice(message, options, 0)
    return sorted_addresses[idx]


def _preset_kind_label(preset: Dict[str, Any]) -> str:
    if "power" in preset:
        return f"POWER {str(preset.get('power', '')).strip().upper()}"
    mode = str(preset.get("mode", "")).strip().upper()
    if mode:
        return mode
    if isinstance(preset.get("per_light"), dict):
        return "PER_LIGHT"
    return "UNKNOWN"


def prompt_select_preset_detailed(
    config_data: Dict[str, Any], message: str = "Select preset"
) -> Optional[str]:
    preset_names = sorted(config_data["presets"].keys())
    if not preset_names:
        return None
    options: List[str] = []
    for name in preset_names:
        preset = config_data["presets"].get(name, {})
        if not isinstance(preset, dict):
            options.append(f"{name} (invalid)")
            continue
        kind = _preset_kind_label(preset)
        target = str(preset.get("lights", ""))
        if len(target) > 36:
            target = target[:33] + "..."
        options.append(f"{name} [{kind}] {target}".rstrip())
    idx = prompt_choice(message, options, 0)
    return preset_names[idx]


def _base_cct_defaults_for_preset(
    preset: Dict[str, Any],
    per_light_existing: Optional[Dict[str, Any]],
) -> Tuple[int, int, int]:
    temp = _normalize_temp_to_kelvin(preset.get("temp"), 5600)
    bri = core._to_int(preset.get("bri"), 30)
    gm = core._to_int(preset.get("gm"), 0)
    if isinstance(per_light_existing, dict):
        temp = _normalize_temp_to_kelvin(per_light_existing.get("temp"), temp)
        bri = core._to_int(per_light_existing.get("bri"), bri)
        gm = core._to_int(per_light_existing.get("gm"), gm)
    return temp, bri, gm


def apply_light_cct_override_to_preset(
    preset: Dict[str, Any],
    address: str,
    temp: int,
    bri: int,
    gm: int,
) -> None:
    normalized_address = core.validate_mac_address(address, context="light address")
    per_light = preset.get("per_light")
    if not isinstance(per_light, dict):
        per_light = {}
        preset["per_light"] = per_light
    entry = per_light.get(normalized_address, {})
    if not isinstance(entry, dict):
        entry = {}
    updated = dict(entry)
    updated["mode"] = "CCT"
    updated["temp"] = int(temp)
    updated["bri"] = int(bri)
    updated["gm"] = int(gm)
    per_light[normalized_address] = updated


def edit_preset_cct_for_light(config_data: Dict[str, Any]) -> bool:
    preset_name = ""
    preset: Optional[Dict[str, Any]] = None
    address = ""
    remove_power = False
    set_mode_cct = False
    requires_conversion_prompt = False
    temp = 5600
    bri = 30
    gm = 0
    step = 1

    while True:
        try:
            if step == 1:
                selected = prompt_select_preset_detailed(
                    config_data, "Select preset to edit CCT"
                )
                if selected is None:
                    print("No presets available.")
                    return False
                preset_name = selected
                raw_preset = config_data["presets"].get(preset_name)
                if not isinstance(raw_preset, dict):
                    raise core.ConfigError(f"Preset '{preset_name}' must be an object")
                preset = raw_preset
                step = 2
                continue

            if step == 2:
                assert preset is not None
                members, unresolved = extract_preset_addresses(preset, config_data["groups"])
                candidate_addresses = [
                    addr for addr in sorted(members) if addr in config_data["lights"]
                ]
                if not candidate_addresses:
                    candidate_addresses = sorted(config_data["lights"].keys())
                    if unresolved:
                        print(
                            "Preset target cannot be fully resolved; showing all configured lights."
                        )
                if not candidate_addresses:
                    print("No configured lights available.")
                    return False
                selected_address = prompt_select_address_from_list(
                    config_data,
                    candidate_addresses,
                    message=f"Select light to edit in preset '{preset_name}'",
                )
                if selected_address is None:
                    print("No light selected.")
                    return False
                address = selected_address
                mode = str(preset.get("mode", "")).strip().upper()
                requires_conversion_prompt = bool("power" in preset and mode != "CCT")
                remove_power = False
                set_mode_cct = mode != "CCT"
                step = 3 if requires_conversion_prompt else 4
                continue

            if step == 3:
                assert preset is not None
                if not prompt_yes_no(
                    f"Preset '{preset_name}' is a power preset. Convert it to CCT-capable?",
                    False,
                ):
                    print("Preset left unchanged.")
                    return False
                remove_power = True
                set_mode_cct = True
                step = 4
                continue

            if step == 4:
                assert preset is not None
                existing_per_light = None
                if isinstance(preset.get("per_light"), dict):
                    existing_per_light = preset["per_light"].get(address)
                default_temp, default_bri, default_gm = _base_cct_defaults_for_preset(
                    preset, existing_per_light if isinstance(existing_per_light, dict) else None
                )
                temp_prompt_default = temp if temp else default_temp
                temp = prompt_temp_kelvin("Temperature (Kelvin)", temp_prompt_default)
                bri_prompt_default = bri if 0 <= bri <= 100 else default_bri
                bri = prompt_int("Brightness (0-100)", bri_prompt_default, 0, 100)
                gm_prompt_default = gm if -50 <= gm <= 50 else default_gm
                gm = prompt_int("GM compensation (-50 to 50)", gm_prompt_default, -50, 50)

                if remove_power:
                    preset.pop("power", None)
                if set_mode_cct:
                    preset["mode"] = "CCT"
                apply_light_cct_override_to_preset(preset, address, temp, bri, gm)
                print(
                    f"Updated preset '{preset_name}' for {address}: "
                    f"CCT temp={temp}K bri={bri} gm={gm}"
                )
                return True
        except WizardBack:
            if step == 1:
                raise
            if step == 2:
                step = 1
            elif step == 3:
                step = 2
            elif step == 4:
                step = 3 if requires_conversion_prompt else 2
            else:
                step = 1
            print(f"Back to preset CCT step {step}.")


def move_light_between_presets(config_data: Dict[str, Any]) -> bool:
    source = prompt_select_preset(config_data, "Select source preset")
    if source is None:
        print("No presets available.")
        return False
    destination = prompt_select_preset(config_data, "Select destination preset")
    if destination is None:
        print("No presets available.")
        return False
    if source == destination:
        print("Source and destination presets are the same.")
        return False
    address = prompt_select_address(config_data, "Select light to move")
    if address is None:
        print("No configured lights available.")
        return False

    update_preset_membership(config_data, source, address, add=False)
    update_preset_membership(config_data, destination, address, add=True)
    print(f"Moved {address} from '{source}' to '{destination}'.")
    return True


def manage_existing_preset(config_data: Dict[str, Any]) -> bool:
    preset_name = prompt_select_preset(config_data)
    if preset_name is None:
        print("No presets available.")
        return False
    address = prompt_select_address(config_data)
    if address is None:
        print("No configured lights available.")
        return False

    action_idx = prompt_choice(
        f"Preset '{preset_name}': choose action",
        ["Add selected light", "Remove selected light"],
        0,
    )
    add = action_idx == 0
    result = update_preset_membership(config_data, preset_name, address, add=add)
    print(result)
    return True


def choose_selector_for_new_preset(config_data: Dict[str, Any]) -> str:
    groups = sorted(config_data["groups"].keys())
    if groups:
        options = ["Use existing group", "Use explicit light list"]
        choice = prompt_choice("Preset target", options, 0)
        if choice == 0:
            group_idx = prompt_choice("Select group", groups, 0)
            return f"group:{groups[group_idx]}"

    addresses = sorted(config_data["lights"].keys())
    if not addresses:
        raise core.ConfigError("No configured lights available to target in a new preset.")

    print("\nConfigured lights:")
    for idx, address in enumerate(addresses, start=1):
        name = str(config_data["lights"][address].get("name", "Configured Light"))
        print(f"{idx:>2}. {address} ({name})")

    while True:
        raw = prompt_text("Select IDs for this preset (example: 1,2-4 or all)", "all")
        try:
            selected_ids = parse_selection(raw, set(range(1, len(addresses) + 1)))
        except ValueError as exc:
            print(f"Invalid selection: {exc}")
            continue
        selected = [addresses[idx - 1] for idx in selected_ids]
        return ",".join(selected)


def create_brand_new_preset(config_data: Dict[str, Any]) -> bool:
    preset_name = prompt_text("New preset name")
    selector = choose_selector_for_new_preset(config_data)

    preset_type = prompt_choice(
        "Preset type",
        ["Power ON", "Power OFF", "CCT setup"],
        0,
    )
    if preset_type == 0:
        body = {"lights": selector, "power": "ON"}
    elif preset_type == 1:
        body = {"lights": selector, "power": "OFF"}
    else:
        temp = prompt_temp_kelvin("Temperature (Kelvin)", 5600)
        bri = prompt_int("Brightness (0-100)", 30, 0, 100)
        gm = prompt_int("GM compensation (-50 to 50)", 0, -50, 50)
        body = {
            "lights": selector,
            "mode": "CCT",
            "temp": temp,
            "bri": bri,
            "gm": gm,
            "power_on_first": True,
        }

    overwrite = True
    if preset_name in config_data["presets"]:
        overwrite = prompt_yes_no(f"Preset '{preset_name}' exists. Overwrite?", False)
    ok = create_or_replace_preset(config_data, preset_name, body, overwrite)
    if ok:
        print(f"Preset '{preset_name}' saved.")
    else:
        print(f"Preset '{preset_name}' unchanged.")
    return ok


async def run_detailed_scan(config_data: Dict[str, Any], args: argparse.Namespace) -> List[core.LightInfo]:
    defaults = config_data.get("defaults", {})
    default_scan_timeout = float(defaults.get("scan_timeout", 8.0))
    default_scan_attempts = max(1, int(defaults.get("scan_attempts", 3)))

    scan_timeout = (
        float(args.scan_timeout) if args.scan_timeout is not None else default_scan_timeout
    )
    scan_attempts = (
        max(1, int(args.scan_attempts))
        if args.scan_attempts is not None
        else default_scan_attempts
    )

    config = core.AppConfig(
        debug=bool(args.debug),
        scan_timeout=scan_timeout,
        scan_attempts=scan_attempts,
        connect_timeout=1.0,
        connect_retries=1,
        write_retries=1,
        passes=1,
        parallel=1,
        settle_delay=0.0,
        power_with_response=True,
    )
    discovered, _ = await core.discover_with_retries(
        config,
        target_addresses=None,
        collect_all=True,
    )
    by_address = {light.address: light for light in discovered}

    configured_targets = set(config_data.get("lights", {}).keys())
    if configured_targets:
        targeted, _ = await core.discover_with_retries(
            config,
            target_addresses=configured_targets,
            collect_all=True,
        )
        for light in targeted:
            existing = by_address.get(light.address)
            if existing is None or light.rssi > existing.rssi:
                by_address[light.address] = light

    return sorted(by_address.values(), key=lambda light: light.rssi, reverse=True)


async def run_onboarding_wizard(config_data: Dict[str, Any], args: argparse.Namespace) -> bool:
    discovered = await run_detailed_scan(config_data, args)
    if not discovered:
        print("No Neewer lights found during detailed scan.")
        return False

    selected_addresses: List[str] = []
    selector = ""
    changed_any = False
    step = 1

    while True:
        try:
            if step == 1:
                selected_addresses = choose_light_addresses(discovered, config_data["lights"])
                if not selected_addresses:
                    print("No lights selected.")
                    return changed_any
                step = 2
                continue

            if step == 2:
                changed_any = bool(
                    update_lights_metadata(config_data, discovered, selected_addresses)
                ) or changed_any
                step = 3
                continue

            if step == 3:
                selector = choose_or_create_group(config_data, selected_addresses)
                step = 4
                continue

            if step == 4:
                changed_any = bool(configure_on_off_presets(config_data, selector)) or changed_any
                step = 5
                continue

            if step == 5:
                if prompt_yes_no("Create/update a CCT setup preset for these lights?", True):
                    setup_name = prompt_text("CCT setup preset name", "setup_cct")
                    if configure_cct_setup_preset(
                        config_data, setup_name, selector, selected_addresses
                    ):
                        changed_any = True
                    else:
                        print(f"Preset '{setup_name}' unchanged.")
                return changed_any
        except WizardBack:
            if step <= 1:
                print("Already at the first onboarding step.")
                continue
            step -= 1
            print(f"Back to onboarding step {step}.")


def _print_config_summary(config_data: Dict[str, Any]) -> None:
    print(
        f"\nConfig summary: lights={len(config_data['lights'])}, "
        f"groups={len(config_data['groups'])}, presets={len(config_data['presets'])}"
    )


async def interactive_wizard(config_data: Dict[str, Any], args: argparse.Namespace) -> bool:
    dirty = False
    print("Tip: type ESC then Enter to go back one step.")
    while True:
        _print_config_summary(config_data)
        action = prompt_choice(
            "Configuration wizard",
            [
                "Onboard lights (scan + groups + setup presets)",
                "Edit preset CCT for a light",
                "Add/remove light in an existing preset",
                "Move light between presets",
                "Create a brand-new preset",
                "Save and exit",
                "Exit without saving",
            ],
            0,
            allow_back=False,
        )

        if action == 0:
            try:
                changed = await run_onboarding_wizard(config_data, args)
            except WizardBack:
                print("Back to main menu.")
                changed = False
            dirty = dirty or changed
            continue
        if action == 1:
            try:
                changed = edit_preset_cct_for_light(config_data)
            except WizardBack:
                print("Back to main menu.")
                changed = False
            except core.ConfigError as exc:
                print(f"[ERROR] {exc}")
                changed = False
            dirty = dirty or changed
            continue
        if action == 2:
            try:
                changed = manage_existing_preset(config_data)
            except WizardBack:
                print("Back to main menu.")
                changed = False
            except core.ConfigError as exc:
                print(f"[ERROR] {exc}")
                changed = False
            dirty = dirty or changed
            continue
        if action == 3:
            try:
                changed = move_light_between_presets(config_data)
            except WizardBack:
                print("Back to main menu.")
                changed = False
            except core.ConfigError as exc:
                print(f"[ERROR] {exc}")
                changed = False
            dirty = dirty or changed
            continue
        if action == 4:
            try:
                changed = create_brand_new_preset(config_data)
            except WizardBack:
                print("Back to main menu.")
                changed = False
            except core.ConfigError as exc:
                print(f"[ERROR] {exc}")
                changed = False
            dirty = dirty or changed
            continue
        if action == 5:
            return dirty
        return False


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Interactive config editor for neewer-cli."
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {core.get_app_version()}",
    )
    parser.add_argument(
        "--config",
        default=core.DEFAULT_CONFIG_PATH,
        help="Config file path (.json, .yaml, .yml). Default: ~/.neewer",
    )
    parser.add_argument("--scan-timeout", default=None, type=float)
    parser.add_argument("--scan-attempts", default=None, type=int)
    parser.add_argument("--debug", action="store_true", help="Verbose debug output")
    return parser


async def _async_main(args: argparse.Namespace) -> int:
    config_data = ensure_config_shape(core.load_user_config(args.config, args.debug))
    changed = await interactive_wizard(config_data, args)
    if not changed:
        print("No changes written.")
        return 0

    if not prompt_yes_no("Write changes to config file now?", True, allow_back=False):
        print("Changes discarded.")
        return 0

    backup_path = write_config_file(args.config, config_data)
    print(f"Saved config: {os.path.expanduser(args.config)}")
    if backup_path:
        print(f"Backup created: {backup_path}")
    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return asyncio.run(_async_main(args))
    except core.ConfigError as exc:
        print(f"[ERROR] {exc}")
        return 2
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
