import json
import os
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool
from langchain_groq import ChatGroq

try:
    from mock_api.data_loader import filter_records, load_source
    from mock_api.schemas import (
        ApiComplianceDataItem,
        ComplianceDataItem,
        ComplianceReviewOutput,
        DataFetchPayload,
        DataFetchResponse,
    )
except ModuleNotFoundError:
    from data_loader import filter_records, load_source
    from schemas import (
        ApiComplianceDataItem,
        ComplianceDataItem,
        ComplianceReviewOutput,
        DataFetchPayload,
        DataFetchResponse,
    )


ROOT_DIR = Path(__file__).resolve().parent.parent
LOG_FILE = ROOT_DIR / "logs" / "data_fetcher.log"

load_dotenv(ROOT_DIR / ".env")
load_dotenv(Path(__file__).resolve().parent / ".env")


def _read_source(
    source_name: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    records = filter_records(
        load_source(source_name),
        start_date=start_date,
        end_date=end_date,
    )
    return {
        "source": source_name,
        "record_count": len(records),
        "records": records,
    }


@tool
def fetch_core_banking_accounts(
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    """Fetch account balance, KYC, account type, and account status data for banking policies."""
    return _read_source("core_banking_accounts", start_date, end_date)


@tool
def fetch_core_banking_transactions(
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    """Fetch banking transaction data, including cash activity and AML risk flags."""
    return _read_source("core_banking_transactions", start_date, end_date)


@tool
def fetch_erp_invoices(
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    """Fetch ERP vendor invoice, tax amount, and payment status data for tax reporting policies."""
    return _read_source("erp_invoices", start_date, end_date)


@tool
def fetch_emr_encounters(
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    """Fetch healthcare EMR encounter and patient record access data for healthcare privacy policies."""
    return _read_source("emr_encounters", start_date, end_date)


@tool
def fetch_data_warehouse_risk_events(
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    """Fetch consolidated risk events for AML, privacy, vendor, and incident monitoring policies."""
    return _read_source("data_warehouse_risk_events", start_date, end_date)


DATA_TOOLS = [
    fetch_core_banking_accounts,
    fetch_core_banking_transactions,
    fetch_erp_invoices,
    fetch_emr_encounters,
    fetch_data_warehouse_risk_events,
]
TOOLS_BY_NAME = {tool_item.name: tool_item for tool_item in DATA_TOOLS}


class DataFetcherAgent:
    """Agent 1: select mock-data tools, run them, and classify the fetched data."""

    def __init__(self) -> None:
        model_name = os.getenv("GROQ_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")
        self.llm = ChatGroq(model=model_name, temperature=0) if os.getenv("GROQ_API_KEY") else None

    async def run(
        self,
        policy_name: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> DataFetchResponse:
        run_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
        self._log_event(
            run_id,
            "request_received",
            "success",
            policy_name=policy_name,
            start_date=start_date,
            end_date=end_date,
        )

        try:
            tool_calls = self._choose_tools(run_id, policy_name, start_date, end_date)
            fetched_data = self._run_tools(run_id, tool_calls)
            reviewed_data = self._review_compliance(run_id, policy_name, fetched_data)

            response = DataFetchResponse(
                result="success",
                message="data fetched",
                data=DataFetchPayload(
                    compliant_data=[
                        ApiComplianceDataItem.model_validate(item.model_dump())
                        for item in reviewed_data.compliant_data
                    ],
                    non_compliant_data=[
                        ApiComplianceDataItem.model_validate(item.model_dump())
                        for item in reviewed_data.non_compliant_data
                    ],
                ),
            )
            self._log_event(
                run_id,
                "response_ready",
                "success",
                compliant_count=len(reviewed_data.compliant_data),
                non_compliant_count=len(reviewed_data.non_compliant_data),
            )
            return response
        except Exception as exc:
            self._log_event(
                run_id,
                "pipeline_failed",
                "failure",
                error=str(exc),
                traceback=traceback.format_exc(),
            )
            return DataFetchResponse(
                result="failure",
                message=f"data fetch failed: {exc}",
                data=DataFetchPayload(compliant_data=[], non_compliant_data=[]),
            )

    def _choose_tools(
        self,
        run_id: str,
        policy_name: str,
        start_date: str | None,
        end_date: str | None,
    ) -> list[dict[str, Any]]:
        self._log_event(
            run_id,
            "tool_selection_started",
            "started",
            policy_name=policy_name,
            llm_enabled=self.llm is not None,
        )
        if self.llm is None:
            tool_calls = self._fallback_tool_calls(policy_name, start_date, end_date)
            self._log_event(
                run_id,
                "tool_selection_completed",
                "success",
                selection_mode="fallback",
                tool_calls=tool_calls,
            )
            return tool_calls

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a data fetcher. Choose only the tools needed for the given policy. "
                    "Call one or more tools. Do not answer in text.",
                ),
                (
                    "human",
                    "Policy name: {policy_name}\n"
                    "Date range: {start_date} to {end_date}\n\n"
                    "Available policy families:\n"
                    "- cash reserve ratio and banking balance policies need account and transaction tools\n"
                    "- AML and suspicious activity policies need transaction and risk event tools\n"
                    "- vendor tax and TDS policies need ERP invoice tools\n"
                    "- HIPAA, healthcare privacy, and record access policies need EMR and risk event tools",
                ),
            ]
        )
        try:
            message = (prompt | self.llm.bind_tools(DATA_TOOLS)).invoke(
                {
                    "policy_name": policy_name,
                    "start_date": start_date or "not provided",
                    "end_date": end_date or "not provided",
                }
            )

            tool_calls = [
                {
                    "name": call["name"],
                    "args": {
                        **call.get("args", {}),
                        "start_date": start_date,
                        "end_date": end_date,
                    },
                }
                for call in message.tool_calls
                if call["name"] in TOOLS_BY_NAME
            ]
            if not tool_calls:
                tool_calls = self._fallback_tool_calls(policy_name, start_date, end_date)
                self._log_event(
                    run_id,
                    "tool_selection_completed",
                    "success",
                    selection_mode="fallback_after_empty_llm_tool_calls",
                    tool_calls=tool_calls,
                )
                return tool_calls

            self._log_event(
                run_id,
                "tool_selection_completed",
                "success",
                selection_mode="llm",
                tool_calls=tool_calls,
            )
            return tool_calls
        except Exception as exc:
            self._log_event(
                run_id,
                "tool_selection_failed",
                "failure",
                error=str(exc),
                traceback=traceback.format_exc(),
            )
            tool_calls = self._fallback_tool_calls(policy_name, start_date, end_date)
            self._log_event(
                run_id,
                "tool_selection_completed",
                "success",
                selection_mode="fallback_after_llm_failure",
                tool_calls=tool_calls,
            )
            return tool_calls

    def _run_tools(self, run_id: str, tool_calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
        fetched_data = []
        for call in tool_calls:
            self._log_event(
                run_id,
                "tool_call_started",
                "started",
                tool_name=call["name"],
                args=call["args"],
            )
            try:
                tool_result = TOOLS_BY_NAME[call["name"]].invoke(call["args"])
                fetched_data.append(tool_result)
                self._log_event(
                    run_id,
                    "tool_call_completed",
                    "success",
                    tool_name=call["name"],
                    source=tool_result["source"],
                    record_count=tool_result["record_count"],
                )
            except Exception as exc:
                self._log_event(
                    run_id,
                    "tool_call_failed",
                    "failure",
                    tool_name=call["name"],
                    args=call["args"],
                    error=str(exc),
                    traceback=traceback.format_exc(),
                )
        return fetched_data

    def _review_compliance(
        self,
        run_id: str,
        policy_name: str,
        fetched_data: list[dict[str, Any]],
    ) -> ComplianceReviewOutput:
        self._log_event(
            run_id,
            "compliance_review_started",
            "started",
            policy_name=policy_name,
            llm_enabled=self.llm is not None,
            source_count=len(fetched_data),
            total_records=sum(payload["record_count"] for payload in fetched_data),
        )
        if self.llm is None:
            reviewed_data = self._fallback_review(fetched_data)
            self._log_event(
                run_id,
                "compliance_review_completed",
                "success",
                review_mode="fallback",
                compliant_count=len(reviewed_data.compliant_data),
                non_compliant_count=len(reviewed_data.non_compliant_data),
            )
            return reviewed_data

        reviewer = self.llm.with_structured_output(ComplianceReviewOutput)
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a compliance reviewer. Review every fetched record. "
                    "Return records as compliant or non compliant. "
                    "Each item must include value, reason, and flag. "
                    "Use flag='compliant' or flag='non_compliant'. "
                    "For value, copy the full source record object whenever possible. "
                    "Do not summarize value as a plain string unless the source record is unavailable.",
                ),
                (
                    "human",
                    "Policy name: {policy_name}\n\nFetched data:\n{fetched_data}",
                ),
            ]
        )
        try:
            reviewed_data = (prompt | reviewer).invoke(
                {
                    "policy_name": policy_name,
                    "fetched_data": json.dumps(fetched_data, indent=2),
                }
            )
            self._log_event(
                run_id,
                "compliance_review_completed",
                "success",
                review_mode="llm",
                compliant_count=len(reviewed_data.compliant_data),
                non_compliant_count=len(reviewed_data.non_compliant_data),
            )
            return reviewed_data
        except Exception as exc:
            self._log_event(
                run_id,
                "compliance_review_failed",
                "failure",
                review_mode="llm",
                error=str(exc),
                traceback=traceback.format_exc(),
            )
            reviewed_data = self._fallback_review(fetched_data)
            self._log_event(
                run_id,
                "compliance_review_completed",
                "success",
                review_mode="fallback_after_llm_failure",
                compliant_count=len(reviewed_data.compliant_data),
                non_compliant_count=len(reviewed_data.non_compliant_data),
            )
            return reviewed_data

    def _fallback_tool_calls(
        self,
        policy_name: str,
        start_date: str | None,
        end_date: str | None,
    ) -> list[dict[str, Any]]:
        normalized = policy_name.lower()
        args = {"start_date": start_date, "end_date": end_date}

        if any(word in normalized for word in ["aml", "suspicious"]):
            names = ["fetch_core_banking_transactions", "fetch_data_warehouse_risk_events"]
        elif any(word in normalized for word in ["vendor", "tds", "tax", "gst"]):
            names = ["fetch_erp_invoices"]
        elif any(word in normalized for word in ["hipaa", "healthcare", "patient", "record access"]):
            names = ["fetch_emr_encounters", "fetch_data_warehouse_risk_events"]
        else:
            names = ["fetch_core_banking_accounts", "fetch_core_banking_transactions"]

        return [{"name": name, "args": args} for name in names]

    def _fallback_review(self, fetched_data: list[dict[str, Any]]) -> ComplianceReviewOutput:
        compliant_data: list[ComplianceDataItem] = []
        non_compliant_data: list[ComplianceDataItem] = []

        for source_payload in fetched_data:
            for record in source_payload["records"]:
                is_flagged, reason = self._basic_compliance_check(record)
                item = ComplianceDataItem(
                    value=record,
                    reason=reason,
                    flag="non_compliant" if is_flagged else "compliant",
                )
                if is_flagged:
                    non_compliant_data.append(item)
                else:
                    compliant_data.append(item)

        return ComplianceReviewOutput(
            compliant_data=compliant_data,
            non_compliant_data=non_compliant_data,
        )

    def _basic_compliance_check(self, record: dict[str, Any]) -> tuple[bool, str]:
        risk_flag = record.get("risk_flag")
        if risk_flag and risk_flag != "none":
            return True, f"Risk flag present: {risk_flag}"

        status = record.get("status")
        if status in {"frozen", "pending_review", "open", "disputed"}:
            return True, f"Record status requires review: {status}"

        payment_status = record.get("payment_status")
        if payment_status == "disputed":
            return True, "Invoice payment status is disputed"

        kyc_status = record.get("kyc_status")
        if kyc_status in {"pending_review", "enhanced_due_diligence"}:
            return True, f"KYC status requires review: {kyc_status}"

        access_reason = record.get("access_reason")
        if access_reason == "unusual_after_hours_access":
            return True, "Patient record access reason is unusual after-hours access"

        return False, "No compliance flags found in fetched data"

    def _log_event(
        self,
        run_id: str,
        step: str,
        status: str,
        **details: Any,
    ) -> None:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "run_id": run_id,
            "step": step,
            "status": status,
            "details": details,
        }
        with LOG_FILE.open("a", encoding="utf-8") as file:
            file.write(json.dumps(entry) + "\n")
