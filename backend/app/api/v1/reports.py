from fastapi import APIRouter, HTTPException, Response

from ...core.database import db
from ...models.schemas import JobReportResponse

router = APIRouter(prefix="/reports", tags=["Reports"])

@router.get("/{job_id}", response_model=JobReportResponse)
async def get_report(job_id: str):
    """Retrieve full analysis report and structured deliverables for a job."""
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    report = db.get_report(job_id)
    if not report:
        if job["status"] in ("queued", "running"):
            raise HTTPException(status_code=202, detail="Analysis is still in progress")
        raise HTTPException(status_code=404, detail="Report not found for this job")

    final_state = report.get("final_state") or {}

    return {
        "job_id": job_id,
        "ticker": job["ticker"],
        "trade_date": job["trade_date"],
        "recommendation": report.get("recommendation") or job.get("decision_signal"),
        "executive_summary": report.get("executive_summary"),
        "entry_price": report.get("entry_price"),
        "stop_loss": report.get("stop_loss"),
        "target_price": report.get("target_price"),
        "complete_report_md": report.get("complete_report_md"),
        "market_report_md": report.get("market_report_md"),
        "sentiment_report_md": report.get("sentiment_report_md"),
        "news_report_md": report.get("news_report_md"),
        "fundamentals_report_md": report.get("fundamentals_report_md"),
        "investment_debate": final_state.get("investment_debate_state"),
        "risk_debate": final_state.get("risk_debate_state"),
        "trader_investment_plan": final_state.get("trader_investment_plan"),
    }

@router.get("/{job_id}/tabs/{tab_name}")
async def get_report_tab(job_id: str, tab_name: str):
    """Retrieve specific report tab content (market, sentiment, news, fundamentals, complete)."""
    report = db.get_report(job_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    tab_map = {
        "market": report.get("market_report_md"),
        "sentiment": report.get("sentiment_report_md"),
        "news": report.get("news_report_md"),
        "fundamentals": report.get("fundamentals_report_md"),
        "complete": report.get("complete_report_md"),
    }
    if tab_name.lower() not in tab_map:
        raise HTTPException(status_code=404, detail=f"Tab '{tab_name}' not recognized")
    return {"job_id": job_id, "tab": tab_name, "content": tab_map[tab_name.lower()]}

@router.get("/{job_id}/download")
async def download_report_md(job_id: str, tab: str = "complete"):
    """Download the analysis report as a Markdown (.md) file attachment."""
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    report = db.get_report(job_id)
    if not report:
        if job.get("status") in ("queued", "running"):
            raise HTTPException(status_code=202, detail="Analysis is still in progress")
        raise HTTPException(status_code=404, detail="Report not found for this job")

    clean_tab = tab.lower().strip()
    tab_map = {
        "market": report.get("market_report_md"),
        "sentiment": report.get("sentiment_report_md"),
        "news": report.get("news_report_md"),
        "fundamentals": report.get("fundamentals_report_md"),
        "complete": report.get("complete_report_md"),
        "overview": report.get("complete_report_md"),
    }

    content = tab_map.get(clean_tab) or report.get("complete_report_md") or report.get("executive_summary") or ""
    if not content:
        raise HTTPException(status_code=404, detail=f"No markdown content available for tab '{tab}'")

    raw_ticker = job.get("ticker", "REPORT")
    clean_ticker = "".join(c for c in raw_ticker if c.isalnum() or c in ("-", "_")).upper() or "REPORT"
    raw_date = str(job.get("trade_date", "DATE"))
    clean_date = "".join(c for c in raw_date if c.isalnum() or c in ("-", "_")) or "DATE"
    tab_suffix = clean_tab.capitalize() if clean_tab not in ("complete", "overview") else "Complete"
    filename = f"TradingAgents_{clean_ticker}_{clean_date}_{tab_suffix}.md"

    return Response(
        content=content.encode("utf-8"),
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-cache",
            "Access-Control-Expose-Headers": "Content-Disposition",
        },
    )


