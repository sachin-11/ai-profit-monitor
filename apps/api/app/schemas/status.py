from typing import Literal

from pydantic import BaseModel


class StatusResponse[DataT](BaseModel):
    success: bool = True
    data: DataT


class HealthData(BaseModel):
    status: Literal["healthy"]


class ReadyData(BaseModel):
    status: Literal["ready", "not_ready"]
    database: Literal["available", "unavailable"]
