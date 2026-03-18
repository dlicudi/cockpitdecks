# X-Plane Adapter

This page describes the architecture boundary for the X-Plane adapter layer.

The adapter repo is `cockpitdecks_xp`.

## Responsibility

`cockpitdecks_xp` connects the Cockpitdecks runtime to X-Plane-specific APIs
and concepts.

It owns:

- the X-Plane simulator implementation used by Cockpitdecks
- X-Plane commands and set-dataref execution
- monitored simulator-variable integration
- X-Plane-specific observables/resources
- X-Plane-specific button representations

It should not own generic Cockpitdecks page/button/deck lifecycle logic.

## Main boundary

The main layering is:

```text
cockpitdecks
  -> cockpitdecks_xp
    -> xpwebapi
      -> X-Plane Web API
```

This means:

- generic runtime orchestration belongs in `cockpitdecks`
- X-Plane transport and simulator semantics belong in `cockpitdecks_xp`
- low-level Web API client behaviour belongs in `xplane-webapi`

## Key files

| Concern | File |
|---|---|
| package entry | `cockpitdecks_xp/__init__.py` |
| simulator implementation | `cockpitdecks_xp/simulators/xplane.py` |
| X-Plane observables/resources | `cockpitdecks_xp/resources/` |
| X-Plane-specific button representations | `cockpitdecks_xp/buttons/representation/` |

## Runtime role

Within Cockpitdecks, this adapter mainly plugs into the simulator abstraction.

The highest-value class boundary is:

- `XPlane` in `cockpitdecks_xp/simulators/xplane.py`

That class is where agent work should start for:

- simulator connection problems
- command execution issues
- dataref monitoring behaviour
- aircraft-change signals coming from the simulator side

## Common task map

| Task | First repo/files |
|---|---|
| change X-Plane connection logic | `cockpitdecks_xp/simulators/xplane.py` |
| change command execution semantics | `cockpitdecks_xp/simulators/xplane.py` |
| change set-dataref behaviour at simulator boundary | `cockpitdecks_xp/simulators/xplane.py` |
| change X-Plane-specific observable/resource behaviour | `cockpitdecks_xp/resources/` |
| change generic simulator abstraction | `cockpitdecks/simulator.py` first, then adapter |
| change Web API client behaviour | `xplane-webapi`, not `cockpitdecks_xp` |

## Traps and invariants

1. Do not move generic runtime lifecycle code into this adapter.
2. Do not change `xpwebapi` concerns here if the issue is really transport/API
   client behaviour.
3. If a bug reproduces only with X-Plane but not with `NoSimulator`, start here.
4. If the issue affects all simulators conceptually, start in
   `cockpitdecks/simulator.py` before editing the adapter.
