# AI Compliance Monitoring: Data Fetcher Agent

This project is a FastAPI + LangChain prototype for an AI Compliance Monitoring system.

The current implementation focuses on **Agent 1: Data Fetcher Agent**. It accepts a policy name, lets an LLM decide which mock internal data tools to call, fetches records from mock datasets, asks the LLM to classify the fetched records as compliant or non-compliant, and returns structured output for regulatory reporting.

## 1. Architecture

### High-Level Flow

```text
Client
  |
  | POST /api/agents/data-fetch
  v
FastAPI Route
  |
  v
DataFetcherAgent
  |
  | 1. LLM chooses tools based on policy_name
  v
LangChain Tool Selection
  |
  | 2. Selected tools read mock datasets
  v
Mock Data Tools
  |
  | 3. LLM reviews fetched records
  v
Compliance Classification
  |
  | 4. API returns grouped compliant / non-compliant data
  v
Client Response
```

The agent also writes detailed execution logs to:

```text
logs/data_fetcher.log
```

Each run gets a unique `run_id`, and each step logs whether it started, succeeded, or failed.

### Project Structure

```text
mock_api/
  main.py            FastAPI routes and API entrypoint
  agent_pipeline.py  LangChain agent pipeline, tools, review flow, logging
  data_loader.py     CSV/JSON dataset loading and filtering
  metrics.py         Optional mock metric aggregation endpoints
  schemas.py         Pydantic request and response models

mock_data/
  regulatory_obligations.json
  core_banking_accounts.json
  core_banking_transactions.csv
  erp_invoices.csv
  emr_encounters.json
  data_warehouse_risk_events.json

logs/
  data_fetcher.log   Created automatically after agent calls

requirements.txt
README.md
```

### Main API Route

The agent endpoint is defined in `mock_api/main.py`:

```python
@app.post(
    "/api/agents/data-fetch",
    response_model=DataFetchResponse,
    response_model_by_alias=True,
)
async def run_data_fetcher_agent(request: DataFetchRequest):
    return await data_fetcher_agent.run(
        policy_name=request.policy_name,
        start_date=request.start_date,
        end_date=request.end_date,
    )
```

### Agent Pipeline

The main pipeline is in `mock_api/agent_pipeline.py`:

```python
tool_calls = self._choose_tools(run_id, policy_name, start_date, end_date)
fetched_data = self._run_tools(run_id, tool_calls)
reviewed_data = self._review_compliance(run_id, policy_name, fetched_data)
```

The architecture is intentionally simple:

```text
choose tools -> run tools -> review compliance -> return structured result
```

### LangChain Tools

Each mock source is exposed as a LangChain tool. The LLM decides which tools are needed for the policy.

```python
@tool
def fetch_core_banking_accounts(
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    """Fetch account balance, KYC, account type, and account status data for banking policies."""
    return _read_source("core_banking_accounts", start_date, end_date)
```

Available tools:

```text
fetch_core_banking_accounts
fetch_core_banking_transactions
fetch_erp_invoices
fetch_emr_encounters
fetch_data_warehouse_risk_events
```

Tool mapping by policy family:

| Policy Type | Likely Tools |
| --- | --- |
| Cash reserve ratio / banking balance | `fetch_core_banking_accounts`, `fetch_core_banking_transactions` |
| AML / suspicious activity | `fetch_core_banking_transactions`, `fetch_data_warehouse_risk_events` |
| Vendor tax / TDS / GST | `fetch_erp_invoices` |
| HIPAA / patient access / healthcare privacy | `fetch_emr_encounters`, `fetch_data_warehouse_risk_events` |

### Tool Selection Prompt

The LLM receives the policy name and chooses the tools:

```python
"You are a data fetcher. Choose only the tools needed for the given policy. "
"Call one or more tools. Do not answer in text."
```

If `GROQ_API_KEY` is missing or the LLM tool call fails, the system uses deterministic fallback rules so the endpoint can still be tested locally.

### Compliance Review

After data is fetched, the LLM reviews the records and returns structured compliant and non-compliant groups:

```python
reviewer = self.llm.with_structured_output(ComplianceReviewOutput)
```

The response is normalized before returning to the client, so every item has:

```json
{
  "value": {},
  "reason": "why this record is compliant or non-compliant",
  "flag": "compliant"
}
```

### Logging

Detailed logging is written as JSON Lines:

```text
logs/data_fetcher.log
```

Logged steps include:

```text
request_received
tool_selection_started
tool_selection_completed
tool_selection_failed
tool_call_started
tool_call_completed
tool_call_failed
compliance_review_started
compliance_review_completed
compliance_review_failed
response_ready
pipeline_failed
```

Example log entry:

```json
{
  "timestamp": "2026-05-06T18:00:00.000000+00:00",
  "run_id": "20260506180000000000",
  "step": "tool_call_completed",
  "status": "success",
  "details": {
    "tool_name": "fetch_core_banking_accounts",
    "source": "core_banking_accounts",
    "record_count": 4
  }
}
```

## 2. How To Run

### Create And Activate Virtual Environment

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### Install Dependencies

```powershell
pip install -r requirements.txt
```

### Configure Groq API Key

Create a `.env` file in the project root:

```env
GROQ_API_KEY=your_groq_api_key
GROQ_MODEL=meta-llama/llama-4-scout-17b-16e-instruct
```

You can also place `.env` inside `mock_api/.env`; the app loads both.

If `GROQ_API_KEY` is not present, the project still runs with fallback logic.

### Start FastAPI

Recommended:

```powershell
uvicorn mock_api.main:app --reload
```

Alternative:

```powershell
python mock_api/main.py
```

### Open API Docs

```text
http://127.0.0.1:8000/docs
```

### Health Check

```powershell
curl.exe http://127.0.0.1:8000/health
```

Expected:

```json
{
  "status": "ok",
  "service": "mock-compliance-data-api"
}
```

## 3. Payloads

### Endpoint

```text
POST /api/agents/data-fetch
```

### Request Schema

```json
{
  "policy_name": "string",
  "start_date": "YYYY-MM-DD",
  "end_date": "YYYY-MM-DD"
}
```

Only `policy_name` is required. `start_date` and `end_date` are optional.

### Response Schema

```json
{
  "result": "success",
  "message": "data fetched",
  "data": {
    "compliant data": [
      {
        "value": {},
        "reason": "Record is compliant because...",
        "flag": "compliant"
      }
    ],
    "non compliant data": [
      {
        "value": {},
        "reason": "Record is non-compliant because...",
        "flag": "non_compliant"
      }
    ]
  }
}
```

### Supported Policy Names

Use these exact names for best results:

```text
Daily Cash Reserve Ratio
Suspicious Activity Monitoring
Vendor Tax Deducted at Source
Patient Record Access Audit
```

The LLM can also understand similar natural names, such as:

```text
cash reserve ratio
AML suspicious activity
GST vendor TDS
HIPAA access audit
healthcare privacy audit
patient record access
```

### Payload: Daily Cash Reserve Ratio

```json
{
  "policy_name": "Daily Cash Reserve Ratio",
  "start_date": "2026-04-01",
  "end_date": "2026-04-30"
}
```

Curl:

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/agents/data-fetch -H "Content-Type: application/json" -d "{\"policy_name\":\"Daily Cash Reserve Ratio\",\"start_date\":\"2026-04-01\",\"end_date\":\"2026-04-30\"}"
```

Expected tool family:

```text
fetch_core_banking_accounts
fetch_core_banking_transactions
```

### Payload: Suspicious Activity Monitoring

```json
{
  "policy_name": "Suspicious Activity Monitoring",
  "start_date": "2026-04-01",
  "end_date": "2026-04-30"
}
```

Curl:

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/agents/data-fetch -H "Content-Type: application/json" -d "{\"policy_name\":\"Suspicious Activity Monitoring\",\"start_date\":\"2026-04-01\",\"end_date\":\"2026-04-30\"}"
```

Expected tool family:

```text
fetch_core_banking_transactions
fetch_data_warehouse_risk_events
```

### Payload: Vendor Tax Deducted At Source

```json
{
  "policy_name": "Vendor Tax Deducted at Source",
  "start_date": "2026-04-01",
  "end_date": "2026-04-30"
}
```

Curl:

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/agents/data-fetch -H "Content-Type: application/json" -d "{\"policy_name\":\"Vendor Tax Deducted at Source\",\"start_date\":\"2026-04-01\",\"end_date\":\"2026-04-30\"}"
```

Expected tool family:

```text
fetch_erp_invoices
```

### Payload: Patient Record Access Audit

```json
{
  "policy_name": "Patient Record Access Audit",
  "start_date": "2026-04-01",
  "end_date": "2026-04-30"
}
```

Curl:

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/agents/data-fetch -H "Content-Type: application/json" -d "{\"policy_name\":\"Patient Record Access Audit\",\"start_date\":\"2026-04-01\",\"end_date\":\"2026-04-30\"}"
```

Expected tool family:

```text
fetch_emr_encounters
fetch_data_warehouse_risk_events
```

## Useful Mock API Endpoints

These are lower-level endpoints for inspecting the mock datasets directly:

```text
GET /
GET /health
GET /api/obligations
GET /api/sources
GET /api/sources/{source_name}
GET /api/reporting/obligations/{obligation_id}/metrics
```

Examples:

```powershell
curl.exe http://127.0.0.1:8000/api/sources
curl.exe http://127.0.0.1:8000/api/sources/core_banking_transactions
curl.exe "http://127.0.0.1:8000/api/sources/core_banking_transactions?start_date=2026-04-01&end_date=2026-04-10&risk_flag=large_cash_withdrawal"
curl.exe http://127.0.0.1:8000/api/reporting/obligations/RBI_CRR_DAILY/metrics
curl.exe http://127.0.0.1:8000/api/reporting/obligations/AML_SUSPICIOUS_ACTIVITY/metrics
```

## Notes

- The agent does not return raw tool execution metadata to the client.
- Tool execution details are available in `logs/data_fetcher.log`.
- The LLM performs both tool selection and compliance classification.
- Fallback logic exists so the API remains usable without a Groq key.
- The current second agent, Compliance Review Agent, can later be separated from `_review_compliance` if we want a true two-agent pipeline.
