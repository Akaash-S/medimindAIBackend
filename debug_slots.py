import asyncio
import os
import sys
from datetime import datetime, date, timedelta

# Add the backend directory to path so we can import from app
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.core.firebase import db

async def check_doctor_availability(doctor_email_or_name: str):
    """Diagnostic script to check why slots might be missing."""
    print(f"--- Diagnosing Availability for: {doctor_email_or_name} ---")
    
    # 1. Find the doctor
    users_ref = db.collection("users")
    query = users_ref.where("role", "==", "doctor")
    docs = query.stream()
    
    doctor = None
    for doc in docs:
        d = doc.to_dict()
        if (doctor_email_or_name.lower() in d.get("email", "").lower() or 
            doctor_email_or_name.lower() in d.get("full_name", "").lower()):
            doctor = d
            doctor["id"] = doc.id
            break
            
    if not doctor:
        print(f"[ERROR] Doctor '{doctor_email_or_name}' not found.")
        return

    print(f"[OK] Found Doctor: {doctor.get('full_name')} (ID: {doctor['id']})")
    
    # 2. Check Working Hours
    working_hours = doctor.get("working_hours", [])
    print(f"\n[1] Working Hours ({len(working_hours)} days configured):")
    if not working_hours:
        print("    [WARNING] No working hours found in profile.")
    else:
        for wh in working_hours:
            status = "ACTIVE" if wh.get("active") else "disabled"
            print(f"    - {wh.get('day', 'unknown'):<10}: {wh.get('start')} to {wh.get('end')} [{status}]")

    # 3. Check Consultation Duration
    duration = doctor.get("consultation_duration", 30)
    print(f"\n[2] Consultation Duration: {duration} minutes")

    # 4. Check Daily Capacities
    capacities = doctor.get("daily_capacities", {})
    print(f"\n[3] Daily Capacity Overrides ({len(capacities)} dates):")
    for d, cap in capacities.items():
        print(f"    - {d}: {cap} max meetings")

    # 5. Check Manual Slots
    manual_slots_ref = db.collection("users").document(doctor["id"]).collection("availability")
    manual_slots = list(manual_slots_ref.stream())
    print(f"\n[4] Manual One-off Slots ({len(manual_slots)} found):")
    for ms in manual_slots:
        s = ms.to_dict()
        print(f"    - {s.get('date')} {s.get('start_time')}-{s.get('end_time')} [{s.get('status')}]")

    # 6. Simulate Slot Generation (14 days)
    now = datetime.now()
    today_date = date.today()
    WEEKDAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    
    day_schedule = {}
    for wh in working_hours:
        if wh.get("active") and wh.get("day") and wh.get("start") and wh.get("end"):
            day_schedule[wh["day"].lower()] = {"start": wh["start"], "end": wh["end"]}

    print(f"\n[5] Simulating Slot Generation (Next 14 Days):")
    print(f"    - Current Server Time: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"    - Today's Date: {today_date}")
    
    total_generated = 0
    for delta in range(0, 14):
        day = today_date + timedelta(days=delta)
        date_str = day.isoformat()
        day_name = WEEKDAY_NAMES[day.weekday()]
        
        daily_cap = capacities.get(date_str)
        if daily_cap is not None and int(daily_cap) <= 0:
            print(f"    ! {date_str} ({day_name}): Skipped (Daily Cap = 0)")
            continue
            
        if day_name not in day_schedule:
            continue
            
        sched = day_schedule[day_name]
        try:
            start_dt = datetime.strptime(f"{date_str} {sched['start']}", "%Y-%m-%d %H:%M")
            end_dt = datetime.strptime(f"{date_str} {sched['end']}", "%Y-%m-%d %H:%M")
        except ValueError:
            print(f"    ! {date_str} ({day_name}): Invalid time format {sched}")
            continue

        day_count = 0
        curr = start_dt
        while curr + timedelta(minutes=duration) <= end_dt:
            if curr > now:
                day_count += 1
            curr += timedelta(minutes=duration)
        
        if day_count > 0:
            print(f"    + {date_str} ({day_name}): Generated {day_count} slots")
            total_generated += day_count

    print(f"\n[FINAL] Total Slots that SHOULD be visible: {total_generated}")

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "Akaash"
    asyncio.run(check_doctor_availability(target))
