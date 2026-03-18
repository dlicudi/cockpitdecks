# Diagrams

This page collects the highest-value sequence views of Cockpitdecks.

These are intentionally lightweight and are meant to complement the prose in
`runtime-flow.md`.

## Startup

```mermaid
sequenceDiagram
    autonumber
    participant CLI as start.py
    participant Cockpit as Cockpit runtime
    participant Sim as Simulator adapter
    participant Devices as Deck drivers
    participant Aircraft as Aircraft loader

    CLI->>Cockpit: create cockpit
    Cockpit->>Cockpit: load extensions and representations
    Cockpit->>Sim: init simulator
    Cockpit->>Cockpit: load global resources
    Cockpit->>Devices: scan devices
    CLI->>Cockpit: start aircraft
    Cockpit->>Aircraft: start aircraft
    Aircraft->>Aircraft: load config and pages
    CLI->>Cockpit: run
    Cockpit->>Sim: connect
    Cockpit->>Cockpit: start event loop
    Cockpit->>Devices: start USB monitoring

    Note over Cockpit,Aircraft: Runtime state is assembled before live simulator monitoring begins.
```

## Deck Event To Render

```mermaid
sequenceDiagram
    autonumber
    participant Device as Deck callback
    participant Event as DeckEvent
    participant Cockpit as Event loop
    participant Button as Button
    participant Sim as Simulator
    participant Render as Render flush

    Device->>Event: create event
    Event->>Cockpit: enqueue
    Cockpit->>Event: dequeue and run
    Event->>Button: activate
    Button->>Button: compute value
    Button->>Sim: write command if needed
    Button->>Cockpit: mark dirty
    Cockpit->>Render: flush dirty buttons
    Render->>Device: render updated output

    Note over Device,Cockpit: Device callbacks stay lightweight and hand work to the queue.
    Note over Button,Render: Rendering is decoupled from activation and can be batched.
```

## Aircraft Change And Reload

```mermaid
sequenceDiagram
    autonumber
    participant Sim as Simulator monitor
    participant Cockpit as Cockpit runtime
    participant Loader as Aircraft loader thread
    participant Aircraft as Aircraft
    participant Decks as Deck instances

    Sim->>Cockpit: aircraft changed
    Cockpit->>Cockpit: resolve aircraft path
    Cockpit->>Loader: schedule aircraft change
    Loader->>Cockpit: acquire reload lock
    Loader->>Sim: notify simulator
    Loader->>Aircraft: terminate current aircraft
    Loader->>Aircraft: start new aircraft
    Aircraft->>Decks: recreate decks and pages
    Decks->>Decks: restore pages

    Note over Cockpit,Loader: Aircraft changes are asynchronous on purpose.
    Note over Aircraft,Decks: The reload path rebuilds state before restoring visible pages.
```

## Repository Boundary Map

```mermaid
flowchart TD
    XP[X-Plane]
    XPP[XPPython3]
    CD[cockpitdecks]
    XPA[cockpitdecks_xp]
    SDA[cockpitdecks_sd]
    LDA[cockpitdecks_ld]
    CFG[cockpitdecks-configs]
    DOCS[cockpitdecks-docs]
    WEB[xplane-webapi]
    LDLIB[python-loupedeck-live]
    SDLIB[streamdeck]

    XP --> XPP
    XPP --> XPA
    XPA --> CD
    WEB --> XPA
    SDA --> CD
    SDLIB --> SDA
    LDA --> CD
    LDLIB --> LDA
    CFG --> CD
    DOCS -. publishes .-> CD
    DOCS -. documents .-> CFG
```
