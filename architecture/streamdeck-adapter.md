# Stream Deck Adapter

This page describes the architecture boundary for the Stream Deck adapter layer.

The adapter repo is `cockpitdecks_sd`.

## Responsibility

`cockpitdecks_sd` connects the Cockpitdecks runtime to Elgato Stream Deck
devices.

It owns:

- Stream Deck device discovery through the Stream Deck library
- Stream Deck callback decoding into Cockpitdecks events
- Stream Deck rendering/output formatting
- Stream Deck-specific deck type/resource definitions
- Stream Deck-specific hardware representations

It should not own generic Cockpitdecks event-loop or page/button lifecycle
logic.

## Main boundary

The main layering is:

```text
cockpitdecks
  -> cockpitdecks_sd
    -> streamdeck
      -> Stream Deck hardware
```

This means:

- generic deck lifecycle belongs in `cockpitdecks`
- Stream Deck device integration belongs in `cockpitdecks_sd`
- low-level Stream Deck library issues belong in the upstream `streamdeck`
  package

## Key files

| Concern | File |
|---|---|
| package entry | `cockpitdecks_sd/__init__.py` |
| main deck implementation | `cockpitdecks_sd/decks/streamdeck.py` |
| Stream Deck hardware representations | `cockpitdecks_sd/buttons/representation/hardware.py` |
| deck type definitions/resources | `cockpitdecks_sd/decks/resources/types/` |

## Runtime role

The central class boundary is:

- `Streamdeck` in `cockpitdecks_sd/decks/streamdeck.py`

That is the first file to inspect for:

- key press callback issues
- touchscreen handling
- encoder/touch strip behaviour on supported models
- render formatting issues specific to Stream Deck devices

## Common task map

| Task | First repo/files |
|---|---|
| change Stream Deck device discovery | `cockpitdecks_sd/decks/streamdeck.py` |
| change callback decoding to Cockpitdecks events | `cockpitdecks_sd/decks/streamdeck.py` |
| change Stream Deck rendering | `cockpitdecks_sd/decks/streamdeck.py` |
| change Stream Deck hardware representations | `cockpitdecks_sd/buttons/representation/` |
| change Stream Deck model capability definitions | `cockpitdecks_sd/decks/resources/types/` |
| change generic deck/page lifecycle | `cockpitdecks/deck.py`, not adapter first |

## Traps and invariants

1. Do not fix generic page-switch problems inside the adapter unless the bug is
   truly Stream Deck-specific.
2. Keep raw device callback work lightweight; hand off real work to Cockpitdecks
   events.
3. Device geometry/capability problems often belong in deck type definitions,
   not in generic runtime code.
4. If a bug reproduces only on one hardware family, check this adapter before
   changing `cockpitdecks`.
