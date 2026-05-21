from commands.moderate.set_room_limit import handle_set_room_limit
from commands.register import register_handler
from commands.schemas import ErrorResponse
from commands.settings.schemas import RequestScreenShareRequest, ScreenShareStateResponse
from database.crud.participants import set_participant_status
from database.crud.rooms import set_room_locked
from utils import broadcast_to_room, CommandContext, RoomParticipantPair


@register_handler(
    "request_screen_share",
    request_model=RequestScreenShareRequest,
    responses={
        "screen_share_state": (
                ScreenShareStateResponse,
                "Уведомление всем (broadcast)"
        ),
        "error": (
                ErrorResponse,
                "Ошибка: участник не в комнате"
        )
    },
    description="Начать или завершить демонстрацию экрана. Состояние рассылается всем.",
    group="settings"
)
async def handle_request_screen_share(ctx: CommandContext, data: dict) -> RoomParticipantPair:
    if not ctx.current_room or not ctx.current_participant:
        return ctx.current_room, ctx.current_participant
    enabled = data.get("enabled", True)
    ctx.current_participant.screen_sharing = enabled
    await set_participant_status(
        ctx.current_participant.id,
        ctx.current_participant.audio_enabled,
        ctx.current_participant.video_enabled,
        enabled
    )
    await broadcast_to_room(ctx.current_room, {
        "type": "screen_share_state",
        "participant_id": ctx.current_participant.id,
        "enabled": enabled
    })
    return ctx.current_room, ctx.current_participant
