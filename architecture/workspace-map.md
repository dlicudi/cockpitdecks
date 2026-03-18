# Workspace Map

This page maps the repositories commonly present in a Cockpitdecks development
workspace and explains which part of the system each one owns.

## Package-level dependency picture

The current repository split is roughly:

```text
cockpitdecks
├── extra: xplane     -> cockpitdecks_xp -> xpwebapi
├── extra: streamdeck -> cockpitdecks_sd -> streamdeck
├── extra: loupedeck  -> cockpitdecks_ld -> loupedeck (python-loupedeck-live)
├── extra: weather    -> cockpitdecks_wm
└── extra: demoext    -> cockpitdecks_ext

cockpitdecks-configs
└── aircraft configuration repository

cockpitdecks-docs
└── published documentation repository
```

## Repository roles

| Repository | Role | Category |
|---|---|---|
| `cockpitdecks` | Main runtime and object model | Core |
| `cockpitdecks-configs` | Aircraft configs, modules, deck types, generated aircraft docs | Core content |
| `cockpitdecks_xp` | X-Plane integration | Adapter |
| `cockpitdecks_sd` | Stream Deck integration | Adapter |
| `cockpitdecks_ld` | Loupedeck integration | Adapter |
| `cockpitdecks_wm` | Weather-related representations/extensions | Optional extension |
| `cockpitdecks_ext` | Demo/sample extension package | Optional extension |
| `xplane-webapi` | Python wrapper for X-Plane Web API | Support library |
| `python-loupedeck-live` | Low-level Loupedeck device library | Support library |
| `cockpitdecks-docs` | Published Cockpitdecks documentation site | Documentation |

## Practical ownership guide

| If the change is about... | First repo to inspect |
|---|---|
| startup, event loop, rendering lifecycle, page switching | `cockpitdecks` |
| simulator integration with X-Plane | `cockpitdecks_xp` |
| Stream Deck support | `cockpitdecks_sd` |
| Loupedeck support | `cockpitdecks_ld` |
| low-level Loupedeck protocol/device library | `python-loupedeck-live` |
| X-Plane Web API client behaviour | `xplane-webapi` |
| aircraft layouts, modules, deckconfig docs | `cockpitdecks-configs` |
| published user docs | `cockpitdecks-docs` |
| weather icons or METAR-based representations | `cockpitdecks_wm` |

## Important note on `python-loupedeck-live`

`python-loupedeck-live` should currently be treated as an active supporting
dependency, not as an obsolete side repo.

Why:

- `cockpitdecks_ld` depends on the `loupedeck` package from that repository
- `cockpitdecks_ld` directly imports `LoupedeckLive` and `DeviceManager` from
  it

So the current layering is:

```text
Cockpitdecks runtime
  -> cockpitdecks_ld
    -> python-loupedeck-live
```

Do not call it obsolete until that dependency edge is removed from the active
Loupedeck adapter.
