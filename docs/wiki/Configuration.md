# Configuration

Default config path:

- `~/.neewer` (Windows: `%USERPROFILE%\.neewer`)

Supported file formats:

- JSON
- YAML / YML (requires `PyYAML`)

## Top-Level Keys

- `defaults`: default CLI flags and scan behavior
- `lights`: per-MAC metadata
- `groups`: named light collections
- `presets`: reusable command payloads

## `lights`

Each key is a MAC address.

Common fields:

- `name`: user label
- `cct_only`: boolean
- `infinity_mode`: integer (`0`, `1`, or `2`)
- `hw_mac`: optional hardware MAC mapping
- `supports_status_query`: optional feature override
- `supports_extended_scene`: optional feature override

## `groups`

Each group value is a list of MAC addresses.

Example:

```json
{
  "groups": {
    "studio": ["D2:E2:75:8B:36:45", "F8:46:85:EF:47:70"]
  }
}
```

## `presets`

Preset entries use CLI-like keys (`mode`, `temp`, `bri`, `gm`, `scene`, `power`, etc.).

Power-aware behavior supported inside presets:

- `power_on_first: true`
- `power_on_delay_ms: 500`

Aliases:

- `power_on` / `poweron` -> `power_on_first`
- `power_on_delay` -> `power_on_delay_ms`

Per-light overrides:

- `presets.<name>.per_light.<mac>.temp`
- `presets.<name>.per_light.<mac>.bri`
- `presets.<name>.per_light.<mac>.gm`

## Recommended Setup Flow

1. Run `neewer-config-tui` for a visual tree workflow.
2. Scan and confirm visible lights.
3. Assign scanned lights into groups and presets.
4. Save.
5. Run `neewer-cli --preset <name>` for runtime control.

Text fallback:

- `neewer-config` for wizard-style setup/editing in plain terminal mode.
