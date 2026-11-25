"""Mobile communication intent builders for the S24+ Android HUD."""

from __future__ import annotations

from typing import Any

VALID_CALL_ACTIONS: frozenset[str] = frozenset({"answer", "reject"})
VALID_NOTIFICATION_ACTIONS: frozenset[str] = frozenset({"read", "reply"})
VALID_MESSAGE_CHANNELS: frozenset[str] = frozenset({"whatsapp", "sms"})
VALID_DEVICE_CONTROL_ACTIONS: frozenset[str] = frozenset(
    {
        "flashlight_on",
        "flashlight_off",
        "volume_up",
        "volume_down",
        "volume_set",
        "mute",
        "set_alarm",
        "set_timer",
    }
)


def build_mobile_call_intent(action: str) -> dict[str, Any]:
    """Build an S24+ call control payload (`answer` or `reject`)."""
    normalized = action.strip().lower()
    if normalized not in VALID_CALL_ACTIONS:
        raise ValueError(f"Unsupported mobile call action: '{action}'.")
    return {
        "device": "s24_plus",
        "mobile_action": {
            "type": "call_control",
            "action": normalized,
        },
    }


def build_mobile_notifications_intent(
    action: str,
    sender: str = "",
    message: str = "",
) -> dict[str, Any]:
    """Build an S24+ notification read or reply payload."""
    normalized = action.strip().lower()
    if normalized not in VALID_NOTIFICATION_ACTIONS:
        raise ValueError(f"Unsupported mobile notification action: '{action}'.")

    clean_sender = sender.strip()
    clean_message = message.strip()
    if normalized == "reply" and not clean_message:
        raise ValueError("Reply message cannot be empty.")

    action_type = "read_notifications" if normalized == "read" else "reply_notification"
    return {
        "device": "s24_plus",
        "mobile_action": {
            "type": action_type,
            "action": normalized,
            "sender": clean_sender,
            "message": clean_message,
        },
    }


def build_mobile_message_intent(
    channel: str,
    recipient: str,
    message: str,
) -> dict[str, Any]:
    """Build an S24+ outbound message payload (`whatsapp` or `sms`)."""
    normalized_channel = channel.strip().lower()
    if normalized_channel not in VALID_MESSAGE_CHANNELS:
        raise ValueError(f"Unsupported mobile message channel: '{channel}'.")

    clean_recipient = recipient.strip()
    clean_message = message.strip()
    if not clean_recipient:
        raise ValueError("Recipient cannot be empty.")
    if not clean_message:
        raise ValueError("Message cannot be empty.")

    return {
        "device": "s24_plus",
        "mobile_action": {
            "type": "send_message",
            "channel": normalized_channel,
            "recipient": clean_recipient,
            "message": clean_message,
        },
    }


def build_mobile_device_control_intent(
    action: str,
    value: str = "",
    label: str = "",
) -> dict[str, Any]:
    """Build an S24+ hardware/device control payload."""
    normalized = action.strip().lower()
    if normalized not in VALID_DEVICE_CONTROL_ACTIONS:
        raise ValueError(f"Unsupported mobile device control action: '{action}'.")

    clean_value = value.strip()
    clean_label = label.strip()
    if normalized in {"volume_set", "set_alarm", "set_timer"} and not clean_value:
        raise ValueError(f"Value cannot be empty for '{normalized}'.")

    return {
        "device": "s24_plus",
        "mobile_action": {
            "type": "device_control",
            "action": normalized,
            "value": clean_value,
            "label": clean_label,
        },
    }
