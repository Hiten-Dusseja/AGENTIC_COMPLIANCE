from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DataFetchRequest(BaseModel):
    policy_name: str = Field(..., examples=["Daily Cash Reserve Ratio"])
    start_date: str | None = Field(default=None, examples=["2026-04-01"])
    end_date: str | None = Field(default=None, examples=["2026-04-30"])


class ComplianceDataItem(BaseModel):
    value: Any
    reason: str
    flag: str

    @field_validator("value", mode="before")
    @classmethod
    def normalize_value(cls, value: Any) -> Any:
        return value


class ApiComplianceDataItem(BaseModel):
    value: dict[str, Any]
    reason: str
    flag: str

    @field_validator("value", mode="before")
    @classmethod
    def normalize_value(cls, value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        return {"value": value}


class ComplianceReviewOutput(BaseModel):
    compliant_data: list[ComplianceDataItem]
    non_compliant_data: list[ComplianceDataItem]


class DataFetchPayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    compliant_data: list[ApiComplianceDataItem] = Field(alias="compliant data")
    non_compliant_data: list[ApiComplianceDataItem] = Field(alias="non compliant data")


class DataFetchResponse(BaseModel):
    result: str
    message: str
    data: DataFetchPayload
