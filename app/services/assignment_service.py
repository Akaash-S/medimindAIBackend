"""
Smart Doctor Assignment Service
================================
Rules (in priority order):
 1. Specialization match  – doctor's specialization keyword matches patient conditions
 2. Availability          – doctor has working_hours set OR at least one free slot
 3. Least-loaded          – fewest assigned patients (LLA algorithm)

Falls back gracefully:
 • If no specialisation match → use any available doctor
 • If no available doctor     → use any doctor with role="doctor"
"""

from app.core.firebase import db, firestore
from typing import Optional
from datetime import date, timedelta, datetime


# ── Specialization → Condition keyword map ───────────────────────────────────
SPEC_KEYWORDS: dict[str, list[str]] = {
    "Cardiology":        ["heart", "cardiac", "chest", "hypertension", "angina", "coronary", "arrhythmia", "palpitation"],
    "Pulmonology":       ["lung", "pulmonary", "respiratory", "asthma", "bronchitis", "copd", "breathing", "tb", "tuberculosis"],
    "Endocrinology":     ["diabetes", "thyroid", "hormone", "insulin", "endocrine", "obesity", "metabolic"],
    "Neurology":         ["brain", "neuro", "seizure", "parkinson", "migraine", "epilepsy", "alzheimer", "stroke", "nerve"],
    "Orthopedics":       ["bone", "joint", "fracture", "spine", "arthritis", "ortho", "knee", "back", "shoulder"],
    "Gastroenterology":  ["stomach", "gut", "digestive", "liver", "intestine", "gastro", "ibs", "crohn", "colitis"],
    "Nephrology":        ["kidney", "renal", "dialysis", "nephr"],
    "Oncology":          ["cancer", "tumor", "oncology", "malignant", "lymphoma", "leukemia"],
    "Dermatology":       ["skin", "eczema", "psoriasis", "acne", "rash", "dermat"],
    "Psychiatry":        ["anxiety", "depression", "mental", "psych", "bipolar", "adhd", "ptsd"],
    "Ophthalmology":     ["eye", "vision", "cataract", "glaucoma", "retina"],
    "General Practice":  [],          # catch-all
}


def _score_specialization(doctor_spec: str, patient_conditions: str) -> int:
    """Return number of keyword hits between doctor specialisation and patient conditions."""
    if not doctor_spec or not patient_conditions:
        return 0
    conditions_lower = patient_conditions.lower()
    spec_normalised = doctor_spec.strip().title()
    keywords = SPEC_KEYWORDS.get(spec_normalised, [])
    return sum(1 for kw in keywords if kw in conditions_lower)


def _doctor_has_availability(doctor_id: str, doctor_data: dict) -> bool:
    """
    Returns True if the doctor has any free time slots available
    (either manual one-off slots in the sub-collection or working_hours configured).
    """
    # Check manual free slots
    try:
        slots_ref = (
            db.collection("users")
            .document(doctor_id)
            .collection("availability")
            .where("status", "==", "free")
            .limit(1)
            .get()
        )
        if slots_ref:
            return True
    except Exception:
        pass

    # Check working hours — if at least one day is active, doctor is available
    working_hours = doctor_data.get("working_hours", [])
    if working_hours and any(wh.get("active") for wh in working_hours):
        return True

    return False


class AssignmentService:

    @staticmethod
    async def get_best_doctor(patient_uid: str) -> Optional[dict]:
        """
        Smart doctor selection:
          1. Fetch patient conditions
          2. Score all role=doctor users by specialisation match
          3. Filter by availability
          4. Sort by (availability_priority, -score, patient_count)
          5. Return the best match
        """
        # ── Fetch patient data ───────────────────────────────────────────────
        patient_doc = db.collection("users").document(patient_uid).get()
        patient_conditions: str = ""
        if patient_doc.exists:
            pd = patient_doc.to_dict()
            conditions = pd.get("conditions", "") or ""
            allergies = pd.get("allergies", "") or ""
            patient_conditions = f"{conditions} {allergies}".strip()

        # ── Fetch all doctors ────────────────────────────────────────────────
        doctors_ref = db.collection("users").where("role", "==", "doctor").stream()
        doctors = [doc.to_dict() | {"id": doc.id} for doc in doctors_ref]

        if not doctors:
            print("[AssignmentService] No doctors found in the system.")
            return None

        # ── Score each doctor ────────────────────────────────────────────────
        scored = []
        for doctor in doctors:
            doc_id = doctor["id"]
            spec = doctor.get("specialization", "") or ""
            spec_score = _score_specialization(spec, patient_conditions)
            available = _doctor_has_availability(doc_id, doctor)

            # Count assigned patients
            try:
                patient_count = len(list(
                    db.collection("users")
                    .where("role", "==", "patient")
                    .where("assigned_doctor", "==", doc_id)
                    .stream()
                ))
            except Exception:
                patient_count = 0

            scored.append({
                "id": doc_id,
                "full_name": doctor.get("full_name", "Unknown"),
                "specialization": spec,
                "spec_score": spec_score,
                "available": available,
                "patient_count": patient_count,
            })

        # ── Select: prefer specialisation-match + available, then LLA ───────
        # Tier 1: spec match AND available
        tier1 = [d for d in scored if d["spec_score"] > 0 and d["available"]]
        # Tier 2: spec match but no availability set (doctor just registered)
        tier2 = [d for d in scored if d["spec_score"] > 0 and not d["available"]]
        # Tier 3: available but no spec match
        tier3 = [d for d in scored if d["spec_score"] == 0 and d["available"]]
        # Tier 4: any doctor
        tier4 = [d for d in scored if d["spec_score"] == 0 and not d["available"]]

        for tier in [tier1, tier2, tier3, tier4]:
            if tier:
                # Within tier: highest spec_score first, then fewest patients
                tier.sort(key=lambda d: (-d["spec_score"], d["patient_count"]))
                best = tier[0]
                print(
                    f"[AssignmentService] Selected Dr. {best['full_name']} "
                    f"(spec={best['specialization']}, score={best['spec_score']}, "
                    f"patients={best['patient_count']}, available={best['available']})"
                )
                return best

        return None

    @staticmethod
    async def assign_doctor_to_patient(patient_uid: str) -> Optional[str]:
        """
        Assigns the best matching doctor to a patient and writes to Firestore.
        Always does a fresh search — never returns a cached doctor.
        """
        doctor_data = await AssignmentService.get_best_doctor(patient_uid)
        if not doctor_data:
            return None

        try:
            user_ref = db.collection("users").document(patient_uid)
            user_doc = user_ref.get()
            user_doc_data = user_doc.to_dict() if user_doc.exists else {}

            # Write assignment to patient
            user_ref.update({
                "assigned_doctor": doctor_data["id"],
                "assigned_doctor_name": doctor_data["full_name"],
                "assigned_doctor_specialization": doctor_data.get("specialization", ""),
                "assigned_at": firestore.SERVER_TIMESTAMP,
            })

            # Create / update formal relationship document
            rel_id = f"{doctor_data['id']}_{patient_uid}"
            db.collection("relationships").document(rel_id).set({
                "id": rel_id,
                "doctor_id": doctor_data["id"],
                "patient_id": patient_uid,
                "doctor_name": doctor_data["full_name"],
                "specialization": doctor_data.get("specialization", ""),
                "spec_score": doctor_data.get("spec_score", 0),
                "status": "active",
                "created_at": firestore.SERVER_TIMESTAMP,
            })

            # Auto-init chat between doctor and patient
            try:
                from app.services.chat_service import chat_service
                patient_name = user_doc_data.get("full_name") or user_doc_data.get("name", "Patient")
                await chat_service.initialize_conversation(
                    participant_1_id=patient_uid,
                    participant_2_id=doctor_data["id"],
                    p1_name=patient_name,
                    p1_role="patient",
                    p2_name=doctor_data["full_name"],
                    p2_role="doctor",
                )
            except Exception as chat_err:
                print(f"[AssignmentService] Auto-chat init failed: {chat_err}")

            return doctor_data["id"]

        except Exception as e:
            print(f"[AssignmentService] Failed to write assignment: {e}")
            return None

    @staticmethod
    async def reassign_doctor(patient_uid: str) -> Optional[str]:
        """
        Allows re-assignment: clears the old doctor link and picks a fresh best match.
        Used when a patient wants to switch doctors or when called per-report.
        """
        # Clear existing assignment first
        db.collection("users").document(patient_uid).update({
            "assigned_doctor": firestore.DELETE_FIELD,
            "assigned_doctor_name": firestore.DELETE_FIELD,
            "assigned_doctor_specialization": firestore.DELETE_FIELD,
        })
        return await AssignmentService.assign_doctor_to_patient(patient_uid)


assignment_service = AssignmentService()
