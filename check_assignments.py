import asyncio
import os
import sys

# Add the backend directory to path so we can import from app
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.core.firebase import db

async def check_assignments(doctor_id: str):
    """Check if any patients are assigned or recommended to this doctor."""
    print(f"--- Checking Assignments for Doctor ID: {doctor_id} ---")
    
    # 1. Check reports
    reports = db.collection("reports").where("doctor_id", "==", doctor_id).stream()
    report_list = list(reports)
    print(f"\n[1] Assigned Reports ({len(report_list)} found):")
    for r in report_list:
        rd = r.to_dict()
        print(f"    - Patient: {rd.get('user_id')} | Title: {rd.get('report_title')}")

    # 2. Check recommendations
    recs = db.collection("consultation_recommendations").where("doctor_id", "==", doctor_id).stream()
    rec_list = list(recs)
    print(f"\n[2] Active Recommendations ({len(rec_list)} found):")
    for r in rec_list:
        rd = r.to_dict()
        print(f"    - Patient: {rd.get('patient_id')} | Status: {rd.get('status')}")

if __name__ == "__main__":
    doctor_id = sys.argv[1] if len(sys.argv) > 1 else "KATVEpcSNDVLOe5adcKzFSsLAr72"
    asyncio.run(check_assignments(doctor_id))
