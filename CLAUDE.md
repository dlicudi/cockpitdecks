# Cockpitdecks

Core framework monorepo. All first-party extensions live in `packages/`.

## Project layout

```
pyproject.toml              # Core package + uv workspace root (members = packages/*)
cockpitdecks/               # Core source (flat layout)
packages/
  cockpitdecks_xp/          # X-Plane simulator interface
  cockpitdecks_wm/          # Weather module
  cockpitdecks_ext/         # Extra button/deck types
  cockpitdecks_ld/          # Loupedeck deck driver integration
  cockpitdecks_sd/          # Stream Deck driver integration
  cockpitdecks_bx/          # Behringer X-Touch Mini integration
  cockpitdecks_tl/          # ToLiss aircraft extension
  xpwebapi/                 # X-Plane REST Web API client
```

## Development

```bash
uv sync
uv run cockpitdecks-cli --help
```

Install with optional extras:

```bash
uv sync --extra xplane --extra loupedeck --extra streamdeck
```

## Key conventions

- Package manager: **uv** with workspaces
- Build system: **Hatchling** (all packages)
- Cross-package dependencies use `[tool.uv.sources]` workspace references — no git URLs between workspace members
- Hardware driver libs (`python-loupedeck-live`, `python-elgato-streamdeck`) remain external git dependencies

## Related repos

- **cockpitdecks-desktop**: desktop launcher/dashboard app (consumes this monorepo)
- **cockpitdecks-editor**: standalone config editor app (consumes this monorepo)
- **cockpitdecks-configs**: aircraft configuration files
- **cockpitdecks-docs**: documentation site
