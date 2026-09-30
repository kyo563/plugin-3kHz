from pydantic import BaseModel, ConfigDict, StrictBool


class ControlDisplaySettings(BaseModel):
    """Operator-only visibility; never changes queue data or OBS output."""

    model_config = ConfigDict(extra="forbid")
    avatar: StrictBool = True
    username: StrictBool = True
    alias: StrictBool = True
    memo: StrictBool = True
    count: StrictBool = True
    order: StrictBool = True
