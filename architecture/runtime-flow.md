# Runtime Flow

This page describes how Cockpitdecks turns configuration plus simulator state
into live deck behaviour.

## Primary source files

The flow described here is mainly implemented in:

- `cockpitdecks/start.py`
- `cockpitdecks/cockpit.py`
- `cockpitdecks/aircraft.py`
- `cockpitdecks/deck.py`
- `cockpitdecks/page.py`
- `cockpitdecks/button.py`
- `cockpitdecks/event.py`
- `cockpitdecks/simulator.py`

## Core object model

The main runtime chain is:

**Cockpit -> Aircraft -> Deck -> Page -> Button**

### Cockpit

`Cockpit` is the top-level runtime container.

It owns:

- simulator selection and lifecycle
- extension loading
- discovered devices
- the current aircraft
- event queues
- dirty-button batching and rendering coordination

### Aircraft

`Aircraft` is the currently active aircraft configuration.

It owns:

- aircraft `deckconfig/config.yaml`
- aircraft resources
- aircraft-local deck types
- the concrete decks loaded for that aircraft

### Deck

A `Deck` is one hardware or virtual device bound to one layout.

It owns:

- the chosen layout directory
- loaded pages
- current page and page history
- deck-specific callbacks and rendering behaviour

### Page

A `Page` is a collection of buttons plus page attributes and includes.

It owns:

- page-level config
- button collection
- the simulator variables required by its buttons

### Button

A `Button` combines:

- activation behaviour
- representation behaviour
- value computation

It reacts to both deck events and variable changes.

## Startup flow

The normal startup path is:

1. `start.py` parses CLI arguments and environment.
2. Cockpitdecks creates the top-level `Cockpit`.
3. `Cockpit.init()` loads extensions, activations, representations, deck
   drivers, and simulator support.
4. `Cockpit.init_simulator()` installs the chosen simulator adapter.
5. Global resources are loaded.
6. Physical devices are scanned.
7. The selected aircraft is loaded.
8. The simulator connection, USB monitoring, and event loop are started.

## Aircraft load flow

When an aircraft is started:

1. the previously loaded aircraft is terminated if needed
2. the aircraft `deckconfig/` is validated
3. aircraft config is loaded
4. aircraft identity such as ICAO/name is set
5. aircraft-local deck types and resources are loaded
6. concrete deck instances are created from the deck entries
7. each deck loads its layout and pages
8. each deck switches to its initial page

If no valid aircraft config is found, Cockpitdecks falls back to default deck
pages instead of aircraft-specific pages.

## Deck and page load flow

Each deck loads one layout directory.

At a high level, `Deck.load()`:

1. reads layout `config.yaml`
2. enumerates page YAML files
3. creates a `Page` object for each valid page
4. loads base buttons
5. merges included fragments
6. validates button capabilities against the selected deck type
7. sets the home page

Each `Page` then builds its `Button` objects and registers the variables needed
by those buttons.

## Deck event flow

The path for a hardware interaction is:

1. a deck callback receives raw device input
2. Cockpitdecks converts it into a typed `DeckEvent`
3. the event is enqueued into the Cockpit event queue
4. the Cockpit event loop dequeues it
5. the current page and target button are resolved
6. `Button.activate(event)` runs the activation
7. the button recomputes its value
8. side effects such as commands or set-dataref writes are applied
9. the button is marked for render if its state changed

Important design rule:

Device callbacks do not directly perform full activations. They enqueue work so
reloads and lifecycle changes happen outside the low-level callback context.

## Variable and render flow

The path for simulator-driven updates is:

1. the active page declares which simulator variables its buttons require
2. the deck registers those variables when the page becomes active
3. variable updates arrive from the simulator or internal-variable system
4. buttons listening to those variables receive `variable_changed(...)`
5. the button recomputes its value
6. if the visible state changed, it requests a render
7. Cockpit batches dirty buttons and flushes them together

## Page switch flow

`Deck.change_page()` is a full dataflow transition, not only navigation.

It:

1. drops dirty buttons from the old page
2. removes old-page simulator variables from monitoring
3. detaches old-page listeners
4. cleans old-page visuals
5. installs the new current page
6. adds new-page simulator variables to monitoring
7. attaches new-page listeners
8. renders the new page

## Aircraft change flow

Cockpitdecks watches monitoring variables for aircraft and livery changes.

When a new aircraft is detected:

1. Cockpit receives the aircraft-change signal
2. it resolves the new aircraft path
3. it schedules the change onto an aircraft-loader thread
4. the simulator adapter is notified
5. the current aircraft is terminated
6. the new aircraft config is loaded
7. decks and pages are recreated

The change is asynchronous on purpose so deck callbacks are not torn down while
still executing.

## Reload flow

Reloads are queue-based:

1. a reload request is enqueued
2. the Cockpit event loop picks it up
3. the actual rebuild happens from the event-loop side
4. current pages are remembered when possible
5. decks or the full aircraft are rebuilt
6. previous pages are restored when possible

This avoids self-destruction bugs where a device callback triggers the teardown
of the object graph that is still handling that callback.

## Invariants and traps

These are the runtime rules most likely to matter during maintenance:

1. **Deck callbacks should stay lightweight**
   Raw device callbacks should enqueue work, not perform full lifecycle
   operations directly.
2. **Page changes are dataflow changes**
   A page switch is not just navigation. It rebinds simulator monitoring and
   listeners.
3. **Reloads are queue-based for safety**
   Triggering rebuilds directly from callback contexts is a bug risk.
4. **The active page is the live monitored surface**
   Simulator monitoring is meant to follow the active page, not all pages at
   once.
5. **Aircraft changes are asynchronous**
   Aircraft switching is intentionally decoupled from foreground event
   processing.
6. **Config and runtime are separate layers**
   If behaviour looks wrong, confirm whether the issue is in the runtime or in
   `cockpitdecks-configs` before editing.

## Fast debugging map

| Symptom | First files |
|---|---|
| startup failure | `cockpitdecks/start.py`, `cockpitdecks/cockpit.py` |
| deck not discovered | `cockpitdecks/cockpit.py`, adapter repo |
| page file ignored | `cockpitdecks/deck.py` |
| button does nothing | `cockpitdecks/event.py`, `cockpitdecks/button.py` |
| page switch breaks updates | `cockpitdecks/deck.py`, `cockpitdecks/page.py` |
| stale values on screen | `cockpitdecks/page.py`, `cockpitdecks/button.py`, `cockpitdecks/simulator.py` |
| reload behaves inconsistently | `cockpitdecks/cockpit.py`, `cockpitdecks/aircraft.py` |
