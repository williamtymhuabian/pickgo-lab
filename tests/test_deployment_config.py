"""部署配置测试：只用标准库，不初始化视觉、Node 或网络服务。"""
import builtins
from contextlib import ExitStack, redirect_stderr, redirect_stdout
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app
from Constants import APP
from deployment_config import MAX_CONFIG_BYTES, load_config


class DeploymentConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "deployment.json"
        self.original_app = copy.deepcopy(APP)

    def tearDown(self):
        self.assertEqual(APP, self.original_app)

    def write_config(self, **changes):
        data = {"schema_version": 1, "host": "127.0.0.1",
                "port": 8767, "vision_only": True}
        data.update(changes)
        self.path.write_text(json.dumps(data), encoding="utf-8")
        return self.path

    def test_defaults_are_independent_and_app_is_unchanged(self):
        expected = {"schema_version": 1, "host": APP["host"],
                    "port": APP["port"], "vision_only": False}
        first = load_config()
        self.assertEqual(first, expected)
        first["port"] = 1234
        self.assertEqual(load_config(), expected)
        with mock.patch.dict(APP, {"port": 9876}):
            self.assertEqual(load_config()["port"], 9876)

    def test_valid_types_and_port_boundaries(self):
        for port in (1, 8767, 65535):
            for vision_only in (False, True):
                with self.subTest(port=port, vision_only=vision_only):
                    self.write_config(port=port, vision_only=vision_only)
                    data = load_config(self.path)
                    self.assertEqual(data["port"], port)
                    self.assertIs(data["vision_only"], vision_only)
                    self.assertEqual(data["host"], "127.0.0.1")
                    self.assertEqual(data["schema_version"], 1)

    def test_invalid_field_types_and_boundaries(self):
        invalid = {
            "schema_version": [True, False, 1.0, 0, 2, "1", None, [], {}],
            "host": ["localhost", "0.0.0.0", "::1", "127.0.0.2", 127, True, None, [], {}],
            "port": [True, False, 0, -1, 65536, 8767.0, "8767", None, [], {}],
            "vision_only": [0, 1, 0.0, "true", "false", None, [], {}],
        }
        for key, values in invalid.items():
            for value in values:
                with self.subTest(field=key, value=value):
                    self.write_config(**{key: value})
                    with self.assertRaises(ValueError):
                        load_config(self.path)

    def test_schema_required_and_optional_defaults(self):
        self.path.write_text('{"schema_version":1}', encoding="utf-8")
        self.assertEqual(load_config(self.path), load_config())
        self.path.write_text('{}', encoding="utf-8")
        with self.assertRaises(ValueError):
            load_config(self.path)

    def test_unknown_fields(self):
        self.write_config(extra=True)
        with self.assertRaises(ValueError):
            load_config(self.path)

    def test_duplicate_keys_including_escaped_and_nested(self):
        for raw in (
            '{"schema_version":1,"schema_version":1}',
            '{"schema_version":1,"port":1,"port":2}',
            '{"schema_version":1,"host":"127.0.0.1","host":"127.0.0.1"}',
            '{"schema_version":1,"vision_only":true,"vision_only":false}',
            r'{"schema_version":1,"port":1,"\u0070ort":2}',
            '{"schema_version":1,"port":{"x":1,"x":2}}',
        ):
            with self.subTest(raw=raw):
                self.path.write_text(raw, encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "重复键"):
                    load_config(self.path)

    def test_non_objects_constants_and_malformed_json(self):
        cases = ['[]', 'null', 'true', '1', '"text"', '', '{',
                 '{"schema_version":1} trailing']
        cases += ['{"schema_version":1,"port":' + value + '}'
                  for value in ('NaN', 'Infinity', '-Infinity', '1e999')]
        for raw in cases:
            with self.subTest(raw=raw):
                self.path.write_text(raw, encoding="utf-8")
                with self.assertRaises(ValueError):
                    load_config(self.path)

    def test_size_limit_in_bytes_and_bounded_read(self):
        raw = b'{"schema_version":1}'
        self.path.write_bytes(raw + b' ' * (MAX_CONFIG_BYTES - len(raw)))
        self.assertEqual(load_config(self.path), load_config())
        self.path.write_bytes(self.path.read_bytes() + b' ')
        with self.assertRaises(ValueError):
            load_config(self.path)
        self.path.write_text('{"schema_version":1,"host":"' + '中' * 6000 + '"}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "16 KiB"):
            load_config(self.path)
        fake_open = mock.mock_open(read_data=b' ' * (MAX_CONFIG_BYTES + 1))
        with mock.patch("builtins.open", fake_open), self.assertRaises(ValueError):
            load_config(self.path)
        fake_open().read.assert_called_once_with(MAX_CONFIG_BYTES + 1)

    def test_bad_files(self):
        with self.assertRaises(OSError):
            load_config(self.path)
        with self.assertRaises(OSError):
            load_config(self.temp.name)
        self.path.write_bytes(b'\xff\xfe')
        with self.assertRaises(ValueError):
            load_config(self.path)
        with mock.patch("builtins.open", side_effect=PermissionError("禁止读取")):
            with self.assertRaises(OSError):
                load_config(self.path)

    def test_raspberry_pi_example(self):
        self.assertEqual(load_config(ROOT / "configs" / "raspberry-pi.json"),
                         {"schema_version": 1, "host": "127.0.0.1",
                          "port": 8767, "vision_only": True})

    def test_cli_defaults_and_sys_argv(self):
        args = app.parse_options([])
        self.assertEqual(args.port, APP["port"])
        self.assertEqual(args.host, APP["host"])
        self.assertIs(args.vision_only, False)
        self.assertIs(args.check_config, False)
        with mock.patch.object(sys, "argv", ["app.py", "--port", "0", "--vision-only"]):
            args = app.parse_options()
        self.assertEqual(args.port, 0)
        self.assertIs(args.vision_only, True)

    def test_cli_overrides_config_and_preserves_zero(self):
        self.write_config(port=1234, vision_only=False)
        args = app.parse_options(["--config", str(self.path)])
        self.assertEqual(args.port, 1234)
        self.assertIs(args.vision_only, False)
        for port in (0, 4321):
            for argv in (["--port", str(port), "--vision-only", "--config", str(self.path)],
                         ["--config", str(self.path), "--port", str(port), "--vision-only"]):
                with self.subTest(argv=argv):
                    args = app.parse_options(argv)
                    self.assertEqual(args.port, port)
                    self.assertIs(args.vision_only, True)
        self.write_config(vision_only=True)
        self.assertIs(app.parse_options(["--config", str(self.path)]).vision_only, True)

    def run_without_startup(self, argv, error=False):
        real_import = builtins.__import__

        def guard_import(name, *args, **kwargs):
            if name.split(".")[0] in {"legacy_vision", "object_vision", "numpy", "cv2"}:
                raise AssertionError("不应导入视觉模块: " + name)
            return real_import(name, *args, **kwargs)

        output = io.StringIO()
        with ExitStack() as stack:
            stack.enter_context(mock.patch("builtins.__import__", side_effect=guard_import))
            guards = [stack.enter_context(mock.patch(target, side_effect=AssertionError(target)))
                      for target in ("app.utils.all_init", "robot.all_init", "subprocess.Popen",
                                     "app.ThreadingHTTPServer", "app.handler_type")]
            stack.enter_context(redirect_stdout(output))
            stack.enter_context(redirect_stderr(io.StringIO()))
            if error:
                with self.assertRaises(SystemExit) as caught:
                    app.main(argv)
                self.assertEqual(caught.exception.code, 2)
                self.assertEqual(output.getvalue(), "")
            else:
                self.assertIsNone(app.main(argv))
            for guard in guards:
                guard.assert_not_called()
        return output.getvalue()

    def test_main_check_config_exits_before_all_initialization(self):
        self.assertEqual(json.loads(self.run_without_startup(["--check-config"])), load_config())
        self.write_config(port=1234, vision_only=False)
        output = self.run_without_startup(["--config", str(self.path), "--check-config",
                                           "--port", "0", "--vision-only"])
        self.assertEqual(json.loads(output), {"schema_version": 1, "host": "127.0.0.1",
                                             "port": 0, "vision_only": True})
        with mock.patch.object(sys, "argv", ["app.py", "--check-config"]):
            self.assertEqual(json.loads(self.run_without_startup(None)), load_config())

    def test_invalid_config_fails_before_startup_even_with_cli_override(self):
        for raw in ('{"schema_version":1,"port":0}', '{', '[]',
                    '{"schema_version":true}', '{"schema_version":1,"extra":1}'):
            self.path.write_text(raw, encoding="utf-8")
            for check in ([], ["--check-config"]):
                with self.subTest(raw=raw, check=check):
                    self.run_without_startup(["--config", str(self.path), "--port", "8767",
                                              "--vision-only"] + check, error=True)
        self.run_without_startup(["--config", str(self.path.parent / "missing.json")], error=True)


if __name__ == "__main__":
    unittest.main()
