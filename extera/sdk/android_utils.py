import extera_engine


def run_on_ui_thread(func, delay=0):
    extera_engine.host.run_on_ui(getattr(func, "run", func), delay)


def log(data):
    extera_engine.log(data)


def copy_to_clipboard(text):
    extera_engine.host.copy_to_clipboard(str(text))
    return True


class OnClickListener:
    def __init__(self, fn):
        self.fn = fn

    def onClick(self, view=None):
        self.fn(view)

    __call__ = onClick


class OnLongClickListener(OnClickListener):
    def onLongClick(self, view=None):
        return bool(self.fn(view))

    __call__ = onLongClick


class R:
    def __init__(self, fn):
        self.fn = fn

    def run(self):
        self.fn()

    __call__ = run
