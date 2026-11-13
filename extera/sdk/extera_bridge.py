"""JSON bridge between the application and the plugin engine."""
import json
import os
import shutil
import sys
import threading
import traceback

import extera_engine
import extera_scan
from extera_engine import engine

try:
    import _extera_host
except ImportError:
    _extera_host = None

_state = {"plugins_dir": "", "data_dir": "", "catalog": {}, "ru": False,
          "engine": True, "safe_mode": False}
_ui_tasks = {}
_alerts = {}
_counter = [0]
_lock = threading.Lock()


def _next():
    with _lock:
        _counter[0] += 1
        return _counter[0]


_TAGS = {
    "TL_messageEntityBold": "bold", "TL_messageEntityItalic": "italic",
    "TL_messageEntityUnderline": "underline", "TL_messageEntityStrike": "strike",
    "TL_messageEntityCode": "code", "TL_messageEntityPre": "pre",
    "TL_messageEntitySpoiler": "spoiler", "TL_messageEntityBlockquote": "quote",
    "TL_messageEntityTextUrl": "url",
}


def _host(name, **payload):
    return json.loads(_extera_host.call(name, json.dumps(payload, ensure_ascii=False)) or "null")


def _entities(items):
    result = []
    for item in items or []:
        tag = _TAGS.get(type(item).__name__)
        if tag:
            result.append({"type": tag, "offset": int(item.offset), "length": int(item.length),
                           "url": str(getattr(item, "url", "") or "")})
    return result


class _LogWriter:
    def __init__(self):
        self.buffer = ""

    def write(self, text):
        self.buffer += str(text)
        while "\n" in self.buffer:
            line, self.buffer = self.buffer.split("\n", 1)
            if line.strip():
                _host("log", text=line)
        return len(text)

    def flush(self):
        pass


class BridgeHost(extera_engine.Host):
    def data_dir(self):
        return _state["data_dir"]

    def log(self, text):
        _host("log", text=str(text))

    def run_on_ui(self, fn, delay_ms=0):
        token = _next()
        _ui_tasks[token] = fn
        _host("ui_post", token=token, delay=int(delay_ms or 0))

    def selected_account(self):
        return 0

    def user_id(self, account):
        return _host("user_id") or 0

    def show_bulletin(self, kind, text, extra=None):
        _host("toast", kind=kind, text=text)

    def show_alert(self, alert):
        alert_id = _next()
        _alerts[alert_id] = alert
        alert._bridge_id = alert_id
        buttons = [[which, str(entry[0])] for which, entry in sorted(alert.buttons.items(), reverse=True)]
        _host("alert", id=alert_id, title=str(alert.title or ""), message=str(alert.message or ""),
              buttons=buttons, items=[str(item) for item in alert.items or []])

    def close_alert(self, alert):
        alert_id = getattr(alert, "_bridge_id", None)
        if _alerts.pop(alert_id, None) is not None:
            _host("alert_close", id=alert_id)

    def send_message(self, account, params):
        text = params.get("message") or params.get("caption") or ""
        if params.get("path"):
            self.log("sending files is not supported on desktop yet")
            return
        _host("send_message", peer=int(params.get("peer") or 0), text=str(text),
              entities=_entities(params.get("entities")))

    def send_request(self, account, request, callback):
        from extera_java import TLRPC

        error = TLRPC.TL_error()
        error.code = 501
        error.text = "NOT_SUPPORTED_ON_DESKTOP"
        self.log("request %s is not supported on desktop yet" % type(request).__name__)
        callback(None, error)
        return 0

    def copy_to_clipboard(self, text):
        _host("copy", text=text)

    def open_url(self, url):
        _host("open_url", url=url)

    def plugins_changed(self):
        pass


def _catalog_path():
    return os.path.join(_state["data_dir"], "plugins.json")


def _load_flags():
    try:
        with open(_catalog_path(), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_flags():
    flags = {key: {"enabled": entry["enabled"], "pinned": entry["pinned"]}
             for key, entry in _state["catalog"].items()}
    os.makedirs(_state["data_dir"], exist_ok=True)
    with open(_catalog_path(), "w", encoding="utf-8") as f:
        json.dump(flags, f)


def _register(path, enabled=True):
    meta = extera_engine.read_metadata(path)
    with open(path, encoding="utf-8") as f:
        status, reason = extera_scan.scan(
            f.read(), meta["name"] + " " + os.path.basename(path), _state["ru"])
    entry = {"meta": meta, "path": path, "status": status, "reason": reason,
             "enabled": enabled, "pinned": False, "error": ""}
    _state["catalog"][meta["id"]] = entry
    return entry


def _runs():
    return _state["engine"] and not _state["safe_mode"]


def _activate(entry):
    plugin_id = entry["meta"]["id"]
    entry["error"] = ""
    if not entry["enabled"] or not _runs():
        engine.unload(plugin_id)
        return
    try:
        engine.load_file(entry["path"])
    except BaseException as e:
        entry["error"] = "%s: %s" % (type(e).__name__, e)
        extera_engine.log("Plugin '%s' failed to load:\n%s" % (plugin_id, traceback.format_exc()))


def _info(entry):
    meta = entry["meta"]
    loaded = engine.plugins.get(meta["id"])
    return {
        "id": meta["id"], "name": meta["name"], "version": meta["version"],
        "author": meta["author"], "description": meta["description"], "icon": meta["icon"],
        "enabled": entry["enabled"], "status": entry["status"], "reason": entry["reason"],
        "error": entry["error"], "loaded": loaded is not None,
        "pinned": entry["pinned"], "path": entry["path"],
        "has_settings": bool(loaded and engine.settings_for(meta["id"])),
        "unsupported": list(loaded.unsupported) if loaded else [],
    }


def start(plugins_dir, data_dir, ru=False, engine_on=True, safe_mode=False):
    _state.update(plugins_dir=plugins_dir, data_dir=data_dir, catalog={}, ru=bool(ru),
                  engine=bool(engine_on), safe_mode=bool(safe_mode))
    os.makedirs(plugins_dir, exist_ok=True)
    extera_engine.set_host(BridgeHost())
    if _extera_host is not None and not isinstance(sys.stdout, _LogWriter):
        sys.stdout = sys.stderr = _LogWriter()
    flags = _load_flags()
    for name in sorted(os.listdir(plugins_dir)):
        if not name.lower().endswith((".plugin", ".py")):
            continue
        path = os.path.join(plugins_dir, name)
        try:
            entry = _register(path)
        except Exception as e:
            extera_engine.log("Skipped %s: %s" % (name, e))
            continue
        saved = flags.get(entry["meta"]["id"], {})
        entry["enabled"] = saved.get("enabled", True)
        entry["pinned"] = saved.get("pinned", False)
        _activate(entry)
    engine.execute_app_event("app_start")
    return list_plugins()


def list_plugins():
    entries = sorted(_state["catalog"].values(),
                     key=lambda entry: (not entry["pinned"], entry["meta"]["name"].lower()))
    return [_info(entry) for entry in entries]


def set_mode(engine_on, safe_mode):
    _state.update(engine=bool(engine_on), safe_mode=bool(safe_mode))
    for entry in list(_state["catalog"].values()):
        _activate(entry)
    return list_plugins()


def about():
    import _sdk_version

    return {"sdk": _sdk_version.version_str}


def inspect(path):
    meta = extera_engine.read_metadata(path)
    with open(path, encoding="utf-8") as f:
        status, reason = extera_scan.scan(
            f.read(), meta["name"] + " " + os.path.basename(path), _state["ru"])
    old = _state["catalog"].get(meta["id"])
    return {
        "id": meta["id"], "name": meta["name"], "version": meta["version"],
        "author": meta["author"], "description": meta["description"], "icon": meta["icon"],
        "status": status, "reason": reason, "installed": old is not None,
        "old_version": old["meta"]["version"] if old else "",
    }


def install(path, enable=None):
    meta = extera_engine.read_metadata(path)
    target = os.path.join(_state["plugins_dir"], meta["id"] + ".plugin")
    old = _state["catalog"].get(meta["id"])
    if old and os.path.abspath(old["path"]) != os.path.abspath(target):
        engine.unload(meta["id"])
        os.remove(old["path"])
    if os.path.abspath(path) != os.path.abspath(target):
        shutil.copyfile(path, target)
    entry = _register(target)
    usable = entry["status"] in (extera_scan.WORKS, extera_scan.PARTIAL)
    if old:
        entry["enabled"] = old["enabled"]
        entry["pinned"] = old["pinned"]
    else:
        entry["enabled"] = usable and (enable is None or bool(enable))
    _activate(entry)
    _save_flags()
    return _info(entry)


def set_enabled(id, enabled):
    if enabled and _state["safe_mode"]:
        raise extera_engine.PluginError("Plugins cannot be enabled while safe mode is active")
    entry = _state["catalog"][id]
    entry["enabled"] = bool(enabled)
    _activate(entry)
    _save_flags()
    return _info(entry)


def set_pinned(id, pinned):
    entry = _state["catalog"][id]
    entry["pinned"] = bool(pinned)
    _save_flags()
    return _info(entry)


def delete(id):
    entry = _state["catalog"].pop(id, None)
    if entry:
        engine.unload(id)
        try:
            os.remove(entry["path"])
        except OSError:
            pass
        _save_flags()
    return True


def send_hook(peer, text, account=0):
    from extera_shims import SendMessageParams

    params = engine.execute_send_message_hook(account, SendMessageParams(text, peer))
    if params is None:
        return {"cancel": True, "text": "", "entities": []}
    message = params.message
    return {"cancel": False, "text": text if message is None else str(message),
            "entities": _entities(params.entities)}


def settings(id):
    plugin = engine.plugins.get(id)
    if plugin is None:
        return []
    result = []
    for index, item in enumerate(engine.settings_for(id)):
        kind = getattr(item, "type", "custom")
        key = getattr(item, "key", None)
        row = {"index": index, "type": kind, "text": str(getattr(item, "text", None) or
                                                         getattr(item, "hint", None) or ""),
               "subtext": str(getattr(item, "subtext", None) or ""), "key": key or ""}
        if key:
            row["value"] = plugin.instance.get_setting(key, getattr(item, "default", None))
        if kind == "selector":
            row["items"] = [str(value) for value in item.items]
        if kind == "text":
            row["clickable"] = bool(item.on_click)
        result.append(row)
    return result


def set_setting(id, key, value):
    engine.change_setting(id, key, value)
    return True


def setting_click(id, index):
    plugin = engine.plugins.get(id)
    items = engine.settings_for(id)
    callback = getattr(items[index], "on_click", None) if index < len(items) else None
    if callback:
        engine._guard(plugin, "setting on_click", callback, None)
    return True


def menu(location):
    owners = {item.item_id: plugin_id for plugin_id, item in engine.menu_items.values()}
    return [{"id": item.item_id, "text": str(item.text),
             "plugin": engine.plugins[owners[item.item_id]].meta["name"]}
            for item in engine.menu_for(location, {"account": 0})]


def menu_click(id):
    from extera_java import HashMap

    engine.click_menu_item(id, HashMap(account=0))
    return True


def ui_run(token):
    fn = _ui_tasks.pop(token, None)
    if fn:
        try:
            fn()
        except Exception:
            extera_engine.log("UI task failed:\n%s" % traceback.format_exc())
    return True


def alert_click(id, which):
    alert = _alerts.pop(id, None)
    if alert:
        try:
            alert.click(which)
        except Exception:
            extera_engine.log("Alert callback failed:\n%s" % traceback.format_exc())
        alert.shown = False
        if alert.on_dismiss:
            alert.on_dismiss(alert)
    return True


def app_event(event):
    engine.execute_app_event(event)
    return True


_COMMANDS = {
    "start": start, "list": list_plugins, "install": install, "set_enabled": set_enabled,
    "set_mode": set_mode, "about": about, "inspect": inspect, "set_pinned": set_pinned,
    "delete": delete, "send_hook": send_hook, "settings": settings, "set_setting": set_setting,
    "setting_click": setting_click, "menu": menu, "menu_click": menu_click, "ui_run": ui_run,
    "alert_click": alert_click, "app_event": app_event,
}


def call(name, payload):
    try:
        result = _COMMANDS[name](**(json.loads(payload) if payload else {}))
        return json.dumps({"ok": True, "result": result}, ensure_ascii=False)
    except BaseException as e:
        return json.dumps({"ok": False, "error": "%s: %s" % (type(e).__name__, e),
                           "trace": traceback.format_exc()}, ensure_ascii=False)
