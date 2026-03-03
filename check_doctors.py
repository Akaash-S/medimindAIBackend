import os
import sys

# Add the current directory to sys.path so 'app' can be imported
sys.path.append(os.getcwd())

from app.core.firebase import db
import json

def check_doctors():
    doctors = db.collection("users").where("role", "==", "doctor").stream()
    results = []
    for doc in doctors:
        data = doc.to_dict()
        results.append({
            "uid": doc.id,
            "full_name": data.get("full_name"),
            "working_hours": data.get("working_hours"),
            "assigned_doctor": data.get("assigned_doctor")
        })
    print(json.dumps(results, indent=2))

if __name__ == "__main__":
    check_doctors()
