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
_BENCHMARK_NETWORK = ipaddress.IPv4Network("198.18.0.0/15")
_RFC1918_NETWORKS = (
    ipaddress.IPv4Network("192.168.0.0/16"),
    ipaddress.IPv4Network("10.0.0.0/8"),
    ipaddress.IPv4Network("172.16.0.0/12"),
)


class DeviceNetworkError(RuntimeError):
    pass


@dataclass(frozen=True)
class NetworkDiscoveryEntry:
    path: str
    label_text: str | None = None

    @property
    def label(self) -> str:
        return self.label_text or self.path


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


def _iter_host_ipv4_candidates() -> list[str]:
    candidates: list[str] = []

    def remember(ip_text: str | None) -> None:
        if not _is_valid_ipv4(ip_text):
            return
        normalized = normalize_ipv4(ip_text)
        if normalized not in candidates:
            candidates.append(normalized)

    for target in ("8.8.8.8", "1.1.1.1", "192.0.2.1"):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect((target, 80))
            remember(sock.getsockname()[0])
        except OSError:
            continue
        finally:
            sock.close()

    try:
        for ip_text in socket.gethostbyname_ex(socket.gethostname())[2]:
            remember(ip_text)
    except OSError:
        pass

    try:
        for item in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET, socket.SOCK_DGRAM):
            remember(item[4][0])
    except OSError:
        pass

    return candidates


def _score_host_ipv4(ip_text: str) -> tuple[int, int]:
    address = ipaddress.IPv4Address(normalize_ipv4(ip_text))
    score = 0

    if address.is_loopback or address.is_multicast or address.is_unspecified:
        return (-100, -int(address))
    if address.is_link_local:
        return (-50, -int(address))
    if address in _BENCHMARK_NETWORK:
        return (-40, -int(address))

    if address in _RFC1918_NETWORKS[0]:
        score = 300
    elif address in _RFC1918_NETWORKS[1]:
        score = 290
    elif address in _RFC1918_NETWORKS[2]:
        score = 280
    elif address.is_private:
        score = 250
    elif address.is_global:
        score = 120
    else:
        score = 20

    return (score, -int(address))


def detect_host_ipv4() -> str:
    candidates = _iter_host_ipv4_candidates()
    if not candidates:
        return "127.0.0.1"

    selected = max(candidates, key=_score_host_ipv4)
    LOGGER.info("Selected host IPv4 %s from candidates=%s", selected, candidates)
    return selected


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
        exclude_paths: Iterable[str] | None = None,
        allow_subnet_scan: bool = True,
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
            return self._verify_discovered_paths(best_result, exclude_paths=exclude_paths)

        if not allow_subnet_scan:
            return []

        fallback_paths = self._scan_local_subnet(command_port=int(command_port))
        return self._verify_discovered_paths(fallback_paths, exclude_paths=exclude_paths)

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
            if self._probe_reader_profile(endpoint):
                LOGGER.info("Subnet scan verified reader endpoint=%s", endpoint)
                verified_endpoints.append(endpoint)

        return verified_endpoints

    def _verify_discovered_paths(
        self,
        paths: Iterable[str],
        *,
        exclude_paths: Iterable[str] | None = None,
    ) -> list[NetworkDiscoveryEntry]:
        normalized_excluded = {path.strip() for path in (exclude_paths or []) if path}
        verified_entries: list[NetworkDiscoveryEntry] = []
        seen_paths: set[str] = set()

        for raw_path in paths:
            path = raw_path.strip()
            if not path or path in normalized_excluded or path in seen_paths:
                continue

            profile = self._probe_reader_profile(path)
            if profile is None:
                LOGGER.debug("Discarded unverified reader candidate path=%s", path)
                continue

            seen_paths.add(path)
            verified_entries.append(
                NetworkDiscoveryEntry(
                    path=path,
                    label_text=f"{path} | 已确认刷卡器，本机IP {profile.local_ip}",
                )
            )

        return verified_entries

    def _probe_reader_profile(self, device_path: str) -> DeviceNetworkProfile | None:
        handle = -1
        for mode in (5, 4):
            try:
                handle = self._dll.lc_init_ex(mode, device_path.encode("ascii"), 0)
                if handle == -1:
                    continue

                profile = DeviceNetworkProfile(
                    local_ip=self._read_ip(handle, self._dll.lc_getNet_local_IP),
                    subnet_mask=self._read_ip(handle, self._dll.lc_getNet_local_mask),
                    gateway=self._read_ip(handle, self._dll.lc_getNet_gateway),
                    server_ip=self._read_ip(handle, self._dll.lc_getNet_serverIP),
                    server_port=self._read_port(handle, self._dll.lc_getNet_serverPort),
                    local_port=self._read_port(handle, self._dll.lc_getNet_local_port),
                )
                LOGGER.info(
                    "Verified reader path=%s mode=%s local_ip=%s server=%s:%s",
                    device_path,
                    mode,
                    profile.local_ip,
                    profile.server_ip,
                    profile.server_port,
                )
                return profile
            except DeviceNetworkError:
                LOGGER.debug("Reader verification failed for path=%s mode=%s", device_path, mode, exc_info=True)
            finally:
                if handle != -1:
                    self._dll.lc_exit(handle)
                    handle = -1

        return None


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

    def discover_devices(
        self,
        exclude_paths: Iterable[str] | None = None,
        allow_subnet_scan: bool = True,
    ) -> list[NetworkDiscoveryEntry]:
        return self.backend.discover_devices(
            listen_port=self.discovery_port,
            command_port=self.command_port,
            exclude_paths=exclude_paths,
            allow_subnet_scan=allow_subnet_scan,
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
