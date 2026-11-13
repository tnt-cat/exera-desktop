import extera_engine


def _plugin(plugin_id):
    return extera_engine.engine.plugins[plugin_id]


def init(plugins_dir_path, all_shared_prefs=None):
    pass


def get_setting(plugin_id, key, default=None):
    return _plugin(plugin_id).settings().get(key, default)


def set_setting(plugin_id, key, value):
    plugin = _plugin(plugin_id)
    plugin.settings()[key] = value
    plugin.save_settings()


def get_all_settings(plugin_id):
    return dict(_plugin(plugin_id).settings())


def set_all_settings(plugin_id, settings):
    plugin = _plugin(plugin_id)
    plugin.settings().clear()
    plugin.settings().update(settings)
    plugin.save_settings()


def clear_settings(plugin_id):
    set_all_settings(plugin_id, {})
