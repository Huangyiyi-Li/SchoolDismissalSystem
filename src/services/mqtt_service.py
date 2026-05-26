from __future__ import annotations

import datetime
import json
import threading


class DismissalMqttService:
    def __init__(
        self,
        device_no,
        command_handler,
        host="111.6.173.61",
        port=1883,
        heartbeat_interval_seconds=60,
        up_topic=None,
        down_topic=None,
        telemetry_topic=None,
        rpc_request_topic=None,
        rpc_response_topic_template=None,
        client_factory=None,
        clock=None,
    ):
        self.device_no = device_no
        self.command_handler = command_handler
        self.host = host
        self.port = int(port)
        self.heartbeat_interval_seconds = int(heartbeat_interval_seconds)
        self.telemetry_topic = telemetry_topic or up_topic or "v1/devices/me/telemetry"
        self.rpc_request_topic = rpc_request_topic or down_topic or "v1/devices/me/rpc/request/+"
        self.rpc_response_topic_template = (
            rpc_response_topic_template
            or "v1/devices/me/rpc/response/{request_id}"
        )
        self.client_factory = client_factory or self._default_client_factory
        self.clock = clock or self._default_clock
        self.client = None
        self._timer = None
        self._running = False

    def _default_client_factory(self, client_id):
        try:
            import paho.mqtt.client as mqtt
        except ImportError as exc:
            raise RuntimeError("paho-mqtt is not installed") from exc
        return mqtt.Client(client_id=client_id)

    def _default_clock(self):
        return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def start(self):
        if not self.device_no:
            print("[MQTT] Skipping start: device number is not set.")
            return False
        try:
            self.client = self.client_factory(self.device_no)
            self.client.username_pw_set(self.device_no)
            self.client.on_connect = self._handle_connect
            self.client.on_message = self._handle_message
            self.client.connect(self.host, self.port, 60)
            self.client.loop_start()
            self._running = True
            self.publish_heartbeat()
            self._schedule_next_heartbeat()
            print(f"[MQTT] Started for device {self.device_no}")
            return True
        except Exception as exc:
            print(f"[MQTT] Start failed: {exc}")
            return False

    def stop(self):
        self._running = False
        if self._timer:
            self._timer.cancel()
            self._timer = None
        if self.client:
            try:
                self.client.loop_stop()
                self.client.disconnect()
            except Exception as exc:
                print(f"[MQTT] Stop failed: {exc}")

    def _schedule_next_heartbeat(self):
        if not self._running:
            return
        self._timer = threading.Timer(self.heartbeat_interval_seconds, self._heartbeat_tick)
        self._timer.daemon = True
        self._timer.start()

    def _heartbeat_tick(self):
        self.publish_heartbeat()
        self._schedule_next_heartbeat()

    def publish_heartbeat(self):
        client = self.client
        if client is None:
            client = self.client_factory(self.device_no)
            self.client = client
        payload = {
            "HeartBeat": {
                "deviceNo": self.device_no,
                "time": self.clock(),
            }
        }
        client.publish(self.telemetry_topic, json.dumps(payload, ensure_ascii=False), qos=0)

    def _handle_connect(self, client, userdata, flags, rc):
        if rc == 0:
            client.subscribe(self.rpc_request_topic)
            print(f"[MQTT] Subscribed: {self.rpc_request_topic}")
        else:
            print(f"[MQTT] Connect returned rc={rc}")

    def _handle_message(self, client, userdata, message):
        try:
            payload = json.loads(message.payload.decode("utf-8"))
            if payload.get("method") != "ManualDismissal":
                return
            result = self.command_handler(payload.get("params") or {})
            if result is None:
                result = {"result": "success"}
        except Exception as exc:
            print(f"[MQTT] Command failed: {exc}")
            result = {"result": "fail", "message": str(exc)}
        request_id = self._extract_request_id(getattr(message, "topic", ""))
        response_topic = self.rpc_response_topic_template.format(request_id=request_id)
        client.publish(response_topic, json.dumps(result, ensure_ascii=False), qos=0)

    def _extract_request_id(self, topic):
        if not topic:
            return ""
        return topic.rstrip("/").split("/")[-1]
