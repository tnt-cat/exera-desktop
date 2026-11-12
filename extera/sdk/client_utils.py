import queue
import threading

import extera_engine
import extera_shims
from extera_shims import HostObject

PLUGINS_QUEUE = "pluginsQueue"
STAGE_QUEUE = "stageQueue"
GLOBAL_QUEUE = "globalQueue"
SEARCH_QUEUE = "searchQueue"
EXTERNAL_NETWORK_QUEUE = "externalNetworkQueue"
THEME_QUEUE = "themeQueue"
CACHE_CLEAR_QUEUE = "cacheClearQueue"
PHONE_BOOK_QUEUE = "phoneBookQueue"

_queues = {}
_queues_lock = threading.Lock()


def _host():
    return extera_engine.host


class _Queue:
    def __init__(self, name):
        self.tasks = queue.Queue()
        threading.Thread(target=self._work, name=name, daemon=True).start()

    def _work(self):
        while True:
            fn = self.tasks.get()
            try:
                fn()
            except Exception as e:
                extera_engine.log("queue task failed: %r" % e)
            finally:
                self.tasks.task_done()

    def postRunnable(self, fn, delay=0):
        fn = getattr(fn, "run", fn)
        if delay:
            threading.Timer(delay / 1000, self.tasks.put, (fn,)).start()
        else:
            self.tasks.put(fn)


def get_queue_by_name(queue_name):
    with _queues_lock:
        if queue_name not in _queues:
            _queues[queue_name] = _Queue(queue_name)
        return _queues[queue_name]


def run_on_queue(fn, queue_name=PLUGINS_QUEUE, delay=0):
    get_queue_by_name(queue_name).postRunnable(fn, delay)


def get_selected_account():
    return _host().selected_account()


def get_hook_account():
    return None


def _account(account):
    return get_selected_account() if account is None else account


def get_last_fragment():
    return HostObject("Fragment", get_selected_account())


def _getter(name):
    def get(account=None):
        return extera_shims.controller(name, account)
    return get


get_account_instance = _getter("org.telegram.messenger.AccountInstance")
get_messages_controller = _getter("org.telegram.messenger.MessagesController")
get_messages_storage = _getter("org.telegram.messenger.MessagesStorage")
get_send_messages_helper = _getter("org.telegram.messenger.SendMessagesHelper")
get_connections_manager = _getter("org.telegram.tgnet.ConnectionsManager")
get_contacts_controller = _getter("org.telegram.messenger.ContactsController")
get_download_controller = _getter("org.telegram.messenger.DownloadController")
get_file_loader = _getter("org.telegram.messenger.FileLoader")
get_location_controller = _getter("org.telegram.messenger.LocationController")
get_media_data_controller = _getter("org.telegram.messenger.MediaDataController")
get_notification_center = _getter("org.telegram.messenger.NotificationCenter")
get_notifications_controller = _getter("org.telegram.messenger.NotificationsController")
get_notifications_settings = _getter("org.telegram.messenger.NotificationsSettings")
get_secret_chat_helper = _getter("org.telegram.messenger.SecretChatHelper")
get_user_config = _getter("org.telegram.messenger.UserConfig")


def get_media_controller():
    return extera_shims.controller("org.telegram.messenger.MediaController")


def _apply_parse_mode(params, parse_mode):
    if not parse_mode:
        return params
    from extera_utils.text_formatting import parse_text
    field = "caption" if params.get("caption") else "message"
    parsed = parse_text(params.get(field) or "", parse_mode)
    return dict(params, **{field: parsed["message"], "entities": parsed["entities"]})


def send_message(params, parse_mode=None, *, account=None):
    _host().send_message(_account(account), _apply_parse_mode(dict(params), parse_mode))


def send_text(peer, text, *, account=None, parse_mode=None, **kwargs):
    send_message(dict(kwargs, peer=peer, message=text), parse_mode, account=account)


def _send_file(kind, peer, file_path, caption, account, parse_mode, kwargs):
    params = dict(kwargs, peer=peer, path=file_path, caption=caption, kind=kind)
    send_message(params, parse_mode, account=account)


def send_document(peer, file_path, caption="", *, account=None, parse_mode=None, **kwargs):
    _send_file("document", peer, file_path, caption, account, parse_mode, kwargs)


def send_photo(peer, file_path, caption="", high_quality=False, *, account=None,
               parse_mode=None, **kwargs):
    _send_file("photo", peer, file_path, caption, account, parse_mode, kwargs)


def send_video(peer, file_path, caption="", *, account=None, parse_mode=None, **kwargs):
    _send_file("video", peer, file_path, caption, account, parse_mode, kwargs)


def send_audio(peer, file_path, caption="", *, account=None, parse_mode=None, **kwargs):
    _send_file("audio", peer, file_path, caption, account, parse_mode, kwargs)


def edit_message(message_obj, text=None, file_path=None, with_spoiler=False, *,
                 account=None, parse_mode=None, **kwargs):
    extera_shims.host_call("Messages", _account(account), "edit", (message_obj, text, file_path))


def send_request(request, fn, *, account=None):
    callback = getattr(fn, "run", fn)
    return _host().send_request(_account(account), request, callback)


class RequestCallback:
    def __init__(self, fn, account=None):
        self.fn = fn

    def run(self, response, error):
        self.fn(response, error)


class NotificationCenterDelegate:
    def didReceivedNotification(self, id, account, args):
        pass


class AccountClient:
    def __init__(self, account):
        self.account = account

    def __getattr__(self, name):
        target = globals().get(name)
        if not callable(target) or name.startswith("_"):
            raise AttributeError(name)
        if name.startswith("get_"):
            return lambda: target(self.account)
        return lambda *args, **kwargs: target(*args, account=self.account, **kwargs)


def get_client(account=None):
    return AccountClient(_account(account))
