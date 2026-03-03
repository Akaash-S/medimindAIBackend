import os
import sys
from datetime import date, timedelta, datetime

# Add the current directory to sys.path so 'app' can be imported
sys.path.append(os.getcwd())

from app.core.firebase import db
import json

def test_get_doctor_slots(doctor_id, patient_uid):
    print(f"Testing for doctor_id: {doctor_id}, patient_uid: {patient_uid}")
    
    # Security check simulation
    has_assignment = bool(list(
        db.collection("reports")
        .where("user_id", "==", patient_uid)
        .where("doctor_id", "==", doctor_id)
        .limit(1)
        .stream()
    ))
    print(f"has_assignment: {has_assignment}")
    
    if not has_assignment:
        has_rec = bool(list(
            db.collection("consultation_recommendations")
            .where("patient_id", "==", patient_uid)
            .where("doctor_id", "==", doctor_id)
            .where("status", "==", "active")
            .limit(1)
            .stream()
        ))
        print(f"has_rec: {has_rec}")
        if not has_rec:
            print("Access denied")
            return

    # Slot generation logic
    doctor_doc = db.collection("users").document(doctor_id).get()
    print(f"doctor_doc exists: {doctor_doc.exists}")
    
    working_hours = []
    consultation_duration = 30
    if doctor_doc.exists:
        data = doctor_doc.to_dict()
        working_hours = data.get("working_hours", [])
        consultation_duration = int(data.get("consultation_duration", 30))
    
    print(f"working_hours count: {len(working_hours)}")
    
    day_schedule = {}
    for wh in working_hours:
        if wh.get("active") and wh.get("day") and wh.get("start") and wh.get("end"):
            day_schedule[wh["day"].lower()] = {
                "start": wh["start"],
                "end": wh["end"],
            }
    
    print(f"day_schedule: {day_schedule}")
    
    WEEKDAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    generated_slots = []
    today = date.today()
    print(f"Today is: {today} ({WEEKDAY_NAMES[today.weekday()]})")
    
    for delta in range(0, 14):
        day = today + timedelta(days=delta)
        day_name = WEEKDAY_NAMES[day.weekday()]
        if day_name not in day_schedule:
            # print(f"Skipping {day_name} (not in schedule)")
            continue
        
        sched = day_schedule[day_name]
        print(f"Processing {day_name} ({day.isoformat()}): {sched['start']} - {sched['end']}")
        
        try:
            start_dt = datetime.strptime(f"{day.isoformat()} {sched['start']}", "%Y-%m-%d %H:%M")
            end_dt = datetime.strptime(f"{day.isoformat()} {sched['end']}", "%Y-%m-%d %H:%M")
        except ValueError as e:
            print(f"Error parsing times for {day_name}: {e}")
            continue

        current_dt = start_dt
        while current_dt + timedelta(minutes=consultation_duration) <= end_dt:
            slot_start = current_dt.strftime("%H:%M")
            slot_end = (current_dt + timedelta(minutes=consultation_duration)).strftime("%H:%M")
            
            generated_slots.append({
                "date": day.isoformat(),
                "start_time": slot_start,
                "end_time": slot_end,
            })
            current_dt += timedelta(minutes=consultation_duration)
    
    print(f"Generated slots count: {len(generated_slots)}")
    if generated_slots:
        print(f"First slot: {generated_slots[0]}")

if __name__ == "__main__":
    # From previous check:
    # Doctor: KATVEpcSNDVLOe5adcKzFSsLAr72
    # Patient: XMqVZuckZcXFxEIeW45E8mQexxz1
    test_get_doctor_slots("KATVEpcSNDVLOe5adcKzFSsLAr72", "XMqVZuckZcXFxEIeW45E8mQexxz1")
