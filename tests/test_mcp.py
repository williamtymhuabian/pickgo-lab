"""真实 stdio 子进程和共享 HTTP 后端测试，不访问外网、不连接实体设备。"""
import hashlib
import http.client
import json
import queue
import subprocess
import sys
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import robot
import utils
from app import handler_type


class Client:
    def __init__(self, *args, no_packages=False):
        self.process = subprocess.Popen([sys.executable, "-B", *(["-S"] if no_packages else []),
                                         str(ROOT / "mcp_server.py"), *args], cwd=ROOT,
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        text=True, encoding="utf-8")
        self.output = queue.Queue()
        self.sequence = 0
        def read():
            for line in self.process.stdout:
                self.output.put(line)
        self.reader = threading.Thread(target=read, daemon=True)
        self.reader.start()

    def send(self, value):
        self.process.stdin.write(json.dumps(value) + "\n")
        self.process.stdin.flush()

    def call(self, method, params=None):
        self.sequence += 1
        self.send({"jsonrpc": "2.0", "id": self.sequence, "method": method, "params": params or {}})
        response = json.loads(self.output.get(timeout=10))
        assert response["id"] == self.sequence, response
        return response

    def init(self, version="2025-11-25"):
        reply = self.call("initialize", {"protocolVersion": version, "capabilities": {},
                                         "clientInfo": {"name": "pickgo-test", "version": "1"}})
        self.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return reply

    def tool(self, name, args=None):
        return self.call("tools/call", {"name": name, "arguments": args or {}})

    def value(self, name, args=None):
        response = self.tool(name, args)
        assert not response["result"]["isError"], response
        return json.loads(response["result"]["content"][0]["text"])

    def close(self):
        self.process.stdin.close()
        try:
            self.process.wait(timeout=6)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=3)
            raise
        self.reader.join(timeout=2)
        self.process.stdout.close()
        errors = self.process.stderr.read()
        self.process.stderr.close()
        assert self.process.returncode == 0, errors
        return errors


class MCPTests(unittest.TestCase):
    def setUp(self):
        self.client = Client("--standalone")

    def tearDown(self):
        self.assertEqual(self.client.close(), "")

    def test_handshake_discovery_and_legacy_version_negotiation(self):
        self.assertEqual(self.client.call("server/discover")["error"]["code"], -32601)
        self.assertEqual(self.client.init("future-version")["result"]["protocolVersion"], "2025-11-25")
        tools = self.client.call("tools/list")["result"]["tools"]
        self.assertEqual({item["name"] for item in tools}, set(utils.TOOL))
        self.assertEqual(self.client.value("get_capabilities")["backend"], "sim")

    def test_action_lifecycle_progress_pause_resume_stop_reset(self):
        self.client.init()
        start = self.client.value("grab_and_send", {"target": "blue", "speed": 6})
        self.assertEqual(start["status"], "RUNNING")
        self.assertTrue(start["task_id"])
        time.sleep(.15)
        running = self.client.value("get_robot_state")
        self.assertGreater(running["time"], start["time"])
        self.assertEqual(running["task_id"], start["task_id"])
        paused = self.client.value("pause_task")
        time.sleep(.15)
        self.assertEqual(self.client.value("get_robot_state")["time"], paused["time"])
        self.assertEqual(self.client.value("resume_task")["status"], "RUNNING")
        self.assertEqual(self.client.value("stop_task")["status"], "CANCELED")
        self.assertIsNone(self.client.value("reset_scene")["task_id"])

    def test_schema_errors_and_execution_errors_are_distinct(self):
        self.client.init()
        for args in [{}, {"target": "green"}, {"target": "red", "speed": True},
                     {"target": "red", "extra": 1}]:
            self.assertEqual(self.client.tool("grab_and_send", args)["error"]["code"], -32602)
        self.assertEqual(self.client.tool("unknown")["error"]["code"], -32602)
        self.assertTrue(self.client.tool("resume_task")["result"]["isError"])
        self.client.value("grab_and_send", {"target": "red"})
        self.assertTrue(self.client.tool("grab_and_send", {"target": "blue"})["result"]["isError"])

    def test_notifications_never_execute_robot_tools(self):
        self.assertEqual(self.client.call("tools/list")["error"]["code"], -32602)
        self.client.init("2024-11-05")
        self.client.send({"jsonrpc": "2.0", "method": "tools/call",
                          "params": {"name": "grab_and_send", "arguments": {"target": "red"}}})
        self.assertEqual(self.client.value("get_robot_state")["status"], "IDLE")

    def test_parse_error_does_not_corrupt_following_request(self):
        self.client.process.stdin.write("invalid json\n")
        self.client.process.stdin.flush()
        self.assertEqual(json.loads(self.client.output.get(timeout=8))["error"]["code"], -32700)
        self.assertEqual(self.client.call("ping")["result"], {})


class IntegrationTests(unittest.TestCase):
    def test_no_optional_python_packages_needed_for_motion(self):
        client = Client("--standalone", no_packages=True)
        try:
            client.init()
            self.assertEqual(client.value("get_robot_state")["status"], "IDLE")
            self.assertFalse(client.value("get_capabilities")["vision_dependencies_installed"])
        finally:
            self.assertEqual(client.close(), "")

    def test_shared_mcp_and_web_state_and_origin_checks(self):
        context = utils.all_init()
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler_type(None, context))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = f"http://127.0.0.1:{server.server_port}"
        client = Client("--server-url", url)
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        try:
            client.init()
            start = client.value("grab_and_send", {"target": "yellow"})
            connection.request("GET", "/api/robot/state")
            state = json.loads(connection.getresponse().read())
            self.assertEqual(state["instance_id"], start["instance_id"])
            self.assertEqual(state["task_id"], start["task_id"])
            self.assertEqual(state["selected"], "yellow")
            self.assertEqual(state["last_command"]["source"], "mcp")
            connection.request("POST", "/api/robot/command", json.dumps({"command": "pause"}), {"Content-Type": "application/json"})
            self.assertEqual(json.loads(connection.getresponse().read())["status"], "PAUSED")
            self.assertEqual(client.value("get_robot_state")["status"], "PAUSED")
            connection.request("POST", "/api/robot/command", '{"command":"reset"}',
                         {"Content-Type": "application/json", "Origin": "https://example.com"})
            response = connection.getresponse()
            self.assertEqual(response.status, 403)
            response.read()
            self.assertEqual(client.value("get_robot_state")["status"], "PAUSED")
            # 关闭 attach 客户端不会关闭共享场景，也不会替用户取消已接收的任务。
            client.close()
            client = None
            self.assertEqual(utils.get_robot_state(context)["status"], "PAUSED")
        finally:
            connection.close()
            if client:
                client.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            utils.close(context)

    def test_vision_tool_executes_original_function(self):
        try:
            import cv2
            import numpy
        except ImportError:
            self.skipTest("Optional vision dependencies not installed")
        from test_vision import fixture, packet
        client = Client("--standalone")
        try:
            client.init()
            image, depth = fixture("blue")
            frame = packet(image, depth, "blue")
            frame.pop("target")
            result = client.value("det_color", {"frame": frame, "target": "blue"})
            self.assertTrue(result["found"])
            self.assertEqual(result["depth"]["mm"], 650)
            self.assertEqual(result["backend"], "original-python-opencv")
        finally:
            self.assertEqual(client.close(), "")

    def test_remote_url_and_unimplemented_hardware_rejected(self):
        for url in ["https://127.0.0.1:8767", "http://example.com:8767", "http://127.0.0.1:8767/x"]:
            with self.assertRaises(ValueError):
                utils.all_init(url)
        with self.assertRaises(ValueError):
            robot.all_init("real")


if __name__ == "__main__":
    unittest.main(verbosity=2)
