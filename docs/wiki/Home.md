# neewer-cli Wiki

`neewer-cli` is a standalone Neewer BLE command-line utility focused on fast and reliable command delivery.

## Start Here

- Configuration reference: [Configuration](Configuration)
- Developer internals: [Developer Guide](Developer-Guide)
- Source repository: https://github.com/SergeDubovsky/neewer-cli

## Typical User Flow

1. Copy `neewer.example.json` to `~/.neewer` (Windows: `%USERPROFILE%\.neewer`).
2. Define your `lights`, `groups`, and `presets`.
3. Use presets:

```bash
neewer-cli --preset all_on
neewer-cli --preset all_off
```

4. Use direct command overrides when needed:

```bash
neewer-cli --light group:studio --mode CCT --temp 5600 --bri 30
```
