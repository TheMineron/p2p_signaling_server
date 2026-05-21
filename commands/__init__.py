from .connection import join
from .connection import leave
from .connection import ping
from .connection import signal

from .chat import chat_send
from .chat import chat_edit
from .chat import chat_delete
from .chat import chat_pin
from .chat import chat_unpin
from .chat import chat_reply
from .chat import chat_clear

from .moderate import kick_participant
from .moderate import mute_participant
from .moderate import unmute_participant
from .moderate import mute_all

from .settings import set_video_enabled
from .settings import set_audio_enabled
from .settings import set_nickname
from .settings import request_screen_share

__all__ = [
    "join",
    "leave",
    "ping",
    "signal",

    "chat_send",
    "chat_edit",
    "chat_delete",
    "chat_pin",
    "chat_unpin",
    "chat_reply",
    "chat_clear",

    "kick_participant",
    "mute_participant",
    "unmute_participant",
    "mute_all",

    "set_video_enabled",
    "set_audio_enabled",
    "set_nickname",
    "request_screen_share",
]


def get_commands_metadata() -> dict:
    from commands.register import _COMMAND_HANDLERS
    metadata = {}
    for cmd, handler in _COMMAND_HANDLERS.items():
        doc = handler.__doc__ or ""
        request_model = getattr(handler, "_request_model", None)
        response_models = getattr(handler, "_response_models", {})
        description = getattr(handler, "_description", "") or doc.split("\n")[0].strip()
        group = getattr(handler, "_group", "other")
        meta = {
            "description": description,
            "docstring": doc,
            "request_schema": request_model.model_json_schema(by_alias=True) if request_model else None,
            "response_schemas": {
                resp_type: {
                    "schema": info["model"].model_json_schema(),
                    "description": info.get("description", "")
                }
                for resp_type, info in response_models.items()
            } if response_models else {},
            "group": group
        }
        metadata[cmd] = meta
    return metadata
