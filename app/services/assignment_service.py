from app.core.firebase import db, firestore
from typing import Optional

class AssignmentService:
    @staticmethod
    async def get_least_loaded_doctor() -> Optional[str]:
        """
        Finds the doctor with the fewest assigned patients (LLA algorithm).
        """
        try:
            # 1. Get all doctors
            doctors_ref = db.collection("users").where("role", "==", "doctor").stream()
            doctors = [doc.to_dict() | {"id": doc.id} for doc in doctors_ref]
            
            if not doctors:
                print("No doctors found in the system.")
                return None
                
            # 2. Count patients for each doctor
            # Note: For production with many doctors/patients, we'd store a 'patient_count' 
            # on the doctor document to avoid expensive counts.
            doctor_loads = []
            for doctor in doctors:
                count_query = db.collection("users").where("role", "==", "patient").where("assigned_doctor", "==", doctor["id"])
                # Use aggregation query for efficiency if available, otherwise manual count
                # Using manual count for MVP/Firestore simplicity here
                patient_count = len(list(count_query.stream()))
                doctor_loads.append({
                    "id": doctor["id"],
                    "count": patient_count
                })
            
            # 3. Sort by count and return the first one
            doctor_loads.sort(key=lambda x: x["count"])
            return doctor_loads[0]["id"]
            
        except Exception as e:
            print(f"Error in LLA algorithm: {e}")
            return None

    @staticmethod
    async def assign_doctor_to_patient(patient_uid: str) -> Optional[str]:
        """
        Assigns the least loaded doctor to a patient and updates Firestore.
        """
        doctor_id = await AssignmentService.get_least_loaded_doctor()
        if not doctor_id:
            return None
            
        try:
            user_ref = db.collection("users").document(patient_uid)
            user_ref.update({
                "assigned_doctor": doctor_id,
                "assigned_at": firestore.SERVER_TIMESTAMP
            })
            return doctor_id
        except Exception as e:
            print(f"Failed to update patient with assigned doctor: {e}")
            return None

assignment_service = AssignmentService()
