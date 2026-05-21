import logging

from commands.moderate.schemas import UnlockRoomRequest, RoomUnlockedResponse
from commands.register import register_handler
from commands.schemas import ErrorResponse
from utils import safe_send_json, broadcast_to_room, CommandContext, RoomParticipantPair

logger = logging.getLogger(__name__)


@register_handler(
    "unlock_room",
    request_model=UnlockRoomRequest,
    responses={
        "room_unlocked": (
                RoomUnlockedResponse,
                "Уведомление о разблокировке комнаты (broadcast)"
        ),
        "error": (
                ErrorResponse,
                "Ошибка: нет прав модератора"
        )
    },
    description="Разблокировка входа новых участников (только для модератора).",
    group="moderate"
)
async def handle_unlock_room(ctx: CommandContext, data: dict) -> RoomParticipantPair:
    if not ctx.current_room or not ctx.current_participant:
        return ctx.current_room, ctx.current_participant
    if ctx.current_participant.role != "moderator":
        await safe_send_json(ctx.websocket, data={
            "type": "error",
            "message":
                "Требуются права модератора"
        })
        return ctx.current_room, ctx.current_participant
    ctx.current_room.is_locked = False
    await ctx.room_manager.update_room_params(ctx.current_room)
    await broadcast_to_room(ctx.current_room, message={"type": "room_unlocked"})
    return ctx.current_room, ctx.current_participant
