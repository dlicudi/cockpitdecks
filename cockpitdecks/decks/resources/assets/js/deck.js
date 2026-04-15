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

const SWIPE_STEP             = 20   // px of movement between incremental swipe events during drag
const SWIPE_MIN              = 10   // px minimum remaining movement to send a final swipe on pointerup
const SWIPE_EDGE_FRACTION    = 0.25 // top/bottom fraction of button that triggers hold-to-repeat
const SWIPE_REPEAT_DELAY_MS  = 400  // ms before auto-repeat starts when holding an edge
const SWIPE_REPEAT_PERIOD_MS = 150  // ms between repeated commands while holding

const DEFAULT_USER_PREFERENCES = {
    highlight: "#ffffff10",
    flash:     "#0f80ffb0",
    flash_duration: 100,
    click_sound:  true,
    click_volume: 0.15
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

// Lazy AudioContext — created on first user gesture to satisfy browser autoplay policy.
// On iOS Safari the context can be suspended after the page loses focus; resume it each time.
var _audioCtx = null;
function _getAudioCtx() {
    if (!_audioCtx) {
        _audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    }
    if (_audioCtx.state === 'suspended') {
        _audioCtx.resume();
    }
    return _audioCtx;
}

// ─── LiveDeck — Canvas 2D deck renderer ───────────────────────────────────────

class LiveDeck {

    constructor(canvas, config) {
        this.canvas   = canvas;
        this.ctx      = canvas.getContext('2d');
        this.config   = config;
        this.deckType = config['deck-type-flat'];
        this.name     = config.name;

        // Prevent iOS Safari text-selection, magnifier and scrolling gestures from cancelling pointers
        this.canvas.style.touchAction = 'none';
        this.canvas.style.userSelect = 'none';
        this.canvas.style.webkitUserSelect = 'none';
        this.canvas.style.webkitTouchCallout = 'none';

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

        // Client-side slider state
        this._sliderMeta     = {};   // key → {fill, track, orientation, label}
        this._sliderFrac     = {};   // key → current fraction 0..1
        this._sliderLastSend = {};   // key → timestamp of last WebSocket send

        // Server-flagged swipe buttons: keys whose activation type is 'swipe'.
        // Used to prefer swipe mode over push when a button has both actions (e.g. iphone deck type).
        this._swipeMeta      = {};   // key → true

        // Server-flagged scroll buttons: keys whose activation type is 'sweep'.
        // Grid buttons with sweep activation respond to mouse wheel events.
        this._scrollMeta     = {};   // key → true

        this._computeLayout();
        this._setupEvents();
    }

    // ── Public API ─────────────────────────────────────────────────────────────

    set_key_image(key, base64jpeg, meta) {
        // Store slider metadata so the client can render fill/handle locally.
        if (meta && meta.slider) {
            this._sliderMeta[key] = meta.slider;
            if (meta.slider.fraction !== undefined && !(key in this._sliderFrac)) {
                this._sliderFrac[key] = meta.slider.fraction;
            }
        }
        // Track server-flagged swipe buttons so pointerdown prefers swipe over push.
        if (meta && meta.swipe) {
            this._swipeMeta[key] = true;
        }
        // Track server-flagged scroll buttons so wheel events reach grid buttons.
        if (meta && meta.scroll) {
            this._scrollMeta[key] = true;
        }
        // When a server image arrives during/after drag, sync fraction from X-Plane truth.
        if (meta && meta.slider && meta.slider.fraction !== undefined && !this._sliderDragging) {
            this._sliderFrac[key] = meta.slider.fraction;
        }
        const img = new Image();
        img.onload = () => {
            this._images[key] = img;
            this._blitButton(key);
        };
        img.src = 'data:image/jpeg;base64,' + base64jpeg;
    }

    clear_images() {
        this._images     = {};
        this._sliderMeta = {};
        this._sliderFrac = {};
        this._swipeMeta  = {};
        this._scrollMeta = {};
        // Reset any span mutations so buttons that shrink back to 1×1 on the
        // new page aren't drawn at the previous page's larger dimensions.
        for (const [key, base] of Object.entries(this._baseLayout)) {
            if (this._layout[key]) {
                this._layout[key].w = base.w;
                this._layout[key].h = base.h;
            }
        }
        this._redrawAll();
    }

    set_key_span(key, span) {
        const layout = this._layout[key];
        if (!layout || !Array.isArray(span) || span.length !== 2) return;
        const [sw, sh] = span;
        const tileW = this._tileW || 90;
        const tileH = this._tileH || 90;
        layout.w = sw * tileW + (sw - 1) * GAP;
        layout.h = sh * tileH + (sh - 1) * GAP;
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

    _playClick() {
        if (!USER_PREFERENCES.click_sound) return;
        try {
            const ctx  = _getAudioCtx();
            const gain = ctx.createGain();
            const osc  = ctx.createOscillator();
            osc.type = 'sine';
            osc.frequency.setValueAtTime(1200, ctx.currentTime);
            osc.frequency.exponentialRampToValueAtTime(400, ctx.currentTime + 0.03);
            gain.gain.setValueAtTime(USER_PREFERENCES.click_volume, ctx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.04);
            osc.connect(gain);
            gain.connect(ctx.destination);
            osc.start();
            osc.stop(ctx.currentTime + 0.04);
        } catch (_) {}
    }

    _playMicroClick() {
        if (!USER_PREFERENCES.click_sound) return;
        try {
            const ctx  = _getAudioCtx();
            const gain = ctx.createGain();
            const osc  = ctx.createOscillator();
            osc.type = 'sine';
            osc.frequency.setValueAtTime(2000, ctx.currentTime);
            osc.frequency.exponentialRampToValueAtTime(800, ctx.currentTime + 0.015);
            gain.gain.setValueAtTime(USER_PREFERENCES.click_volume * 0.5, ctx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.02);
            osc.connect(gain);
            gain.connect(ctx.destination);
            osc.start();
            osc.stop(ctx.currentTime + 0.02);
        } catch (_) {}
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
        this._tileW = tileW;
        this._tileH = tileH;

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
            const btnW = Array.isArray(btn.dimension) ? btn.dimension[0] : tileW;
            const btnH = Array.isArray(btn.dimension) ? btn.dimension[1] : tileH;
            this._layout[btn.name] = {
                x: gridStartX + col * (tileW + GAP),
                y: gridStartY + row * (tileH + GAP),
                w: btnW, h: btnH,
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

        // Snapshot original w/h so clear_images() can reset span mutations.
        this._baseLayout = {};
        for (const [key, r] of Object.entries(this._layout)) {
            this._baseLayout[key] = { w: r.w, h: r.h };
        }

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
        if (!layout) return;
        if (img) this.ctx.drawImage(img, layout.x, layout.y, layout.w, layout.h);
        if (this._sliderMeta[key]) this._drawSliderOverlay(key, layout);
    }

    // ── Client-side slider overlay ─────────────────────────────────────────────

    _drawSliderOverlay(key, layout) {
        const meta = this._sliderMeta[key];
        if (!meta) return;
        const frac = Math.max(0, Math.min(1, this._sliderFrac[key] ?? 0));
        const ctx  = this.ctx;
        const {x, y, w, h} = layout;

        const horiz = meta.orientation === 'horizontal';
        const r = 8;

        if (!horiz) {
            // ── Vertical ──────────────────────────────────────────────────────
            const margin = Math.round(w * 0.18);
            const pad    = Math.round(h * 0.02);
            const tx0 = x + margin;
            const tx1 = x + w - margin;
            const ty0 = y + pad;
            const ty1 = y + h - pad;
            const trackH = ty1 - ty0;
            const fillH  = Math.round(trackH * frac);

            // Fill (bottom-up)
            if (fillH > 0) {
                ctx.fillStyle = meta.fill || 'rgba(0,180,255,1)';
                ctx.beginPath();
                const fr = Math.min(r, fillH / 2);
                if (ctx.roundRect) {
                    ctx.roundRect(tx0, ty1 - fillH, tx1 - tx0, fillH, fr);
                } else {
                    ctx.rect(tx0, ty1 - fillH, tx1 - tx0, fillH);
                }
                ctx.fill();
            }

            // Handle bar
            const hy = Math.max(ty0 + 4, Math.min(ty1 - 4, ty1 - fillH));
            ctx.fillStyle = 'rgba(255,255,255,0.92)';
            ctx.beginPath();
            if (ctx.roundRect) {
                ctx.roundRect(tx0 + 4, hy - 3, tx1 - tx0 - 8, 6, 3);
            } else {
                ctx.rect(tx0 + 4, hy - 3, tx1 - tx0 - 8, 6);
            }
            ctx.fill();

            // Value text — fixed at top
            const fontSize = Math.max(12, Math.round(h * 0.08));
            ctx.fillStyle = 'white';
            ctx.font = `bold ${fontSize}px sans-serif`;
            ctx.textAlign = 'center';
            ctx.textBaseline = 'top';
            ctx.fillText(Math.round(frac * 100) + '%', x + w / 2, ty0 + 4);

        } else {
            // ── Horizontal ────────────────────────────────────────────────────
            const pad  = Math.round(w * 0.02);
            const midY = y + h / 2;
            const barH = Math.round(h * 0.24);
            const tx0  = x + pad;
            const tx1  = x + w - pad;
            const ty0  = midY - barH / 2;
            const trackW = tx1 - tx0;
            const fillW  = Math.round(trackW * frac);

            if (fillW > 0) {
                ctx.fillStyle = meta.fill || 'rgba(0,180,255,1)';
                ctx.beginPath();
                const fr = Math.min(r, fillW / 2);
                if (ctx.roundRect) {
                    ctx.roundRect(tx0, ty0, fillW, barH, fr);
                } else {
                    ctx.rect(tx0, ty0, fillW, barH);
                }
                ctx.fill();
            }

            const hx = Math.max(tx0 + 4, Math.min(tx1 - 4, tx0 + fillW));
            ctx.fillStyle = 'rgba(255,255,255,0.92)';
            ctx.beginPath();
            if (ctx.roundRect) {
                ctx.roundRect(hx - 3, ty0 + 4, 6, barH - 8, 3);
            } else {
                ctx.rect(hx - 3, ty0 + 4, 6, barH - 8);
            }
            ctx.fill();

            const fontSize = Math.max(10, Math.round(h * 0.22));
            ctx.fillStyle = 'white';
            ctx.font = `bold ${fontSize}px sans-serif`;
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillText(Math.round(frac * 100) + '%', tx1 - 8, midY);
        }
    }

    // Returns 0..1 fraction from a pointer position within a button layout.
    _sliderFracFromXY(layout, cx, cy) {
        const horiz = layout.w > layout.h;
        const pos   = horiz ? cx - layout.x : cy - layout.y;
        const span  = horiz ? layout.w : layout.h;
        let frac    = Math.max(0, Math.min(1, pos / span));
        if (!horiz) frac = 1 - frac;
        return frac;
    }

    // Throttle & trailing debounce — max 10 updates per second, ensures final value sent
    _sendSliderThrottled(btnName, rawValue) {
        const now = Date.now();
        const limit = 75; // 75ms limit

        if (!this._sliderDebounceTimers) this._sliderDebounceTimers = {};
        
        if (now - (this._sliderLastSend[btnName] || 0) >= limit) {
            this._sliderLastSend[btnName] = now;
            sendEvent(this.name, btnName, 9, {value: rawValue, ts: now});
        }
        
        if (this._sliderDebounceTimers[btnName]) {
            clearTimeout(this._sliderDebounceTimers[btnName]);
        }
        this._sliderDebounceTimers[btnName] = setTimeout(() => {
            this._sliderLastSend[btnName] = Date.now();
            sendEvent(this.name, btnName, 9, {value: rawValue, ts: Date.now()});
        }, limit);
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
        return range[0] + frac * (range[1] - range[0]);
    }

    // ── Swipe hold-to-repeat ──────────────────────────────────────────────────

    // Returns -1 (top/up edge), +1 (bottom/down edge), or 0 (middle) for a
    // relative position within a swipe button's layout rect.
    _swipeEdgeZone(layout, rx, ry) {
        const edgeH = layout.h * SWIPE_EDGE_FRACTION;
        if (ry <= edgeH)             return -1;  // top → up
        if (ry >= layout.h - edgeH)  return  1;  // bottom → down
        return 0;
    }

    // Sends a synthetic code-10 + code-11 pair representing one step in the
    // given direction (-1=up, +1=down) so Python's Swipe.activate fires normally.
    _fireSwipeStep(btnName, direction) {
        const sy = direction === -1 ? SWIPE_STEP : 0;
        const ey = direction === -1 ? 0 : SWIPE_STEP;
        this._playMicroClick();
        sendEvent(this.name, btnName, 10, {x: 0, y: sy, ts: Date.now()});
        sendEvent(this.name, btnName, 11, {x: 0, y: ey, ts: Date.now()});
    }

    _startSwipeRepeat(btnName, direction) {
        this._stopSwipeRepeat();
        this._swipeRepeatInitTimer = setTimeout(() => {
            this._fireSwipeStep(btnName, direction);
            this._swipeRepeatTimer = setInterval(
                () => this._fireSwipeStep(btnName, direction),
                SWIPE_REPEAT_PERIOD_MS
            );
        }, SWIPE_REPEAT_DELAY_MS);
    }

    _stopSwipeRepeat() {
        if (this._swipeRepeatInitTimer) {
            clearTimeout(this._swipeRepeatInitTimer);
            this._swipeRepeatInitTimer = null;
        }
        if (this._swipeRepeatTimer) {
            clearInterval(this._swipeRepeatTimer);
            this._swipeRepeatTimer = null;
        }
    }

    // ── Event wiring ───────────────────────────────────────────────────────────

    _setupEvents() {
        const canvas = this.canvas;

        // ── Pointer down ──────────────────────────────────────────────────────
        canvas.addEventListener('pointerdown', (e) => {
            e.preventDefault();
            
            // Reject secondary multitouch points while an interaction is ongoing
            if (this._activePointerId !== null && this._activePointerId !== undefined) return;

            const [cx, cy] = this._canvasXY(e);
            const btn    = this._buttonAt(cx, cy);
            if (!btn) return;

            this._activePointerId = e.pointerId;
            if (e.pointerId !== undefined) {
                canvas.setPointerCapture(e.pointerId);
            }

            const layout = this._layout[btn.name];

            this._pressing    = btn;
            this._sliding     = false;
            this._swipeAnchor = null;

            this._playClick();

            // Check slider meta first: if this button is currently rendering a slider,
            // treat it as a cursor interaction regardless of deck-type action order.
            // This lets buttons that declare both 'cursor' and 'push' work correctly —
            // push on non-slider pages, cursor on slider pages — without ambiguity.
            if (this._sliderMeta[btn.name] || (!this._hasAction(btn, 'push') && !this._hasAction(btn, 'swipe') && this._hasAction(btn, 'cursor'))) {
                canvas.style.cursor = layout.w > layout.h ? 'ew-resize' : 'ns-resize';
                this._sliderDragging = { btn, layout };
                const frac = this._sliderFracFromXY(layout, cx, cy);
                this._sliderFrac[btn.name] = frac;
                this._blitButton(btn.name);
                this._sendSliderThrottled(btn.name, this._sliderValue(btn, layout, cx, cy));

            } else if (this._swipeMeta[btn.name] || (!this._hasAction(btn, 'push') && this._hasAction(btn, 'swipe'))) {
                // Server flagged this button as a swipe activation, or it has swipe but not push.
                // Must be checked before the push branch so iphone-style decks (which give all
                // buttons push+swipe) still enter swipe mode when the page config says swipe.
                canvas.style.cursor = 'grab';
                if (layout) {
                    const [rx, ry] = this._relPos(layout, cx, cy);
                    const zone = this._swipeEdgeZone(layout, rx, ry);
                    if (zone !== 0) this._startSwipeRepeat(btn.name, zone);
                }

            } else if (this._hasAction(btn, 'push')) {
                canvas.style.cursor = 'pointer';
                sendEvent(this.name, btn.name, 1, {x: cx - layout.x, y: cy - layout.y, ts: Date.now()});
            }
        }, { passive: false });

        // ── Pointer move ──────────────────────────────────────────────────────
        canvas.addEventListener('pointermove', (e) => {
            e.preventDefault();
            if (this._activePointerId !== undefined && e.pointerId !== this._activePointerId) return;

            const [cx, cy] = this._canvasXY(e);

            if (this._sliderDragging) {
                const { btn, layout } = this._sliderDragging;
                const frac = this._sliderFracFromXY(layout, cx, cy);
                this._sliderFrac[btn.name] = frac;
                this._blitButton(btn.name);
                this._sendSliderThrottled(btn.name, this._sliderValue(btn, layout, cx, cy));
                return;
            }

            if (this._pressing && this._hasAction(this._pressing, 'swipe')) {
                const layout = this._layout[this._pressing.name];
                if (layout) {
                    const [rx, ry] = this._relPos(layout, cx, cy);
                    if (!this._sliding) {
                        // First move — enter sliding mode, cancel any hold-to-repeat timer
                        this._stopSwipeRepeat();
                        this._sliding     = true;
                        this._swipeAnchor = {x: rx, y: ry};
                        canvas.style.cursor = 'grabbing';
                    } else if (this._swipeAnchor) {
                        // Subsequent moves — fire incremental swipe when far enough from anchor
                        const dx   = rx - this._swipeAnchor.x;
                        const dy   = ry - this._swipeAnchor.y;
                        const dist = Math.sqrt(dx * dx + dy * dy);
                        if (dist >= SWIPE_STEP) {
                            this._playMicroClick();
                            sendEvent(this.name, this._pressing.name, 10, {x: this._swipeAnchor.x, y: this._swipeAnchor.y, ts: Date.now()});
                            sendEvent(this.name, this._pressing.name, 11, {x: rx, y: ry, ts: Date.now()});
                            this._swipeAnchor = {x: rx, y: ry};
                        }
                    }
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

        // ── Pointer up & cancel ───────────────────────────────────────────────
        const handlePointerUp = (e) => {
            if (e.cancelable && e.type !== 'pointercancel') e.preventDefault();
            if (this._activePointerId !== undefined && this._activePointerId !== null && e.pointerId !== this._activePointerId) return;

            if (e.pointerId !== undefined && canvas.hasPointerCapture(e.pointerId)) {
                canvas.releasePointerCapture(e.pointerId);
            }
            
            this._activePointerId = null;
            const [cx, cy] = this._canvasXY(e);
            canvas.style.cursor = 'auto';

            if (this._sliderDragging) {
                const { btn, layout } = this._sliderDragging;
                const frac = this._sliderFracFromXY(layout, cx, cy);
                this._sliderFrac[btn.name] = frac;
                this._blitButton(btn.name);
                
                if (this._sliderDebounceTimers && this._sliderDebounceTimers[btn.name]) {
                    clearTimeout(this._sliderDebounceTimers[btn.name]);
                }
                sendEvent(this.name, btn.name, 9, {value: this._sliderValue(btn, layout, cx, cy), ts: Date.now()});
                this._sliderDragging = null;
                this._pressing = null;
                return;
            }

            const btn = this._pressing;
            this._pressing = null;
            if (!btn) return;

            const layout = this._layout[btn.name];

            this._stopSwipeRepeat();

            // If a swipe gesture was in progress, send a final incremental event for
            // any remaining movement since the last committed anchor position.
            if (this._sliding && this._hasAction(btn, 'swipe')) {
                if (layout && this._swipeAnchor) {
                    const [rx, ry] = this._relPos(layout, cx, cy);
                    const dx   = rx - this._swipeAnchor.x;
                    const dy   = ry - this._swipeAnchor.y;
                    const dist = Math.sqrt(dx * dx + dy * dy);
                    if (dist >= SWIPE_MIN) {
                        sendEvent(this.name, btn.name, 10, {x: this._swipeAnchor.x, y: this._swipeAnchor.y, ts: Date.now()});
                        sendEvent(this.name, btn.name, 11, {x: rx, y: ry, ts: Date.now()});
                    }
                }
                this._swipeAnchor = null;
                this._sliding = false;

            } else if (this._hasAction(btn, 'swipe')) {
                // If it supports swipe but we didn't slide, and it DOES NOT support push, send a generic press (code 14)
                if (!this._hasAction(btn, 'push')) {
                    if (layout) {
                        const [rx, ry] = this._relPos(layout, cx, cy);
                        sendEvent(this.name, btn.name, 14, {x: rx, y: ry, ts: Date.now()});
                    }
                }
                this._sliding = false;
            }

            // Release push only if the button was actually activated as a push (not swipe mode).
            if (this._hasAction(btn, 'push') && !this._swipeMeta[btn.name]) {
                sendEvent(this.name, btn.name, 0, {x: cx - (layout?.x || 0), y: cy - (layout?.y || 0), ts: Date.now()});
            }
        };

        canvas.addEventListener('pointerup', handlePointerUp, { passive: false });
        canvas.addEventListener('pointercancel', handlePointerUp, { passive: false });
        // Note: pointerout is intentionally NOT used as a release handler. With
        // setPointerCapture active, pointerup fires on the canvas even when the
        // pointer is outside its bounds, so pointerout is not needed as a fallback.
        // Registering pointerout as handlePointerUp caused a double-release bug:
        // it fired (and released capture) while the finger was still held after an
        // accidental drag, so the subsequent pointerup never reached the canvas and
        // the endCommand for begin-end-command buttons was silently dropped.

        // ── Wheel (encoder rotation) ───────────────────────────────────────────
        canvas.addEventListener('wheel', (e) => {
            e.preventDefault();
            const [cx, cy] = this._canvasXY(e);
            const step = 4;
            const enc = this._encoderAt(cx, cy);
            if (enc) {
                const zone = this._encZones.find(z => z.name === enc.name);
                this._playClick();
                if (e.deltaY > step) {
                    sendEvent(this.name, enc.name, 2, {x: cx - (zone?.x || 0), y: cy - (zone?.y || 0), ts: Date.now()});
                } else if (e.deltaY < -step) {
                    sendEvent(this.name, enc.name, 3, {x: cx - (zone?.x || 0), y: cy - (zone?.y || 0), ts: Date.now()});
                }
                return;
            }
            // Grid buttons with sweep activation also respond to scroll.
            // Scroll up (deltaY < 0) = forward = clockwise (2); scroll down = backward (3).
            const btn = this._buttonAt(cx, cy);
            if (!btn || !this._scrollMeta[btn.name]) return;
            const layout = this._layout[btn.name] || {};
            this._playClick();
            if (e.deltaY < -step) {
                sendEvent(this.name, btn.name, 2, {x: cx - (layout.x || 0), y: cy - (layout.y || 0), ts: Date.now()});
            } else if (e.deltaY > step) {
                sendEvent(this.name, btn.name, 3, {x: cx - (layout.x || 0), y: cy - (layout.y || 0), ts: Date.now()});
            }
        }, { passive: false });

    }
}
