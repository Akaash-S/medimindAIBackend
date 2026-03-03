import os
import sys

# Add the current directory to sys.path so 'app' can be imported
sys.path.append(os.getcwd())

from app.core.firebase import db
import json

def check_availability(doctor_id):
    slots = db.collection("users").document(doctor_id).collection("availability").stream()
    results = []
    for doc in slots:
        data = doc.to_dict()
        data["id"] = doc.id
        results.append(data)
    print(json.dumps(results, indent=2))

if __name__ == "__main__":
    check_availability("KATVEpcSNDVLOe5adcKzFSsLAr72")
