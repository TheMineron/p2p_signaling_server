from pydantic import BaseModel, Field
from typing import Optional


class ChatMessageResponse(BaseModel):
    msg_id: str = Field(
        ...,
        description="Уникальный идентификатор сообщения")
    from_id: str = Field(
        ...,
        description="ID отправителя"
    )
    from_name: str = Field(
        ...,
        description="Имя отправителя"
    )
    text: str = Field(
        ...,
        description="Текст сообщения"
    )
    target_id: Optional[str] = Field(
        None,
        description="ID получателя (для личного сообщения)"
    )
    timestamp: float = Field(
        ...,
        description="Временная метка отправки"
    )
    edited: bool = Field(
        False,
        description="Было ли отредактировано"
    )
    deleted: bool = Field(
        False,
        description="Удалено ли сообщение"
    )
    is_pinned: bool = Field(
        False,
        description="Закреплено ли сообщение"
    )
    reply_to_msg_id: Optional[str] = Field(
        None,
        description="ID сообщения, на которое дан ответ"
    )


class ChatSendRequest(BaseModel):
    text: str = Field(
        ...,
        description="Текст сообщения"
    )
    target_id: Optional[str] = Field(
        None,
        description="ID получателя (для личного сообщения)"
    )


class ChatEditRequest(BaseModel):
    msg_id: str = Field(
        ...,
        description="ID сообщения для редактирования"
    )
    text: str = Field(
        ...,
        description="Новый текст"
    )


class ChatDeleteRequest(BaseModel):
    msg_id: str = Field(
        ...,
        description="ID сообщения для удаления"
    )


class ChatPinRequest(BaseModel):
    msg_id: str = Field(
        ...,
        description="ID сообщения для закрепления"
    )


class ChatUnpinRequest(BaseModel):
    msg_id: str = Field(
        ...,
        description="ID сообщения для открепления"
    )


class ChatReplyRequest(BaseModel):
    text: str = Field(
        ...,
        description="Текст ответа"
    )
    reply_to_msg_id: str = Field(
        ...,
        description="ID исходного сообщения"
    )
    target_id: Optional[str] = Field(
        None,
        description="ID получателя (личный ответ)"
    )


class ChatClearRequest(BaseModel):
    pass


class ChatDeletedResponse(BaseModel):
    msg_id: str = Field(
        ...,
        description="ID удалённого сообщения"
    )


class ChatEditedResponse(BaseModel):
    msg_id: str = Field(
        ...,
        description="ID отредактированного сообщения"
    )
    text: str = Field(
        ...,
        description="Новый текст"
    )
    edited: bool = Field(
        True,
        description="Признак редактирования"
    )


class ChatPinnedResponse(BaseModel):
    msg_id: str = Field(
        ...,
        description="ID закреплённого сообщения"
    )


class ChatUnpinnedResponse(BaseModel):
    msg_id: str = Field(
        ...,
        description="ID откреплённого сообщения"
    )


class ChatClearedResponse(BaseModel):
    pass
