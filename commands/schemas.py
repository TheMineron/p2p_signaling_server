from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    message: str = Field(..., description="Текст ошибки")
