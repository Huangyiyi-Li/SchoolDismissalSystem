from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass


@dataclass(frozen=True)
class SwipeDecision:
    should_voice: bool
    voice_text: str
    should_push_api: bool
    action: str
    reason: str


def _safe_positive_int(value, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _build_voice_text(class_name: str, broadcast_count) -> str:
    count = _safe_positive_int(broadcast_count, 1)
    base_text = f"{class_name}正在放学"
    return "，".join([base_text] * count)


def evaluate_swipe(
    *,
    class_name: str | None,
    class_id: str | None,
    card_id: str,
    window_signature: str | None,
    now: _dt.datetime,
    voice_history: dict[str, str],
    api_push_history: dict[str, _dt.datetime],
    deduplication_interval_seconds,
    broadcast_count,
    test_mode: bool,
    api_service_available: bool,
) -> SwipeDecision:
    if not class_name:
        return SwipeDecision(
            should_voice=False,
            voice_text="",
            should_push_api=False,
            action="跳过",
            reason="无效卡号",
        )

    if not window_signature:
        return SwipeDecision(
            should_voice=False,
            voice_text="",
            should_push_api=False,
            action="跳过",
            reason="非播报时段",
        )

    last_window = voice_history.get(class_name)
    should_voice = last_window != window_signature
    if should_voice:
        action = "语音播报"
        reason = "正常"
        voice_text = _build_voice_text(class_name, broadcast_count)
    else:
        action = "语音跳过"
        reason = "重复播报"
        voice_text = ""

    should_push_api = False
    cooldown_seconds = _safe_positive_int(deduplication_interval_seconds, 300)
    last_push = api_push_history.get(card_id)
    cooldown_passed = (
        last_push is None or (now - last_push).total_seconds() > cooldown_seconds
    )

    if not api_service_available or not class_id:
        if should_voice:
            reason += "/无API服务"
    elif cooldown_passed:
        if test_mode:
            if should_voice:
                reason += "/测试模式"
            else:
                action += "/测试模式"
        else:
            should_push_api = True
            if should_voice:
                reason += "/推送成功"
            else:
                action += "/推送成功"
    else:  # cooldown not passed
        if should_voice:
            reason += "/推送冷却"
        else:
            reason = "重复/推送冷却"

    return SwipeDecision(should_voice, voice_text, should_push_api, action, reason)
