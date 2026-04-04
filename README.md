# Welcome to Cockpit Deck

<div float="right">
<img src="https://github.com/devleaks/cockpitdecks/raw/main/cockpitdecks/resources/icon.png" width="200" alt="Cockpitdecks icon"/>
</div>
Cockpitdecks is a python software to interface

- Elgato Stream Decks
- Loupedeck LoupedeckLive
- Behringer XTouch Mini

with X-Plane flight simulator.

Cockpitdecks also allows you to create and use [Web decks](https://devleaks.github.io/cockpitdecks-docs/Extending/Web%20Decks/) in a browser window.

The project is in active development, and will remain perpetual beta software.

Please head to the [documentation](https://devleaks.github.io/cockpitdecks-docs/) for more information.

You can find [numerous configurations for different aircrafts here](https://github.com/dlicudi/cockpitdecks-configs).

Fly safely.


## Architecture

The runtime architecture source of truth lives in this repository:

- `architecture/index.md`
- `architecture/runtime-flow.md`
- `architecture/diagrams.md`
- `architecture/workspace-map.md`
- `architecture/agent-notes.md`
- `architecture/xplane-adapter.md`
- `architecture/streamdeck-adapter.md`
- `architecture/loupedeck-adapter.md`

These notes are intended for maintainers and AI agents and are kept next to the
runtime code on purpose.

To preview them locally:

```sh
python3 -m pip install -r requirements-docs.txt
mkdocs serve
```


## Installation


WARNING: The latest version of Cockpitdecks, release 15 and above, requires the latest version of X-Plane, 12.1.4 or above.
Read the [documentation](https://devleaks.github.io/cockpitdecks-docs/Installation/).

Create a python environment. Python 3.12 minimum.
In that environment, install the following packages:

```sh
pip install 'cockpitdecks[demoext,weather,streamdeck] @ git+https://github.com/devleaks/cockpitdecks.git'
```

Valid installable extras (between the `[` `]`, comma separated, no space) are:

| Extra              | Content                                                                                                    |
| ------------------ | ---------------------------------------------------------------------------------------------------------- |
| `weather`          | Add special iconic representation for weather. These icons sometimes fetch information outside of X-Plane. |
| `toliss`           | Add special features for ToLiss airbus aircrafts. Useless for other aircrafts.                             |
| `demoext`          | Add a few Loupedeck and Stream Deck+ demo extensions.                                                      |
| `streamdeck`       | For Elgato Stream Deck devices                                                                             |
| `loupedeck`        | For Loupedeck LoupedeckLive, LoupedeckLive.s and Loupedeck CT devices                                      |
| `xtouchmini`       | For Berhinger X-Touch Mini devices                                                                         |
| `development`      | For developer only, add testing packages and python types                                                  |


```sh
cockpitdecks_cli --demo'
```

Fly safely.


## Launcher and Packaging

`launcher.py` is a thin entrypoint that runs `cockpitdecks.start` as `__main__`. It exists so the app can be launched directly or bundled cleanly for distribution.

The PyInstaller build definition is [cockpitdecks.spec](/Users/duanelicudi/GitHub/cockpitdecks/cockpitdecks.spec). It collects the core package plus the optional backends used by Cockpitdecks:

- `cockpitdecks`
- `cockpitdecks_xp`
- `cockpitdecks_ld`
- `cockpitdecks_sd`
- `cockpitdecks_wm`
- `cockpitdecks_ext`
- `avwx`
- `StreamDeck`
- `Loupedeck`
- `requests_cache`

### Build the launcher

```sh
python -m pip install pyinstaller
pyinstaller cockpitdecks.spec
```

The generated executable is named `cockpitdecks`.

### Automated macOS Apple Silicon release

GitHub Actions can build and publish a macOS arm64 launcher release from this repo.

- Workflow: `.github/workflows/release-macos-arm64.yml`
- Build-only workflow: `.github/workflows/build-macos-arm64.yml`
- Dependency manifest: `.github/cockpitdecks-release-deps.env`
- Trigger: push a tag matching `v*`
- Manual trigger: `workflow_dispatch` with a required `release_tag`
- Runner: `macos-14`
- Output artifact: `cockpitdecks-macos-arm64-<tag>.tar.gz`
- Release metadata: `build-metadata.json`

Example:

```sh
git tag v15.15.2-beta.2
git push origin v15.15.2-beta.2
```

The workflow checks out the sibling Cockpitdecks repos into the workspace layout expected by `cockpitdecks.spec`, using the exact refs pinned in `.github/cockpitdecks-release-deps.env`. It then builds `dist/cockpitdecks`, verifies it is `arm64`, records the resolved commits and Python distribution versions in `build-metadata.json`, and uploads the tarball plus a SHA-256 checksum.

When recreating the build environment, the workflow installs the local repos with `--no-build-isolation` and removes any pre-existing wheel install of `loupedeck` first. This avoids accidentally freezing a PyPI copy instead of the checked-out `python-loupedeck-live` repository.

Recommended release flow:

1. Update `.github/cockpitdecks-release-deps.env` to the dependency refs you want to ship.
2. Commit that manifest change in `cockpitdecks`.
3. Push a release tag such as `v15.15.2-beta.2`.

This keeps the launcher release reproducible even when the dependency repos keep moving.

For CI verification without creating a GitHub Release, run `.github/workflows/build-macos-arm64.yml` manually. It uses the same manifest and build steps, but only uploads the tarball, checksum, and `build-metadata.json` as Actions artifacts.

### Automated Windows x64 build

GitHub Actions can also produce a first-pass Windows x64 launcher artifact from this repo.

- Workflow: `.github/workflows/build-windows-x64.yml`
- Dependency manifest: `.github/cockpitdecks-release-deps.env`
- Runner: `windows-latest`
- Output artifact: `cockpitdecks-windows-x64-<build-id>.zip`
- Release status: build-only for now, not yet a public GitHub Release workflow

The Windows workflow uses the same pinned sibling-repo refs as the macOS build, installs Cairo and hidapi DLLs from MSYS2, and bundles those DLLs into the PyInstaller output. This is intended to validate frozen Windows packaging before adding an official Windows release workflow.

### Notes

- If a package is not installed, the spec logs the `collect_all` failure and continues.
- Some backends are only needed for specific devices or integrations, so the bundled app may still be valid even if not every optional package is present.
- `cockpitdecks_ext` currently uses a stack tag in the manifest because that repo does not yet expose a matching semantic-version tag.
- The launcher spec bundles native Cairo and HID libraries for the current platform and preloads those bundled libraries at startup so the frozen app does not rely on a system install being discoverable at runtime.

## Developer note

Recompilation of rt-midi on MacOS < 15 may require the specification of

export CPLUS_INCLUDE_PATH=/opt/homebrew/Caskroom/miniforge/base/include/c++/v1

## Local Dev Desktop

Run the sibling desktop checkout against this repo's local launcher with:

```sh
make run
```

This uses:

- `../cockpitdecks-desktop/.venv/bin/python -m cockpitdecks_desktop.app`
- `./dist/cockpitdecks`

The target builds `dist/cockpitdecks` first if needed. In dev mode, the desktop app resolves that executable path itself.

## Runtime Config

The `cockpitdecks` binary can load a per-user runtime config file. By default it looks for:

- macOS: `~/Library/Application Support/Cockpitdecks/config.yaml`
- Linux: `~/.config/cockpitdecks/config.yaml`
- Windows: `%LOCALAPPDATA%/Cockpitdecks/config.yaml`

Override that path with `--config /path/to/config.yaml`.

Example:

```yaml
deck_paths:
  - /Users/duanelicudi/Library/Application Support/Cockpitdecks/decks
  - /Users/duanelicudi/GitHub/cockpitdecks-configs/decks

target: null

xplane_api:
  host: 127.0.0.1
  port: 8086

cockpitdecks_server:
  host: 127.0.0.1
  port: 7777

simulator_host: null
launch_log: null

logging:
  console: true
```

Current precedence is:

1. CLI arguments
2. `config.yaml`
3. environment variables
4. built-in defaults
