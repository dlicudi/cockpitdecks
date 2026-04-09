/* Cockpitdecks web deck — Canvas 2D renderer (device-agnostic layout)
 *
 * Receives PIL-rendered PNG tiles from the server over WebSocket and blits
 * them onto a plain <canvas> at computed positions — no hardware background
 * image is used. Layout is derived from the deck-type-flat button metadata.
 *
 * Button groups (classified from metadata):
 *   strips      — 'left' / 'right': tall image panels beside the main grid
 *   gridBtns    — image tiles, push/swipe action, form the main NxM key grid
 *   touchscreen — special wide image panel (Stream Deck +)
 *   ledBtns     — colored-led feedback buttons, bottom row
 *   encoders    — encoder+push, no image tile; receive wheel events only
 */

// ─── Constants ────────────────────────────────────────────────────────────────

const PRESENTATION_DEFAULTS = "presentation-default"
const ASSET_IMAGE_PATH = "/assets/images/"

const PAD = 16   // outer canvas padding (px)
const GAP = 4    // gap between buttons (px)

const DEFAULT_USER_PREFERENCES = {
    highlight: "#ffffff10",
    flash:     "#0f80ffb0",
    flash_duration: 100
}

var USER_PREFERENCES = DEFAULT_USER_PREFERENCES

// Event codes
//  0 = Release   1 = Press    2 = CW   3 = CCW
//  4 = Pull      9 = Slider  10 = Touch start
// 11 = Touch end 14 = Tap

// ─── Helpers ──────────────────────────────────────────────────────────────────

function toDataUrl(url, callback) {
    var xhr = new XMLHttpRequest();
    xhr.onload = function() {
        var reader = new FileReader();
        reader.onloadend = function() { callback(reader.result); };
        reader.readAsDataURL(xhr.response);
    };
    xhr.open('GET', url);
    xhr.responseType = 'blob';
    xhr.send();
}

var POINTERS = {};
["push","pull","clockwise","counter-clockwise"].forEach(function(name) {
    toDataUrl(ASSET_IMAGE_PATH + name + ".svg", function(b64) {
        POINTERS[name.replace("-","")] = b64;
    });
});

var Sound = (function () {
    var df = document.createDocumentFragment();
    return function Sound(src) {
        var snd = new Audio(src);
        df.appendChild(snd);
        snd.addEventListener('ended', function() { df.removeChild(snd); });
        snd.play();
        return snd;
    };
}());

// ─── LiveDeck — Canvas 2D deck renderer ───────────────────────────────────────

class LiveDeck {

    constructor(canvas, config) {
        this.canvas   = canvas;
        this.ctx      = canvas.getContext('2d');
        this.config   = config;
        this.deckType = config['deck-type-flat'];
        this.name     = config.name;

        USER_PREFERENCES = Object.assign({}, DEFAULT_USER_PREFERENCES, config[PRESENTATION_DEFAULTS]);

        // Index button descriptors by name
        this.buttons = {};
        (this.deckType.buttons || []).forEach(btn => { this.buttons[btn.name] = btn; });

        // Received images (key → HTMLImageElement)
        this._images = {};

        // Background colour from deck type (fallback dark)
        this._bgColor = this.deckType.background?.color || '#1c1c1c';

        // Computed layout: key → {x, y, w, h}
        this._layout   = {};
        // Encoder hit zones for wheel events: [{name, x, y, w, h}, …]
        this._encZones = [];

        this._pressing       = null;
        this._sliding        = false;
        this._sliderDragging = null;

        this._computeLayout();
        this._setupEvents();
    }

    // ── Public API ─────────────────────────────────────────────────────────────

    set_key_image(key, base64jpeg) {
        const img = new Image();
        img.onload = () => {
            this._images[key] = img;
            this._blitButton(key);
        };
        img.src = 'data:image/jpeg;base64,' + base64jpeg;
    }

    /** Hardware background image is not used — just accept the colour hint. */
    set_background_image(imageUrl, fallbackColor) {
        if (fallbackColor && fallbackColor !== this._bgColor) {
            this._bgColor = fallbackColor;
            this._redrawAll();
        }
    }

    play_sound(sound, type) {
        Sound('data:audio/' + type + ';base64,' + sound);
    }

    // ── Layout computation ─────────────────────────────────────────────────────

    _computeLayout() {
        const allBtns = Object.values(this.buttons);

        // ── Classify ──────────────────────────────────────────────────────────
        const strips      = {};   // 'left' / 'right' → btn
        let   touchscreen = null;
        const gridBtns    = [];
        const encoders    = [];
        const ledBtns     = [];

        for (const btn of allBtns) {
            const acts = btn.actions  || [];
            const fbs  = btn.feedbacks || [];
            const isEnc   = acts.includes('encoder');
            const hasImg  = fbs.includes('image');
            const hasLed  = fbs.includes('colored-led');

            if (isEnc) {
                encoders.push(btn);
            } else if (btn.name === 'left' || btn.name === 'right') {
                strips[btn.name] = btn;
            } else if (btn.name === 'touchscreen') {
                touchscreen = btn;
            } else if (hasImg) {
                gridBtns.push(btn);
            } else if (hasLed || acts.includes('push')) {
                ledBtns.push(btn);
            }
        }

        const byIndex = (a, b) => (a.index || 0) - (b.index || 0);
        gridBtns.sort(byIndex);
        ledBtns.sort(byIndex);
        encoders.sort(byIndex);

        // ── Grid dimensions ───────────────────────────────────────────────────
        const hasDim = b => b.position != null;
        const uxSet  = new Set(gridBtns.filter(hasDim).map(b => b.position[0]));
        const uySet  = new Set(gridBtns.filter(hasDim).map(b => b.position[1]));
        const nCols  = uxSet.size  || Math.ceil(Math.sqrt(gridBtns.length)) || 1;
        const nRows  = uySet.size  || Math.ceil(gridBtns.length / nCols)   || 1;

        const tileW = gridBtns.length && Array.isArray(gridBtns[0].dimension)
            ? gridBtns[0].dimension[0] : 90;
        const tileH = gridBtns.length && Array.isArray(gridBtns[0].dimension)
            ? gridBtns[0].dimension[1] : 90;

        const gridW = nCols * tileW + (nCols - 1) * GAP;
        const gridH = nRows * tileH + (nRows - 1) * GAP;

        // ── Strip dimensions ──────────────────────────────────────────────────
        const stripDim = (name) => {
            const b = strips[name];
            return b && Array.isArray(b.dimension)
                ? { w: b.dimension[0], h: b.dimension[1] }
                : { w: 0, h: 0 };
        };
        const lsd = stripDim('left');
        const rsd = stripDim('right');

        // ── LED row dimensions ────────────────────────────────────────────────
        const ledDim = () => {
            if (!ledBtns.length) return 0;
            const b = ledBtns[0];
            return Array.isArray(b.dimension) ? b.dimension[0]
                 : typeof b.dimension === 'number' ? b.dimension * 2 : 48;
        };
        const ledSize = ledDim();
        const ledRowH = ledBtns.length ? ledSize : 0;

        // ── Touchscreen dimensions ────────────────────────────────────────────
        const tsW = touchscreen && Array.isArray(touchscreen.dimension) ? touchscreen.dimension[0] : 0;
        const tsH = touchscreen && Array.isArray(touchscreen.dimension) ? touchscreen.dimension[1] : 0;

        // ── Column widths ─────────────────────────────────────────────────────
        const leftColW  = lsd.w > 0 ? lsd.w + GAP : 0;
        const rightColW = rsd.w > 0 ? GAP + rsd.w : 0;

        // ── Canvas size ───────────────────────────────────────────────────────
        const centerH    = Math.max(gridH, lsd.h, rsd.h);
        const bottomRows = [tsH > 0 ? tsH + GAP : 0, ledRowH > 0 ? ledRowH + GAP : 0]
                               .reduce((s, v) => s + v, 0);

        const canvasW = PAD + leftColW + gridW + rightColW + PAD;
        const canvasH = PAD + centerH + bottomRows + PAD;

        // ── Place grid buttons ────────────────────────────────────────────────
        const sortedUX = [...uxSet].sort((a, b) => a - b);
        const sortedUY = [...uySet].sort((a, b) => a - b);
        const gridStartX = PAD + leftColW;
        const gridStartY = PAD + Math.round((centerH - gridH) / 2);

        gridBtns.forEach(btn => {
            let col, row;
            if (btn.position && sortedUX.length > 1) {
                col = sortedUX.indexOf(btn.position[0]);
                row = sortedUY.indexOf(btn.position[1]);
            } else {
                const idx = btn.index || 0;
                col = idx % nCols;
                row = Math.floor(idx / nCols);
            }
            this._layout[btn.name] = {
                x: gridStartX + col * (tileW + GAP),
                y: gridStartY + row * (tileH + GAP),
                w: tileW, h: tileH,
            };
        });

        // ── Place strips ──────────────────────────────────────────────────────
        if (strips['left']) {
            this._layout['left'] = {
                x: PAD,
                y: PAD + Math.round((centerH - lsd.h) / 2),
                w: lsd.w, h: lsd.h,
            };
        }
        if (strips['right']) {
            this._layout['right'] = {
                x: PAD + leftColW + gridW + GAP,
                y: PAD + Math.round((centerH - rsd.h) / 2),
                w: rsd.w, h: rsd.h,
            };
        }

        // ── Place touchscreen (below grid) ────────────────────────────────────
        let nextRowY = PAD + centerH + GAP;
        if (touchscreen) {
            this._layout['touchscreen'] = {
                x: PAD + leftColW,
                y: nextRowY,
                w: tsW, h: tsH,
            };
            // Mosaic sub-tiles: buttons whose names start with 'touchscreen'
            // but are not 'touchscreen' itself — keep their relative position
            // within the panel using hardware offset data.
            const subTiles = Object.values(this.buttons).filter(
                b => b.name !== 'touchscreen' && String(b.name).startsWith('touchscreen')
            );
            if (subTiles.length) {
                const hwMinX = Math.min(...subTiles.map(b => b.position?.[0] ?? 0));
                const hwMinY = Math.min(...subTiles.map(b => b.position?.[1] ?? 0));
                const tsLayout = this._layout['touchscreen'];
                subTiles.forEach(b => {
                    if (!b.position || !Array.isArray(b.dimension)) return;
                    this._layout[b.name] = {
                        x: tsLayout.x + (b.position[0] - hwMinX),
                        y: tsLayout.y + (b.position[1] - hwMinY),
                        w: b.dimension[0], h: b.dimension[1],
                    };
                });
            }
            nextRowY += tsH + GAP;
        }

        // ── Place LED / hardware buttons ──────────────────────────────────────
        if (ledBtns.length) {
            const ledTotalW = ledBtns.length * ledSize + (ledBtns.length - 1) * GAP;
            const ledStartX = Math.round((canvasW - ledTotalW) / 2);
            ledBtns.forEach((btn, i) => {
                this._layout[btn.name] = {
                    x: ledStartX + i * (ledSize + GAP),
                    y: nextRowY,
                    w: ledSize, h: ledSize,
                };
            });
        }

        // ── Encoder hit zones ─────────────────────────────────────────────────
        // Classify encoders into left / right / bottom groups via hardware x
        // relative to the hardware grid extent.
        const hwPositioned = gridBtns.filter(hasDim);
        const hwMinX = hwPositioned.length
            ? Math.min(...hwPositioned.map(b => b.position[0])) : 0;
        const hwMaxX = hwPositioned.length
            ? Math.max(...hwPositioned.map(b => b.position[0] + (b.dimension?.[0] || 0))) : 1;
        const hwMaxY = hwPositioned.length
            ? Math.max(...hwPositioned.map(b => b.position[1] + (b.dimension?.[1] || 0))) : 1;

        const leftEncs   = encoders.filter(e => e.position && e.position[0] <  hwMinX);
        const rightEncs  = encoders.filter(e => e.position && e.position[0] >= hwMaxX);
        const bottomEncs = encoders.filter(
            e => e.position && e.position[1] >= hwMaxY && !leftEncs.includes(e) && !rightEncs.includes(e)
        );

        const makeEncZones = (encs, baseRect) => {
            if (!encs.length || !baseRect) return;
            const zoneH = baseRect.h / encs.length;
            encs.forEach((enc, i) => {
                this._encZones.push({
                    name: enc.name,
                    x: baseRect.x, y: baseRect.y + i * zoneH,
                    w: baseRect.w, h: zoneH,
                });
            });
        };

        makeEncZones(leftEncs,  this._layout['left']);
        makeEncZones(rightEncs, this._layout['right']);

        // Bottom encoders (e.g. Stream Deck +): give each a square zone
        if (bottomEncs.length) {
            const encSize  = 60;
            const encTotalW = bottomEncs.length * encSize + (bottomEncs.length - 1) * GAP;
            const encStartX = Math.round((canvasW - encTotalW) / 2);
            const encY = nextRowY;
            bottomEncs.forEach((enc, i) => {
                this._encZones.push({
                    name: enc.name,
                    x: encStartX + i * (encSize + GAP), y: encY,
                    w: encSize, h: encSize,
                });
            });
        }

        this._canvasW = canvasW;
        this._canvasH = canvasH;
        this._applySize(canvasW, canvasH);
    }

    // ── Sizing ─────────────────────────────────────────────────────────────────

    _applySize(w, h) {
        const dpr = window.devicePixelRatio || 1;
        this.canvas.width = Math.round(w * dpr);
        this.canvas.height = Math.round(h * dpr);
        this.canvas.style.width = `${w}px`;
        this.canvas.style.height = `${h}px`;
        this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        if (typeof window.cockpitdecksSetDeckSize === 'function') {
            window.cockpitdecksSetDeckSize(w, h);
        }
        this._redrawAll();
    }

    // ── Drawing ────────────────────────────────────────────────────────────────

    _redrawAll() {
        const ctx = this.ctx;
        ctx.clearRect(0, 0, this._canvasW, this._canvasH);
        ctx.fillStyle = this._bgColor;
        ctx.fillRect(0, 0, this._canvasW, this._canvasH);
        for (const key of Object.keys(this._images)) {
            this._blitButton(key);
        }
    }

    _blitButton(key) {
        const img    = this._images[key];
        const layout = this._layout[key];
        if (!img || !layout) return;
        this.ctx.drawImage(img, layout.x, layout.y, layout.w, layout.h);
    }

    // ── Hit detection ──────────────────────────────────────────────────────────

    /** Pointer hit — matches strips, grid, LED; skips encoder zones. */
    _buttonAt(cx, cy) {
        for (const [key, r] of Object.entries(this._layout)) {
            if (cx >= r.x && cx <= r.x + r.w && cy >= r.y && cy <= r.y + r.h) {
                return this.buttons[key] || null;
            }
        }
        return null;
    }

    /** Wheel hit — matches encoder zones only. */
    _encoderAt(cx, cy) {
        for (const zone of this._encZones) {
            if (cx >= zone.x && cx <= zone.x + zone.w &&
                cy >= zone.y && cy <= zone.y + zone.h) {
                return this.buttons[zone.name] || null;
            }
        }
        return null;
    }

    _hasAction(btn, action) {
        return btn && Array.isArray(btn.actions) && btn.actions.includes(action);
    }

    _canvasXY(e) {
        const rect = this.canvas.getBoundingClientRect();
        const src = e.touches ? e.touches[0] : e;
        const sx = this._canvasW / rect.width;
        const sy = this._canvasH / rect.height;
        return [(src.clientX - rect.left) * sx, (src.clientY - rect.top) * sy];
    }

    _relPos(layout, cx, cy) {
        return [cx - layout.x, cy - layout.y];
    }

    // ── Slider value from pointer position ────────────────────────────────────

    _sliderValue(btn, layout, cx, cy) {
        const range = btn.range || [0, 100];
        const horiz = layout.w > layout.h;
        const pos   = horiz ? cx - layout.x : cy - layout.y;
        const span  = horiz ? layout.w : layout.h;
        let frac    = Math.max(0, Math.min(1, pos / span));
        if (!horiz) frac = 1 - frac;
        return range[0] + Math.round(frac * (range[1] - range[0]));
    }

    // ── Event wiring ───────────────────────────────────────────────────────────

    _setupEvents() {
        const canvas = this.canvas;

        // ── Pointer down ──────────────────────────────────────────────────────
        canvas.addEventListener('pointerdown', (e) => {
            e.preventDefault();
            const [cx, cy] = this._canvasXY(e);
            const btn    = this._buttonAt(cx, cy);
            if (!btn) return;
            const layout = this._layout[btn.name];

            this._pressing = btn;
            this._sliding  = false;

            if (this._hasAction(btn, 'push')) {
                canvas.style.cursor = 'pointer';
                sendEvent(this.name, btn.name, 1, {x: cx - layout.x, y: cy - layout.y, ts: Date.now()});

            } else if (this._hasAction(btn, 'swipe')) {
                canvas.style.cursor = 'grab';

            } else if (this._hasAction(btn, 'cursor')) {
                canvas.style.cursor = 'ns-resize';
                this._sliderDragging = { btn, layout };
                sendEvent(this.name, btn.name, 9, {x: cx, y: cy, value: this._sliderValue(btn, layout, cx, cy), ts: Date.now()});
            }
        }, { passive: false });

        // ── Pointer move ──────────────────────────────────────────────────────
        canvas.addEventListener('pointermove', (e) => {
            e.preventDefault();
            const [cx, cy] = this._canvasXY(e);

            if (this._sliderDragging) return;

            if (this._pressing && this._hasAction(this._pressing, 'swipe') && !this._sliding) {
                this._sliding = true;
                canvas.style.cursor = 'grabbing';
                const layout = this._layout[this._pressing.name];
                if (layout) {
                    const [rx, ry] = this._relPos(layout, cx, cy);
                    sendEvent(this.name, this._pressing.name, 10, {x: rx, y: ry, ts: Date.now()});
                }
            }

            if (!this._pressing) {
                const btn = this._buttonAt(cx, cy);
                if (btn) {
                    canvas.style.cursor = 'pointer';
                } else {
                    const enc = this._encoderAt(cx, cy);
                    canvas.style.cursor = enc ? `url('${POINTERS.clockwise}') 12 0, pointer` : 'auto';
                }
            }
        }, { passive: false });

        // ── Pointer up ────────────────────────────────────────────────────────
        canvas.addEventListener('pointerup', (e) => {
            e.preventDefault();
            const [cx, cy] = this._canvasXY(e);
            canvas.style.cursor = 'auto';

            if (this._sliderDragging) {
                const { btn, layout } = this._sliderDragging;
                sendEvent(this.name, btn.name, 9, {x: cx, y: cy, value: this._sliderValue(btn, layout, cx, cy), ts: Date.now()});
                this._sliderDragging = null;
                this._pressing = null;
                return;
            }

            const btn = this._pressing;
            this._pressing = null;
            if (!btn) return;

            const layout = this._layout[btn.name];

            if (this._hasAction(btn, 'push')) {
                sendEvent(this.name, btn.name, 0, {x: cx - (layout?.x || 0), y: cy - (layout?.y || 0), ts: Date.now()});

            } else if (this._hasAction(btn, 'swipe')) {
                if (layout) {
                    const [rx, ry] = this._relPos(layout, cx, cy);
                    sendEvent(this.name, btn.name, this._sliding ? 11 : 14, {x: rx, y: ry, ts: Date.now()});
                }
                this._sliding = false;
            }
        }, { passive: false });

        // ── Wheel (encoder rotation) ───────────────────────────────────────────
        canvas.addEventListener('wheel', (e) => {
            e.preventDefault();
            const [cx, cy] = this._canvasXY(e);
            const enc = this._encoderAt(cx, cy);
            if (!enc) return;
            const zone = this._encZones.find(z => z.name === enc.name);
            const step = 4;
            if (e.deltaY > step) {
                sendEvent(this.name, enc.name, 2, {x: cx - (zone?.x || 0), y: cy - (zone?.y || 0), ts: Date.now()});
            } else if (e.deltaY < -step) {
                sendEvent(this.name, enc.name, 3, {x: cx - (zone?.x || 0), y: cy - (zone?.y || 0), ts: Date.now()});
            }
        }, { passive: false });

        // ── Touch (mobile) ────────────────────────────────────────────────────
        canvas.addEventListener('touchstart', (e) => {
            e.preventDefault();
            const [cx, cy] = this._canvasXY(e);
            const btn = this._buttonAt(cx, cy);
            if (!btn) return;
            this._pressing = btn;
            this._sliding  = false;
            if (this._hasAction(btn, 'swipe')) {
                const layout = this._layout[btn.name];
                if (layout) {
                    const [rx, ry] = this._relPos(layout, cx, cy);
                    sendEvent(this.name, btn.name, 10, {x: rx, y: ry, ts: Date.now()});
                }
            }
        }, { passive: false });

        canvas.addEventListener('touchend', (e) => {
            e.preventDefault();
            const btn = this._pressing;
            this._pressing = null;
            if (!btn) return;
            const touch  = e.changedTouches[0];
            const rect   = canvas.getBoundingClientRect();
            const cx = (touch.clientX - rect.left) * canvas.width  / rect.width;
            const cy = (touch.clientY - rect.top)  * canvas.height / rect.height;
            const layout = this._layout[btn.name];
            if (!layout) return;
            const [rx, ry] = this._relPos(layout, cx, cy);
            if (this._hasAction(btn, 'swipe')) {
                sendEvent(this.name, btn.name, 11, {x: rx, y: ry, ts: Date.now()});
            } else if (this._hasAction(btn, 'push')) {
                sendEvent(this.name, btn.name, 14, {x: rx, y: ry, ts: Date.now()});
            }
        }, { passive: false });
    }
}
