import extera_engine


def _plugin(plugin_id):
    return extera_engine.engine.plugins[plugin_id]


def get_setting(plugin_id, key, default=None):
    return _plugin(plugin_id).settings().get(key, default)


def set_setting(plugin_id, key, value):
    plugin = _plugin(plugin_id)
    plugin.settings()[key] = value
    plugin.save_settings()


def get_settings(plugin_id):
    return dict(_plugin(plugin_id).settings())


def set_settings(plugin_id, settings):
    plugin = _plugin(plugin_id)
    plugin.settings().update(settings)
    plugin.save_settings()
