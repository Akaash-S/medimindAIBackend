import os
import sys
from datetime import date, timedelta, datetime

# Add the current directory to sys.path so 'app' can be imported
sys.path.append(os.getcwd())

from app.core.firebase import db
import json

def test_get_doctor_slots(doctor_id, patient_uid):
    print(f"--- DEBUG START ---")
    print(f"doctor_id: '{doctor_id}'")
    print(f"patient_uid: '{patient_uid}'")
    
    # 1. Security Check
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
            print("RESULT: Forbidden (403)")
            return

    # 2. Fetch Doctor Info
    doctor_doc = db.collection("users").document(doctor_id).get()
    print(f"doctor_doc exists: {doctor_doc.exists}")
    
    if not doctor_doc.exists:
        print("RESULT: Doctor not found (404)")
        return
        
    data = doctor_doc.to_dict()
    working_hours = data.get("working_hours", [])
    print(f"working_hours count: {len(working_hours)}")
    
    # 3. Manual Slots
    manual_slots = []
    slots_ref = db.collection("users").document(doctor_id).collection("availability").stream()
    for doc in slots_ref:
        slot = doc.to_dict()
        print(f"Checking manual slot: {slot}")
        if slot.get("status", "free") == "free":
            slot["id"] = doc.id
            slot["source"] = "manual"
            manual_slots.append(slot)
    print(f"manual_slots count: {len(manual_slots)}")

    # 4. Working Hours Schedule
    day_schedule = {}
    for wh in working_hours:
        if wh.get("active") and wh.get("day") and wh.get("start") and wh.get("end"):
            day_schedule[wh["day"].lower()] = {
                "start": wh["start"],
                "end": wh["end"],
            }
    print(f"day_schedule: {day_schedule}")
    
    # 5. Generated Slots
    WEEKDAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    generated_slots = []
    today = date.today()
    print(f"Today: {today}")
    
    consultation_duration = int(data.get("consultation_duration", 30))
    
    # (Existing appointments suppression omitted for now as it's just filtering)
    existing_times = set() 

    for delta in range(0, 14):
        day = today + timedelta(days=delta)
        day_name = WEEKDAY_NAMES[day.weekday()]
        if day_name not in day_schedule:
            continue
        
        sched = day_schedule[day_name]
        try:
            start_dt = datetime.strptime(f"{day.isoformat()} {sched['start']}", "%Y-%m-%d %H:%M")
            end_dt = datetime.strptime(f"{day.isoformat()} {sched['end']}", "%Y-%m-%d %H:%M")
        except ValueError:
            continue

        current_dt = start_dt
        while current_dt + timedelta(minutes=consultation_duration) <= end_dt:
            slot_start = current_dt.strftime("%H:%M")
            slot_end = (current_dt + timedelta(minutes=consultation_duration)).strftime("%H:%M")
            generated_slots.append({
                "id": f"gen_{day.isoformat()}_{slot_start}",
                "date": day.isoformat(),
                "start_time": slot_start,
                "end_time": slot_end,
                "status": "free",
                "source": "schedule",
            })
            current_dt += timedelta(minutes=consultation_duration)
            
    print(f"generated_slots count: {len(generated_slots)}")
    
    # 6. Merge & Sort
    seen = set()
    all_slots = []
    for slot in manual_slots + generated_slots:
        key = (slot.get("date", ""), slot.get("start_time", ""))
        if key not in seen:
            seen.add(key)
            all_slots.append(slot)
            
    all_slots.sort(key=lambda x: (x.get("date", ""), x.get("start_time", "")))
    print(f"RESULT: {len(all_slots)} slots found")
    if all_slots:
        print(f"First 3 slots: {json.dumps(all_slots[:3], indent=2)}")

if __name__ == "__main__":
    # Real IDs from Firestore checks
    doctor_id = "KATVEpcSNDVLOe5adcKzFSsLAr72"
    patient_uid = "XMqVZuckZcXFxEIeW45E8mQexxz1"
    test_get_doctor_slots(doctor_id, patient_uid)
