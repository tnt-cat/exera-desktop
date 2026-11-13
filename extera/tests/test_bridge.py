import json
import os
import shutil
import sys
import tempfile
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "sdk"))

calls = []


def _call(name, payload):
    data = json.loads(payload)
    calls.append((name, data))
    if name == "user_id":
        return "777"
    if name == "ui_post":
        pending.append(data["token"])
    return "null"


pending = []
fake = types.ModuleType("_extera_host")
fake.call = _call
sys.modules["_extera_host"] = fake

import extera_bridge  # noqa: E402
import extera_scan  # noqa: E402


def call(name, **payload):
    answer = json.loads(extera_bridge.call(name, json.dumps(payload)))
    if not answer["ok"]:
        raise AssertionError(answer["trace"])
    return answer["result"]


def pump():
    while pending:
        call("ui_run", token=pending.pop(0))


class BridgeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp()
        cls.plugins = os.path.join(cls.root, "plugins")
        os.makedirs(cls.plugins)
        for name in ("hello.plugin", "commands.plugin"):
            shutil.copy(os.path.join(HERE, "plugins", name), cls.plugins)
        cls.listed = call("start", plugins_dir=cls.plugins, data_dir=os.path.join(cls.root, "data"))

    def test_start_lists_plugins(self):
        ids = {item["id"] for item in self.listed}
        self.assertEqual(ids, {"hello_plugin", "commands"})
        self.assertTrue(all(item["loaded"] for item in self.listed))

    def test_send_hook(self):
        result = call("send_hook", peer=123, text="plain")
        self.assertEqual(result, {"cancel": False, "text": "plain ok", "entities": []})
        result = call("send_hook", peer=123, text=".ping")
        self.assertTrue(result["cancel"])
        sent = [data for name, data in calls if name == "send_message"]
        self.assertEqual(sent[-1]["peer"], 123)
        self.assertEqual(sent[-1]["text"], "pong from 777")
        self.assertEqual(sent[-1]["entities"], [{"type": "bold", "offset": 0, "length": 4, "url": ""}])

    def test_menu_and_alert(self):
        items = call("menu", location="main_menu")
        self.assertEqual([item["text"] for item in items], ["About"])
        call("menu_click", id=items[0]["id"])
        pump()
        alert = [data for name, data in calls if name == "alert"][-1]
        self.assertEqual(alert["title"], "About")
        self.assertEqual(alert["buttons"], [[-1, "OK"]])
        call("alert_click", id=alert["id"], which=-1)

    def test_toggle_and_delete(self):
        info = call("set_enabled", id="hello_plugin", enabled=False)
        self.assertFalse(info["loaded"])
        info = call("set_enabled", id="hello_plugin", enabled=True)
        self.assertTrue(info["loaded"])
        target = os.path.join(self.root, "deep.plugin")
        shutil.copy(os.path.join(HERE, "plugins", "deep.plugin"), target)
        info = call("install", path=target)
        self.assertEqual(info["status"], "partial")
        self.assertTrue(os.path.exists(os.path.join(self.plugins, info["id"] + ".plugin")))
        call("delete", id=info["id"])
        self.assertNotIn(info["id"], {item["id"] for item in call("list")})

    def test_pin_and_modes(self):
        call("set_pinned", id="hello_plugin", pinned=True)
        self.assertEqual(call("list")[0]["id"], "hello_plugin")
        call("set_pinned", id="hello_plugin", pinned=False)
        self.assertEqual(call("list")[0]["id"], "commands")

        listed = call("set_mode", engine_on=True, safe_mode=True)
        self.assertFalse(any(item["loaded"] for item in listed))
        answer = json.loads(extera_bridge.call(
            "set_enabled", json.dumps({"id": "hello_plugin", "enabled": True})))
        self.assertFalse(answer["ok"])
        listed = call("set_mode", engine_on=False, safe_mode=False)
        self.assertFalse(any(item["loaded"] for item in listed))
        listed = call("set_mode", engine_on=True, safe_mode=False)
        self.assertTrue(all(item["loaded"] for item in listed))
        self.assertEqual(call("about")["sdk"], "1.4.6.3")

    def test_inspect_and_install_choice(self):
        source = os.path.join(HERE, "plugins", "deep.plugin")
        info = call("inspect", path=source)
        self.assertFalse(info["installed"])
        self.assertEqual(info["status"], "partial")
        installed = call("install", path=source, enable=False)
        self.assertFalse(installed["enabled"])
        again = call("inspect", path=source)
        self.assertTrue(again["installed"])
        self.assertEqual(again["old_version"], installed["version"])
        call("delete", id=installed["id"])
        installed = call("install", path=source, enable=True)
        self.assertTrue(installed["enabled"])
        call("delete", id=installed["id"])

    def test_settings(self):
        listed = {item["id"]: item for item in call("list")}
        self.assertTrue(listed["hello_plugin"]["has_settings"])
        rows = call("settings", id="hello_plugin")
        self.assertTrue(rows)
        switch = next(row for row in rows if row["type"] == "switch")
        call("set_setting", id="hello_plugin", key=switch["key"], value=not switch["value"])
        again = next(row for row in call("settings", id="hello_plugin") if row["key"] == switch["key"])
        self.assertEqual(again["value"], not switch["value"])

    def test_scan(self):
        scan = extera_scan.scan
        self.assertEqual(scan("import requests\nfrom base_plugin import BasePlugin")[0], "works")
        self.assertEqual(scan("from org.telegram.tgnet import TLRPC")[0], "works")
        self.assertEqual(scan("from android.widget import TextView")[0], "partial")
        self.assertEqual(scan("from dalvik.system import InMemoryDexClassLoader")[0], "broken")
        self.assertEqual(scan("from android.hardware import SensorManager")[0], "phone")
        self.assertEqual(scan("x = 1", "Round video tools")[0], "phone")
        self.assertEqual(scan("def (")[0], "broken")


if __name__ == "__main__":
    unittest.main()
