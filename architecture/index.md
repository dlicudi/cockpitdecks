# Cockpitdecks Architecture

This folder is the source of truth for Cockpitdecks architecture notes.

It is meant for maintainers, contributors, and AI agents who need a stable map
of the runtime before making changes.

## Main layers

At a high level, the Cockpitdecks stack is made of:

1. **X-Plane**
   Owns aircraft state, commands, datarefs, aircraft loading, and simulator
   runtime.
2. **XPPython3**
   Hosts Python plugins inside X-Plane.
3. **Cockpitdecks runtime**
   Owns startup, event handling, simulator abstraction, aircraft lifecycle,
   deck/page/button orchestration, and rendering coordination.
4. **Simulator and deck adapters**
   Bridge the runtime to X-Plane and to hardware families such as Stream Deck
   and Loupedeck.
5. **Configuration repository**
   Aircraft layouts, modules, deck types, and generated aircraft
   documentation live in `cockpitdecks-configs`.
6. **Documentation repositories**
   Published user-facing docs may live elsewhere, but the runtime architecture
   source of truth should stay beside the runtime code.

## Main runtime model

The core runtime chain is:

**Cockpit -> Aircraft -> Deck -> Page -> Button**

Cross-cutting concerns:

- **Simulator**
  Commands, variables, monitoring, and aircraft change detection.
- **Event loop**
  Safe handling of deck input, reload requests, and queued work.
- **Render batching**
  Dirty-button flushing and deck update coordination.

## High-level flow

```text
Deck hardware / web decks
    ^
    | input events / visual updates
    v
Cockpitdecks runtime
    ^
    | commands, monitored values, aircraft changes
    v
Simulator adapter
    ^
    | plugin or API bridge
    v
X-Plane

cockpitdecks-configs
    |
    | aircraft YAML, modules, deck types
    v
Aircraft deckconfig/
```

## Ownership boundaries

Use this split before editing:

| Concern | Primary home |
|---|---|
| startup, event loop, page switching, rendering lifecycle | `cockpitdecks` |
| X-Plane integration | `cockpitdecks_xp` |
| Stream Deck support | `cockpitdecks_sd` |
| Loupedeck support | `cockpitdecks_ld` |
| low-level Loupedeck transport | `python-loupedeck-live` |
| aircraft layouts and modules | `cockpitdecks-configs` |
| published user docs | `cockpitdecks-docs` |

## Reading order

Start with:

1. `architecture/index.md`
2. `architecture/runtime-flow.md`
3. `architecture/workspace-map.md`

Then go deeper into code:

- `cockpitdecks/start.py`
- `cockpitdecks/cockpit.py`
- `cockpitdecks/aircraft.py`
- `cockpitdecks/deck.py`
- `cockpitdecks/page.py`
- `cockpitdecks/button.py`
- `cockpitdecks/event.py`
- `cockpitdecks/simulator.py`

## Code entry points

If you need to open code immediately, these are the highest-value starting
files:

| Concern | File |
|---|---|
| CLI startup and bootstrapping | `cockpitdecks/start.py` |
| global runtime container and event loop | `cockpitdecks/cockpit.py` |
| aircraft lifecycle and deck creation | `cockpitdecks/aircraft.py` |
| layout/page switching and deck lifecycle | `cockpitdecks/deck.py` |
| page/button loading and variable registration | `cockpitdecks/page.py` |
| button activation, value computation, render requests | `cockpitdecks/button.py` |
| event types and event execution path | `cockpitdecks/event.py` |
| simulator abstraction and monitoring | `cockpitdecks/simulator.py` |

## Common task map

Use this when you already know what kind of change you need:

| Task | First files to inspect |
|---|---|
| change startup or boot sequence | `cockpitdecks/start.py`, `cockpitdecks/cockpit.py` |
| change event routing or queue semantics | `cockpitdecks/cockpit.py`, `cockpitdecks/event.py` |
| change aircraft loading or reload behaviour | `cockpitdecks/aircraft.py`, `cockpitdecks/cockpit.py` |
| change page switching | `cockpitdecks/deck.py` |
| change page/button parsing or includes | `cockpitdecks/deck.py`, `cockpitdecks/page.py` |
| change button activation semantics | `cockpitdecks/button.py`, activation classes |
| change variable propagation or monitoring | `cockpitdecks/page.py`, `cockpitdecks/simulator.py`, `cockpitdecks/button.py` |
| change render scheduling or dirty-button batching | `cockpitdecks/cockpit.py`, `cockpitdecks/button.py`, deck adapter render methods |
| change simulator integration | `cockpitdecks_xp`, `cockpitdecks/simulator.py` |
| change Stream Deck behaviour | `cockpitdecks_sd` |
| change Loupedeck behaviour | `cockpitdecks_ld`, and possibly `python-loupedeck-live` |

## Agent notes

For AI agents, the intended workflow is:

1. classify the request by ownership boundary first
2. open the task-map files before doing wide searches
3. treat this folder as orientation, not as a substitute for code
4. prefer updating the architectural source of truth here when repeated
   rediscovery is required
