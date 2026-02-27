from app.core.firebase import db, firestore
from typing import Optional

class AssignmentService:
    @staticmethod
    async def get_least_loaded_doctor() -> Optional[dict]:
        """
        Finds the doctor with the fewest assigned patients (LLA algorithm).
        Returns a dict with doctor 'id' and 'full_name'.
        """
        try:
            # 1. Get all doctors with complete profiles
            doctors_ref = db.collection("users").where("role", "==", "doctor").where("profile_complete", "==", True).stream()
            doctors = [doc.to_dict() | {"id": doc.id} for doc in doctors_ref]
            
            if not doctors:
                print("No active doctors found in the system.")
                return None
                
            # 2. Count patients for each doctor
            doctor_loads = []
            for doctor in doctors:
                count_query = db.collection("users").where("role", "==", "patient").where("assigned_doctor", "==", doctor["id"])
                patient_count = len(list(count_query.stream()))
                doctor_loads.append({
                    "id": doctor["id"],
                    "full_name": doctor.get("full_name", "Unknown"),
                    "count": patient_count
                })
            
            # 3. Sort by count and return the first one
            doctor_loads.sort(key=lambda x: x["count"])
            return doctor_loads[0]
            
        except Exception as e:
            print(f"Error in LLA algorithm: {e}")
            return None

    @staticmethod
    async def assign_doctor_to_patient(patient_uid: str) -> Optional[str]:
        """
        Assigns the least loaded doctor to a patient and updates Firestore.
        """
        doctor_data = await AssignmentService.get_least_loaded_doctor()
        if not doctor_data:
            return None
            
        try:
            # 1. Update patient profile for quick lookup
            user_ref = db.collection("users").document(patient_uid)
            user_doc = user_ref.get()
            user_data = user_doc.to_dict() if user_doc.exists else {}
            
            user_ref.update({
                "assigned_doctor": doctor_data["id"],
                "assigned_doctor_name": doctor_data["full_name"],
                "assigned_at": firestore.SERVER_TIMESTAMP
            })

            # 2. Create formal relationship document
            rel_id = f"{doctor_data['id']}_{patient_uid}"
            db.collection("relationships").document(rel_id).set({
                "id": rel_id,
                "doctor_id": doctor_data["id"],
                "patient_id": patient_uid,
                "doctor_name": doctor_data["full_name"],
                "status": "active",
                "created_at": firestore.SERVER_TIMESTAMP
            })

            # 3. Auto-initialize chat
            try:
                from app.services.chat_service import chat_service
                patient_name = user_data.get("full_name") or user_data.get("name", "Patient")
                await chat_service.initialize_conversation(
                    participant_1_id=patient_uid,
                    participant_2_id=doctor_data["id"],
                    p1_name=patient_name,
                    p1_role="patient",
                    p2_name=doctor_data["full_name"],
                    p2_role="doctor"
                )
            except Exception as chat_err:
                print(f"Auto-chat initialization failed: {chat_err}")
            
            return doctor_data["id"]
        except Exception as e:
            print(f"Failed to update patient with assigned doctor: {e}")
            return None

assignment_service = AssignmentService()
