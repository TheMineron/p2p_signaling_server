from pydantic import BaseModel, Field
from typing import Optional


class SetVideoEnabledRequest(BaseModel):
    enabled: bool = Field(
        True,
        description="Включить (true) или выключить (false) камеру"
    )


class SetAudioEnabledRequest(BaseModel):
    enabled: bool = Field(
        True,
        description="Включить (true) или выключить (false) микрофон"
    )


class SetNicknameRequest(BaseModel):
    nickname: str = Field(
        ...,
        description="Новый никнейм (не может быть пустым)", min_length=1
    )


class RequestScreenShareRequest(BaseModel):
    enabled: bool = Field(
        True,
        description="Начать (true) или завершить (false) демонстрацию экрана"
    )


# Ответы / уведомления
class ParticipantUpdatedResponse(BaseModel):
    participant_id: str = Field(
        ...,
        description="ID участника"
    )
    audio_enabled: Optional[bool] = Field(
        None,
        description="Новое состояние микрофона (если менялось)"
    )
    video_enabled: Optional[bool] = Field(
        None,
        description="Новое состояние камеры (если менялось)"
    )


class ParticipantRenamedResponse(BaseModel):
    participant_id: str = Field(
        ..., description="ID участника"
    )
    old_name: str = Field(
        ..., description="Старый никнейм"
    )
    new_name: str = Field(
        ..., description="Новый никнейм"
    )


class ScreenShareStateResponse(BaseModel):
    participant_id: str = Field(
        ...,
        description="ID участника"
    )
    enabled: bool = Field(
        ...,
        description="Включена ли демонстрация экрана"
    )
