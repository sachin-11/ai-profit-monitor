from typing import Any

from pydantic import BaseModel


class ApiResponse[DataT](BaseModel):
    success: bool = True
    data: DataT


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Any | None = None


class ErrorResponse(BaseModel):
    success: bool = False
    error: ErrorDetail
