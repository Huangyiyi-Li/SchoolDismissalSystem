CLASS_TYPE_LABELS = {
    1: "行政班",
    2: "社团班",
}


def normalize_class_type(class_type):
    if class_type is None or class_type == "":
        return None
    try:
        return int(class_type)
    except (TypeError, ValueError):
        try:
            as_float = float(class_type)
            if as_float.is_integer():
                return int(as_float)
        except (TypeError, ValueError):
            pass
        return class_type


def format_class_type_label(class_type):
    normalized = normalize_class_type(class_type)
    if normalized is None:
        return "未知类型"
    return CLASS_TYPE_LABELS.get(normalized, f"类型{normalized}")


def format_class_type_section_title(class_type):
    return f"{format_class_type_label(class_type)}放学时段"
