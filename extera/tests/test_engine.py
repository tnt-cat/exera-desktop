import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "sdk"))

import client_utils  # noqa: E402
import extera_engine  # noqa: E402
from extera_engine import engine  # noqa: E402
from extera_shims import SendMessageParams  # noqa: E402
from markdown_utils import parse_markdown  # noqa: E402
from extera_utils.text_formatting import parse_text  # noqa: E402


class FakeHost(extera_engine.Host):
    def __init__(self):
        self.dir = tempfile.mkdtemp()
        self.logs = []
        self.bulletins = []
        self.alerts = []
        self.sent = []
        self.requests = []

    def data_dir(self):
        return self.dir

    def log(self, text):
        self.logs.append(text)

    def user_id(self, account):
        return 777

    def show_bulletin(self, kind, text, extra=None):
        self.bulletins.append((kind, text))

    def show_alert(self, alert):
        self.alerts.append(alert)

    def send_message(self, account, params):
        self.sent.append(params)

    def send_request(self, account, request, callback):
        self.requests.append(request)
        callback("result", None)
        return 1

    def method_hook_keys(self):
        return ("org.telegram.ui.Cells.ChatMessageCell.setMessageObject",)


class Message:
    def __init__(self, out):
        self.out = out

    def isOut(self):
        return self.out

    def getId(self):
        return 42


def plugin(name):
    return os.path.join(HERE, "plugins", name + ".plugin")


class EngineTest(unittest.TestCase):
    def setUp(self):
        self.host = FakeHost()
        extera_engine.set_host(self.host)
        for plugin_id in list(engine.plugins):
            engine.unload(plugin_id)

    def send(self, text):
        return engine.execute_send_message_hook(0, SendMessageParams(text, 100))

    def test_send_hook_and_settings(self):
        engine.load_file(plugin("hello"))
        self.assertEqual(self.send("hi").message, "hi ok")
        items = engine.settings_for("hello_plugin")
        self.assertEqual([item.type for item in items], ["header", "switch"])
        engine.change_setting("hello_plugin", "enabled", False)
        self.assertEqual(self.send("hi").message, "hi")
        self.assertIn("[hello_plugin] enabled=False", self.host.logs)
        engine.unload("hello_plugin")
        engine.load_file(plugin("hello"))
        self.assertEqual(self.send("hi").message, "hi")

    def test_commands_chain(self):
        engine.load_file(plugin("hello"))
        engine.load_file(plugin("commands"))
        self.assertIsNone(self.send(".ping"))
        sent = self.host.sent[0]
        self.assertEqual(sent["message"], "pong from 777")
        self.assertEqual(type(sent["entities"][0]).__name__, "TL_messageEntityBold")
        self.assertEqual(self.send(".dp").message, "[8, 0] Hello")
        self.assertEqual(self.send("plain").message, "plain ok")
        self.assertIsNone(self.send(".search"))
        self.assertEqual(type(self.host.requests[0]).__name__, "TL_messages_search")
        self.assertEqual(self.host.bulletins, [("success", "found result")])

    def test_request_hooks(self):
        engine.load_file(plugin("commands"))
        self.assertIsNone(engine.execute_pre_request_hook("TL_messages_readHistory", 0, object()))
        request = object()
        self.assertIs(engine.execute_pre_request_hook("TL_messages_search", 0, request), request)

    def test_menu(self):
        engine.load_file(plugin("commands"))
        context = {"message": Message(True)}
        items = engine.menu_for("message_context_menu", context)
        self.assertEqual([item.text for item in items], ["Message id"])
        self.assertEqual(engine.menu_for("message_context_menu", {"message": Message(False)}), [])
        engine.click_menu_item(items[0].item_id, context)
        self.assertEqual(self.host.bulletins, [("info", "42")])
        about = engine.menu_for("main_menu", {})
        engine.click_menu_item(about[0].item_id, {})
        alert = self.host.alerts[0]
        self.assertEqual((alert.title, alert.message), ("About", "v1"))
        alert.click(alert.BUTTON_POSITIVE)
        self.assertFalse(alert.shown)

    def test_android_plugin_degrades(self):
        loaded = engine.load_file(plugin("deep"))
        self.assertEqual(loaded.unsupported, ["org.telegram.ui.ChatActivity.isSwipeBackEnabled"])
        key = "org.telegram.ui.Cells.ChatMessageCell.setMessageObject"
        engine.fire_method_hook(key, None, [None], after=True)
        engine.fire_method_hook(key, None, ["msg"], after=True)
        self.assertEqual(loaded.instance.seen, ["msg"])
        param = engine.fire_method_hook("org.telegram.ui.ChatActivity.isSwipeBackEnabled", None, [])
        self.assertIs(param.result, False)
        self.assertTrue(param.returnEarly)
        item = engine.menu_for("chat_action_menu", {})[0]
        engine.click_menu_item(item.item_id, {})
        self.assertTrue(any("android.widget.LinearLayout is not available" in line
                            for line in self.host.logs))
        self.assertIn("deep", engine.plugins)

    def test_bad_plugin(self):
        path = os.path.join(self.host.dir, "bad.plugin")
        with open(path, "w") as f:
            f.write('__id__ = "bad"\n__name__ = "Bad"\nraise RuntimeError("boom")\n')
        with self.assertRaises(RuntimeError):
            engine.load_file(path)
        self.assertNotIn("bad", engine.plugins)

    def test_text_formatting(self):
        parsed = parse_markdown("a **b** `c` [d](http://e) 😀 ~~f~~")
        self.assertEqual(parsed.text, "a b c d 😀 f")
        self.assertEqual([(type(e).__name__, e.offset, e.length) for e in parsed.entities], [
            ("TL_messageEntityBold", 2, 1), ("TL_messageEntityCode", 4, 1),
            ("TL_messageEntityTextUrl", 6, 1), ("TL_messageEntityStrike", 11, 1)])
        html = parse_text('<b>x</b> <a href="http://y">z</a><br><blockquote>q</blockquote>')
        self.assertEqual(html["message"], "x z\nq")
        self.assertEqual(html["entities"][1].url, "http://y")

    def test_queue(self):
        done = []
        client_utils.run_on_queue(lambda: done.append(1))
        client_utils.get_queue_by_name(client_utils.PLUGINS_QUEUE).tasks.join()
        self.assertEqual(done, [1])


if __name__ == "__main__":
    unittest.main()
