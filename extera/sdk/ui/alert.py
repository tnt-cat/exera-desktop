import extera_engine


class AlertDialogBuilder:
    ALERT_TYPE_MESSAGE = 0
    ALERT_TYPE_LOADING = 2
    ALERT_TYPE_SPINNER = 3
    BUTTON_POSITIVE = -1
    BUTTON_NEGATIVE = -2
    BUTTON_NEUTRAL = -3

    def __init__(self, context=None, progress_style=0, resources_provider=None):
        self.context = context
        self.progress_style = progress_style
        self.title = None
        self.message = None
        self.buttons = {}
        self.red_buttons = set()
        self.items = None
        self.items_listener = None
        self.view = None
        self.cancelable = True
        self.on_dismiss = None
        self.on_cancel = None
        self.shown = False

    def set_title(self, title):
        self.title = title
        return self

    def set_message(self, message):
        self.message = message
        return self

    def _button(self, kind, text, listener):
        self.buttons[kind] = (text, listener)
        return self

    def set_positive_button(self, text, listener=None):
        return self._button(self.BUTTON_POSITIVE, text, listener)

    def set_negative_button(self, text, listener=None):
        return self._button(self.BUTTON_NEGATIVE, text, listener)

    def set_neutral_button(self, text, listener=None):
        return self._button(self.BUTTON_NEUTRAL, text, listener)

    def make_button_red(self, button_type):
        self.red_buttons.add(button_type)
        return self

    def set_items(self, items, listener=None, icons=None):
        self.items = list(items)
        self.items_listener = listener
        return self

    def _ignored(self, *args, **kwargs):
        return self

    set_blurred_background = set_dialog_button_color_key = set_dim_enabled = _ignored
    set_message_text_view_clickable = set_on_back_button_listener = _ignored
    set_top_animation = set_top_animation_is_new = set_top_drawable = set_top_image = _ignored

    def set_view(self, view, height=-2):
        self.view = view
        return self

    def set_cancelable(self, cancelable):
        self.cancelable = cancelable
        return self

    def set_canceled_on_touch_outside(self, cancel):
        return self

    def set_on_dismiss_listener(self, listener=None):
        self.on_dismiss = listener
        return self

    def set_on_cancel_listener(self, listener=None):
        self.on_cancel = listener
        return self

    def set_progress(self, progress):
        self.progress = progress

    def create(self):
        return self

    def show(self):
        self.shown = True
        host = extera_engine.host
        host.run_on_ui(lambda: host.show_alert(self))
        return self

    def dismiss(self):
        self.shown = False
        close = getattr(extera_engine.host, "close_alert", None)
        if close:
            close(self)
        if self.on_dismiss:
            self.on_dismiss(self)

    def click(self, which):
        entry = self.buttons.get(which)
        if entry and entry[1]:
            entry[1](self, which)
        elif which >= 0 and self.items_listener:
            self.items_listener(self, which)

    def get_dialog(self):
        return self if self.shown else None

    def get_button(self, button_type):
        return None

    def get_context(self):
        return self.context

    def __getattr__(self, name):
        if name.startswith("set_"):
            return lambda *args, **kwargs: self
        raise AttributeError(name)
