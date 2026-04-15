# ###########################
# Slider representation — vertical filled-bar gauge designed for use with
# the "slider" activation on web decks (touch-draggable on iPad/iPhone).
#
# The PIL image contains only the static background (track outline + label).
# The fill, handle bar, and value text are rendered client-side in deck.js
# using Canvas2D so dragging is immediate with no server round-trip.
#
import logging

from PIL import Image, ImageDraw

from cockpitdecks.resources.color import convert_color
from .draw import DrawBase, ICON_SIZE

logger = logging.getLogger(__name__)

TRACK_COLOR  = (50,  50,  50,  255)
LABEL_COLOR  = (180, 180, 180, 255)
TRACK_RADIUS = 10


def _to_css(color) -> str:
    """Convert a PIL color tuple or CSS string to a CSS rgba() string."""
    if isinstance(color, (list, tuple)):
        r, g, b = int(color[0]), int(color[1]), int(color[2])
        a = int(color[3]) if len(color) > 3 else 255
        return f"rgba({r},{g},{b},{a / 255:.3f})"
    return str(color)


class SliderIcon(DrawBase):
    """Vertical (or horizontal) filled-bar slider for web decks.

    The server renders a static background image (track outline + label).
    The browser renders the fill, handle, and value text locally for
    zero-latency dragging, then sends the dataref value to the server.

    YAML config key: ``slider-icon``

    Example::

        representation:
          type: slider-icon
          slider-icon:
            value-min: 0
            value-max: 1
            label: POWER
            fill-color: cyan
            track-color: "#3c3c3c"
            orientation: vertical   # or horizontal
    """

    EDITOR_FAMILY = "Gauge / Dial"
    EDITOR_LABEL  = "Slider"

    REPRESENTATION_NAME = "slider-icon"

    PARAMETERS = DrawBase.PARAMETERS | {
        "value-min":    {"type": "float",  "prompt": "Minimum value"},
        "value-max":    {"type": "float",  "prompt": "Maximum value"},
        "label":        {"type": "string", "prompt": "Label"},
        "fill-color":   {"type": "color",  "prompt": "Fill colour"},
        "track-color":  {"type": "color",  "prompt": "Track colour"},
        "orientation":  {"type": "string", "prompt": "Orientation (vertical/horizontal)"},
    }

    def __init__(self, button: "Button"):
        DrawBase.__init__(self, button=button)
        cfg = self._config.get(self.REPRESENTATION_NAME, {})

        self.value_min   = float(cfg.get("value-min",  0))
        self.value_max   = float(cfg.get("value-max", 100))
        self.label       = cfg.get("label", "")
        self.orientation = cfg.get("orientation", "vertical")
        self.vertical    = self.orientation != "horizontal"

        raw_fill  = cfg.get("fill-color",  "cyan")
        raw_track = cfg.get("track-color", "#323232")
        self.fill_color  = convert_color(raw_fill)
        self.track_color = convert_color(raw_track)

        self.label_font_size = int(cfg.get("label-font-size", round(ICON_SIZE * 0.11)))

    # ──────────────────────────────────────────────────────────────────────────

    def _fraction(self) -> float:
        """Current value mapped to [0, 1]."""
        raw = self.button.value
        if raw is None:
            return 0.0
        try:
            v = float(raw)
        except (TypeError, ValueError):
            return 0.0
        span = self.value_max - self.value_min
        if span == 0:
            return 0.0
        return max(0.0, min(1.0, (v - self.value_min) / span))

    def get_slider_meta(self) -> dict:
        """Return rendering metadata for client-side slider drawing."""
        return {
            "fill":        _to_css(self.fill_color),
            "track":       _to_css(self.track_color),
            "orientation": self.orientation,
            "fraction":    self._fraction(),
            "label":       self.label,
        }

    # ──────────────────────────────────────────────────────────────────────────

    def get_image_for_icon(self):
        """Render static background only — track outline and label.

        Fill, handle, and value text are drawn client-side by deck.js.
        """
        S = ICON_SIZE
        image = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        draw  = ImageDraw.Draw(image)

        if self.vertical:
            self._draw_vertical_bg(draw, S)
        else:
            self._draw_horizontal_bg(draw, S)

        return self.move_and_send(image)

    # ──────────────────────────────────────────────────────────────────────────

    def _draw_vertical_bg(self, draw: ImageDraw.ImageDraw, S: int):
        margin = int(S * 0.18)
        pad    = int(S * 0.02)
        r      = TRACK_RADIUS

        tx0 = margin
        tx1 = S - margin
        ty0 = pad
        ty1 = S - pad

        # Track background only — no fill
        draw.rounded_rectangle([tx0, ty0, tx1, ty1], radius=r, fill=self.track_color)

        # Label at bottom inside track
        if self.label:
            try:
                font_l = self.get_font(None, self.label_font_size)
                draw.text(
                    (S // 2, ty1 - 4),
                    self.label,
                    font=font_l,
                    fill=LABEL_COLOR,
                    anchor="mb",
                )
            except Exception:
                pass

    def _draw_horizontal_bg(self, draw: ImageDraw.ImageDraw, S: int):
        pad = int(S * 0.02)
        r   = TRACK_RADIUS

        ty0 = S // 2 - int(S * 0.12)
        ty1 = S // 2 + int(S * 0.12)
        tx0 = pad
        tx1 = S - pad

        # Track background only — no fill
        draw.rounded_rectangle([tx0, ty0, tx1, ty1], radius=r, fill=self.track_color)

        # Label at right edge
        if self.label:
            try:
                font_l = self.get_font(None, self.label_font_size)
                draw.text(
                    (tx1 - 6, (ty0 + ty1) // 2),
                    self.label,
                    font=font_l,
                    fill=LABEL_COLOR,
                    anchor="rm",
                )
            except Exception:
                pass

    # ──────────────────────────────────────────────────────────────────────────

    def get_variables(self) -> set:
        """Return the display dataref so the button re-renders when X-Plane changes it."""
        dataref = self._config.get(self.REPRESENTATION_NAME, {}).get("dataref")
        return {dataref} if dataref else set()

    def render(self):
        return self.get_image_for_icon()

    def describe(self) -> str:
        return (
            f"Slider bar ({self.orientation}) showing value between "
            f"[{self.value_min}, {self.value_max}]. Label: '{self.label}'."
        )
