import base64
import http.client
import json
from pathlib import Path
import subprocess
import sys
import threading
import unittest
from unittest import mock
from http.server import ThreadingHTTPServer

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import speech_audio as speech
from app import handler_type

WAVE = b'RIFF' + bytes(4) + b'WAVE' + bytes(32)


class SpeechTests(unittest.TestCase):
    def setUp(self):
        speech.synthesize.cache_clear()

    def test_plain_text_is_validated_before_engine(self):
        for text in (None, '', ' ', 'x'*121, 'bad\x00text', []):
            with self.subTest(text=text), self.assertRaises((ValueError, TypeError)):
                speech.validate_text(text)
        self.assertEqual(speech.validate_text(' 杯子 '), '杯子')

    def test_text_is_stdin_data_and_repeated_audio_is_cached(self):
        text = '杯子；$camera = 123'
        result = subprocess.CompletedProcess([], 0, base64.b64encode(WAVE), b'')
        with mock.patch.object(speech, 'status', return_value={'available': True}), mock.patch.object(speech.subprocess, 'run', return_value=result) as run:
            value = speech.synthesize(text)
            self.assertEqual(base64.b64decode(value['audio'].split(',')[1]), WAVE)
            self.assertFalse(value['network_used'])
            speech.synthesize(text)
            self.assertEqual(run.call_count, 1)
            args, kwargs = run.call_args
            self.assertEqual(base64.b64decode(kwargs['input']).decode('utf-8'), text)
            self.assertEqual(base64.b64decode(args[0][-1]).decode('utf-16-le'), speech.SCRIPT)
            self.assertNotIn(text, speech.SCRIPT)

    def test_unavailable_failed_and_invalid_audio_do_not_report_success(self):
        with mock.patch.object(speech, 'status', return_value={'available': False}), self.assertRaises(RuntimeError):
            speech.synthesize('杯子')
        for completed in (subprocess.CompletedProcess([], 1, b'', b'error'), subprocess.CompletedProcess([], 0, b'not-audio', b'')):
            with mock.patch.object(speech, 'status', return_value={'available': True}), mock.patch.object(speech.subprocess, 'run', return_value=completed), self.assertRaises(RuntimeError):
                speech.synthesize('杯子')

    def test_timeout_releases_busy_lock(self):
        with mock.patch.object(speech, 'status', return_value={'available': True}), mock.patch.object(speech.subprocess, 'run', side_effect=subprocess.TimeoutExpired('tts', 12)), self.assertRaises(RuntimeError):
            speech.synthesize('杯子')
        self.assertFalse(speech.LOCK.locked())

    def test_http_audio_and_origin_restriction(self):
        class Quiet(handler_type(None)):
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), Quiet)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        def request(method, route, payload=None, origin=None):
            connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
            headers = {'Content-Type': 'application/json'}
            if origin:
                headers['Origin'] = origin
            connection.request(method, route, json.dumps(payload) if payload is not None else None, headers)
            response = connection.getresponse()
            value = response.status, json.loads(response.read())
            connection.close()
            return value
        try:
            self.assertEqual(request('GET', '/api/vision/speech/status')[0], 200)
            self.assertEqual(request('POST', '/api/vision/speech', {'text': ''})[0], 400)
            self.assertEqual(request('POST', '/api/vision/speech', {'text': '杯子'}, 'https://external.invalid')[0], 403)
            with mock.patch.object(speech, 'synthesize', return_value={'audio': 'data:audio/wav;base64,test', 'network_used': False}):
                code, value = request('POST', '/api/vision/speech', {'text': '杯子'})
                self.assertEqual(code, 200)
                self.assertFalse(value['network_used'])
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
