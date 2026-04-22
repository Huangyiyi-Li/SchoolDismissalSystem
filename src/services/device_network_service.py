from __future__ import annotations

import ctypes
import concurrent.futures
import ipaddress
import logging
import socket
import sys
import time
from dataclasses import dataclass
from typing import Iterable

from ..utils.path_utils import get_resource_path

LOGGER = logging.getLogger(__name__)

DEFAULT_DEVICE_COMMAND_PORT = 1000
DEFAULT_DEVICE_DISCOVERY_PORT = 51006
DEFAULT_SUBNET_MASK = "255.255.255.0"


class DeviceNetworkError(RuntimeError):
    pass


@dataclass(frozen=True)
class NetworkDiscoveryEntry:
    path: str

    @property
    def label(self) -> str:
        return self.path


@dataclass(frozen=True)
class DeviceNetworkProfile:
    local_ip: str
    subnet_mask: str
    gateway: str
    server_ip: str
    server_port: int
    local_port: int


def parse_device_path_list(raw_buffer: bytes) -> list[str]:
    items: list[str] = []
    for chunk in raw_buffer.split(b"\x00"):
        value = chunk.decode("utf-8", errors="ignore").strip()
        if value:
            items.append(value)
    return items


def normalize_ipv4(ip_text: str) -> str:
    try:
        return str(ipaddress.IPv4Address(ip_text.strip()))
    except ipaddress.AddressValueError as exc:
        raise DeviceNetworkError(f"无效的 IPv4 地址: {ip_text}") from exc


def detect_host_ipv4() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("192.0.2.1", 80))
        detected_ip = sock.getsockname()[0]
        return normalize_ipv4(detected_ip)
    except OSError:
        try:
            return normalize_ipv4(socket.gethostbyname(socket.gethostname()))
        except OSError:
            return "127.0.0.1"
    finally:
        sock.close()


def suggest_device_profile(
    host_ip: str,
    current_ip: str | None,
    occupied_ips: Iterable[str],
    server_port: int,
    local_port: int,
) -> DeviceNetworkProfile:
    host_addr = ipaddress.IPv4Address(normalize_ipv4(host_ip))
    network = ipaddress.IPv4Network(f"{host_addr}/24", strict=False)
    gateway = str(next(network.hosts(), host_addr))
    if gateway == str(host_addr):
        gateway = str(ipaddress.IPv4Address(int(network.network_address) + 1))

    normalized_occupied = {
        str(ipaddress.IPv4Address(ip))
        for ip in occupied_ips
        if _is_valid_ipv4(ip)
    }
    normalized_occupied.discard(str(host_addr))

    chosen_ip = None
    if _is_valid_ipv4(current_ip):
        current_addr = ipaddress.IPv4Address(current_ip)
        if current_addr in network and current_addr != host_addr:
            chosen_ip = str(current_addr)

    if chosen_ip is None:
        candidate_ranges = list(range(80, 100)) + list(range(20, 80)) + list(range(100, 240))
        for suffix in candidate_ranges:
            candidate = str(ipaddress.IPv4Address(int(network.network_address) + suffix))
            if candidate not in normalized_occupied and candidate != str(host_addr):
                chosen_ip = candidate
                break

    if chosen_ip is None:
        raise DeviceNetworkError("未找到可用的推荐 IP，请手动指定。")

    return DeviceNetworkProfile(
        local_ip=chosen_ip,
        subnet_mask=DEFAULT_SUBNET_MASK,
        gateway=gateway,
        server_ip=str(host_addr),
        server_port=int(server_port),
        local_port=int(local_port),
    )


def _is_valid_ipv4(ip_text: str | None) -> bool:
    if not ip_text:
        return False
    try:
        ipaddress.IPv4Address(ip_text.strip())
        return True
    except ipaddress.AddressValueError:
        return False


class RFProSDKBackend:
    def __init__(self, dll_path: str | None = None):
        self.dll_path = dll_path or get_resource_path("vendor/rfpro/win64/comPro.dll")
        self._dll = None
        self._availability_reason = ""
        self._load()

    @property
    def availability_reason(self) -> str:
        return self._availability_reason

    @property
    def is_available(self) -> bool:
        return self._dll is not None

    def _load(self) -> None:
        if sys.platform != "win32":
            self._availability_reason = "网络配置功能仅在 Windows 客户端中可用。"
            return

        windll = getattr(ctypes, "WinDLL", None)
        if windll is None:
            self._availability_reason = "当前 Python 环境不支持加载 Windows DLL。"
            return

        try:
            self._dll = windll(self.dll_path)
        except OSError as exc:
            self._availability_reason = f"未能加载网络配置组件: {exc}"
            LOGGER.exception("Failed to load RFPro SDK DLL")
            self._dll = None
            return

        self._bind_functions()

    def _bind_functions(self) -> None:
        assert self._dll is not None

        self._dll.lc_init_ex.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_long]
        self._dll.lc_init_ex.restype = ctypes.c_int
        self._dll.lc_exit.argtypes = [ctypes.c_int]
        self._dll.lc_exit.restype = ctypes.c_int
        self._dll.lc_devReboot.argtypes = [ctypes.c_int]
        self._dll.lc_devReboot.restype = ctypes.c_int
        self._dll.lc_net_serverStart.argtypes = [ctypes.c_ushort]
        self._dll.lc_net_serverStart.restype = ctypes.c_int
        self._dll.lc_net_serverExit.argtypes = []
        self._dll.lc_net_serverExit.restype = ctypes.c_int
        self._dll.lc_net_termList.argtypes = [ctypes.c_void_p]
        self._dll.lc_net_termList.restype = ctypes.c_int

        for name in (
            "lc_setNet_serverIP",
            "lc_getNet_serverIP",
            "lc_setNet_local_IP",
            "lc_getNet_local_IP",
            "lc_setNet_local_mask",
            "lc_getNet_local_mask",
            "lc_setNet_gateway",
            "lc_getNet_gateway",
        ):
            getattr(self._dll, name).argtypes = [ctypes.c_int, ctypes.c_void_p]
            getattr(self._dll, name).restype = ctypes.c_int

        for name in (
            "lc_setNet_serverPort",
            "lc_getNet_serverPort",
            "lc_setNet_local_port",
            "lc_getNet_local_port",
        ):
            getattr(self._dll, name).argtypes = [ctypes.c_int, ctypes.c_void_p]
            getattr(self._dll, name).restype = ctypes.c_int

        self._dll.lc_setNet_serverPort.argtypes = [ctypes.c_int, ctypes.c_int]
        self._dll.lc_setNet_local_port.argtypes = [ctypes.c_int, ctypes.c_int]

    def discover_devices(
        self,
        listen_port: int = DEFAULT_DEVICE_DISCOVERY_PORT,
        command_port: int = DEFAULT_DEVICE_COMMAND_PORT,
        timeout_seconds: float = 1.5,
    ) -> list[NetworkDiscoveryEntry]:
        self._ensure_available()
        status = self._dll.lc_net_serverStart(int(listen_port))
        if status != 0:
            raise DeviceNetworkError(f"启动设备监听失败，错误码: {status}")

        try:
            deadline = time.time() + timeout_seconds
            best_result: list[str] = []
            while time.time() < deadline:
                buffer = ctypes.create_string_buffer(4096)
                count = self._dll.lc_net_termList(buffer)
                if count > 0:
                    best_result = parse_device_path_list(buffer.raw)
                    if best_result:
                        break
                time.sleep(0.15)
        finally:
            self._dll.lc_net_serverExit()

        if best_result:
            return [NetworkDiscoveryEntry(path=item) for item in best_result]

        fallback_paths = self._scan_local_subnet(command_port=int(command_port))
        return [NetworkDiscoveryEntry(path=item) for item in fallback_paths]

    def read_profile(self, *, current_ip: str | None, current_port: int, device_path: str | None) -> DeviceNetworkProfile:
        handle = self._open_handle(current_ip=current_ip, current_port=current_port, device_path=device_path)
        try:
            return DeviceNetworkProfile(
                local_ip=self._read_ip(handle, self._dll.lc_getNet_local_IP),
                subnet_mask=self._read_ip(handle, self._dll.lc_getNet_local_mask),
                gateway=self._read_ip(handle, self._dll.lc_getNet_gateway),
                server_ip=self._read_ip(handle, self._dll.lc_getNet_serverIP),
                server_port=self._read_port(handle, self._dll.lc_getNet_serverPort),
                local_port=self._read_port(handle, self._dll.lc_getNet_local_port),
            )
        finally:
            self._close_handle(handle)

    def apply_profile(
        self,
        profile: DeviceNetworkProfile,
        *,
        current_ip: str | None,
        current_port: int,
        device_path: str | None,
        reboot: bool = True,
    ) -> None:
        handle = self._open_handle(current_ip=current_ip, current_port=current_port, device_path=device_path)
        try:
            self._write_ip(handle, self._dll.lc_setNet_serverIP, profile.server_ip, "服务器 IP")
            self._write_port(handle, self._dll.lc_setNet_serverPort, profile.server_port, "服务器端口")
            self._write_ip(handle, self._dll.lc_setNet_local_IP, profile.local_ip, "本地 IP")
            self._write_ip(handle, self._dll.lc_setNet_local_mask, profile.subnet_mask, "子网掩码")
            self._write_ip(handle, self._dll.lc_setNet_gateway, profile.gateway, "网关")
            self._write_port(handle, self._dll.lc_setNet_local_port, profile.local_port, "本地端口")
            if reboot:
                status = self._dll.lc_devReboot(handle)
                if status != 0:
                    raise DeviceNetworkError(f"下发成功，但设备重启失败，错误码: {status}")
        finally:
            self._close_handle(handle)

    def _open_handle(self, *, current_ip: str | None, current_port: int, device_path: str | None) -> int:
        self._ensure_available()

        attempts: list[tuple[int, str]] = []
        if device_path:
            attempts.extend([(4, device_path), (5, device_path)])

        if current_ip:
            endpoint = f"{normalize_ipv4(current_ip)}:{int(current_port)}"
            attempts.extend([(5, endpoint), (4, endpoint)])

        last_error = None
        for mode, path in attempts:
            handle = self._dll.lc_init_ex(mode, path.encode("ascii"), 0)
            if handle != -1:
                LOGGER.info("Opened reader network session mode=%s path=%s handle=%s", mode, path, handle)
                return handle
            last_error = f"mode={mode}, path={path}"

        raise DeviceNetworkError(f"无法连接到设备，请确认当前 IP、端口和设备网络模式。最后尝试: {last_error}")

    def _close_handle(self, handle: int) -> None:
        if handle == -1:
            return
        self._dll.lc_exit(handle)

    def _read_ip(self, handle: int, func) -> str:
        data = (ctypes.c_ubyte * 4)()
        status = func(handle, data)
        if status != 0:
            raise DeviceNetworkError(f"读取网络参数失败，错误码: {status}")
        return ".".join(str(part) for part in data)

    def _read_port(self, handle: int, func) -> int:
        port = ctypes.c_int()
        status = func(handle, ctypes.byref(port))
        if status != 0:
            raise DeviceNetworkError(f"读取端口失败，错误码: {status}")
        return int(port.value)

    def _write_ip(self, handle: int, func, ip_text: str, label: str) -> None:
        normalized = normalize_ipv4(ip_text)
        data = (ctypes.c_ubyte * 4)(*ipaddress.IPv4Address(normalized).packed)
        status = func(handle, data)
        if status != 0:
            raise DeviceNetworkError(f"设置{label}失败，错误码: {status}")

    def _write_port(self, handle: int, func, port: int, label: str) -> None:
        status = func(handle, int(port))
        if status != 0:
            raise DeviceNetworkError(f"设置{label}失败，错误码: {status}")

    def _ensure_available(self) -> None:
        if not self.is_available:
            raise DeviceNetworkError(self.availability_reason or "网络配置组件不可用。")

    def _scan_local_subnet(self, command_port: int, timeout_seconds: float = 0.18) -> list[str]:
        host_ip = detect_host_ipv4()
        network = ipaddress.IPv4Network(f"{host_ip}/24", strict=False)
        host_text = str(ipaddress.IPv4Address(host_ip))
        candidates = [
            str(ip)
            for ip in network.hosts()
            if str(ip) != host_text
        ]

        def probe(ip_text: str) -> str | None:
            try:
                with socket.create_connection((ip_text, command_port), timeout=timeout_seconds):
                    return ip_text
            except OSError:
                return None

        reachable_ips: list[str] = []
        max_workers = min(32, max(4, len(candidates) // 8))
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {executor.submit(probe, ip_text): ip_text for ip_text in candidates}
            for future in concurrent.futures.as_completed(future_map):
                ip_text = future.result()
                if ip_text:
                    reachable_ips.append(ip_text)

        verified_endpoints: list[str] = []
        for ip_text in sorted(set(reachable_ips)):
            endpoint = f"{ip_text}:{command_port}"
            handle = -1
            try:
                for mode in (5, 4):
                    handle = self._dll.lc_init_ex(mode, endpoint.encode("ascii"), 0)
                    if handle != -1:
                        LOGGER.info("Subnet scan verified reader endpoint=%s mode=%s", endpoint, mode)
                        verified_endpoints.append(endpoint)
                        break
            finally:
                if handle != -1:
                    self._dll.lc_exit(handle)

        return verified_endpoints


class DeviceNetworkService:
    def __init__(self, config_manager=None, backend: RFProSDKBackend | None = None):
        self.config = config_manager
        self.backend = backend or RFProSDKBackend()

    @property
    def discovery_port(self) -> int:
        if self.config:
            return int(self.config.get("device_network_discovery_port", DEFAULT_DEVICE_DISCOVERY_PORT))
        return DEFAULT_DEVICE_DISCOVERY_PORT

    @property
    def command_port(self) -> int:
        if self.config:
            return int(self.config.get("device_network_command_port", DEFAULT_DEVICE_COMMAND_PORT))
        return DEFAULT_DEVICE_COMMAND_PORT

    @property
    def is_available(self) -> bool:
        return self.backend.is_available

    @property
    def availability_reason(self) -> str:
        return getattr(self.backend, "availability_reason", "")

    def discover_devices(self) -> list[NetworkDiscoveryEntry]:
        return self.backend.discover_devices(
            listen_port=self.discovery_port,
            command_port=self.command_port,
        )

    def read_profile(
        self,
        *,
        current_ip: str | None,
        current_port: int | None = None,
        device_path: str | None = None,
    ) -> DeviceNetworkProfile:
        return self.backend.read_profile(
            current_ip=current_ip,
            current_port=int(current_port or self.command_port),
            device_path=device_path,
        )

    def apply_profile(
        self,
        profile: DeviceNetworkProfile,
        *,
        current_ip: str | None,
        current_port: int | None = None,
        device_path: str | None = None,
    ) -> None:
        self.backend.apply_profile(
            profile,
            current_ip=current_ip,
            current_port=int(current_port or self.command_port),
            device_path=device_path,
        )

    def suggest_profile(
        self,
        *,
        current_ip: str | None,
        occupied_ips: Iterable[str],
        local_port: int | None = None,
    ) -> DeviceNetworkProfile:
        host_ip = detect_host_ipv4()
        server_port = int(self.config.get("udp_port", 39169)) if self.config else 39169
        return suggest_device_profile(
            host_ip=host_ip,
            current_ip=current_ip,
            occupied_ips=occupied_ips,
            server_port=server_port,
            local_port=int(local_port or self.command_port),
        )
