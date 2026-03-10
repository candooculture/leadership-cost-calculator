from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict

import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from calculator import calculate_leadership_misalignment_cost


APP_DIR = Path(__file__).resolve().parent
BENCHMARKS_PATH = APP_DIR / "benchmarks.json"
DEFAULT_BENCHMARK_PCT = 18.0


def load_benchmarks() -> Dict[str, float]:
    if not BENCHMARKS_PATH.exists():
        return {}
    with BENCHMARKS_PATH.open("r", encoding="utf-8") as f:
        raw = json.load(f) or {}
    out: Dict[str, float] = {}
    for k, v in raw.items():
        try:
            out[str(k)] = float(v)
        except Exception:
            continue
    return out


BENCHMARKS = load_benchmarks()

app = FastAPI(title="Leadership Performance Impact API", version="1.1.0")

allowed_origins_env = os.getenv("ALLOWED_ORIGINS", "").strip()
if allowed_origins_env:
    allowed_origins = [o.strip() for o in allowed_origins_env.split(",") if o.strip()]
else:
    allowed_origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


class LeadershipMisalignmentRequest(BaseModel):
    industry: str = Field(..., min_length=1)
    total_employees: int = Field(..., ge=1)
    avg_salary: float = Field(..., gt=0)
    misalignment_pct: float = Field(..., ge=0, le=100)
    market: str | None = None


class EmailReportRequest(BaseModel):
    email: str = Field(..., min_length=3)
    inputs: Dict[str, Any]
    result: Dict[str, Any]


def get_industry_benchmark_pct(industry: str) -> float:
    v = BENCHMARKS.get(industry)
    return float(v) if v is not None else DEFAULT_BENCHMARK_PCT


def format_currency(n: Any, market: str | None) -> str:
    try:
        value = float(n)
    except Exception:
        value = 0.0

    m = (market or "uae").lower()

    if m in ["aud", "australia"]:
        return f"AUD ${value:,.0f}"
    else:
        return f"AED ${value:,.0f}"


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/benchmarks/leadership-misalignment")
def benchmark(industry: str):
    if not industry:
        raise HTTPException(status_code=400, detail="industry is required")
    return {"industry_benchmark_pct": get_industry_benchmark_pct(industry)}


@app.post("/run-leadership-misalignment")
def run_calc(data: LeadershipMisalignmentRequest):
    try:
        industry_benchmark_pct = get_industry_benchmark_pct(data.industry)

        r = calculate_leadership_misalignment_cost(
            employees=data.total_employees,
            avg_salary=data.avg_salary,
            misalignment_pct=data.misalignment_pct,
            industry_benchmark_pct=industry_benchmark_pct,
        )

        market = data.market or "uae"

        return {
            "monthly_cost": r.monthly_cost,
            "annual_cost": r.annual_cost,
            "cost_per_employee": r.cost_per_employee,
            "recoverable_profit": r.recoverable_profit,
            "industry_benchmark_pct": r.industry_benchmark_pct,
            "user_misalignment_pct": r.user_misalignment_pct,
            "excess_pct": r.excess_pct,
            "market": market,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/send-leadership-misalignment-report")
def send_email(req: EmailReportRequest):

    recipient = (req.email or "").strip()
    if "@" not in recipient:
        raise HTTPException(status_code=400, detail="Invalid email")

    mg_api_key = os.getenv("MAILGUN_API_KEY", "").strip()
    mg_domain = os.getenv("MAILGUN_DOMAIN", "").strip()
    mg_sender = os.getenv("MAILGUN_SENDER", "").strip()

    if not (mg_api_key and mg_domain and mg_sender):
        raise HTTPException(status_code=500, detail="Missing Mailgun environment variables")

    inputs = req.inputs or {}
    result = req.result or {}

    market = inputs.get("market") or result.get("market") or "uae"

    annual_cost = float(result.get("annual_cost", 0) or 0)
    monthly_cost = float(result.get("monthly_cost", 0) or 0)
    cost_per_employee = float(result.get("cost_per_employee", 0) or 0)
    recoverable_profit = float(result.get("recoverable_profit", 0) or 0)
    industry_benchmark_pct = float(result.get("industry_benchmark_pct", 0) or 0)
    user_misalignment_pct = float(result.get("user_misalignment_pct", 0) or 0)
    excess_pct = float(result.get("excess_pct", 0) or 0)

    benchmark_status = "Above benchmark range." if excess_pct > 0 else "Within benchmark range."

    if excess_pct > 0:
        insight_text = (
            f"At this level, leadership performance loss is eroding approximately "
            f"<strong>{format_currency(annual_cost, market)} per year</strong>. "
            f"Organisations that strengthen role clarity, decision rights, management consistency, "
            f"and operating cadence typically reduce this closer to the 4 - 10% range."
        )
    else:
        insight_text = (
            f"This estimate sits within the range commonly seen across organisations. "
            f"Even so, performance loss at this level still represents meaningful value erosion. "
            f"High-performing organisations usually reduce this closer to the 4 - 10% range "
            f"through sharper alignment, execution discipline, and leadership clarity."
        )

    subject = "Your Leadership Performance Impact Result"
# ---- Lead capture to Google Sheet ----

sheet_webhook = "https://script.google.com/macros/s/AKfycbx8t-KcrO5Ib9wF9iehQAB3mmHhkCWgs7JwtZGhaq60vMPL900x2Hfsahp9MDhL_WOs/exec"

try:
    payload = {
        "email": recipient,
        "market": market,
        "industry": inputs.get("industry"),
        "total_employees": inputs.get("total_employees"),
        "avg_salary": inputs.get("avg_salary"),
        "misalignment_pct": inputs.get("misalignment_pct"),
        "annual_cost": annual_cost,
        "monthly_cost": monthly_cost,
        "recoverable_profit": recoverable_profit
    }

    requests.post(sheet_webhook, json=payload, timeout=5)

except Exception:
    pass
    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Leadership Performance Impact</title>
<style>
body {{
font-family: Arial, Helvetica, sans-serif;
color: #111111;
margin: 0;
padding: 24px 18px;
background: #ffffff;
max-width: 680px;
}}
h2 {{
margin: 0 0 6px;
font-size: 28px;
line-height: 1.2;
}}
.muted {{
color: #666666;
font-size: 13px;
}}
.box {{
margin-top: 14px;
padding: 14px;
border: 1px solid #e6e6e6;
border-radius: 10px;
background: #ffffff;
}}
table {{
width: 100%;
border-collapse: collapse;
margin-top: 8px;
}}
td {{
padding: 8px 0;
border-bottom: 1px solid #f0f0f0;
}}
td:last-child {{
text-align: right;
font-weight: 700;
white-space: nowrap;
}}
.section-title {{
margin: 0 0 8px;
font-size: 14px;
font-weight: 700;
}}
</style>
</head>

<body>

<h2>Leadership Performance Impact</h2>

<p>
Based on the inputs provided, leadership performance loss is impacting approximately
<strong>{format_currency(annual_cost, market)} per year</strong>.
</p>

<div class="box">
<div class="section-title">Summary</div>
<table>
<tr><td>Monthly Performance Impact</td><td>{format_currency(monthly_cost, market)}</td></tr>
<tr><td>Annual Performance Impact</td><td>{format_currency(annual_cost, market)}</td></tr>
<tr><td>Impact Per Employee</td><td>{format_currency(cost_per_employee, market)}</td></tr>
<tr><td>Recoverable Value Opportunity (Annual)</td><td>{format_currency(recoverable_profit, market)}</td></tr>
</table>
</div>

<div class="box">
<div class="section-title">Benchmark Comparison</div>
<div style="margin-top:8px; line-height:1.6">
Sector Benchmark: {industry_benchmark_pct:.1f}%<br/>
Your Estimate: {user_misalignment_pct:.1f}%<br/>
{benchmark_status}
</div>
</div>

<div class="box">
<div class="section-title">Performance Readout</div>
<div style="line-height:1.6">
{insight_text}
</div>
</div>

<p class="muted" style="margin-top:14px">
Inputs captured: industry={inputs.get("industry")} |
employees={inputs.get("total_employees")} |
avg_salary={inputs.get("avg_salary")} |
misalignment_pct={inputs.get("misalignment_pct")}
</p>

</body>
</html>
"""

    try:
        r = requests.post(
            f"https://api.mailgun.net/v3/{mg_domain}/messages",
            auth=("api", mg_api_key),
            data={
                "from": f"Candoo Insights <{mg_sender}>",
                "to": [recipient],
                "subject": subject,
                "html": html,
            },
            timeout=20,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Mailgun request failed: {e}")

    if r.status_code >= 300:
        raise HTTPException(status_code=502, detail=f"Mailgun error: {r.text}")

    return {"success": True}
