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

The PyInstaller build definition is [cockpitdecks-launcher.spec](/Users/duanelicudi/GitHub/cockpitdecks/cockpitdecks-launcher.spec). It collects the core package plus the optional backends used by Cockpitdecks:

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
pyinstaller cockpitdecks-launcher.spec
```

The generated executable is named `cockpitdecks-launcher`.

### Notes

- If a package is not installed, the spec logs the `collect_all` failure and continues.
- Some backends are only needed for specific devices or integrations, so the bundled app may still be valid even if not every optional package is present.

## Developer note

Recompilation of rt-midi on MacOS < 15 may require the specification of

export CPLUS_INCLUDE_PATH=/opt/homebrew/Caskroom/miniforge/base/include/c++/v1
