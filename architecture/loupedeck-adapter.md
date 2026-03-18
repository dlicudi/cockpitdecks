# Loupedeck Adapter

This page describes the architecture boundary for the Loupedeck adapter layer.

The adapter repo is `cockpitdecks_ld`.

## Responsibility

`cockpitdecks_ld` connects the Cockpitdecks runtime to Loupedeck devices.

It owns:

- Loupedeck device discovery through the Loupedeck library
- Loupedeck callback decoding into Cockpitdecks events
- Loupedeck rendering/output formatting
- Loupedeck-specific deck type/resource definitions
- Loupedeck-specific hardware and side-screen representations

It should not own generic Cockpitdecks lifecycle logic.

## Main boundary

The main layering is:

```text
cockpitdecks
  -> cockpitdecks_ld
    -> python-loupedeck-live
      -> Loupedeck hardware
```

This means:

- generic deck lifecycle belongs in `cockpitdecks`
- Loupedeck integration belongs in `cockpitdecks_ld`
- low-level device protocol/library behaviour belongs in
  `python-loupedeck-live`

## Key files

| Concern | File |
|---|---|
| package entry | `cockpitdecks_ld/__init__.py` |
| main deck implementation | `cockpitdecks_ld/decks/loupedeck.py` |
| side/hardware/LED representations | `cockpitdecks_ld/buttons/representation/` |
| deck type definitions/resources | `cockpitdecks_ld/decks/resources/types/` |

## Runtime role

The central class boundary is:

- `Loupedeck` in `cockpitdecks_ld/decks/loupedeck.py`

That is the first file to inspect for:

- touch and side-screen event handling
- encoder mapping
- button-index translation between Loupedeck naming and Cockpitdecks naming
- Loupedeck-specific rendering problems

## Common task map

| Task | First repo/files |
|---|---|
| change Loupedeck device discovery | `cockpitdecks_ld/decks/loupedeck.py` |
| change callback decoding to Cockpitdecks events | `cockpitdecks_ld/decks/loupedeck.py` |
| change side-screen or LED rendering | `cockpitdecks_ld/buttons/representation/` |
| change Loupedeck model capability definitions | `cockpitdecks_ld/decks/resources/types/` |
| change low-level Loupedeck protocol/device behaviour | `python-loupedeck-live` |
| change generic deck/page lifecycle | `cockpitdecks/deck.py`, not adapter first |

## Traps and invariants

1. Do not call `python-loupedeck-live` obsolete while `cockpitdecks_ld`
   still depends on and imports it.
2. Keep device callback logic adapter-local and lifecycle logic runtime-local.
3. Mapping bugs may live in adapter key translation, not in config files.
4. Side-screen behaviour is more adapter-specific than generic icon rendering,
   so start here before touching core runtime.
