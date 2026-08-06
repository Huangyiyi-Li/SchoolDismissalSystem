from dataclasses import dataclass


BX_6E1XP_MAX_WIDTH = 2048
BX_6E1XP_MAX_HEIGHT = 1024
BX_6E1XP_MAX_MONO_PIXELS = 512 * 1024
BX_6E1XP_MAX_DUAL_PIXELS = 256 * 1024


@dataclass(frozen=True)
class LedDimensionValidation:
    ok: bool
    width: int = 0
    height: int = 0
    message: str = ""


def validate_led_dimensions(width_value, height_value, color_mode="single"):
    try:
        width = int(str(width_value).strip())
        height = int(str(height_value).strip())
    except (TypeError, ValueError):
        return LedDimensionValidation(
            False,
            message="像素宽度和高度必须填写正整数",
        )
    if width <= 0 or height <= 0:
        return LedDimensionValidation(
            False,
            message="像素宽度和高度必须大于 0",
        )
    if width > BX_6E1XP_MAX_WIDTH:
        return LedDimensionValidation(
            False,
            message="BX-6E1XP 单色屏宽度不能超过 2048 像素",
        )
    if height > BX_6E1XP_MAX_HEIGHT:
        return LedDimensionValidation(
            False,
            message="BX-6E1XP 屏幕高度不能超过 1024 像素",
        )
    dual_color = str(color_mode or "").strip().lower() == "double"
    max_pixels = (
        BX_6E1XP_MAX_DUAL_PIXELS if dual_color else BX_6E1XP_MAX_MONO_PIXELS
    )
    if width * height > max_pixels:
        return LedDimensionValidation(
            False,
            message=(
                "BX-6E1XP 双色屏总像素不能超过 262144（256K）"
                if dual_color
                else "BX-6E1XP 单色屏总像素不能超过 524288（512K）"
            ),
        )
    return LedDimensionValidation(True, width=width, height=height)
