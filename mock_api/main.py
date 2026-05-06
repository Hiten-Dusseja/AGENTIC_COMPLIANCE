import logging
from datetime import datetime, timezone
from typing import Annotated

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse

try:
    from mock_api.agent_pipeline import DataFetcherAgent
    from mock_api.data_loader import (
        UnknownSourceError,
        filter_records,
        list_source_names,
        load_obligations,
        load_source,
        select_fields,
    )
    from mock_api.metrics import build_reporting_metrics
    from mock_api.schemas import DataFetchRequest, DataFetchResponse
except ModuleNotFoundError:
    from agent_pipeline import DataFetcherAgent
    from data_loader import (
        UnknownSourceError,
        filter_records,
        list_source_names,
        load_obligations,
        load_source,
        select_fields,
    )
    from metrics import build_reporting_metrics
    from schemas import DataFetchRequest, DataFetchResponse


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("mock_compliance_api")

app = FastAPI(
    title="AI Compliance Monitoring Mock API",
    version="0.1.0",
    description="Mock internal systems for regulatory reporting data extraction.",
)

data_fetcher_agent = DataFetcherAgent()


@app.middleware("http")
async def log_requests(request: Request, call_next):
    started_at = datetime.now(timezone.utc)
    response = await call_next(request)
    elapsed_ms = (datetime.now(timezone.utc) - started_at).total_seconds() * 1000
    logger.info(
        "method=%s path=%s status=%s elapsed_ms=%.2f",
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
    )
    return response


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail, "status": exc.status_code, "path": request.url.path},
    )


def simulate_failure(fail: bool, x_mock_failure: str | None) -> None:
    if fail or x_mock_failure == "true":
        raise HTTPException(status_code=503, detail="Simulated upstream connection failure")


@app.get("/")
def root():
    return {
        "service": "AI Compliance Monitoring Mock API",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health")
def health():
    return {"status": "ok", "service": "mock-compliance-data-api"}


@app.get("/api/obligations")
def get_obligations(
    fail: bool = False,
    x_mock_failure: Annotated[str | None, Header()] = None,
):
    simulate_failure(fail, x_mock_failure)
    return load_obligations()


@app.get("/api/sources")
def get_sources(
    fail: bool = False,
    x_mock_failure: Annotated[str | None, Header()] = None,
):
    simulate_failure(fail, x_mock_failure)
    return {"sources": list_source_names()}


@app.get("/api/sources/{source_name}")
def get_source_records(
    source_name: str,
    start_date: str | None = None,
    end_date: str | None = None,
    domain: str | None = None,
    status: str | None = None,
    risk_flag: str | None = None,
    fields: Annotated[list[str] | None, Query()] = None,
    fail: bool = False,
    x_mock_failure: Annotated[str | None, Header()] = None,
):
    simulate_failure(fail, x_mock_failure)
    try:
        records = load_source(source_name)
    except UnknownSourceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    filtered = filter_records(
        records,
        start_date=start_date,
        end_date=end_date,
        domain=domain,
        status=status,
        risk_flag=risk_flag,
    )
    return {
        "source": source_name,
        "count": len(filtered),
        "records": select_fields(filtered, fields),
    }


@app.get("/api/reporting/obligations/{obligation_id}/metrics")
def get_obligation_metrics(
    obligation_id: str,
    start_date: str | None = None,
    end_date: str | None = None,
    fail: bool = False,
    x_mock_failure: Annotated[str | None, Header()] = None,
):
    simulate_failure(fail, x_mock_failure)
    payload = build_reporting_metrics(
        obligation_id,
        start_date=start_date,
        end_date=end_date,
    )
    if payload is None:
        raise HTTPException(status_code=404, detail=f"Unknown obligation: {obligation_id}")
    return payload


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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
