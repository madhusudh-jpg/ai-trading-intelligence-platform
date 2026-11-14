from typing import Literal

from pydantic import BaseModel, Field


class ModuleStatus(BaseModel):
    name: str
    status: Literal["planned", "building", "available", "degraded"]


class PlatformOverview(BaseModel):
    name: str
    supported_markets: list[str]
    execution_mode: Literal["analysis_only"]
    modules: list[ModuleStatus] = Field(default_factory=list)
