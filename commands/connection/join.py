import logging
import os

from commands.connection.schemas import JoinRequest, JoinedResponse, ParticipantJoinedBroadcast, \
    ChatHistoryResponse, ExistingParticipantsResponse
from commands.register import register_handler
from commands.schemas import ErrorResponse
from database.models import Participant
from database.crud import get_chat_history
from utils import (
    CommandContext,
    RoomParticipantPair,
    safe_send_json,
    broadcast_to_room
)

logger = logging.getLogger(__name__)


@register_handler(
    "join",
    request_model=JoinRequest,
    responses={
        "joined": (
                JoinedResponse,
                "Подтверждение входа, содержит ice_servers и роль"
        ),
        "participant_joined": (
                ParticipantJoinedBroadcast,
                "Уведомление другим участникам (broadcast)"
        ),
        "existing_participants": (
                ExistingParticipantsResponse,
                "Список уже присутствующих (только новому участнику)"
        ),
        "chat_history": (
                ChatHistoryResponse,
                "История чата (только новому участнику)"
        ),
        "error": (
                ErrorResponse,
                "Ошибка: неверный пароль, комната заблокирована, лимит участников и т.п."
        )
    },
    description="Вход в комнату. При успехе участник получает "
                "joined, остальным рассылается participant_joined, "
                "новичку отправляется existing_participants и chat_history.",
    group="connection"
)
async def handle_join(ctx: CommandContext, data: dict) -> RoomParticipantPair:
    room_id = data.get("room")
    nickname = data.get("nickname")
    password = data.get("password")
    if not room_id or not nickname:
        await safe_send_json(ctx.websocket, data={
            "type": "error",
            "message": "room и nickname обязательны"
        })
        return ctx.current_room, ctx.current_participant

    room = await ctx.room_manager.get_or_create(room_id)

    can_join, reason = room.can_join(password)
    if not can_join:
        await safe_send_json(ctx.websocket, data={
            "type": "error",
            "message": reason
        })
        return ctx.current_room, ctx.current_participant

    participant = Participant(ctx.websocket, nickname=nickname)
    await ctx.room_manager.add_participant(room, participant)

    logger.info(f"Участник {nickname} ({participant.id}) вошёл в комнату {room_id}")
    ice_servers = _build_ice_servers()
    await safe_send_json(ctx.websocket, {
        "type": "joined",
        "room": room_id,
        "nickname": nickname,
        "participant_id": participant.id,
        "role": participant.role,
        "ice_servers": ice_servers
    })
    await broadcast_to_room(
        room,
        message={
            "type": "participant_joined",
            "participant": {
                "id": participant.id,
                "name": nickname,
                "role": participant.role,
                "audio_enabled": True,
                "video_enabled": True,
            }
        },
        exclude_ws=ctx.websocket
    )
    existing = room.get_info_list(exclude_id=participant.id)
    await safe_send_json(ctx.websocket, data={
        "type": "existing_participants",
        "participants": existing
    })
    history = await get_chat_history(room.id, participant.id)
    if history:
        await safe_send_json(ctx.websocket, data={
            "type": "chat_history",
            "messages": history
        })
    return room, participant


def _build_ice_servers() -> list[dict]:
    servers = []
    stun = os.getenv("STUN_SERVER")
    if stun:
        servers.append({"urls": stun})
    turn = os.getenv("TURN_SERVER")
    if turn:
        servers.append({
            "urls": turn,
            "username": os.getenv("TURN_USERNAME", ""),
            "credential": os.getenv("TURN_CREDENTIAL", "")
        })
    return servers
