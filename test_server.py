import io
import json
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

import server


def response(payload):
    return io.BytesIO(json.dumps(payload, ensure_ascii=False).encode("utf-8"))


def valid_payload(uid="306936843", name="雨说体育徐静雨"):
    return {"code": 0, "data": {"card": {"mid": uid, "name": name, "face": "https://i0.hdslb.com/bfs/face/test.jpg", "level_info": {"current_level": 6}}, "follower": 1773469}}


class InputTests(unittest.TestCase):
    def test_uid_and_space_urls(self):
        values = ["306936843", " 306936843 ", "000306936843", "https://space.bilibili.com/306936843", "http://space.bilibili.com/306936843/", "space.bilibili.com/306936843/video?tid=0", "https://space.bilibili.com/306936843?spm_id_from=333.1007#top"]
        for value in values:
            with self.subTest(value=value):
                self.assertEqual(server.parse_uid(value), "306936843")

    def test_reject_invalid_and_foreign_urls(self):
        values = ["", "0", "-1", "1.5", "abc", "１２３", "1e6", "9223372036854775808", "9" * 3000, "https://evil.test/306936843", "https://space.bilibili.com.evil.test/306936843", "https://space.bilibili.com@evil.test/306936843", "https://space.bilibili.com/", "https://space.bilibili.com/306936843abc", "file:///306936843", "https://space.bilibili.com:443/306936843"]
        for value in values:
            with self.subTest(value=value), self.assertRaises(server.LookupFailure) as error:
                server.parse_uid(value)
            self.assertEqual(error.exception.status, 400)


class UpstreamTests(unittest.TestCase):
    @patch("server.urlopen")
    def test_unicode_and_identity(self, open_mock):
        open_mock.return_value = response(valid_payload())
        result = server.fetch_profile("306936843")
        self.assertEqual(result["nickname"], "雨说体育徐静雨")
        self.assertEqual(result["uid"], "306936843")
        self.assertEqual(result["followers"], 1773469)
        self.assertNotIn("Cookie", open_mock.call_args.args[0].headers)

    @patch("server.urlopen")
    def test_missing_and_mismatched_users(self, open_mock):
        for payload in [{"code": -404}, {"code": 0, "data": {"card": {}}}, valid_payload("2")]:
            open_mock.return_value = response(payload)
            with self.assertRaises(server.LookupFailure) as error:
                server.fetch_profile("306936843")
            self.assertEqual(error.exception.status, 404)

    @patch("server.urlopen")
    def test_limits_and_network_errors(self, open_mock):
        cases = [(HTTPError(server.API, 412, "limited", None, None), "rate_limited"), (URLError("DNS failed"), "network_error"), (TimeoutError(), "timeout")]
        for error, expected in cases:
            open_mock.side_effect = error
            with self.assertRaises(server.LookupFailure) as raised:
                server.fetch_profile("306936843")
            self.assertEqual(raised.exception.code, expected)
        open_mock.side_effect = None
        open_mock.return_value = response({"code": -352})
        with self.assertRaises(server.LookupFailure) as raised:
            server.fetch_profile("306936843")
        self.assertEqual(raised.exception.code, "rate_limited")

    @patch("server.urlopen", return_value=io.BytesIO(b"<html>blocked</html>"))
    def test_non_json_response(self, open_mock):
        with self.assertRaises(server.LookupFailure):
            server.fetch_profile("306936843")

    def test_avatar_allowlist(self):
        self.assertEqual(server.safe_avatar("javascript:alert(1)"), "")
        self.assertEqual(server.safe_avatar("https://evil.test/avatar.jpg"), "")
        self.assertEqual(server.safe_avatar("http://i0.hdslb.com/test.jpg"), "https://i0.hdslb.com/test.jpg")


class CacheTests(unittest.TestCase):
    def setUp(self):
        server.cache.clear()
        server.last_request = 0

    @patch("server.fetch_profile", return_value={"uid": "2", "nickname": "测试"})
    def test_cache_expiry_and_failure_not_cached(self, fetch_mock):
        self.assertFalse(server.lookup("2")["cached"])
        self.assertTrue(server.lookup("https://space.bilibili.com/2")["cached"])
        self.assertEqual(fetch_mock.call_count, 1)
        server.cache["2"] = (0, {"uid": "2", "nickname": "旧昵称"})
        with patch("server.time.sleep"):
            self.assertFalse(server.lookup("2")["cached"])
        self.assertEqual(fetch_mock.call_count, 2)
        fetch_mock.side_effect = server.LookupFailure("temporary")
        with patch("server.time.sleep"), self.assertRaises(server.LookupFailure):
            server.lookup("3")
        self.assertNotIn("3", server.cache)


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = server.LocalHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.httpd.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join()

    def test_ui_assets_and_health(self):
        for path in ("/", "/app.js", "/batch.js", "/style.css", "/favicon.svg", "/api/health"):
            with urlopen(self.base + path) as result:
                self.assertEqual(result.status, 200)
                self.assertTrue(result.read())
                self.assertEqual(result.headers["Cache-Control"], "no-store")

    def test_invalid_input_does_not_call_bilibili(self):
        with patch("server.fetch_profile") as fetch_mock, self.assertRaises(HTTPError) as error:
            urlopen(self.base + "/api/user?uid=abc")
        self.assertEqual(error.exception.code, 400)
        self.assertEqual(json.load(error.exception)["code"], "invalid_uid")
        fetch_mock.assert_not_called()

    def test_no_source_file_exposure(self):
        with self.assertRaises(HTTPError) as error:
            urlopen(self.base + "/server.py")
        self.assertEqual(error.exception.code, 404)

    def test_second_server_cannot_share_the_port(self):
        with self.assertRaises(OSError):
            with server.LocalHTTPServer(("127.0.0.1", self.httpd.server_port), server.Handler):
                pass


class LaunchTests(unittest.TestCase):
    @patch("server.webbrowser.open")
    @patch("server.urlopen")
    @patch("server.LocalHTTPServer", side_effect=OSError("occupied"))
    def test_old_version_is_not_silently_reopened(self, server_mock, open_mock, browser_mock):
        open_mock.return_value = response({"app": "bilibili-uid-lookup", "version": "1.1.0"})
        with patch("sys.argv", ["server.py", "--open"]), self.assertRaises(SystemExit) as error:
            server.main()
        self.assertIn("older", str(error.exception))
        browser_mock.assert_not_called()

    @patch("server.webbrowser.open")
    @patch("server.urlopen")
    @patch("server.LocalHTTPServer", side_effect=OSError("occupied"))
    def test_current_version_can_be_reopened(self, server_mock, open_mock, browser_mock):
        open_mock.return_value = response({"app": "bilibili-uid-lookup", "version": server.VERSION})
        with patch("sys.argv", ["server.py", "--open"]):
            server.main()
        browser_mock.assert_called_once_with("http://127.0.0.1:18763")


if __name__ == "__main__":
    unittest.main()
