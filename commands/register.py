import logging
from typing import Callable, Coroutine, Any, Optional, Type

from pydantic import BaseModel

from utils import CommandContext, RoomParticipantPair

logger = logging.getLogger(__name__)

Handler = Callable[[CommandContext, dict], Coroutine[Any, Any, RoomParticipantPair]]
ResponseSpec = Type[BaseModel] | tuple[Type[BaseModel], str]

_COMMAND_HANDLERS: dict[str, Handler] = {}


def register_handler(
        command: str,
        *,
        overwrite: bool = False,
        request_model: Optional[Type[BaseModel]] = None,
        responses: Optional[dict[str, ResponseSpec]] = None,
        description: str = "",
        group: str = 'общее',
) -> Callable[[Handler], Handler]:
    def decorator(handler: Handler) -> Handler:
        if command in _COMMAND_HANDLERS and not overwrite:
            logger.warning(...)
        else:
            _COMMAND_HANDLERS[command] = handler
            if request_model:
                handler._request_model = request_model
            if responses:
                normalized = {}
                for resp_type, spec in responses.items():
                    if isinstance(spec, tuple):
                        model, desc = spec
                    else:
                        model, desc = spec, ""
                    normalized[resp_type] = {"model": model, "description": desc}
                handler._response_models = normalized  # type: ignore
            if description:
                handler._description = description
            if group:
                handler._group = group
        return handler

    return decorator


def get_commands_handlers() -> dict[str, Handler]:
    return dict(_COMMAND_HANDLERS)
