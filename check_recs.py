import os
import sys

# Add the current directory to sys.path so 'app' can be imported
sys.path.append(os.getcwd())

from app.core.firebase import db
import json

def check_recommendations():
    recs = db.collection("consultation_recommendations").stream()
    results = []
    for doc in recs:
        data = doc.to_dict()
        results.append({
            "rec_id": doc.id,
            "patient_id": data.get("patient_id"),
            "doctor_id": data.get("doctor_id"),
            "doctor_name": data.get("doctor_name"),
            "status": data.get("status")
        })
    print(json.dumps(results, indent=2))

if __name__ == "__main__":
    check_recommendations()
