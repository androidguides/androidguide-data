import ftplib
import os
import unittest
from unittest import mock

import push_to_wp


class FakeFTPS:
    def __init__(self, *, context=None, timeout=None):
        self.files = {
            "devices.json": b"old-json",
            "devices-static.html": b"old-html",
        }
        self.protected = False
        self.fail_rename_for = None

    def connect(self, host, port):
        self.host = host
        self.port = port

    def login(self, user, password):
        self.user = user
        self.password = password

    def prot_p(self):
        self.protected = True

    def storbinary(self, command, stream):
        self.files[command.removeprefix("STOR ")] = stream.read()

    def retrbinary(self, command, callback):
        name = command.removeprefix("RETR ")
        if name not in self.files:
            raise ftplib.error_perm("550 missing")
        callback(self.files[name])

    def rename(self, source, target):
        if target == self.fail_rename_for:
            self.fail_rename_for = None
            raise ftplib.error_temp("450 simulated promotion failure")
        self.files[target] = self.files.pop(source)

    def delete(self, name):
        if name not in self.files:
            raise ftplib.error_perm("550 missing")
        del self.files[name]

    def quit(self):
        pass

    def close(self):
        pass


class PushToWordPressTests(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ, {
            "SG_FTPS_HOST": "ftp.example.test",
            "SG_FTPS_USER": "directory-only-user",
            "SG_FTPS_PASSWORD": "secret",
            "SG_FTPS_PORT": "21",
        })
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def test_sgcaptcha_is_identified_explicitly(self):
        response = mock.MagicMock()
        response.status = 202
        response.geturl.return_value = push_to_wp.ENDPOINT
        response.read.return_value = (
            b'<meta http-equiv="refresh" '
            b'content="0;/.well-known/sgcaptcha/?r=%2Fwp-json%2Fandroidguide">'
        )
        response.__enter__.return_value = response
        with mock.patch("urllib.request.urlopen", return_value=response):
            result = push_to_wp.push_once("devices.json", b"{}", "auth")
        self.assertFalse(result.ok)
        self.assertTrue(result.retryable)
        self.assertEqual(result.reason, "sgcaptcha")

    def test_generic_non_json_does_not_trigger_ftps_reason(self):
        response = mock.MagicMock()
        response.status = 200
        response.geturl.return_value = push_to_wp.ENDPOINT
        response.read.return_value = b"not json"
        response.__enter__.return_value = response
        with mock.patch("urllib.request.urlopen", return_value=response):
            result = push_to_wp.push_once("devices.json", b"{}", "auth")
        self.assertEqual(result.reason, "non_json")

    def test_main_falls_back_with_the_complete_pair_only_for_sgcaptcha(self):
        files = {"devices.json": b"new-json", "devices-static.html": b"new-html"}
        challenge = push_to_wp.AttemptResult(False, True, "sgcaptcha", "challenge")
        with mock.patch.dict(os.environ, {
            "WP_APP_USER": "admin",
            "WP_APP_PASSWORD": "application-password",
        }), mock.patch.object(push_to_wp, "_local_files", return_value=files), \
             mock.patch.object(push_to_wp, "push_file", return_value=challenge), \
             mock.patch.object(push_to_wp, "publish_via_ftps") as fallback:
            self.assertEqual(0, push_to_wp.main([]))
        fallback.assert_called_once_with(files)

    def test_main_does_not_hide_a_generic_non_json_failure(self):
        files = {"devices.json": b"new-json", "devices-static.html": b"new-html"}
        failure = push_to_wp.AttemptResult(False, True, "non_json", "bad response")
        with mock.patch.dict(os.environ, {
            "WP_APP_USER": "admin",
            "WP_APP_PASSWORD": "application-password",
        }), mock.patch.object(push_to_wp, "_local_files", return_value=files), \
             mock.patch.object(push_to_wp, "push_file", return_value=failure), \
             mock.patch.object(push_to_wp, "publish_via_ftps") as fallback:
            self.assertEqual(1, push_to_wp.main([]))
        fallback.assert_not_called()

    def test_ftps_publish_protects_data_channel_and_verifies_pair(self):
        client = FakeFTPS()
        files = {"devices.json": b"new-json", "devices-static.html": b"new-html"}
        push_to_wp.publish_via_ftps(files, factory=lambda **kwargs: client)
        self.assertTrue(client.protected)
        self.assertEqual(client.files["devices.json"], b"new-json")
        self.assertEqual(client.files["devices-static.html"], b"new-html")
        self.assertFalse(any(name.endswith((".tmp", ".rollback")) for name in client.files))

    def test_failed_second_promotion_restores_first_live_file(self):
        client = FakeFTPS()
        client.fail_rename_for = "devices-static.html"
        files = {"devices.json": b"new-json", "devices-static.html": b"new-html"}
        with self.assertRaisesRegex(RuntimeError, "previous live bytes were restored"):
            push_to_wp.publish_via_ftps(files, factory=lambda **kwargs: client)
        self.assertEqual(client.files["devices.json"], b"old-json")
        self.assertEqual(client.files["devices-static.html"], b"old-html")

    def test_preflight_changes_no_live_file(self):
        client = FakeFTPS()
        before = dict(client.files)
        push_to_wp.ftps_preflight(factory=lambda **kwargs: client)
        self.assertEqual(client.files, before)

    def test_preflight_rejects_the_wrong_account_home(self):
        client = FakeFTPS()
        del client.files["devices-static.html"]
        with self.assertRaisesRegex(ftplib.error_perm, "550 missing"):
            push_to_wp.ftps_preflight(factory=lambda **kwargs: client)


if __name__ == "__main__":
    unittest.main()
