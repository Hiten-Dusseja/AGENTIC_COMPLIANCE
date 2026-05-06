from typing import Any

try:
    from mock_api.data_loader import filter_records, load_obligations, load_source
except ModuleNotFoundError:
    from data_loader import filter_records, load_obligations, load_source


def build_reporting_metrics(
    obligation_id: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any] | None:
    obligation = _find_obligation(obligation_id)
    if not obligation:
        return None

    metrics = []
    for metric in obligation["required_metrics"]:
        source_records = filter_records(
            load_source(metric["source"]),
            start_date=start_date,
            end_date=end_date,
        )
        metrics.append(
            {
                "metric_id": metric["metric_id"],
                "source": metric["source"],
                "field_mapping": metric["field_mapping"],
                "value": _metric_value(metric["metric_id"], source_records),
                "source_record_count": len(source_records),
            }
        )

    return {
        "obligation_id": obligation["id"],
        "obligation_name": obligation["name"],
        "domain": obligation["domain"],
        "jurisdiction": obligation["jurisdiction"],
        "reporting_frequency": obligation["reporting_frequency"],
        "metrics": metrics,
    }


def _find_obligation(obligation_id: str) -> dict[str, Any] | None:
    return next((item for item in load_obligations() if item["id"] == obligation_id), None)


def _metric_value(metric_id: str, records: list[dict[str, Any]]) -> Any:
    if metric_id == "total_demand_liabilities":
        return sum(
            record["current_balance"]
            for record in records
            if record.get("account_type") in {"demand_deposit", "current_account"}
            and record.get("status") == "active"
        )

    if metric_id == "large_cash_withdrawals":
        return [record for record in records if record.get("risk_flag") == "large_cash_withdrawal"]

    if metric_id == "high_risk_transactions":
        return [record for record in records if record.get("risk_flag") not in {None, "none"}]

    if metric_id == "open_aml_cases":
        return [
            record
            for record in records
            if record.get("domain") == "aml" and record.get("status") == "open"
        ]

    if metric_id == "taxable_vendor_payments":
        return [record for record in records if record.get("payment_status") == "paid"]

    if metric_id == "patient_record_accesses":
        return records

    if metric_id == "privacy_incidents":
        return [
            record
            for record in records
            if record.get("domain") == "privacy" and record.get("status") == "open"
        ]

    return records
