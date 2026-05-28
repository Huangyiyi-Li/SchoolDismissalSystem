import datetime
import unittest

from src.services.api_service import ApiService


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, response_payload):
        self.response_payload = response_payload
        self.calls = []

    def post(self, url, json, headers, timeout, **kwargs):
        self.calls.append(
            {
                "url": url,
                "json": json,
                "headers": headers,
                "timeout": timeout,
                "kwargs": kwargs,
            }
        )
        return FakeResponse(self.response_payload)


class FakeNetworkLogger:
    def __init__(self):
        self.entries = []

    def record(self, **entry):
        self.entries.append(entry)


class ApiServiceV2Tests(unittest.TestCase):
    def test_get_classes_uses_v2_endpoint(self):
        session = FakeSession({"code": 200, "data": [{"classId": "1"}]})
        network_logger = FakeNetworkLogger()
        api = ApiService(
            "40125",
            base_url="https://rest-test.xxt.cn",
            session=session,
            network_logger=network_logger,
        )

        classes = api.get_classes()

        self.assertEqual(classes, [{"classId": "1"}])
        self.assertEqual(
            session.calls[0]["url"],
            "https://rest-test.xxt.cn/kq-http/school-dismissal-system/get-classes-v2",
        )
        self.assertEqual(session.calls[0]["json"], {"schoolId": "40125"})
        self.assertEqual(network_logger.entries[0]["protocol"], "HTTP")
        self.assertEqual(network_logger.entries[0]["direction"], "OUT")
        self.assertEqual(network_logger.entries[0]["request"], {"schoolId": "40125"})
        self.assertEqual(network_logger.entries[0]["response"], {"code": 200, "data": [{"classId": "1"}]})

    def test_push_dismissal_notice_uses_v2_payload(self):
        session = FakeSession({"code": 200, "message": "请求成功"})
        network_logger = FakeNetworkLogger()
        api = ApiService(
            "40125",
            base_url="https://rest-test.xxt.cn",
            session=session,
            network_logger=network_logger,
        )
        post_time = datetime.datetime(2026, 5, 1, 18, 0, 0)

        result = api.push_dismissal_notice(
            class_id="123",
            card_id="9988",
            class_type=2,
            trigger_type=1,
            dismissal_status=1,
            trigger_teacher_id=7,
            trigger_teacher_name="测试老师",
            post_time=post_time,
        )

        self.assertTrue(result)
        self.assertEqual(
            session.calls[0]["url"],
            "https://rest-test.xxt.cn/kq-http/school-dismissal-system/push-dismissal-notice-v2",
        )
        self.assertEqual(
            session.calls[0]["json"],
            {
                "schoolId": "40125",
                "classId": "123",
                "classType": 2,
                "triggerType": 1,
                "cardId": "9988",
                "dismissalStatus": 1,
                "triggerTeacherId": 7,
                "trigger_teacher_name": "测试老师",
                "postTime": "2026-05-01 18:00:00",
            },
        )
        self.assertEqual(network_logger.entries[0]["response"], {"code": 200, "message": "请求成功"})

    def test_get_school_dismissal_schedule_returns_v2_data_list(self):
        payload = {
            "code": 200,
            "data": [
                {
                    "schoolId": "40125",
                    "classType": 1,
                    "schedules": [
                        {
                            "weekday": 1,
                            "timeRanges": [{"startTime": "15:30", "endTime": "16:00"}],
                        }
                    ],
                }
            ],
        }
        session = FakeSession(payload)
        api = ApiService("40125", base_url="https://rest-test.xxt.cn", session=session)

        schedules = api.get_school_dismissal_schedule()

        self.assertEqual(schedules, payload["data"])
        self.assertEqual(
            session.calls[0]["url"],
            "https://rest-test.xxt.cn/kq-http/school-dismissal-system/get-school-dismissal-schedule-v2",
        )


if __name__ == "__main__":
    unittest.main()
