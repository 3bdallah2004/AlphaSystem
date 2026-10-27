from pydantic import BaseModel, ConfigDict, Field
from pydantic import field_validator


class CaseCreate(BaseModel):
    case_text: str = Field(min_length=20)

    @field_validator("case_text")
    @classmethod
    def validate_case_text(cls, value):
        if len(value.strip()) < 20:
            raise ValueError("case_text must contain at least 20 non-whitespace characters")
        return value


class CasePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_name: str | None = None
    case_number: str | None = None
    case_type: str | None = None
    location: str | None = None
    date: str | None = None
    case_text: str | None = None
    latitude: float | None = None
    longitude: float | None = None

    @field_validator("case_text")
    @classmethod
    def validate_optional_case_text(cls, value):
        if value is not None and len(value.strip()) < 20:
            raise ValueError("case_text must contain at least 20 non-whitespace characters")
        return value
