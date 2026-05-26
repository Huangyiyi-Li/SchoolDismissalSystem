import json
import unittest

from src.services.mqtt_service import DismissalMqttService


class FakeClient:
    def __init__(self):
        self.username = None
        self.connected = None
        self.subscriptions = []
        self.published = []
        self.on_connect = None
        self.on_message = None

    def username_pw_set(self, username, password=None):
        self.username = username

    def connect(self, host, port, keepalive):
        self.connected = (host, port, keepalive)

    def loop_start(self):
        return None

    def loop_stop(self):
        return None

    def disconnect(self):
        return None

    def subscribe(self, topic):
        self.subscriptions.append(topic)

    def publish(self, topic, payload, qos=0):
        self.published.append((topic, json.loads(payload), qos))


class MqttServiceTests(unittest.TestCase):
    def test_start_configures_client_and_subscribes_down_topic(self):
        client = FakeClient()
        service = DismissalMqttService(
            device_no="device-1",
            client_factory=lambda client_id: client,
            command_handler=lambda command: {"result": "success"},
        )

        service.start()
        client.on_connect(client, None, None, 0)

        self.assertEqual(client.username, "device-1")
        self.assertEqual(client.connected, ("111.6.173.61", 1883, 60))
        self.assertEqual(client.subscriptions, ["v1/devices/me/rpc/request/+"])

    def test_publish_heartbeat_uses_document_payload(self):
        client = FakeClient()
        service = DismissalMqttService(
            device_no="device-1",
            client_factory=lambda client_id: client,
            command_handler=lambda command: {"result": "success"},
            clock=lambda: "2026-05-01 18:00:00",
        )

        service.publish_heartbeat()

        self.assertEqual(
            client.published,
            [
                (
                    "v1/devices/me/telemetry",
                    {"HeartBeat": {"deviceNo": "device-1", "time": "2026-05-01 18:00:00"}},
                    0,
                )
            ],
        )

    def test_manual_dismissal_invokes_handler_and_replies_success(self):
        client = FakeClient()
        received = []
        service = DismissalMqttService(
            device_no="device-1",
            client_factory=lambda client_id: client,
            command_handler=lambda command: received.append(command) or {"result": "success"},
        )
        message = type(
            "Message",
            (),
            {
                "payload": json.dumps(
                    {
                        "method": "ManualDismissal",
                        "params": {"classType": 1, "classId": "123"},
                    }
                ).encode("utf-8"),
                "topic": "v1/devices/me/rpc/request/42",
            },
        )()

        service._handle_message(client, None, message)

        self.assertEqual(received, [{"classType": 1, "classId": "123"}])
        self.assertEqual(client.published[-1], ("v1/devices/me/rpc/response/42", {"result": "success"}, 0))

    def test_manual_dismissal_replies_fail_on_handler_error(self):
        client = FakeClient()
        service = DismissalMqttService(
            device_no="device-1",
            client_factory=lambda client_id: client,
            command_handler=lambda command: (_ for _ in ()).throw(ValueError("bad command")),
        )
        message = type(
            "Message",
            (),
            {
                "payload": json.dumps(
                    {
                        "method": "ManualDismissal",
                        "params": {"classType": 1, "classId": "123"},
                    }
                ).encode("utf-8"),
                "topic": "v1/devices/me/rpc/request/43",
            },
        )()

        service._handle_message(client, None, message)

        self.assertEqual(
            client.published[-1],
            ("v1/devices/me/rpc/response/43", {"result": "fail", "message": "bad command"}, 0),
        )


if __name__ == "__main__":
    unittest.main()
