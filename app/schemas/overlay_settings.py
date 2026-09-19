from pydantic import BaseModel, ConfigDict, Field
from typing import Annotated, Literal

FontId = Annotated[str, Field(pattern=r'^(default|gothic|mincho|meiryo|sans|serif|[a-f0-9]{64})$')]

class FontSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    all: FontId = 'default'
    ui_body: FontId | None = None
    ui_heading: FontId | None = None
    ui_controls: FontId | None = None
    status: FontId | None = None
    now_heading: FontId | None = None
    next_heading: FontId | None = None
    queue_heading: FontId | None = None
    now_names: FontId | None = None
    next_names: FontId | None = None
    summary: FontId | None = None

class OverlaySettings(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    open_label: str = Field(default="受付中", max_length=40)
    closed_label: str = Field(default="受付終了", max_length=40)
    now_label: str = Field(default="NOW", max_length=40)
    next_label: str = Field(default="NEXT", max_length=40)
    queue_label: str = Field(default="QUEUE", max_length=40)
    layout: Literal["vertical", "horizontal", "custom"] = "vertical"
    custom_text: str = Field(default="[受付]\n\n[NOW見出し]\n[NOW1]\n[NOW2]\n[NOW3]\n\n[NEXT見出し]\n[NEXT1]\n[NEXT2]\n[NEXT3]\n\n[QUEUE見出し]\n[待機人数]", max_length=4000)
    vertical_text: str = Field(default="[受付]\n\n[NOW見出し]\n[NOW1]\n[NOW2]\n[NOW3]\n\n[NEXT見出し]\n[NEXT1]\n[NEXT2]\n[NEXT3]\n\n[QUEUE見出し]\n[待機人数]", max_length=4000)
    horizontal_status_text: str = Field(default="[受付]", max_length=4000)
    horizontal_now_text: str = Field(default="[NOW見出し]\n[NOW1]\n[NOW2]\n[NOW3]", max_length=4000)
    horizontal_next_text: str = Field(default="[NEXT見出し]\n[NEXT1]\n[NEXT2]\n[NEXT3]", max_length=4000)
    horizontal_queue_text: str = Field(default="[QUEUE見出し]\n[待機グループ]\n/[待機人数のみ]", max_length=4000)
    name_mode: Literal["youtube", "declared", "youtube_declared", "declared_youtube"] | None = None
    width: int = Field(default=480, ge=160, le=3840)
    height: int = Field(default=600, ge=200, le=2160)
    font_size: int = Field(default=28, ge=12, le=96)
    fonts: FontSettings = Field(default_factory=FontSettings)
