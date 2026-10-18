"""Mock-only power API tests: no OS execution-state or power configuration call."""
import json
import unittest
from unittest.mock import patch

import sector_v48_main_awake as awake


class AwakeTests(unittest.TestCase):
    def setUp(self):
        self.platform = patch.object(awake.sys, "platform", "win32")
        self.api = patch.object(awake, "_set_thread_execution_state")
        self.platform.start()
        self.fake = self.api.start()
        self.addCleanup(self.platform.stop)
        self.addCleanup(self.api.stop)

    def test_lifetime_request_clear_and_serializable_records(self):
        self.fake.side_effect = [awake.ES_CONTINUOUS, awake.FLAGS]
        token = awake.acquire()
        self.assertEqual(token["status"], "active")
        self.assertEqual(token["flags"], 0x80000001)
        result = awake.release(token)
        self.assertEqual(result["status"], "released")
        self.assertEqual(self.fake.call_args_list[1].args, (awake.ES_CONTINUOUS,))
        self.assertFalse(token["permanent_power_configuration_changed"])
        json.dumps([token, result], allow_nan=False)

    def test_finally_releases_after_operation_exception(self):
        self.fake.side_effect = [awake.ES_CONTINUOUS, awake.FLAGS]
        token = awake.acquire()
        with self.assertRaisesRegex(RuntimeError, "synthetic"):
            try:
                raise RuntimeError("synthetic operation failure")
            finally:
                result = awake.release(token)
        self.assertEqual(result["status"], "released")
        self.assertEqual(self.fake.call_count, 2)

    def test_preserves_preexisting_thread_requirement(self):
        prior = awake.ES_CONTINUOUS | 2
        self.fake.side_effect = [prior, awake.FLAGS]
        result = awake.release(awake.acquire())
        self.assertEqual(result["restore_flags"], prior)
        self.assertEqual(result["status"], "released")

    def test_null_acquire_is_not_a_success_and_no_release_api(self):
        self.fake.return_value = 0
        token = awake.acquire()
        self.assertEqual(token["status"], "request_failed")
        self.assertEqual(awake.release(token)["status"], "no_active_request")
        self.assertEqual(self.fake.call_count, 1)

    def test_api_exception_retained(self):
        self.fake.side_effect = OSError("synthetic exception")
        token = awake.acquire()
        self.assertEqual(token["status"], "request_failed")
        self.assertEqual(token["error_type"], "OSError")

    def test_wrong_thread_does_not_claim_release(self):
        self.fake.return_value = awake.ES_CONTINUOUS
        token = awake.acquire()
        with patch.object(awake.threading, "get_native_id", return_value=token["owner_thread_id"] + 1):
            result = awake.release(token)
        self.assertEqual(result["status"], "wrong_thread")
        self.assertFalse(token["released"])
        self.assertEqual(self.fake.call_count, 1)

    def test_release_failure_retained_and_retry_explicit(self):
        self.fake.side_effect = [awake.ES_CONTINUOUS, 0, awake.FLAGS]
        token = awake.acquire()
        self.assertEqual(awake.release(token)["status"], "release_failed")
        self.assertFalse(token["released"])
        self.assertEqual(awake.release(token)["status"], "released")
        self.assertEqual(awake.release(token)["status"], "already_released")
        self.assertEqual(self.fake.call_count, 3)

    def test_unsupported_platform_does_not_call_windows(self):
        with patch.object(awake.sys, "platform", "synthetic_other_platform"):
            token = awake.acquire()
            self.assertEqual(token["status"], "unsupported_platform")
        self.fake.assert_not_called()

    def test_invalid_token_and_invalid_return_fail(self):
        self.assertEqual(awake.release(None)["status"], "invalid_token")
        self.fake.return_value = True
        self.assertEqual(awake.acquire()["status"], "request_failed")


if __name__ == "__main__":
    unittest.main(verbosity=2)
