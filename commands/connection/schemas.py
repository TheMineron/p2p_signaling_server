from pydantic import BaseModel, Field
from typing import Optional, List, Any


class IceServer(BaseModel):
    urls: str = Field(
        ...,
        description="URL сервера (stun:... или turn:...)"
    )
    username: Optional[str] = Field(
        None,
        description="Имя пользователя для TURN"
    )
    credential: Optional[str] = Field(
        None,
        description="Пароль для TURN"
    )


class ParticipantInfo(BaseModel):
    id: str = Field(
        ...,
        description="Уникальный ID участника"
    )
    name: str = Field(
        ...,
        description="Никнейм"
    )
    role: str = Field(
        ...,
        description="Роль: moderator или participant"
    )
    audio_enabled: bool = Field(
        ...,
        description="Включён ли микрофон"
    )
    video_enabled: bool = Field(
        ...,
        description="Включена ли камера"
    )


class ChatHistoryMessage(BaseModel):
    msg_id: str
    from_id: str
    from_name: str
    text: str
    target_id: Optional[str] = None
    timestamp: float
    edited: bool = False
    deleted: bool = False
    is_pinned: bool = False
    reply_to_msg_id: Optional[str] = None


class JoinRequest(BaseModel):
    room: str = Field(
        ...,
        description="Идентификатор комнаты"
    )
    nickname: str = Field(
        ...,
        description="Отображаемое имя участника"
    )
    password: Optional[str] = Field(
        None,
        description="Пароль комнаты (если установлен)"
    )


class LeaveRequest(BaseModel):
    pass


class PingRequest(BaseModel):
    timestamp: float = Field(
        ...,
        description="Временная метка отправки (клиентское время)"
    )


class SignalRequest(BaseModel):
    target_id: str = Field(
        ...,
        description="ID получателя сигнала"
    )
    data: Any = Field(
        ...,
        description="Тело сигнала (SDP или ICE candidate)"
    )


class JoinedResponse(BaseModel):
    room: str = Field(
        ...,
        description="ID комнаты"
    )
    nickname: str = Field(
        ...,
        description="Никнейм участника"
    )
    participant_id: str = Field(
        ...,
        description="Уникальный ID участника"
    )
    role: str = Field(
        ...,
        description="Роль: moderator или participant"
    )
    ice_servers: List[IceServer] = Field(
        default_factory=list,
        description="Список STUN/TURN серверов для WebRTC"
    )


class ParticipantJoinedBroadcast(BaseModel):
    participant: ParticipantInfo = Field(
        ...,
        description="Информация о новом участнике"
    )


class ExistingParticipantsResponse(BaseModel):
    participants: List[ParticipantInfo] = Field(
        ...,
        description="Список уже присутствующих участников"
    )


class ChatHistoryResponse(BaseModel):
    messages: List[ChatHistoryMessage] = Field(
        ...,
        description="История последних N сообщений"
    )


class PongResponse(BaseModel):
    timestamp: float = Field(
        ...,
        description="Временная метка, полученная от ping"
    )


class ParticipantLeftBroadcast(BaseModel):
    participant_id: str = Field(
        ...,
        description="ID участника, покинувшего комнату"
    )


class SignalRelay(BaseModel):
    from_id: str = Field(
        ...,
        description="ID отправителя"
    )
    from_name: str = Field(
        ...,
        description="Имя отправителя"
    )
    data: Any = Field(
        ...,
        description="Сигнальные данные (SDP или ICE)"
    )
