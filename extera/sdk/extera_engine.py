"""Desktop plugin engine: loads exteraGram plugins and runs their hooks."""
import ast
import importlib.machinery
import importlib.util
import json
import os
import re
import sys
import threading
import traceback

import extera_java

extera_java.install()

ID_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]{1,31}$")
META_KEYS = ("id", "name", "description", "author", "version", "icon")


class Host:
    """What the application provides. The app replaces it with set_host()."""

    def data_dir(self):
        return os.path.join(os.path.expanduser("~"), ".extera")

    def log(self, text):
        print(text, file=sys.stderr)

    def run_on_ui(self, fn, delay_ms=0):
        fn()

    def selected_account(self):
        return 0

    def user_id(self, account):
        return 0

    def show_bulletin(self, kind, text, extra=None):
        self.log("[bulletin:%s] %s" % (kind, text))

    def show_alert(self, alert):
        self.log("[alert] %s: %s" % (alert.title, alert.message))

    def send_message(self, account, params):
        self.log("[send] %r" % (params,))

    def send_request(self, account, request, callback):
        callback(None, None)
        return 0

    def copy_to_clipboard(self, text):
        pass

    def open_url(self, url):
        pass

    def method_hook_keys(self):
        return ()

    def plugins_changed(self):
        pass


host = Host()


def set_host(value):
    global host
    host = value


def log(text):
    host.log(str(text))


class PluginError(Exception):
    pass


class LoadedPlugin:
    def __init__(self, meta, path):
        self.id = meta["id"]
        self.meta = meta
        self.path = path
        self.instance = None
        self.module = None
        self.unsupported = []
        self.cleanups = []
        self.stop_event = threading.Event()
        self._settings = None

    def settings_path(self):
        return os.path.join(host.data_dir(), "plugin_settings", self.id + ".json")

    def settings(self):
        if self._settings is None:
            try:
                with open(self.settings_path(), encoding="utf-8") as f:
                    self._settings = json.load(f)
            except (OSError, ValueError):
                self._settings = {}
        return self._settings

    def save_settings(self):
        path = self.settings_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self._settings, f, ensure_ascii=False)


def read_metadata(path):
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    meta = {key: "" for key in META_KEYS}
    meta["requirements"] = []
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        key = target.id.strip("_")
        value = node.value
        if key in META_KEYS and isinstance(value, ast.Constant) and isinstance(value.value, str):
            meta[key] = value.value
        elif key == "requirements" and isinstance(value, (ast.List, ast.Tuple)):
            meta[key] = [e.value for e in value.elts if isinstance(e, ast.Constant)]
    if not meta["id"] or not meta["name"]:
        raise PluginError("plugin must define __id__ and __name__")
    if not ID_RE.match(meta["id"]):
        raise PluginError("invalid __id__: %s" % meta["id"])
    return meta


class Engine:
    def __init__(self):
        self.plugins = {}
        self.event_hooks = []
        self.send_hooks = []
        self.menu_items = {}
        self.method_hooks = {}
        self._menu_counter = 0
        self._lock = threading.RLock()

    # loading

    def load_file(self, path):
        import base_plugin

        meta = read_metadata(path)
        if meta["id"] in self.plugins:
            self.unload(meta["id"])
        plugin = LoadedPlugin(meta, path)
        loader = importlib.machinery.SourceFileLoader(meta["id"], path)
        spec = importlib.util.spec_from_loader(meta["id"], loader)
        module = importlib.util.module_from_spec(spec)
        self.plugins[plugin.id] = plugin
        try:
            base_plugin._loading.plugin = plugin
            loader.exec_module(module)
            cls = next((
                value for value in vars(module).values()
                if isinstance(value, type)
                and issubclass(value, base_plugin.BasePlugin)
                and value is not base_plugin.BasePlugin
                and value.__module__ == module.__name__), None)
            if cls is None:
                raise PluginError("no BasePlugin subclass in %s" % path)
            plugin.module = module
            plugin.instance = cls()
            plugin.instance.on_plugin_load()
        except BaseException:
            self._drop(plugin.id)
            raise
        finally:
            base_plugin._loading.plugin = None
        host.plugins_changed()
        return plugin

    def unload(self, plugin_id):
        plugin = self.plugins.get(plugin_id)
        if plugin is None:
            return
        plugin.stop_event.set()
        self._guard(plugin, "on_plugin_unload", plugin.instance.on_plugin_unload)
        for cleanup in plugin.cleanups:
            self._guard(plugin, "cleanup", cleanup)
        self._drop(plugin_id)
        host.plugins_changed()

    def _drop(self, plugin_id):
        with self._lock:
            self.plugins.pop(plugin_id, None)
            self.event_hooks = [h for h in self.event_hooks if h[0] != plugin_id]
            self.send_hooks = [h for h in self.send_hooks if h[0] != plugin_id]
            self.menu_items = {k: v for k, v in self.menu_items.items() if v[0] != plugin_id}
            for key in list(self.method_hooks):
                self.method_hooks[key] = [h for h in self.method_hooks[key] if h[0] != plugin_id]

    def _guard(self, plugin, where, fn, *args):
        try:
            return fn(*args)
        except Exception:
            log("Plugin '%s' crashed in %s:\n%s" % (plugin.id, where, traceback.format_exc()))
            return None

    # registration, called from BasePlugin

    def add_event_hook(self, plugin_id, name, match_substring, priority):
        with self._lock:
            self.event_hooks.append((plugin_id, name, match_substring, priority))

    def remove_event_hook(self, plugin_id, name):
        with self._lock:
            self.event_hooks = [h for h in self.event_hooks if h[:2] != (plugin_id, name)]

    def add_send_hook(self, plugin_id, priority):
        with self._lock:
            self.send_hooks.append((plugin_id, priority))

    def add_menu_item(self, plugin_id, item):
        with self._lock:
            if not item.item_id:
                self._menu_counter += 1
                item.item_id = "%s_%d" % (plugin_id, self._menu_counter)
            self.menu_items[item.item_id] = (plugin_id, item)
        host.plugins_changed()
        return item.item_id

    def remove_menu_item(self, plugin_id, item_id):
        with self._lock:
            found = self.menu_items.get(item_id, (None,))[0] == plugin_id
            if found:
                del self.menu_items[item_id]
        return found

    def add_method_hook(self, plugin_id, key, hook, priority):
        plugin = self.plugins[plugin_id]
        if key not in host.method_hook_keys():
            plugin.unsupported.append(key)
            log("Plugin '%s': no desktop analog for %s" % (plugin_id, key))
        entry = (plugin_id, hook, priority or 0)
        with self._lock:
            self.method_hooks.setdefault(key, []).append(entry)
        return entry

    def remove_method_hook(self, entry):
        with self._lock:
            for hooks in self.method_hooks.values():
                if entry in hooks:
                    hooks.remove(entry)

    # dispatch, called from the application

    def _ordered(self, entries):
        best = {}
        for plugin_id, priority in entries:
            best[plugin_id] = max(priority, best.get(plugin_id, priority))
        ids = sorted(best, key=lambda plugin_id: (-best[plugin_id], plugin_id))
        return [self.plugins[i] for i in ids if i in self.plugins]

    def _interested(self, name):
        return self._ordered(
            (plugin_id, priority)
            for plugin_id, hook_name, substring, priority in self.event_hooks
            if hook_name == name or (substring and hook_name in name))

    def _chain(self, plugins, method, field, value, make_args, can_cancel=True):
        from base_plugin import HookStrategy

        for plugin in plugins:
            fn = getattr(plugin.instance, method)
            result = self._guard(plugin, method, fn, *make_args(value))
            strategy = getattr(result, "strategy", HookStrategy.DEFAULT)
            if strategy == HookStrategy.CANCEL and can_cancel:
                return None
            if strategy in (HookStrategy.MODIFY, HookStrategy.MODIFY_FINAL):
                changed = getattr(result, field, None)
                if changed is not None:
                    value = changed
                if strategy == HookStrategy.MODIFY_FINAL:
                    break
        return value

    def execute_send_message_hook(self, account, params):
        return self._chain(
            self._ordered(self.send_hooks), "on_send_message_hook", "params", params,
            lambda value: (account, value))

    def execute_pre_request_hook(self, name, account, request):
        return self._chain(
            self._interested(name), "pre_request_hook", "request", request,
            lambda value: (name, account, value))

    def execute_post_request_hook(self, name, account, response, error):
        from base_plugin import HookStrategy

        for plugin in self._interested(name):
            result = self._guard(
                plugin, "post_request_hook", plugin.instance.post_request_hook,
                name, account, response, error)
            strategy = getattr(result, "strategy", HookStrategy.DEFAULT)
            if strategy in (HookStrategy.MODIFY, HookStrategy.MODIFY_FINAL):
                response, error = result.response, result.error
                if strategy == HookStrategy.MODIFY_FINAL:
                    break
        return response, error

    def execute_update_hook(self, name, account, update):
        return self._chain(
            self._interested(name), "on_update_hook", "update", update,
            lambda value: (name, account, value))

    def execute_updates_hook(self, name, account, updates):
        return self._chain(
            self._interested(name), "on_updates_hook", "updates", updates,
            lambda value: (name, account, value))

    def execute_app_event(self, event):
        from base_plugin import AppEvent

        try:
            event = AppEvent(event)
        except ValueError:
            pass
        for plugin in list(self.plugins.values()):
            self._guard(plugin, "on_app_event", plugin.instance.on_app_event, event)

    def fire_method_hook(self, key, this, args, after=False, result=None):
        from base_plugin import MethodHookParam

        param = MethodHookParam(key, this, list(args), result)
        hooks = sorted(self.method_hooks.get(key, ()), key=lambda h: (-h[2], h[0]))
        for plugin_id, hook, _ in hooks:
            plugin = self.plugins.get(plugin_id)
            if plugin is not None:
                self._guard(plugin, key, hook.run, param, after)
        return param

    def menu_for(self, location, context):
        from base_plugin import eval_condition

        aliases = {"main_menu": ("main_menu", "drawer_menu"), "drawer_menu": ("main_menu", "drawer_menu")}
        wanted = aliases.get(location, (location,))
        items = [
            item for plugin_id, item in self.menu_items.values()
            if item.menu_type.value in wanted and eval_condition(item.condition, context)]
        return sorted(items, key=lambda item: -item.priority)

    def click_menu_item(self, item_id, context):
        entry = self.menu_items.get(item_id)
        if entry:
            plugin = self.plugins.get(entry[0])
            self._guard(plugin, "menu on_click", entry[1].on_click, context)

    def settings_for(self, plugin_id):
        plugin = self.plugins[plugin_id]
        items = self._guard(plugin, "create_settings", plugin.instance.create_settings) or []
        return list(items)

    def change_setting(self, plugin_id, key, value):
        plugin = self.plugins[plugin_id]
        plugin.instance.set_setting(key, value)
        for item in self.settings_for(plugin_id):
            callback = getattr(item, "on_change", None)
            if getattr(item, "key", None) == key and callback:
                self._guard(plugin, "on_change", callback, value)


engine = Engine()

import extera_shims  # noqa: E402,F401
