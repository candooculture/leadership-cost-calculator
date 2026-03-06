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

app = FastAPI(title="Leadership Performance Impact API", version="1.0.0")

# CORS
# In production, set ALLOWED_ORIGINS to your Wix domain + your Render Static Site domain.
# Example: https://www.yoursite.com,https://your-frontend.onrender.com
allowed_origins_env = os.getenv("ALLOWED_ORIGINS", "").strip()
if allowed_origins_env:
    allowed_origins = [o.strip() for o in allowed_origins_env.split(",") if o.strip()]
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
        raise HTTPException(status_code=500, detail="Missing Mailgun environment variables")

    inputs = req.inputs or {}
    result = req.result or {}

    subject = "Your Leadership Performance Impact Result"

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
            f"<strong>{AED(annual_cost)} per year</strong>. Organisations that strengthen "
            f"role clarity, decision rights, management consistency, and operating cadence "
            f"typically reduce this closer to the 4 - 10% range."
        )
    else:
        insight_text = (
            f"This estimate sits within the range commonly seen across organisations. "
            f"Even so, performance loss at this level still represents meaningful value erosion. "
            f"High-performing organisations usually reduce this closer to the 4 - 10% range "
            f"through sharper alignment, execution discipline, and leadership clarity."
        )

    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
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
    .lead {{
      margin-top: 14px;
      font-size: 15px;
      line-height: 1.6;
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
      vertical-align: top;
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
      color: #333333;
    }}
    .cta {{
      margin-top: 18px;
      padding: 14px;
      border-radius: 10px;
      background: #f7f7f7;
      line-height: 1.6;
    }}
    .cta a {{
      color: #111111;
      font-weight: 700;
      text-decoration: none;
    }}
    .spacer {{
      height: 10px;
    }}
    .note {{
      margin-top: 14px;
      color: #666666;
      font-size: 13px;
      line-height: 1.6;
    }}
  </style>
</head>
<body>
  <h2>Leadership Performance Impact</h2>
  <div class="muted">A practical view of how leadership alignment influences execution quality, payroll efficiency, and recoverable enterprise value.</div>

  <div class="lead">
    Based on the inputs provided, leadership performance loss is impacting approximately <strong>{AED(annual_cost)} per year</strong>.
  </div>

  <div class="box">
    <div class="section-title">Summary</div>
    <table>
      <tr><td>Monthly Performance Impact</td><td>{AED(monthly_cost)}</td></tr>
      <tr><td>Annual Performance Impact</td><td>{AED(annual_cost)}</td></tr>
      <tr><td>Impact Per Employee</td><td>{AED(cost_per_employee)}</td></tr>
      <tr><td>Recoverable Value Opportunity (Annual)</td><td>{AED(recoverable_profit)}</td></tr>
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

  <div class="box">
    <div class="section-title">What this usually reflects</div>
    <div style="line-height:1.6">
      Leadership performance loss rarely comes from one issue. It typically shows up through unclear priorities, slow decision-making, inconsistent management standards, blurred accountability, and reduced execution discipline across the business.
    </div>
  </div>

  <div class="cta">
    <div class="section-title">Next Steps</div>

    <div>
      <strong>Option 1 - Strengthen alignment internally</strong><br/>
      Leadership Alignment Workbook - AED 97<br/>
      <span class="muted">[Insert workbook payment link]</span>
    </div>

    <div class="spacer"></div>

    <div>
      <strong>Option 2 - Explore performance uplift</strong><br/>
      If you want help translating this result into a sharper leadership plan, book a short consultation with Candoo Culture.<br/>
      <span class="muted">[Insert strategy call link]</span>
    </div>

    <div class="muted" style="margin-top:10px">Candoo Culture</div>
  </div>

  <p class="note">
    Inputs captured: industry={inputs.get("industry")} | employees={inputs.get("total_employees")} |
    avg_salary={inputs.get("avg_salary")} | misalignment_pct={inputs.get("misalignment_pct")}
  </p>

  <p class="note">
    This estimate is directional and should be used as a leadership decision-support tool alongside internal business context, operating data, and management judgement.
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
