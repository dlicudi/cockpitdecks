# List known deck drivers, their constructor, and their device manager for enumeration.
#
# Do not import VirtualDeck here: cockpitdecks.deck loads cockpitdecks.decks.resources,
# which loads this package; eager import of virtualdeck would re-enter cockpitdecks.deck
# before DeckWithIcons exists (breaks PyInstaller and cockpitdecks_ld/sd import order).


def __getattr__(name: str):
    if name == "VirtualDeck":
        from .virtualdeck import VirtualDeck

        return VirtualDeck
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
