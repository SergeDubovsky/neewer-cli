"""Textual TUI config editor for neewer-cli."""

from __future__ import annotations

import argparse
import json
import os
from typing import Any, Dict, List, Optional, Set, Tuple

from rich.text import Text

import neewer_cli as core
import neewer_config_cli as cfg

_TEXTUAL_IMPORT_ERROR: Optional[Exception] = None
_TEXTUAL_AVAILABLE = False
try:
    from textual import on
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Container, Horizontal, Vertical
    from textual.widgets import Button, Footer, Header, Input, Select, Static, Tree

    _TEXTUAL_AVAILABLE = True
except ModuleNotFoundError as exc:
    _TEXTUAL_IMPORT_ERROR = exc


def _preset_kind_label(preset: Dict[str, Any]) -> str:
    if "power" in preset:
        return f"POWER {str(preset.get('power', '')).strip().upper()}"
    mode = str(preset.get("mode", "")).strip().upper()
    if mode:
        return mode
    if isinstance(preset.get("per_light"), dict):
        return "PER_LIGHT"
    return "UNKNOWN"


def format_preset_option(config_data: Dict[str, Any], preset_name: str) -> str:
    preset = config_data["presets"].get(preset_name, {})
    if not isinstance(preset, dict):
        return f"{preset_name} (invalid)"
    kind = _preset_kind_label(preset)
    target = str(preset.get("lights", "")).strip()
    if len(target) > 36:
        target = target[:33] + "..."
    return f"{preset_name} [{kind}] {target}".rstrip()


def resolve_candidate_lights_for_preset(
    config_data: Dict[str, Any], preset_name: str
) -> List[str]:
    preset = config_data["presets"].get(preset_name, {})
    if not isinstance(preset, dict):
        return []
    members, _ = cfg.extract_preset_addresses(preset, config_data.get("groups", {}))
    configured_lights = set(config_data.get("lights", {}).keys())
    candidates = sorted(addr for addr in members if addr in configured_lights)
    if candidates:
        return candidates
    return sorted(config_data.get("lights", {}).keys())


def parse_temp_kelvin(raw: str) -> int:
    text = str(raw).strip()
    if not text:
        raise ValueError("Temperature is required.")
    try:
        value = int(text)
    except ValueError as exc:
        raise ValueError("Temperature must be an integer.") from exc
    if 25 <= value <= 100:
        value *= 100
    if value < 2500 or value > 10000:
        raise ValueError(
            "Temperature must be between 2500 and 10000 (or shorthand 25-100)."
        )
    return value


def parse_brightness(raw: str) -> int:
    text = str(raw).strip()
    if not text:
        raise ValueError("Brightness is required.")
    try:
        value = int(text)
    except ValueError as exc:
        raise ValueError("Brightness must be an integer.") from exc
    if value < 0 or value > 100:
        raise ValueError("Brightness must be between 0 and 100.")
    return value


def parse_gm(raw: str) -> int:
    text = str(raw).strip()
    if not text:
        raise ValueError("GM is required.")
    try:
        value = int(text)
    except ValueError as exc:
        raise ValueError("GM must be an integer.") from exc
    if value < -50 or value > 50:
        raise ValueError("GM must be between -50 and 50.")
    return value


def parse_bool_text(raw: str) -> bool:
    text = str(raw).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    raise ValueError("CCT-only must be true/false.")


def parse_infinity_mode(raw: str) -> int:
    text = str(raw).strip()
    if not text:
        raise ValueError("Infinity mode is required.")
    try:
        value = int(text)
    except ValueError as exc:
        raise ValueError("Infinity mode must be an integer.") from exc
    if value not in {0, 1, 2}:
        raise ValueError("Infinity mode must be 0, 1, or 2.")
    return value


def cct_defaults_for_selection(
    config_data: Dict[str, Any], preset_name: str, address: str
) -> Tuple[int, int, int]:
    preset = config_data["presets"].get(preset_name, {})
    if not isinstance(preset, dict):
        return 5600, 30, 0
    per_light_entry = None
    per_light = preset.get("per_light")
    if isinstance(per_light, dict):
        value = per_light.get(address)
        if isinstance(value, dict):
            per_light_entry = value
    return cfg._base_cct_defaults_for_preset(preset, per_light_entry)


if _TEXTUAL_AVAILABLE:

    class NeewerConfigTui(App[None]):
        """Textual app for editing neewer config."""

        CSS = """
        Screen { layout: vertical; }
        #root { padding: 1 2; layout: vertical; }
        #scan_panel { border: round $surface; padding: 0 1; margin-bottom: 1; min-height: 9; height: 11; }
        #scan_results { height: 1fr; min-height: 4; overflow: auto auto; }
        #scan_controls { layout: horizontal; height: auto; margin-top: 1; }
        #scan_light_select { width: 1fr; }
        #scan_controls Button, #scan_controls Select { margin-right: 1; }
        #main { layout: horizontal; height: 1fr; }
        #tree_container { width: 38; min-width: 32; border: round $surface; padding: 0 1; margin-right: 1; }
        #config_tree { height: 1fr; }
        #editor_container { width: 1fr; border: round $surface; padding: 0 1; }
        #context_line { margin-bottom: 1; text-style: bold; }
        #mode_hint { color: $text-muted; margin-bottom: 1; }
        #cct_fields, #light_fields, #cct_buttons, #file_buttons { layout: horizontal; height: auto; margin-bottom: 1; }
        .field { width: 1fr; margin-right: 1; }
        #cct_buttons Button, #file_buttons Button { margin-right: 1; }
        #summary { border: round $surface; padding: 0 1; height: 1fr; min-height: 8; overflow: auto auto; margin-top: 1; }
        #status { border: heavy $accent; padding: 0 1; margin-top: 1; }
        """

        BINDINGS = [
            Binding("ctrl+s", "save", "Save"),
            Binding("ctrl+r", "reload", "Reload"),
            Binding("ctrl+f", "scan", "Scan"),
            Binding("q", "quit_app", "Quit"),
        ]

        def __init__(self, config_path: str, debug: bool = False) -> None:
            super().__init__()
            self.config_path = os.path.abspath(os.path.expanduser(config_path))
            self._debug_enabled = debug
            self.config_missing = False
            self.config_data: Dict[str, Any] = {
                "lights": {},
                "groups": {},
                "presets": {},
                "defaults": {},
            }
            self.dirty = False
            self.quit_armed = False
            self.current_preset: Optional[str] = None
            self.current_light: Optional[str] = None
            self._tree_nodes: Dict[str, Any] = {}
            self.scan_results: List[core.LightInfo] = []
            self.scan_lookup: Dict[str, core.LightInfo] = {}
            self.confirmed_addresses: Set[str] = set()

        def compose(self) -> ComposeResult:
            yield Header(show_clock=True)
            with Container(id="root"):
                with Vertical(id="scan_panel"):
                    yield Static("Scan Findings", id="scan_title")
                    yield Static("No scan results yet.", id="scan_results")
                    with Horizontal(id="scan_controls"):
                        yield Button("Scan", id="scan_button", variant="primary")
                        yield Select([], prompt="Scanned light", id="scan_light_select", allow_blank=True)
                        yield Button("Assign -> Group", id="assign_group_button")
                        yield Button("Assign -> Preset", id="assign_preset_button")

                with Horizontal(id="main"):
                    with Vertical(id="tree_container"):
                        yield Static("Current Config Tree")
                        yield Tree("Config", id="config_tree")
                    with Vertical(id="editor_container"):
                        yield Static("Selection: (none)", id="context_line")
                        yield Static("Select a preset or light in the tree.", id="mode_hint")
                        with Horizontal(id="cct_fields"):
                            with Vertical(classes="field"):
                                yield Static("Temperature (Kelvin or 25-100)")
                                yield Input("", id="temp_input")
                            with Vertical(classes="field"):
                                yield Static("Brightness (0-100)")
                                yield Input("", id="bri_input")
                            with Vertical(classes="field"):
                                yield Static("GM (-50 to 50)")
                                yield Input("", id="gm_input")
                        with Horizontal(id="cct_buttons"):
                            yield Button("Apply Preset Defaults", id="apply_preset_button", variant="primary")
                            yield Button("Apply Per-Light Override", id="apply_override_button")
                            yield Button("Remove Override", id="remove_override_button")
                        with Horizontal(id="light_fields"):
                            with Vertical(classes="field"):
                                yield Static("Light Name")
                                yield Input("", id="light_name_input")
                            with Vertical(classes="field"):
                                yield Static("CCT-only (true/false)")
                                yield Input("", id="light_cct_only_input")
                            with Vertical(classes="field"):
                                yield Static("Infinity Mode (0/1/2)")
                                yield Input("", id="light_infinity_input")
                        with Horizontal(id="file_buttons"):
                            yield Button("Apply Light Params", id="apply_light_button")
                            yield Button("Create Config", id="create_config_button")
                            yield Button("Save", id="save_button", variant="success")
                            yield Button("Reload", id="reload_button")
                        yield Static("", id="summary")
                yield Static("", id="status")
            yield Footer()

        def on_mount(self) -> None:
            self._load_config()

        def _set_status(self, message: str) -> None:
            self.query_one("#status", Static).update(message)

        def _update_title(self) -> None:
            suffix = " *" if self.dirty else ""
            missing = " (missing)" if self.config_missing else ""
            self.title = f"neewer-config-tui{suffix}"
            self.sub_title = f"{self.config_path}{missing}"

        def _selected_tree_node_data(self) -> Dict[str, Any]:
            tree = self.query_one("#config_tree", Tree)
            node = tree.cursor_node
            if node is None:
                return {}
            data = node.data
            if isinstance(data, dict):
                return data
            return {}

        def _selected_tree_key(self) -> Optional[str]:
            data = self._selected_tree_node_data()
            key = data.get("key")
            return str(key) if key else None

        def _selected_scan_address(self) -> Optional[str]:
            select = self.query_one("#scan_light_select", Select)
            value = select.value
            if value == Select.BLANK:
                return None
            return str(value)

        def _load_config(self) -> None:
            self.config_missing = not os.path.exists(self.config_path)
            self.config_data = cfg.ensure_config_shape(
                core.load_user_config(self.config_path, self._debug_enabled)
            )

            preset_names = sorted(self.config_data.get("presets", {}).keys())
            light_addresses = sorted(self.config_data.get("lights", {}).keys())
            if self.current_preset not in preset_names:
                self.current_preset = preset_names[0] if preset_names else None
            if self.current_light not in light_addresses:
                self.current_light = light_addresses[0] if light_addresses else None
            if self.current_preset and not self.current_light:
                candidates = resolve_candidate_lights_for_preset(
                    self.config_data, self.current_preset
                )
                if candidates:
                    self.current_light = candidates[0]

            self.dirty = False
            self.quit_armed = False
            self._update_title()
            self._refresh_scan_panel()
            self._refresh_tree()
            self._refresh_edit_fields()
            self._update_summary()
            if self.config_missing:
                self._set_status(
                    f"No config file found at {self.config_path}. Press Create Config."
                )
            else:
                self._set_status("Config loaded. Ctrl+F scan, Ctrl+S save, q quit.")

        def _refresh_scan_panel(self) -> None:
            panel = self.query_one("#scan_results", Static)
            select = self.query_one("#scan_light_select", Select)
            old_scan = self._selected_scan_address()

            output = Text()
            if not self.scan_results:
                output.append("No scan results yet.", style="grey62")
            else:
                output.append(
                    f"Found {len(self.scan_results)} light(s)  "
                    f"(configured: {len(self.config_data.get('lights', {}))})\n",
                    style="bold",
                )
                output.append("Legend: ✓ confirmed in scan, ? configured but unconfirmed\n", style="grey62")
                for light in self.scan_results:
                    in_config = light.address in self.config_data.get("lights", {})
                    suffix = " configured" if in_config else " new"
                    output.append(
                        f"✓ {light.address}  {light.name}  RSSI {light.rssi}  ({suffix.strip()})\n",
                        style="bold white",
                    )

            configured = sorted(self.config_data.get("lights", {}).keys())
            missing = [addr for addr in configured if addr not in self.confirmed_addresses]
            if missing:
                output.append("\nUnconfirmed configured lights:\n", style="bold grey62")
                for addr in missing:
                    name = str(
                        self.config_data["lights"]
                        .get(addr, {})
                        .get("name", "Configured Light")
                    )
                    output.append(f"? {addr}  {name}\n", style="grey62")

            panel.update(output)

            options = [
                (f"{light.address} ({light.name}) RSSI {light.rssi}", light.address)
                for light in self.scan_results
            ]
            select.set_options(options)
            if not options:
                select.clear()
            elif old_scan and any(value == old_scan for _, value in options):
                select.value = old_scan
            else:
                select.value = options[0][1]
            self._update_control_state()

        def _light_style(self, address: str) -> str:
            if address in self.confirmed_addresses:
                return "bold white"
            return "grey62"

        def _add_tree_node(self, node: Any, key: str) -> None:
            self._tree_nodes[key] = node

        def _refresh_tree(self) -> None:
            tree = self.query_one("#config_tree", Tree)
            previous_key = self._selected_tree_key()
            tree.clear()
            self._tree_nodes = {}

            root = tree.root
            root.set_label(Text("Config", style="bold"))
            root.data = {"kind": "root", "key": "root"}
            root.expand()
            self._add_tree_node(root, "root")

            presets_branch = root.add(
                Text("Presets", style="bold"),
                data={"kind": "branch", "branch": "presets", "key": "branch:presets"},
                expand=True,
            )
            self._add_tree_node(presets_branch, "branch:presets")
            preset_names = sorted(self.config_data.get("presets", {}).keys())
            for preset_name in preset_names:
                preset = self.config_data["presets"].get(preset_name, {})
                kind = _preset_kind_label(preset if isinstance(preset, dict) else {})
                preset_label = Text(f"{preset_name} [{kind}]", style="bold white")
                preset_key = f"preset:{preset_name}"
                preset_node = presets_branch.add(
                    preset_label,
                    data={"kind": "preset", "preset": preset_name, "key": preset_key},
                    expand=True,
                )
                self._add_tree_node(preset_node, preset_key)

                if isinstance(preset, dict) and isinstance(preset.get("per_light"), dict):
                    for address in sorted(preset["per_light"].keys()):
                        style = self._light_style(address)
                        marker = "✓" if address in self.confirmed_addresses else "?"
                        label = Text(f"{marker} {address} (override)", style=style)
                        override_key = f"preset_light:{preset_name}:{address}"
                        node = preset_node.add_leaf(
                            label,
                            data={
                                "kind": "preset_light",
                                "preset": preset_name,
                                "address": address,
                                "key": override_key,
                            },
                        )
                        self._add_tree_node(node, override_key)

            groups_branch = root.add(
                Text("Groups", style="bold"),
                data={"kind": "branch", "branch": "groups", "key": "branch:groups"},
                expand=True,
            )
            self._add_tree_node(groups_branch, "branch:groups")
            group_names = sorted(self.config_data.get("groups", {}).keys())
            for group_name in group_names:
                group_key = f"group:{group_name}"
                group_node = groups_branch.add(
                    Text(group_name, style="bold white"),
                    data={"kind": "group", "group": group_name, "key": group_key},
                    expand=True,
                )
                self._add_tree_node(group_node, group_key)
                members = self.config_data["groups"].get(group_name, [])
                for address in members:
                    style = self._light_style(address)
                    marker = "✓" if address in self.confirmed_addresses else "?"
                    name = str(
                        self.config_data["lights"]
                        .get(address, {})
                        .get("name", "Configured Light")
                    )
                    member_key = f"group_member:{group_name}:{address}"
                    member = group_node.add_leaf(
                        Text(f"{marker} {address} ({name})", style=style),
                        data={
                            "kind": "group_member",
                            "group": group_name,
                            "address": address,
                            "key": member_key,
                        },
                    )
                    self._add_tree_node(member, member_key)

            lights_branch = root.add(
                Text("Lights", style="bold"),
                data={"kind": "branch", "branch": "lights", "key": "branch:lights"},
                expand=True,
            )
            self._add_tree_node(lights_branch, "branch:lights")
            for address in sorted(self.config_data.get("lights", {}).keys()):
                meta = self.config_data["lights"].get(address, {})
                name = str(meta.get("name", "Configured Light"))
                style = self._light_style(address)
                marker = "✓" if address in self.confirmed_addresses else "?"
                light_key = f"light:{address}"
                light_node = lights_branch.add_leaf(
                    Text(f"{marker} {address} ({name})", style=style),
                    data={"kind": "light", "address": address, "key": light_key},
                )
                self._add_tree_node(light_node, light_key)

            select_key = previous_key
            if not select_key and self.current_preset and self.current_light:
                candidate = f"preset_light:{self.current_preset}:{self.current_light}"
                if candidate in self._tree_nodes:
                    select_key = candidate
            if not select_key and self.current_preset:
                candidate = f"preset:{self.current_preset}"
                if candidate in self._tree_nodes:
                    select_key = candidate
            if not select_key and self.current_light:
                candidate = f"light:{self.current_light}"
                if candidate in self._tree_nodes:
                    select_key = candidate
            if not select_key:
                if preset_names:
                    select_key = f"preset:{preset_names[0]}"
                elif group_names:
                    select_key = f"group:{group_names[0]}"
                elif self.config_data.get("lights"):
                    first_light = sorted(self.config_data["lights"].keys())[0]
                    select_key = f"light:{first_light}"
                else:
                    select_key = "root"

            node = self._tree_nodes.get(select_key, root)
            tree.select_node(node)

        def _refresh_edit_fields(self) -> None:
            context = self.query_one("#context_line", Static)
            hint = self.query_one("#mode_hint", Static)
            selected = self._selected_tree_node_data()
            kind = str(selected.get("kind", "root"))
            preset_text = self.current_preset or "(none)"
            light_text = self.current_light or "(none)"
            context.update(
                f"Selection: {kind}  |  preset={preset_text}  |  light={light_text}"
            )
            hint_map = {
                "preset": "Edit preset defaults, or assign scanned light to this preset.",
                "preset_light": "Edit per-light override values, or remove override.",
                "group": "Assign scanned light to this group.",
                "group_member": "Edit selected light metadata, or switch to preset to edit CCT.",
                "light": "Edit selected light metadata. Select preset for CCT editing.",
                "root": "Select a preset, group, or light in the tree to edit.",
            }
            hint.update(hint_map.get(kind, hint_map["root"]))

            temp_input = self.query_one("#temp_input", Input)
            bri_input = self.query_one("#bri_input", Input)
            gm_input = self.query_one("#gm_input", Input)
            if self.current_preset:
                if self.current_light:
                    temp, bri, gm = cct_defaults_for_selection(
                        self.config_data, self.current_preset, self.current_light
                    )
                else:
                    preset = self.config_data["presets"].get(self.current_preset, {})
                    if isinstance(preset, dict):
                        temp = cfg._normalize_temp_to_kelvin(preset.get("temp"), 5600)
                        bri = core._to_int(preset.get("bri"), 30)
                        gm = core._to_int(preset.get("gm"), 0)
                    else:
                        temp, bri, gm = 5600, 30, 0
                temp_input.value = str(temp)
                bri_input.value = str(bri)
                gm_input.value = str(gm)
            else:
                temp_input.value = ""
                bri_input.value = ""
                gm_input.value = ""

            name_input = self.query_one("#light_name_input", Input)
            cct_input = self.query_one("#light_cct_only_input", Input)
            infinity_input = self.query_one("#light_infinity_input", Input)
            if self.current_light:
                meta = self.config_data.get("lights", {}).get(self.current_light, {})
                name_input.value = str(meta.get("name", "Configured Light"))
                cct_input.value = (
                    "true"
                    if core._to_bool(meta.get("cct_only"), False)
                    else "false"
                )
                infinity_input.value = str(core._to_int(meta.get("infinity_mode"), 0))
            else:
                name_input.value = ""
                cct_input.value = ""
                infinity_input.value = ""
            self._update_control_state()

        def _update_control_state(self) -> None:
            has_preset = bool(self.current_preset)
            has_light = bool(self.current_light)
            has_scan_light = bool(self._selected_scan_address())
            has_group_selection = bool(self._selected_group_from_tree())
            has_preset_selection = bool(self._selected_preset_from_tree())

            self.query_one("#assign_group_button", Button).disabled = not (
                has_scan_light and has_group_selection
            )
            self.query_one("#assign_preset_button", Button).disabled = not (
                has_scan_light and has_preset_selection
            )

            self.query_one("#temp_input", Input).disabled = not has_preset
            self.query_one("#bri_input", Input).disabled = not has_preset
            self.query_one("#gm_input", Input).disabled = not has_preset
            self.query_one("#apply_preset_button", Button).disabled = not has_preset
            self.query_one("#apply_override_button", Button).disabled = not (
                has_preset and has_light
            )
            self.query_one("#remove_override_button", Button).disabled = not (
                has_preset and has_light
            )

            self.query_one("#light_name_input", Input).disabled = not has_light
            self.query_one("#light_cct_only_input", Input).disabled = not has_light
            self.query_one("#light_infinity_input", Input).disabled = not has_light
            self.query_one("#apply_light_button", Button).disabled = not has_light

            self.query_one("#create_config_button", Button).disabled = not self.config_missing

        def _update_summary(self) -> None:
            summary = self.query_one("#summary", Static)
            selected = self._selected_tree_node_data()
            kind = selected.get("kind")
            if kind == "preset":
                preset_name = selected.get("preset")
                data = self.config_data.get("presets", {}).get(preset_name, {})
                rendered = json.dumps(data, indent=2, ensure_ascii=True)
                summary.update(f"Preset: {preset_name}\n{rendered}")
                return
            if kind == "preset_light":
                preset_name = selected.get("preset")
                address = selected.get("address")
                preset = self.config_data.get("presets", {}).get(preset_name, {})
                value = {}
                if isinstance(preset, dict):
                    per_light = preset.get("per_light")
                    if isinstance(per_light, dict):
                        value = per_light.get(address, {})
                rendered = json.dumps(value, indent=2, ensure_ascii=True)
                summary.update(f"Override: {preset_name} -> {address}\n{rendered}")
                return
            if kind == "group":
                group_name = selected.get("group")
                members = self.config_data.get("groups", {}).get(group_name, [])
                rendered = json.dumps(members, indent=2, ensure_ascii=True)
                summary.update(f"Group: {group_name}\n{rendered}")
                return
            if kind in {"light", "group_member"}:
                address = selected.get("address")
                data = self.config_data.get("lights", {}).get(address, {})
                rendered = json.dumps(data, indent=2, ensure_ascii=True)
                summary.update(f"Light: {address}\n{rendered}")
                return
            rendered = json.dumps(
                {
                    "counts": {
                        "lights": len(self.config_data.get("lights", {})),
                        "groups": len(self.config_data.get("groups", {})),
                        "presets": len(self.config_data.get("presets", {})),
                    }
                },
                indent=2,
                ensure_ascii=True,
            )
            summary.update(rendered)

        def _set_dirty(self, value: bool = True) -> None:
            self.dirty = value
            self.quit_armed = False
            self._update_title()

        def _ensure_light_entry_from_scan(self, address: str) -> None:
            if address in self.config_data.get("lights", {}):
                return
            meta: Dict[str, Any] = {}
            found = self.scan_lookup.get(address)
            if found is not None:
                meta["name"] = found.name
                meta["cct_only"] = bool(found.cct_only)
                meta["infinity_mode"] = int(found.infinity_mode)
            else:
                meta["name"] = "Configured Light"
                meta["cct_only"] = False
                meta["infinity_mode"] = 0
            self.config_data["lights"][address] = meta

        def _selected_preset_from_tree(self) -> Optional[str]:
            data = self._selected_tree_node_data()
            kind = data.get("kind")
            if kind == "preset":
                return str(data.get("preset"))
            if kind == "preset_light":
                return str(data.get("preset"))
            return None

        def _selected_group_from_tree(self) -> Optional[str]:
            data = self._selected_tree_node_data()
            if data.get("kind") == "group":
                return str(data.get("group"))
            return None

        def _parse_cct_inputs(self) -> Optional[Tuple[int, int, int]]:
            temp_text = self.query_one("#temp_input", Input).value
            bri_text = self.query_one("#bri_input", Input).value
            gm_text = self.query_one("#gm_input", Input).value
            try:
                temp = parse_temp_kelvin(temp_text)
                bri = parse_brightness(bri_text)
                gm = parse_gm(gm_text)
            except ValueError as exc:
                self._set_status(f"[error] {exc}")
                return None
            return temp, bri, gm

        def _parse_light_inputs(self) -> Optional[Tuple[str, bool, int]]:
            name = self.query_one("#light_name_input", Input).value.strip()
            cct_text = self.query_one("#light_cct_only_input", Input).value
            infinity_text = self.query_one("#light_infinity_input", Input).value
            if not name:
                self._set_status("[error] Light name is required.")
                return None
            try:
                cct_only = parse_bool_text(cct_text)
                infinity_mode = parse_infinity_mode(infinity_text)
            except ValueError as exc:
                self._set_status(f"[error] {exc}")
                return None
            return name, cct_only, infinity_mode

        async def _run_scan(self) -> None:
            defaults = self.config_data.get("defaults", {})
            scan_timeout = float(defaults.get("scan_timeout", 6.0))
            scan_attempts = max(1, int(defaults.get("scan_attempts", 3)))

            self._set_status(
                f"Scanning for Neewer lights (attempts={scan_attempts}, timeout={scan_timeout:.1f}s)..."
            )
            app_config = core.AppConfig(
                debug=self._debug_enabled,
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
            try:
                found, _ = await core.discover_with_retries(
                    app_config,
                    target_addresses=None,
                    collect_all=True,
                )
            except Exception as exc:
                self._set_status(f"[error] Scan failed: {exc}")
                return

            self.scan_results = sorted(found, key=lambda light: light.rssi, reverse=True)
            self.scan_lookup = {light.address: light for light in self.scan_results}
            self.confirmed_addresses = set(self.scan_lookup.keys())
            self._refresh_scan_panel()
            self._refresh_tree()
            self._update_summary()
            if not self.scan_results:
                self._set_status("Scan finished: no lights found.")
            else:
                self._set_status(f"Scan finished: {len(self.scan_results)} light(s) found.")

        @on(Tree.NodeSelected, "#config_tree")
        def _tree_node_selected(self, event: Tree.NodeSelected) -> None:
            data = event.node.data if isinstance(event.node.data, dict) else {}
            kind = data.get("kind")
            if kind == "preset":
                self.current_preset = str(data.get("preset"))
                candidates = resolve_candidate_lights_for_preset(
                    self.config_data, self.current_preset
                )
                if candidates and self.current_light not in candidates:
                    self.current_light = candidates[0]
            elif kind == "preset_light":
                self.current_preset = str(data.get("preset"))
                self.current_light = str(data.get("address"))
            elif kind == "light":
                self.current_light = str(data.get("address"))
                if self.current_preset is None and self.config_data.get("presets"):
                    self.current_preset = sorted(self.config_data["presets"].keys())[0]
            elif kind == "group_member":
                self.current_light = str(data.get("address"))

            self._refresh_edit_fields()
            self._update_summary()

        @on(Button.Pressed, "#scan_button")
        def _scan_pressed(self) -> None:
            self.action_scan()

        @on(Select.Changed, "#scan_light_select")
        def _scan_selection_changed(self, _event: Select.Changed) -> None:
            self._update_control_state()

        @on(Button.Pressed, "#assign_group_button")
        def _assign_group_pressed(self) -> None:
            address = self._selected_scan_address()
            if not address:
                self._set_status("[error] Select a scanned light first.")
                return
            group_name = self._selected_group_from_tree()
            if not group_name:
                self._set_status("[error] Select a group node in the tree.")
                return
            self._ensure_light_entry_from_scan(address)
            members = set(self.config_data.get("groups", {}).get(group_name, []))
            members.add(address)
            self.config_data["groups"][group_name] = sorted(members)
            self.current_light = address
            self._set_dirty(True)
            self._refresh_tree()
            self._refresh_edit_fields()
            self._update_summary()
            self._set_status(f"Assigned {address} to group '{group_name}'.")

        @on(Button.Pressed, "#assign_preset_button")
        def _assign_preset_pressed(self) -> None:
            address = self._selected_scan_address()
            if not address:
                self._set_status("[error] Select a scanned light first.")
                return
            preset_name = self._selected_preset_from_tree()
            if not preset_name:
                self._set_status("[error] Select a preset node in the tree.")
                return
            self._ensure_light_entry_from_scan(address)
            try:
                cfg.update_preset_membership(self.config_data, preset_name, address, add=True)
            except core.ConfigError as exc:
                self._set_status(f"[error] {exc}")
                return
            self.current_preset = preset_name
            self.current_light = address
            self._set_dirty(True)
            self._refresh_tree()
            self._refresh_edit_fields()
            self._update_summary()
            self._set_status(f"Assigned {address} to preset '{preset_name}'.")

        @on(Button.Pressed, "#apply_preset_button")
        def _apply_preset_defaults(self) -> None:
            if not self.current_preset:
                self._set_status("[error] Select a preset in the tree.")
                return
            parsed = self._parse_cct_inputs()
            if parsed is None:
                return
            temp, bri, gm = parsed
            preset = self.config_data.get("presets", {}).get(self.current_preset)
            if not isinstance(preset, dict):
                preset = {}
                self.config_data["presets"][self.current_preset] = preset
            if "power" in preset:
                preset.pop("power", None)
            preset["mode"] = "CCT"
            preset["temp"] = temp
            preset["bri"] = bri
            preset["gm"] = gm
            self._set_dirty(True)
            self._refresh_tree()
            self._update_summary()
            self._set_status(
                f"Updated preset defaults for '{self.current_preset}' (temp={temp}K bri={bri} gm={gm})."
            )

        @on(Button.Pressed, "#apply_override_button")
        def _apply_override(self) -> None:
            if not self.current_preset or not self.current_light:
                self._set_status("[error] Select preset and light in the tree.")
                return
            parsed = self._parse_cct_inputs()
            if parsed is None:
                return
            temp, bri, gm = parsed
            preset = self.config_data.get("presets", {}).get(self.current_preset)
            if not isinstance(preset, dict):
                self._set_status(f"[error] Preset '{self.current_preset}' is invalid.")
                return
            if "power" in preset and str(preset.get("mode", "")).upper() != "CCT":
                preset.pop("power", None)
            if str(preset.get("mode", "")).upper() != "CCT":
                preset["mode"] = "CCT"
            cfg.apply_light_cct_override_to_preset(preset, self.current_light, temp, bri, gm)
            self._set_dirty(True)
            self._refresh_tree()
            self._update_summary()
            self._set_status(
                f"Applied override {self.current_preset} -> {self.current_light}: temp={temp}K bri={bri} gm={gm}."
            )

        @on(Button.Pressed, "#remove_override_button")
        def _remove_override(self) -> None:
            if not self.current_preset or not self.current_light:
                self._set_status("[error] Select preset and light in the tree.")
                return
            preset = self.config_data.get("presets", {}).get(self.current_preset)
            if not isinstance(preset, dict):
                self._set_status(f"[error] Preset '{self.current_preset}' is invalid.")
                return
            per_light = preset.get("per_light")
            if not isinstance(per_light, dict) or self.current_light not in per_light:
                self._set_status("No per-light override exists for selected light.")
                return
            per_light.pop(self.current_light, None)
            self._set_dirty(True)
            self._refresh_tree()
            self._update_summary()
            self._set_status(f"Removed override {self.current_preset} -> {self.current_light}.")

        @on(Button.Pressed, "#apply_light_button")
        def _apply_light_params(self) -> None:
            if not self.current_light:
                self._set_status("[error] Select a light node in the tree.")
                return
            parsed = self._parse_light_inputs()
            if parsed is None:
                return
            name, cct_only, infinity_mode = parsed
            entry = self.config_data.get("lights", {}).get(self.current_light, {})
            if not isinstance(entry, dict):
                entry = {}
            entry["name"] = name
            entry["cct_only"] = cct_only
            entry["infinity_mode"] = infinity_mode
            self.config_data["lights"][self.current_light] = entry
            self._set_dirty(True)
            self._refresh_tree()
            self._update_summary()
            self._set_status(f"Updated light metadata for {self.current_light}.")

        @on(Button.Pressed, "#create_config_button")
        def _create_config_pressed(self) -> None:
            self.action_create_config()

        @on(Button.Pressed, "#save_button")
        def _save_pressed(self) -> None:
            self.action_save()

        @on(Button.Pressed, "#reload_button")
        def _reload_pressed(self) -> None:
            self.action_reload()

        def action_scan(self) -> None:
            self.run_worker(self._run_scan(), name="scan", exclusive=True)

        def action_create_config(self) -> None:
            if os.path.exists(self.config_path) and not self.config_missing:
                self._set_status("Config file already exists.")
                return
            backup_path = cfg.write_config_file(self.config_path, self.config_data)
            self.config_missing = False
            self._set_dirty(False)
            self._update_control_state()
            if backup_path:
                self._set_status(f"Config created. Backup: {backup_path}")
            else:
                self._set_status(f"Config created: {self.config_path}")

        def action_save(self) -> None:
            backup_path = cfg.write_config_file(self.config_path, self.config_data)
            self.config_missing = False
            self._set_dirty(False)
            self._update_control_state()
            if backup_path:
                self._set_status(f"Saved. Backup: {backup_path}")
            else:
                self._set_status("Saved.")

        def action_reload(self) -> None:
            self._load_config()

        def action_quit_app(self) -> None:
            if self.dirty and not self.quit_armed:
                self.quit_armed = True
                self._set_status("Unsaved changes. Press q again to quit without saving.")
                return
            self.exit()

else:

    class NeewerConfigTui:  # pragma: no cover - runtime fallback only
        def __init__(self, config_path: str, debug: bool = False) -> None:
            self.config_path = config_path
            self._debug_enabled = debug

        def run(self) -> None:
            raise RuntimeError("Textual is not installed")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Text UI config editor for neewer-cli.")
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
    parser.add_argument("--debug", action="store_true", help="Verbose debug output")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if not _TEXTUAL_AVAILABLE:
        print(
            "Missing dependency: textual. Install with:\n"
            "  pip install textual\n"
            "or\n"
            "  pip install \"neewer-cli[tui]\""
        )
        if _TEXTUAL_IMPORT_ERROR:
            print(f"Details: {_TEXTUAL_IMPORT_ERROR}")
        return 2

    try:
        app = NeewerConfigTui(args.config, debug=args.debug)
        app.run()
        return 0
    except core.ConfigError as exc:
        print(f"[ERROR] {exc}")
        return 2
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
