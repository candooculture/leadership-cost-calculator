from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MisalignmentCalcResult:
    monthly_cost: float
    annual_cost: float
    cost_per_employee: float
    recoverable_profit: float
    industry_benchmark_pct: float
    user_misalignment_pct: float
    excess_pct: float


def calculate_leadership_misalignment_cost(
    *,
    employees: int,
    avg_salary: float,
    misalignment_pct: float,
    industry_benchmark_pct: float,
) -> MisalignmentCalcResult:
    employees = int(employees)
    avg_salary = float(avg_salary)
    misalignment_pct = float(misalignment_pct)
    industry_benchmark_pct = float(industry_benchmark_pct)

    payroll = float(employees) * avg_salary

    drag_rate = misalignment_pct / 100.0
    annual_cost = payroll * drag_rate
    monthly_cost = annual_cost / 12.0

    cost_per_employee = (annual_cost / float(employees)) if employees > 0 else 0.0

    # Benchmark comparison for display
    excess_pct = max(0.0, misalignment_pct - industry_benchmark_pct)

    # Recoverable opportunity against high-performance target
    TARGET_MISALIGNMENT_PCT = 5.0
    recoverable_pct = max(0.0, misalignment_pct - TARGET_MISALIGNMENT_PCT)
    recoverable_rate = recoverable_pct / 100.0
    recoverable_profit = payroll * recoverable_rate

    return MisalignmentCalcResult(
        monthly_cost=monthly_cost,
        annual_cost=annual_cost,
        cost_per_employee=cost_per_employee,
        recoverable_profit=recoverable_profit,
        industry_benchmark_pct=industry_benchmark_pct,
        user_misalignment_pct=misalignment_pct,
        excess_pct=excess_pct,
    )
