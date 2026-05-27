import re
import uuid


MAX_MAC_NODE = 0xFFFFFFFFFFFF


def format_device_no_from_node(node):
    return f"{int(node) & MAX_MAC_NODE:012X}"


def normalize_device_no(value):
    if value is None:
        return ""

    raw = str(value).strip()
    if not raw:
        return ""

    without_separators = re.sub(r"[:\s-]", "", raw)
    if re.fullmatch(r"[0-9A-Fa-f]{12}", without_separators):
        return without_separators.upper()

    if raw.isdigit():
        node = int(raw)
        if 0 <= node <= MAX_MAC_NODE:
            return format_device_no_from_node(node)

    return raw


def get_or_create_device_no(config_manager, node_getter=uuid.getnode):
    current = normalize_device_no(config_manager.get("device_no", ""))
    if current:
        if current != config_manager.get("device_no", ""):
            config_manager.set("device_no", current)
            config_manager.save()
        return current

    generated = format_device_no_from_node(node_getter())
    config_manager.set("device_no", generated)
    config_manager.save()
    return generated
