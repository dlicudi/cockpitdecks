# Agent Notes

This page is a compact checklist for AI agents working in the Cockpitdecks
ecosystem.

## First decision

Before reading code, classify the task:

| Question | If yes, start in |
|---|---|
| Is this runtime behaviour? | `cockpitdecks` |
| Is this aircraft layout/config content? | `cockpitdecks-configs` |
| Is this X-Plane integration behaviour? | `cockpitdecks_xp` |
| Is this Stream Deck hardware behaviour? | `cockpitdecks_sd` |
| Is this Loupedeck hardware behaviour? | `cockpitdecks_ld` |
| Is this low-level Loupedeck device transport? | `python-loupedeck-live` |

## High-value files

Open these before broad search when possible:

- `cockpitdecks/cockpit.py`
- `cockpitdecks/aircraft.py`
- `cockpitdecks/deck.py`
- `cockpitdecks/page.py`
- `cockpitdecks/button.py`
- `cockpitdecks/event.py`
- `cockpitdecks/simulator.py`

## Rules of thumb

1. Do not infer runtime guarantees from `cockpitdecks-configs`.
2. Do not edit generated config docs in `cockpitdecks-configs/docs/decks/`.
3. Treat reload behaviour as queue-driven unless code proves otherwise.
4. Treat page switching as a listener/monitoring transition, not just a UI
   navigation event.
5. Check adapter repos before changing core runtime for hardware-specific
   behaviour.
6. Check support-library repos before changing adapters for low-level transport
   issues.

## Common mistakes

- changing the wrong repo because the same words appear in config and runtime
- editing derived docs instead of config/generators
- debugging page updates without checking listener attach/detach on page switch
- calling a support library obsolete while it is still an adapter dependency

## When to update these notes

Update this folder when:

- agents repeatedly misclassify ownership
- the runtime lifecycle changes materially
- a support repo becomes optional, replaced, or obsolete
- a debugging trap recurs often enough to deserve documentation
