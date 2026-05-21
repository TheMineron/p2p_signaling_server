from pydantic import BaseModel, Field
from typing import Optional


class KickParticipantRequest(BaseModel):
    target_id: str = Field(
        ...,
        description="ID участника для удаления"
    )
    reason: Optional[str] = Field(
        None,
        description="Причина удаления (опционально)"
    )


class MuteParticipantRequest(BaseModel):
    target_id: str = Field(
        ...,
        description="ID участника для отключения микрофона"
    )


class UnmuteParticipantRequest(BaseModel):
    target_id: str = Field(
        ...,
        description="ID участника для включения микрофона"
    )


class MuteAllRequest(BaseModel):
    pass


class LockRoomRequest(BaseModel):
    pass


class UnlockRoomRequest(BaseModel):
    pass


class SetRoomLimitRequest(BaseModel):
    limit: Optional[int] = Field(
        None,
        description="Максимальное количество участников (null для снятия лимита)"
    )


class SetRoomPasswordRequest(BaseModel):
    password: Optional[str] = Field(
        None,
        description="Пароль комнаты (null или пустая строка для удаления)"
    )


class KickedResponse(BaseModel):
    reason: str = Field(
        "",
        description="Причина удаления"
    )


class ForceMuteResponse(BaseModel):
    by: str = Field(
        ...,
        description="Имя модератора, который отключил микрофон"
    )


class ForceUnmuteResponse(BaseModel):
    by: str = Field(
        ...,
        description="Имя модератора, который включил микрофон"
    )


class AllMutedResponse(BaseModel):
    pass


class ParticipantUpdatedResponse(BaseModel):
    participant_id: str = Field(
        ...,
        description="ID участника"
    )
    audio_enabled: bool = Field(
        ...,
        description="Состояние микрофона"
    )


class RoomLockedResponse(BaseModel):
    pass


class RoomUnlockedResponse(BaseModel):
    pass


class RoomLimitUpdatedResponse(BaseModel):
    limit: Optional[int] = Field(
        None,
        description="Новый лимит участников"
    )


class RoomPasswordUpdatedResponse(BaseModel):
    has_password: bool = Field(
        ...,
        description="Установлен ли пароль"
    )
