import logging

from commands.connection.schemas import PingRequest, PongResponse
from commands.register import register_handler
from utils import CommandContext, RoomParticipantPair, safe_send_json

logger = logging.getLogger(__name__)


@register_handler(
    "ping",
    request_model=PingRequest,
    responses={
        "pong": (
                PongResponse,
                "Ответ с той же временной меткой для расчёта RTT"
        )
    },
    description="Измерение задержки WebSocket. "
                "Сервер немедленно отвечает pong.",
    group="connection"
)
async def handle_ping(ctx: CommandContext, data: dict) -> RoomParticipantPair:
    if not ctx.current_participant:
        return ctx.current_room, ctx.current_participant

    timestamp = data.get("timestamp")
    if timestamp:
        await safe_send_json(ctx.websocket, data={
            "type": "pong",
            "timestamp": timestamp
        })

    return ctx.current_room, ctx.current_participant
