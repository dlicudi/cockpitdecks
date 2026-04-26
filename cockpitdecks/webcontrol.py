import logging
import os
import platform
import threading
import time
from collections import deque

try:
    import resource
except ImportError:  # pragma: no cover - not available on Windows
    resource = None

from flask import jsonify, render_template_string, request

from cockpitdecks import __version__
from cockpitdecks.aircraft import Aircraft
from cockpitdecks.constant import CONFIG_FOLDER


LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
LOG_LEVEL_ORDER = {name: index for index, name in enumerate(LOG_LEVELS)}
_metrics_prev_wall: float | None = None
_metrics_prev_cpu: float | None = None


class RecentLogHandler(logging.Handler):
    def __init__(self, maxlen: int = 400):
        super().__init__()
        self.recent_logs: deque[dict[str, str]] = deque(maxlen=maxlen)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.recent_logs.append(
                {
                    "level": record.levelname.upper(),
                    "text": self.format(record),
                }
            )
        except Exception:
            pass


def install_recent_log_handler(format_string: str) -> RecentLogHandler:
    handler = RecentLogHandler()
    handler.setFormatter(logging.Formatter(format_string))
    logging.getLogger().addHandler(handler)
    return handler


CONTROL_TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Cockpitdecks Control</title>
  <style>
    :root {
      --bg: #f7f7f7;
      --panel: #ffffff;
      --line: #d8d8d8;
      --nav: #ffffff;
      --nav-badge: #f1f1f1;
      --tab: #efefef;
      --tab-active: #ffffff;
      --primary: #1f5fd1;
      --success-bg: #f2fff5;
      --success-line: #bde7c8;
      --text: #1b1b1b;
      --muted: #666666;
      --shadow: none;
    }
    * { box-sizing: border-box; }
    body { font-family: Verdana, Geneva, sans-serif; margin: 0; background: var(--bg); color: var(--text); line-height: 1.3; font-size: 12px; }
    .shell { max-width: 1280px; margin: 0 auto; border-left: 1px solid var(--line); border-right: 1px solid var(--line); background: #fafafa; }
    .hero { background: var(--nav); color: var(--text); padding: 0.75rem 0.9rem; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--line); }
    .hero-title { font-size: 1.2rem; font-weight: 700; letter-spacing: 0; }
    .hero-meta { display: flex; gap: 0.75rem; align-items: center; }
    .hero-badge, .poll-badge { background: var(--nav-badge); padding: 0.15rem 0.35rem; border: 1px solid var(--line); border-radius: 0; color: #555; font-size: 0.8rem; }
    .toolbar { background: #fbfbfb; border-bottom: 1px solid var(--line); padding: 0.5rem 0.9rem; }
    .toolbtn { padding: 0.38rem 0.7rem; border-radius: 0; border: 1px solid #c8c8c8; background: #fff; font-size: 0.82rem; font-weight: 700; cursor: pointer; box-shadow: none; }
    .toolbtn.primary { background: #f5f8ff; color: var(--primary); border-color: #b8c8ec; }
    .tabs { display: flex; gap: 0; padding: 0 0.9rem; border-bottom: 1px solid #c6c6c6; background: #efefef; }
    .tab { padding: 0.44rem 0.72rem; border: 1px solid #c6c6c6; border-bottom: 0; border-radius: 0; margin: 0.35rem 0.15rem 0 0; text-decoration: none; color: #222; background: var(--tab); font-size: 0.82rem; }
    .tab.active { background: var(--tab-active); position: relative; top: 1px; }
    .content { padding: 0.8rem 0.9rem 1rem; }
    .msg { padding: 0.5rem 0.65rem; border-radius: 0; background: var(--success-bg); border: 1px solid var(--success-line); margin-bottom: 0.7rem; color: #1f6b32; font-weight: 700; font-size: 0.84rem; }
    .readybar { padding: 0.5rem 0.65rem; border-radius: 0; background: #f5f5f5; border: 1px solid var(--line); margin-bottom: 0.8rem; color: #333; font-weight: 700; font-size: 0.84rem; }
    .readybar.running { background: var(--success-bg); border-color: var(--success-line); color: #1f6b32; }
    .readybar.failed { background: #fff1f1; border-color: #f0b4b4; color: #9b1c1c; }
    .cards { display: grid; grid-template-columns: 1.4fr 0.9fr; gap: 1rem; }
    .card { background: var(--panel); border-radius: 0; padding: 0.75rem 0.8rem; border: 1px solid var(--line); box-shadow: var(--shadow); }
    .card h2 { margin: 0 0 0.65rem; font-size: 0.96rem; }
    .status-row { margin: 0.6rem 0; }
    .status-label { font-weight: 700; font-size: 0.78rem; color: #555; margin-bottom: 0.18rem; }
    .status-value { padding: 0.28rem 0.42rem; border: 1px solid #e2e2e2; background: #fff; font-size: 0.76rem; }
    .status-good { color: #0a8754; }
    .muted { color: var(--muted); }
    .mini-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0.8rem; margin-top: 0.8rem; }
    .mini { text-align: center; padding-top: 0.2rem; }
    .mini-value { font-size: 1rem; font-weight: 700; line-height: 1; margin-bottom: 0.2rem; color: #222; }
    .mini-label { color: #666; font-weight: 700; font-size: 0.76rem; }
    code { background: #f1f1f1; padding: 0.05rem 0.2rem; border-radius: 0; }
    form { margin: 0; }
    label { display: block; font-weight: 700; margin-top: 0.8rem; color: #444; font-size: 0.78rem; }
    input, textarea, select { width: 100%; padding: 0.42rem 0.55rem; margin-top: 0.2rem; border-radius: 0; border: 1px solid #cfcfcf; background: #fff; font-size: 0.78rem; }
    textarea { min-height: 7rem; font-family: ui-monospace, SFMono-Regular, monospace; }
    .row { display: grid; grid-template-columns: minmax(0, 1fr) 220px; gap: 1rem; align-items: end; }
    .actions { display: flex; gap: 0.6rem; flex-wrap: wrap; margin-top: 0.9rem; }
    .panel { display: none; }
    .panel.active { display: block; }
    .logbox { background: #0d1117; color: #e8e8e8; padding: 0.7rem; border-radius: 0; overflow: auto; border: 1px solid #1e2632; height: 60vh; max-height: 60vh; }
    .logline { font-family: ui-monospace, SFMono-Regular, monospace; font-size: 0.68rem; line-height: 1.18; white-space: pre-wrap; padding: 0.08rem 0; border-bottom: 1px solid rgba(255,255,255,0.04); }
    .logline:last-child { border-bottom: 0; }
    .log-debug { color: #93c5fd; }
    .log-info { color: #7ec3ff; }
    .log-warning { color: #fcd34d; }
    .log-error { color: #fca5a5; }
    .log-critical { color: #fda4af; font-weight: 700; }
    .form-note { margin-top: 0.7rem; }
    .log-toolbar { display: flex; gap: 0.45rem; align-items: center; flex-wrap: wrap; margin-bottom: 0.7rem; }
    .log-toolbar select { padding: 0.32rem 0.45rem; border-radius: 0; border: 1px solid #cfcfcf; background: #fff; font-size: 0.78rem; }
    @media (max-width: 980px) {
      .cards { grid-template-columns: 1fr; }
      .row { grid-template-columns: 1fr; }
      .hero { flex-direction: column; align-items: flex-start; gap: 0.7rem; }
    }
  </style>
</head>
<body>
  <div class="shell">
    <header class="hero">
      <div class="hero-meta">
        <div class="hero-title">Cockpitdecks</div>
        <div class="hero-badge">v{{ version }}</div>
      </div>
      <div class="poll-badge">Runtime config {{ config_path }}</div>
    </header>
    <div class="toolbar"></div>
    <div class="tabs">
      <a class="tab {% if active_tab == 'status' %}active{% endif %}" href="/control?tab=status">Status</a>
      <a class="tab {% if active_tab == 'control' %}active{% endif %}" href="/control?tab=control">Config</a>
      <a class="tab {% if active_tab == 'logs' %}active{% endif %}" href="/control?tab=logs">Logs</a>
    </div>
    <main class="content">
      {% if message %}
      <div class="msg">{{ message }}</div>
      {% endif %}
      <div class="readybar {{ runtime_status }}">{{ runtime_message or runtime_status|title }}</div>
      <section class="panel {% if active_tab == 'status' %}active{% endif %}">
        <div class="cards">
          <div class="card">
            <h2>Connectivity</h2>
            <div class="status-row">
              <div class="status-label">X-Plane API</div>
              <div class="status-value">{{ current_api_host }}:{{ current_api_port }}</div>
            </div>
            <div class="status-row">
              <div class="status-label">Cockpitdecks Server</div>
              <div class="status-value status-good">{{ current_server_host }}:{{ current_server_port }}</div>
            </div>
            <div class="status-row">
              <div class="status-label">Aircraft</div>
              <div class="status-value">{{ current_aircraft_path or "none" }}</div>
            </div>
            <div class="status-row">
              <div class="status-label">Deck Search Roots</div>
              <div class="status-value">{{ current_deck_paths or "none" }}</div>
            </div>
          </div>
          <div class="card">
            <h2>Runtime</h2>
            <div class="status-row">
              <div class="status-label">Mode</div>
              <div class="status-value">{{ mode_name or "unknown" }}</div>
            </div>
            <div class="status-row">
              <div class="status-label">Simulator</div>
              <div class="status-value">{{ simulator_name or "unknown" }}</div>
            </div>
            <div class="status-row">
              <div class="status-label">Config File</div>
              <div class="status-value">{{ config_path }}</div>
            </div>
            <div class="mini-grid">
              <div class="mini">
                <div class="mini-value">{{ deck_root_count }}</div>
                <div class="mini-label">Deck Roots</div>
              </div>
              <div class="mini">
                <div class="mini-value">{{ recent_log_count }}</div>
                <div class="mini-label">Recent Logs</div>
              </div>
            </div>
          </div>
        </div>
      </section>
      <section class="panel {% if active_tab == 'control' %}active{% endif %}">
        <div class="card">
          <h2>Configuration</h2>
          <form method="post">
            <input type="hidden" name="tab" value="control">
            <label for="target">Target aircraft path</label>
            <input id="target" name="target" type="text" value="{{ target or '' }}" placeholder="/path/to/aircraft">
            <label for="deck_paths">Deck search roots</label>
            <textarea id="deck_paths" name="deck_paths" placeholder="/path/one&#10;/path/two">{{ deck_paths_text }}</textarea>
            <div class="row">
              <div>
                <label for="xplane_api_host">X-Plane API host</label>
                <input id="xplane_api_host" name="xplane_api_host" type="text" value="{{ xplane_api_host }}">
              </div>
              <div>
                <label for="xplane_api_port">X-Plane API port</label>
                <input id="xplane_api_port" name="xplane_api_port" type="number" value="{{ xplane_api_port }}">
              </div>
            </div>
            <div class="row">
              <div>
                <label for="cockpitdecks_server_host">Cockpitdecks server host</label>
                <input id="cockpitdecks_server_host" name="cockpitdecks_server_host" type="text" value="{{ cockpitdecks_server_host }}">
              </div>
              <div>
                <label for="cockpitdecks_server_port">Cockpitdecks server port</label>
                <input id="cockpitdecks_server_port" name="cockpitdecks_server_port" type="number" value="{{ cockpitdecks_server_port }}">
              </div>
            </div>
            <div class="actions">
              <button class="toolbtn primary" type="submit" name="action" value="reload">Reload decks</button>
              <button class="toolbtn" type="submit" name="action" value="save">Save config</button>
              <button class="toolbtn" type="submit" name="action" value="apply_target">Apply target now</button>
            </div>
            <p class="muted form-note">Changing host/port values updates <code>config.yaml</code>. It does not rebind the current process; restart is required for those fields to take effect.</p>
          </form>
        </div>
      </section>
      <section class="panel {% if active_tab == 'logs' %}active{% endif %}">
        <div class="card">
          <form method="post" class="log-toolbar">
            <input type="hidden" name="tab" value="logs">
            <select id="log_level" name="log_level">
              {% for level in log_levels %}
              <option value="{{ level }}" {% if level == selected_log_level %}selected{% endif %}>{{ level }}</option>
              {% endfor %}
            </select>
            <button class="toolbtn" type="submit" name="action" value="filter_logs">Apply filter</button>
            <button class="toolbtn" type="submit" name="action" value="clear_logs">Clear logs</button>
            <button class="toolbtn" type="button" onclick="copySelectedLogs()">Copy selected</button>
          </form>
          <div class="logbox">
            {% if filtered_logs %}
              {% for entry in filtered_logs %}
              <div class="logline log-{{ entry.level|lower }}">{{ entry.text }}</div>
              {% endfor %}
            {% else %}
              <div class="logline log-info">(no recent logs captured)</div>
            {% endif %}
          </div>
        </div>
      </section>
    </main>
  </div>
</body>
<script>
function copySelectedLogs() {
  const selection = window.getSelection ? String(window.getSelection()) : "";
  const fallback = Array.from(document.querySelectorAll(".logbox .logline")).map((node) => node.textContent || "").join("\\n");
  const text = selection.trim() || fallback.trim();
  if (!text) {
    return;
  }
  navigator.clipboard.writeText(text);
}
</script>
</html>
"""


def _sample_process_cpu_percent() -> float | None:
    global _metrics_prev_wall, _metrics_prev_cpu
    now_wall = time.perf_counter()
    now_cpu = time.process_time()
    if _metrics_prev_wall is None or _metrics_prev_cpu is None:
        _metrics_prev_wall = now_wall
        _metrics_prev_cpu = now_cpu
        return None
    dw = now_wall - _metrics_prev_wall
    dc = now_cpu - _metrics_prev_cpu
    _metrics_prev_wall = now_wall
    _metrics_prev_cpu = now_cpu
    if dw <= 0:
        return None
    return max(0.0, (dc / dw) * 100.0)


def _safe_len(value) -> int:
    try:
        return len(value) if value is not None else 0
    except TypeError:
        return 0


def _dataref_traffic_stats(sim) -> dict:
    if sim is None:
        return {}
    stats = getattr(sim, "_stats", None)
    if not isinstance(stats, dict):
        return {}
    return {
        "ws_messages_received": stats.get("receive", 0),
        "dataref_updates_received": stats.get("response_update", 0),
        "dataref_values_processed": stats.get("update_dataref", 0),
        "batch_events": stats.get("batch_events", 0),
        "ws_stall_count": getattr(sim, "_ws_stall_count", 0),
    }


def register_web_control(
    app,
    *,
    recent_log_handler: RecentLogHandler,
    get_cockpit,
    get_runtime_state,
    get_runtime_config,
    persist_runtime_config,
    runtime_config_path,
    environment,
    environ_kw,
    config_path_list,
    merge_runtime_config,
    process_start_ts: float,
):
    def cockpit_is_ready() -> bool:
        return get_cockpit() is not None and get_runtime_state().get("status") == "running"

    def control_view_model(message: str | None = None) -> dict:
        current_paths = environment.get(environ_kw.COCKPITDECKS_PATH.value, "")
        current_server = environment.get(environ_kw.APP_HOST.value, ["127.0.0.1", 7777])
        current_api_host = environment.get(environ_kw.API_HOST.value, "127.0.0.1")
        current_api_port = environment.get(environ_kw.API_PORT.value, 8086)
        runtime_config = get_runtime_config()
        deck_paths = config_path_list(runtime_config.get("deck_paths"))
        cockpit = get_cockpit()
        current_sim = getattr(cockpit, "sim", None)
        current_mode = getattr(cockpit, "mode", None)
        current_aircraft = getattr(cockpit, "aircraft", None)
        state = get_runtime_state()
        selected_target = runtime_config.get("target")
        logging_cfg = runtime_config.get("logging", {})
        persisted_log_level = str(logging_cfg.get("log_level_filter", "DEBUG")).upper()
        selected_log_level = request.args.get("log_level", request.form.get("log_level", persisted_log_level)).upper()
        if selected_log_level not in LOG_LEVEL_ORDER:
            selected_log_level = "DEBUG"
        filtered_logs = [
            entry for entry in recent_log_handler.recent_logs if LOG_LEVEL_ORDER.get(entry.get("level", "INFO"), 1) >= LOG_LEVEL_ORDER[selected_log_level]
        ]
        return {
            "version": __version__,
            "message": message,
            "active_tab": request.args.get("tab", request.form.get("tab", "control")),
            "config_path": str(runtime_config_path),
            "runtime_status": state.get("status", "starting"),
            "runtime_message": state.get("message", ""),
            "runtime_error": state.get("error"),
            "target": selected_target,
            "deck_paths_text": "\n".join(deck_paths),
            "xplane_api_host": runtime_config.get("xplane_api", {}).get("host", "127.0.0.1"),
            "xplane_api_port": runtime_config.get("xplane_api", {}).get("port", 8086),
            "cockpitdecks_server_host": runtime_config.get("cockpitdecks_server", {}).get("host", "127.0.0.1"),
            "cockpitdecks_server_port": runtime_config.get("cockpitdecks_server", {}).get("port", 7777),
            "current_aircraft_path": getattr(current_aircraft, "acpath", None),
            "current_deck_paths": current_paths,
            "current_api_host": current_api_host,
            "current_api_port": current_api_port,
            "current_server_host": current_server[0] if isinstance(current_server, (list, tuple)) and len(current_server) >= 2 else "127.0.0.1",
            "current_server_port": current_server[1] if isinstance(current_server, (list, tuple)) and len(current_server) >= 2 else 7777,
            "mode_name": getattr(current_mode, "name", None),
            "simulator_name": type(current_sim).__name__ if current_sim is not None else None,
            "deck_root_count": len(deck_paths),
            "recent_log_count": len(recent_log_handler.recent_logs),
            "log_levels": LOG_LEVELS,
            "selected_log_level": selected_log_level,
            "filtered_logs": filtered_logs,
        }

    def update_runtime_config_from_form(form) -> tuple[dict, str | None]:
        updated = merge_runtime_config(get_runtime_config())
        updated["target"] = form.get("target", "").strip() or None
        updated["deck_paths"] = [line.strip() for line in form.get("deck_paths", "").splitlines() if line.strip()]
        updated["xplane_api"]["host"] = form.get("xplane_api_host", "127.0.0.1").strip() or "127.0.0.1"
        updated["cockpitdecks_server"]["host"] = form.get("cockpitdecks_server_host", "127.0.0.1").strip() or "127.0.0.1"
        updated.setdefault("logging", {})
        requested_log_level = form.get("log_level", updated["logging"].get("log_level_filter", "DEBUG")).strip().upper()
        updated["logging"]["log_level_filter"] = requested_log_level if requested_log_level in LOG_LEVEL_ORDER else "DEBUG"
        try:
            updated["xplane_api"]["port"] = int(form.get("xplane_api_port", "8086").strip() or "8086")
            updated["cockpitdecks_server"]["port"] = int(form.get("cockpitdecks_server_port", "7777").strip() or "7777")
        except ValueError:
            return get_runtime_config(), "Ports must be integers."
        return updated, None

    @app.route("/control", methods=["GET", "POST"])
    def control():
        message = None
        if request.method == "POST":
            action = request.form.get("action", "")
            if action == "reload":
                cockpit = get_cockpit()
                if cockpit_is_ready():
                    cockpit.reload_decks()
                    message = "Deck reload requested."
                else:
                    message = "Runtime is not ready yet."
            elif action == "clear_logs":
                recent_log_handler.recent_logs.clear()
                message = "Recent log buffer cleared."
            elif action == "filter_logs":
                updated = merge_runtime_config(get_runtime_config())
                requested_log_level = request.form.get("log_level", updated.get("logging", {}).get("log_level_filter", "DEBUG")).upper()
                updated.setdefault("logging", {})
                updated["logging"]["log_level_filter"] = requested_log_level if requested_log_level in LOG_LEVEL_ORDER else "DEBUG"
                persist_runtime_config(updated)
                message = f"Showing logs from {updated['logging']['log_level_filter']} and above."
            else:
                updated, error = update_runtime_config_from_form(request.form)
                if error is not None:
                    message = error
                else:
                    runtime_config = persist_runtime_config(updated)
                    message = f"Saved config to {runtime_config_path}."
                    if action == "apply_target":
                        cockpit = get_cockpit()
                        if not cockpit_is_ready():
                            message = "Saved config. Runtime is not ready yet to apply target."
                            return render_template_string(CONTROL_TEMPLATE, **control_view_model(message=message))
                        target = runtime_config.get("target")
                        if not target:
                            message = "Saved config. No target set to apply."
                        else:
                            target_path = os.path.abspath(os.path.expanduser(target))
                            if not os.path.isdir(target_path):
                                message = f"Saved config, but target path does not exist: {target_path}"
                            elif not os.path.isdir(os.path.join(target_path, CONFIG_FOLDER)):
                                message = f"Saved config, but target has no {CONFIG_FOLDER}: {target_path}"
                            else:
                                acname = Aircraft.get_aircraft_name_from_aircraft_path(target_path)
                                cockpit.schedule_aircraft_change(acname=acname, acpath=target_path, liverypath=None)
                                message = f"Saved config and scheduled aircraft change to {target_path}."
        return render_template_string(CONTROL_TEMPLATE, **control_view_model(message=message))

    @app.route("/api/status", methods=["GET"])
    def desktop_status():
        cockpit = get_cockpit()
        if cockpit is None:
            return jsonify(
                {
                    "cockpitdecks_version": __version__,
                    "aircraft_name": "",
                    "aircraft_path": None,
                    "deckconfig_path": None,
                    "deck_names": [],
                    "runtime_status": get_runtime_state().get("status"),
                }
            )
        ac = cockpit.aircraft
        deckconfig_path = None
        if ac.acpath is not None:
            deckconfig_path = os.path.abspath(os.path.join(ac.acpath, CONFIG_FOLDER))
        decks_info = []
        if ac.decks:
            for deck_name in sorted(ac.decks.keys()):
                deck = ac.decks[deck_name]
                deck_type_name = ""
                if hasattr(deck, "deck_type") and deck.deck_type and hasattr(deck.deck_type, "name"):
                    deck_type_name = deck.deck_type.name
                decks_info.append({
                    "name": deck_name,
                    "type": deck_type_name,
                    "serial": getattr(deck, "serial", None),
                    "connected": getattr(deck, "device", None) is not None,
                    "running": getattr(deck, "running", False),
                    "virtual": deck.is_virtual_deck() if hasattr(deck, "is_virtual_deck") else False,
                })
        return jsonify(
            {
                "cockpitdecks_version": __version__,
                "aircraft_name": ac.name or "",
                "aircraft_path": ac.acpath,
                "deckconfig_path": deckconfig_path,
                "deck_names": [d["name"] for d in decks_info],  # kept for backward compat
                "decks": decks_info,
            }
        )

    @app.route("/api/metrics", methods=["GET"])
    def desktop_metrics():
        rss_mb: float | None = None
        try:
            if resource is not None:
                rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                rss_mb = (rss / (1024 * 1024)) if platform.system() == "Darwin" else (rss / 1024.0)
        except OSError:
            rss_mb = None

        cockpit = get_cockpit()
        sim = getattr(cockpit, "sim", None) if cockpit is not None else None
        vdb = getattr(cockpit, "variable_database", None) if cockpit is not None else None
        ac = getattr(cockpit, "aircraft", None) if cockpit is not None else None
        deck_count = _safe_len(getattr(ac, "decks", None))
        pages_count = 0
        if ac is not None and getattr(ac, "decks", None):
            for deck in ac.decks.values():
                pages_count += _safe_len(getattr(deck, "pages", None))

        return jsonify(
            {
                "timestamp": int(time.time()),
                "uptime_s": round(max(0.0, time.time() - process_start_ts), 3),
                "process": {
                    "pid": os.getpid(),
                    "thread_count": threading.active_count(),
                    "cpu_percent": _sample_process_cpu_percent(),
                    "max_rss_mb": round(rss_mb, 2) if rss_mb is not None else None,
                },
                "cockpit": {
                    "mode": str(getattr(getattr(cockpit, "mode", None), "name", "")),
                    "decks_count": deck_count,
                    "pages_count": pages_count,
                    "registered_variables": _safe_len(getattr(vdb, "database", None)),
                    "dirty_marks": getattr(cockpit, "_dirty_marks", 0) if cockpit is not None else 0,
                    "dirty_flushes": getattr(cockpit, "_dirty_flushes", 0) if cockpit is not None else 0,
                    "dirty_rendered": getattr(cockpit, "_dirty_rendered", 0) if cockpit is not None else 0,
                    "event_queue_depth": (cockpit.event_queue.qsize() + cockpit.priority_event_queue.qsize()) if cockpit is not None else 0,
                },
                "simulator": {
                    "name": type(sim).__name__ if sim is not None else "",
                    "running": bool(getattr(sim, "running", False)),
                    "status": str(getattr(sim, "xplane_status_str", "")),
                    "datarefs_monitored": _safe_len(getattr(sim, "simulator_variable_to_monitor", None)),
                    "events_monitored": _safe_len(getattr(sim, "simulator_event_to_monitor", None)),
                },
                "dataref_traffic": _dataref_traffic_stats(sim),
                "diagnostics": cockpit.get_diagnostics() if cockpit is not None and hasattr(cockpit, "get_diagnostics") else {},
            }
        )

    @app.route("/api/reload")
    def reload():
        cockpit = get_cockpit()
        if not cockpit_is_ready():
            return {"status": "not-ready"}, 503
        cockpit.reload_decks()
        return {"status": "ok"}

    @app.route("/api/deck/<name>/reload", methods=["POST"])
    def deck_reload(name):
        cockpit = get_cockpit()
        if not cockpit_is_ready():
            return {"status": "not-ready"}, 503
        if name not in cockpit.decks:
            return {"status": "error", "message": f"deck {name} not found"}, 404
        cockpit.reload_deck(name)
        return {"status": "ok"}

    @app.route("/api/watch", methods=["GET", "POST"])
    def api_watch():
        cockpit = get_cockpit()
        if request.method == "GET":
            enabled = getattr(cockpit, "_watch_config", False) if cockpit is not None else get_runtime_config().get("watch_config", False)
            return jsonify({"watch_config": bool(enabled)})
        data = request.get_json(silent=True) or {}
        enabled = bool(data.get("watch_config", False))
        rc = get_runtime_config()
        rc["watch_config"] = enabled
        persist_runtime_config(rc)
        if cockpit is not None:
            cockpit._watch_config = enabled
            if enabled:
                acpath = getattr(cockpit.aircraft, "acpath", None) if cockpit.aircraft is not None else None
                if acpath:
                    cockpit._start_file_watcher(acpath)
            else:
                cockpit._stop_file_watcher()
        return jsonify({"status": "ok", "watch_config": enabled})

    @app.route("/api/target", methods=["GET", "POST"])
    def api_target():
        cockpit = get_cockpit()
        rc = get_runtime_config()
        if request.method == "GET":
            current_ac = getattr(cockpit, "aircraft", None) if cockpit is not None else None
            return jsonify({
                "target": rc.get("target"),
                "current_aircraft": getattr(current_ac, "name", None),
                "current_path": getattr(current_ac, "acpath", None),
            })
        data = request.get_json(silent=True) or {}
        target = (data.get("target") or "").strip()
        if not target:
            return {"status": "error", "message": "missing target path"}, 400
        target_path = os.path.abspath(os.path.expanduser(target))
        if not os.path.isdir(target_path):
            return {"status": "error", "message": f"path does not exist: {target_path}"}, 400
        if not os.path.isdir(os.path.join(target_path, CONFIG_FOLDER)):
            return {"status": "error", "message": f"no {CONFIG_FOLDER} folder in {target_path}"}, 400
        rc["target"] = target
        persist_runtime_config(rc)
        if not cockpit_is_ready():
            return {"status": "saved", "message": "target saved, cockpit not ready to apply yet"}
        acname = Aircraft.get_aircraft_name_from_aircraft_path(target_path)
        cockpit.schedule_aircraft_change(acname=acname, acpath=target_path, liverypath=None)
        return {"status": "ok", "message": f"switching to {acname}", "path": target_path}
