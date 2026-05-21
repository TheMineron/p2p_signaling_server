import logging

from commands.connection.schemas import SignalRequest, SignalRelay
from commands.register import register_handler
from commands.schemas import ErrorResponse
from utils import CommandContext, RoomParticipantPair, safe_send_json

logger = logging.getLogger(__name__)


@register_handler(
    "signal",
    request_model=SignalRequest,
    responses={
        "signal": (
                SignalRelay,
                "Ретрансляция сигнала целевому участнику (S→C)"
        ),
        "error": (
                ErrorResponse,
                "Ошибка: цель не найдена или отсутствуют поля"
        )
    },
    description="Прозрачная пересылка WebRTC-сигналов (SDP, ICE) "
                "между участниками. Сервер не анализирует содержимое data.",
    group="connection"
)
async def handle_signal(ctx: CommandContext, data: dict) -> RoomParticipantPair:
    if not ctx.current_room or not ctx.current_participant:
        return ctx.current_room, ctx.current_participant

    target_id = data.get("target_id")
    if target_id == ctx.current_participant.id:
        logger.warning(f"Попытка отправить сигнал самому "
                       f"себе от {ctx.current_participant.id}")
        return ctx.current_room, ctx.current_participant

    signal_data = data.get("data")
    if not target_id or not signal_data:
        return ctx.current_room, ctx.current_participant

    target = ctx.current_room.participants.get(target_id)
    if target:
        await safe_send_json(target.websocket, {
            "type": "signal",
            "from_id": ctx.current_participant.id,
            "from_name": ctx.current_participant.nickname,
            "data": signal_data
        })
    else:
        logger.warning(f"Цель {target_id} не найдена в комнате {ctx.current_room.id}")

    return ctx.current_room, ctx.current_participant
