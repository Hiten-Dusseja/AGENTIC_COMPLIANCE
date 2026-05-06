import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any


DATA_DIR = Path(__file__).resolve().parent.parent / "mock_data"

SOURCE_FILES = {
    "regulatory_obligations": "regulatory_obligations.json",
    "core_banking_accounts": "core_banking_accounts.json",
    "core_banking_transactions": "core_banking_transactions.csv",
    "erp_invoices": "erp_invoices.csv",
    "emr_encounters": "emr_encounters.json",
    "data_warehouse_risk_events": "data_warehouse_risk_events.json",
}


class UnknownSourceError(ValueError):
    pass


def list_source_names() -> list[str]:
    return [name for name in SOURCE_FILES if name != "regulatory_obligations"]


def load_source(source_name: str) -> list[dict[str, Any]]:
    file_name = SOURCE_FILES.get(source_name)
    if not file_name:
        raise UnknownSourceError(f"Unknown source: {source_name}")

    file_path = DATA_DIR / file_name
    if file_path.suffix == ".csv":
        with file_path.open(newline="", encoding="utf-8") as file:
            return [_coerce_record(row) for row in csv.DictReader(file)]

    with file_path.open(encoding="utf-8") as file:
        return json.load(file)


def load_obligations() -> list[dict[str, Any]]:
    return load_source("regulatory_obligations")


def filter_records(
    records: list[dict[str, Any]],
    start_date: str | None = None,
    end_date: str | None = None,
    domain: str | None = None,
    status: str | None = None,
    risk_flag: str | None = None,
) -> list[dict[str, Any]]:
    return [
        record
        for record in records
        if _within_date_range(record, start_date, end_date)
        and (domain is None or record.get("domain") == domain)
        and (
            status is None
            or record.get("status") == status
            or record.get("payment_status") == status
        )
        and (risk_flag is None or record.get("risk_flag") == risk_flag)
    ]


def select_fields(records: list[dict[str, Any]], fields: list[str] | None) -> list[dict[str, Any]]:
    if not fields:
        return records
    return [{field: record[field] for field in fields if field in record} for record in records]


def _coerce_record(record: dict[str, str]) -> dict[str, Any]:
    coerced: dict[str, Any] = {}
    for key, value in record.items():
        try:
            coerced[key] = float(value) if "." in value else int(value)
        except ValueError:
            coerced[key] = value
    return coerced


def _within_date_range(
    record: dict[str, Any],
    start_date: str | None,
    end_date: str | None,
) -> bool:
    if not start_date and not end_date:
        return True

    candidate = (
        record.get("posted_at")
        or record.get("invoice_date")
        or record.get("accessed_at")
        or record.get("detected_at")
        or record.get("updated_at")
    )
    if not candidate:
        return True

    candidate_date = _parse_date(candidate)
    if start_date and candidate_date < _parse_date(start_date):
        return False
    if end_date and candidate_date > _parse_date(end_date, end_of_day=True):
        return False
    return True


def _parse_date(value: str, end_of_day: bool = False) -> datetime:
    normalized = value.replace("Z", "+00:00")
    if "T" not in normalized:
        suffix = "T23:59:59+00:00" if end_of_day else "T00:00:00+00:00"
        normalized = f"{normalized}{suffix}"
    return datetime.fromisoformat(normalized)
