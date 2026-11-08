from typing import Literal
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator


CounterKind = Literal["round", "unique"]
COUNTER_TOKENS = {"round": "{round}", "unique": "{unique}"}
COUNTER_TITLES = {"round": "現在の対局数", "unique": "対戦済み人数"}


class ObsCounterSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    round: str = Field(default="現在{round}局目", max_length=80)
    unique: str = Field(default="現在{unique}人の方と対戦済み", max_length=80)

    @field_validator("round", "unique")
    @classmethod
    def validate_wording(cls, value, info):
        token = COUNTER_TOKENS[info.field_name]
        if token not in value or re.search(r"[\x00-\x1f\x7f-\x9f\u2028\u2029]", value):
            raise ValueError(f"1行の文言に {token} を含めてください")
        return value.strip()
