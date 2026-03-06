from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

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

app = FastAPI(title="Leadership Misalignment Cost API", version="1.0.0")

# CORS
# In production, set ALLOWED_ORIGINS to your Wix domain + your Render Static Site domain.
# Example: https://www.yoursite.com,https://your-frontend.onrender.com
allowed_origins_env = os.getenv("ALLOWED_ORIGINS", "").strip()
if allowed_origins_env:
    allowed_origins = [o.strip()
                       for o in allowed_origins_env.split(",") if o.strip()]
else:
    # Dev-friendly default. Tighten in production via ALLOWED_ORIGINS.
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


class EmailReportRequest(BaseModel):
    email: str = Field(..., min_length=3)
    inputs: Dict[str, Any]
    result: Dict[str, Any]


def get_industry_benchmark_pct(industry: str) -> float:
    v = BENCHMARKS.get(industry)
    return float(v) if v is not None else DEFAULT_BENCHMARK_PCT


def AED(n: Any) -> str:
    try:
        return f"AED ${float(n):,.0f}"
    except Exception:
        return "AED $0"


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

        return {
            "monthly_cost": r.monthly_cost,
            "annual_cost": r.annual_cost,
            "cost_per_employee": r.cost_per_employee,
            "recoverable_profit": r.recoverable_profit,
            "industry_benchmark_pct": r.industry_benchmark_pct,
            "user_misalignment_pct": r.user_misalignment_pct,
            "excess_pct": r.excess_pct,
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
        raise HTTPException(
            status_code=500, detail="Missing Mailgun environment variables")

    inputs = req.inputs or {}
    result = req.result or {}

    subject = "Your Leadership Misalignment Cost Result"

    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Leadership Misalignment Cost</title>
  <style>
    body {{
      font-family: Arial, Helvetica, sans-serif;
      color: #111;
      margin: 0;
      padding: 24px 18px;
      background: #fff;
      max-width: 680px;
    }}
    h2 {{
      margin: 0 0 6px;
    }}
    .muted {{
      color: #666;
      font-size: 13px;
    }}
    .lead {{
      margin-top: 14px;
      font-size: 15px;
      line-height: 1.5;
    }}
    .box {{
      margin-top: 14px;
      padding: 14px;
      border: 1px solid #e6e6e6;
      border-radius: 10px;
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
    }}
    .section-title {{
      margin: 0 0 8px;
      font-size: 14px;
      font-weight: 700;
      color: #333;
    }}
    .cta {{
      margin-top: 18px;
      padding: 14px;
      border-radius: 10px;
      background: #f7f7f7;
      line-height: 1.5;
    }}
    .cta a {{
      color: #111;
      font-weight: 700;
      text-decoration: none;
    }}
    .spacer {{
      height: 10px;
    }}
  </style>
</head>
<body>
  <h2>Leadership Misalignment Cost</h2>
  <div class="muted">The hidden cost of leadership drag inside your organisation.</div>

  <div class="lead">
    Based on the inputs provided, leadership misalignment may be costing approximately <strong>{AED(result.get("annual_cost"))} per year</strong>.
  </div>

  <div class="box">
    <div class="section-title">Summary</div>
    <table>
      <tr><td>Monthly Leadership Cost</td><td>{AED(result.get("monthly_cost"))}</td></tr>
      <tr><td>Annual Leadership Cost</td><td>{AED(result.get("annual_cost"))}</td></tr>
      <tr><td>Cost Per Employee</td><td>{AED(result.get("cost_per_employee"))}</td></tr>
      <tr><td>Recoverable Profit Opportunity (Annual)</td><td>{AED(result.get("recoverable_profit"))}</td></tr>
    </table>
  </div>

  <div class="box">
    <div class="section-title">Benchmark Comparison</div>
    <div style="margin-top:8px; line-height:1.5">
      Industry Benchmark: {float(result.get("industry_benchmark_pct", 0)):.1f}%<br/>
      Your Estimate: {float(result.get("user_misalignment_pct", 0)):.1f}%<br/>
      {"Above typical industry range." if float(result.get("excess_pct", 0)) > 0 else "Within typical industry range."}
    </div>
  </div>

  <div class="box">
    <div class="section-title">What this usually reflects</div>
    <div style="line-height:1.6">
      Leadership inefficiency rarely comes from one issue. It usually shows up through unclear priorities, slow decision-making, inconsistent expectations, and gaps in leadership capability.
    </div>
  </div>

  <div class="cta">
    <div class="section-title">What leaders typically do next</div>

    <div>
      <strong>Option 1 - Work through the alignment process internally</strong><br/>
      Leadership Alignment Workbook - AED 97<br/>
      <span class="muted">[Insert workbook payment link]</span>
    </div>

    <div class="spacer"></div>

    <div>
      <strong>Option 2 - Discuss the result</strong><br/>
      If you want help translating this result into a practical plan for your leadership team, book a short strategy call.<br/>
      <span class="muted">[Insert strategy call link]</span>
    </div>

    <div class="muted" style="margin-top:10px">Candoo Culture</div>
  </div>

  <p class="muted" style="margin-top:16px; line-height:1.5">
    Inputs captured: industry={inputs.get("industry")} | employees={inputs.get("total_employees")} |
    avg_salary={inputs.get("avg_salary")} | misalignment_pct={inputs.get("misalignment_pct")}
  </p>

  <p class="muted" style="margin-top:12px; line-height:1.5">
    This estimate is based on benchmark ranges observed across leadership and engagement research including Gallup, McKinsey, and Deloitte studies.
  </p>
</body>
</html>
"""

    try:
        r = requests.post(
            f"https://api.mailgun.net/v3/{mg_domain}/messages",
            auth=("api", mg_api_key),
            data={
                "from": f"Candoo Culture Reports <{mg_sender}>",
                "to": [recipient],
                "subject": subject,
                "html": html,
            },
            timeout=20,
        )
    except Exception as e:
        raise HTTPException(
            status_code=502, detail=f"Mailgun request failed: {e}")

    if r.status_code >= 300:
        raise HTTPException(status_code=502, detail=f"Mailgun error: {r.text}")

    return {"success": True}
