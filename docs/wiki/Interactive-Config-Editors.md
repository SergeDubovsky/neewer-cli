# Interactive Config Editors

`neewer-cli` ships with two separate config utilities:

- `neewer-config`: wizard flow
- `neewer-config-tui`: tree-based TUI flow

## `neewer-config` (Wizard)

Run:

```bash
neewer-config
```

Primary workflows:

- Onboard lights through scan and guided prompts
- Create or update groups
- Set light metadata (`name`, `cct_only`, `infinity_mode`)
- Create presets (`POWER ON`, `POWER OFF`, CCT)
- Add/remove/move lights across presets
- Edit CCT parameters in existing presets

Use `Esc` to step back to prior wizard selections.

## `neewer-config-tui` (Tree UI)

Run:

```bash
neewer-config-tui
```

Layout:

- Top: scan findings and assignment controls
- Left: config tree (`Presets`, `Groups`, `Lights`)
- Right: editor panel for selected preset/light

Presence validation:

- `✓` bright white: confirmed in latest scan
- `?` grey: configured but not currently discovered

Assignment flow:

1. Scan (`Ctrl+F` or `Scan` button).
2. Select a scanned light in the top selector.
3. Select target group/preset node in tree.
4. Click `Assign -> Group` or `Assign -> Preset`.

Editor behavior:

- Selecting a preset enables preset CCT editing.
- Selecting a preset-light node edits/removes per-light overrides.
- Selecting a light/group-member enables light metadata editing.
- Controls enable/disable automatically based on selection context.

Key bindings:

- `Ctrl+S`: save
- `Ctrl+R`: reload
- `Ctrl+F`: scan
- `q`: quit (press twice if unsaved changes)
