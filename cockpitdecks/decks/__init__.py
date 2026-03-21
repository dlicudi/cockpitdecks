# Subpackage for built-in deck resources (e.g. cockpitdecks.decks.resources).
#
# Do not import cockpitdecks.decks.virtualdeck (VirtualDeck) here: loading that
# module pulls in cockpitdecks.deck while cockpitdecks.deck may still be
# initializing (e.g. PyInstaller analyzing cockpitdecks_ld / cockpitdecks_sd).
# Import the driver with: from cockpitdecks.decks.virtualdeck import VirtualDeck
