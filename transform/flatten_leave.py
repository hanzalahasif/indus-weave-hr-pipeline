"""
Stage 2d — flatten_leave.py
Transforms nested leave_requests.json according to business rules:
  1. Rule 16: Counts only if both approvals (Manager & HR) are 'Approved' and cancelled_at is empty.
  2. Rule 17: Leave day is any day in from-to range. Sundays and plant holidays inside range are excluded.
  3. Writes:
     - staging.leave_requests
     - staging.leave_approval_steps
     - staging.leave_days
"""
import json
import pandas as pd

from config import RAW_FILES, create_db_engine
from transform.clean_employees import _write_staging

PLANT_TO_SCOPE = {
    "Head Office": "HO",
    "Korangi Plant": "KOR",
    "SITE Plant": "SITE",
    "Faisalabad Plant": "FSD",
}


def run(engine=None):
    if engine is None:
        engine = create_db_engine()

    # ── Read holidays for plant filtering ─────────────────────────────────────
    holidays_path = RAW_FILES["holidays"]
    df_hol = pd.read_csv(holidays_path, dtype=str)
    # dict: plant_scope -> set of holiday dates
    holiday_map = {}
    for _, row in df_hol.iterrows():
        dt = row["holiday_date"].strip()
        scope = row["scope"].strip().upper()
        holiday_map.setdefault(scope, set()).add(dt)

    def is_plant_holiday(dt_str, plant_name):
        scope = PLANT_TO_SCOPE.get(plant_name, "")
        if dt_str in holiday_map.get("ALL", set()):
            return True
        if scope and dt_str in holiday_map.get(scope, set()):
            return True
        return False

    # ── Read leave_requests.json ──────────────────────────────────────────────
    leave_file = RAW_FILES["leave_requests"]
    with open(leave_file, encoding="utf-8") as f:
        data = json.load(f)

    print(f"Loaded {len(data):,} leave requests from {leave_file.name}")

    requests_list = []
    approvals_list = []
    leave_days_list = []

    for item in data:
        req_id = item.get("request_id")
        emp = item.get("employee", {})
        emp_id = emp.get("emp_id")
        plant = emp.get("plant")

        l_info = item.get("leave", {})
        leave_type = l_info.get("type")
        from_str = l_info.get("from")
        to_str = l_info.get("to")
        days_req = l_info.get("days_requested")

        sub_at = item.get("submitted_at")
        canc_at = item.get("cancelled_at")

        approvals = item.get("approvals", [])

        # Check approval rule: Manager AND HR both Approved, and cancelled_at is empty
        is_mgr_approved = False
        is_hr_approved = False

        for step_data in approvals:
            step_no = step_data.get("step")
            role = step_data.get("approver_role")
            action = step_data.get("action")
            approver_id = step_data.get("approver_id")
            acted_at = step_data.get("acted_at")

            if role == "Manager" and action == "Approved":
                is_mgr_approved = True
            elif role == "HR" and action == "Approved":
                is_hr_approved = True

            approvals_list.append({
                "request_id": req_id,
                "step": step_no,
                "approver_role": role,
                "approver_id": approver_id,
                "action": action,
                "acted_at": acted_at,
            })

        has_cancelled = bool(canc_at and str(canc_at).strip() not in ("", "None", "nan"))
        is_fully_approved = is_mgr_approved and is_hr_approved and not has_cancelled

        requests_list.append({
            "request_id": req_id,
            "emp_id": emp_id,
            "plant": plant,
            "leave_type": leave_type,
            "from_date": from_str,
            "to_date": to_str,
            "days_requested": days_req,
            "submitted_at": sub_at,
            "cancelled_at": canc_at if has_cancelled else None,
            "is_approved": 1 if is_fully_approved else 0,
        })

        # If fully approved, generate daily rows excluding Sundays and plant holidays
        if is_fully_approved and from_str and to_str:
            try:
                date_range = pd.date_range(start=from_str, end=to_str, freq="D")
                for d in date_range:
                    if d.weekday() == 6:  # Sunday
                        continue
                    d_str = d.strftime("%Y-%m-%d")
                    if is_plant_holiday(d_str, plant):
                        continue
                    leave_days_list.append({
                        "request_id": req_id,
                        "emp_id": emp_id,
                        "plant": plant,
                        "leave_type": leave_type,
                        "leave_date": d_str,
                    })
            except Exception as e:
                print(f"Warning: invalid leave dates for request {req_id}: {e}")

    df_requests = pd.DataFrame(requests_list)
    df_approvals = pd.DataFrame(approvals_list)
    df_leave_days = pd.DataFrame(leave_days_list)

    print(f"  Processed leave requests: {len(df_requests):,} (approved: {df_requests['is_approved'].sum():,})")
    print(f"  Processed approval steps: {len(df_approvals):,}")
    print(f"  Generated approved leave days: {len(df_leave_days):,}")

    _write_staging(engine, "leave_requests", df_requests)
    _write_staging(engine, "leave_approval_steps", df_approvals)
    _write_staging(engine, "leave_days", df_leave_days)

    print("flatten_leave: done")
    return df_requests, df_approvals, df_leave_days


if __name__ == "__main__":
    run()
