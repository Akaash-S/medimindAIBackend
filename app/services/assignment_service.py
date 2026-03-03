"""
Smart Doctor Assignment Service — Per-Report Model
====================================================
Doctor is assigned to a REPORT, not globally to a patient.
Each report has its own doctor_id, doctor_name, consultation_status lifecycle.

Assignment rules (in priority order):
 1. Specialization match  – doctor's specialization keyword matches patient conditions
 2. Availability          – doctor has working_hours OR free slot
 3. Least-loaded          – fewest active report assignments (LLA on reports, not patients)

Consultation lifecycle per report:
  unassigned → assigned → in_consultation → completed
"""

from app.core.firebase import db, firestore
from typing import Optional


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
    "General Practice":  [],  # catch-all
}


def _score_specialization(doctor_spec: str, patient_conditions: str) -> int:
    if not doctor_spec or not patient_conditions:
        return 0
    conditions_lower = patient_conditions.lower()
    keywords = SPEC_KEYWORDS.get(doctor_spec.strip().title(), [])
    return sum(1 for kw in keywords if kw in conditions_lower)


def _doctor_has_availability(doctor_id: str, doctor_data: dict) -> bool:
    try:
        slots = (
            db.collection("users").document(doctor_id)
            .collection("availability").where("status", "==", "free").limit(1).get()
        )
        if slots:
            return True
    except Exception:
        pass
    working_hours = doctor_data.get("working_hours", [])
    return bool(working_hours and any(wh.get("active") for wh in working_hours))


class AssignmentService:

    @staticmethod
    async def get_best_doctor(patient_uid: str, report_id: str | None = None) -> Optional[dict]:
        """
        Smart doctor selection for a specific report.
        Scores by: specialization match → availability → fewest active report assignments.
        """
        # ── Patient conditions ────────────────────────────────────────────────
        patient_doc = db.collection("users").document(patient_uid).get()
        patient_conditions = ""
        if patient_doc.exists:
            pd = patient_doc.to_dict()
            conditions = pd.get("conditions", "") or ""
            allergies  = pd.get("allergies", "")  or ""
            patient_conditions = f"{conditions} {allergies}".strip()

        # ── Also check report's own AI analysis for condition clues ──────────
        if report_id:
            rep_doc = db.collection("reports").document(report_id).get()
            if rep_doc.exists:
                rd = rep_doc.to_dict()
                ai_summary = (rd.get("summary") or (rd.get("analysis") or {}).get("summary", ""))
                patient_conditions = f"{patient_conditions} {ai_summary}".strip()

        # ── Fetch all doctors ─────────────────────────────────────────────────
        doctors_ref = db.collection("users").where("role", "==", "doctor").stream()
        doctors = [doc.to_dict() | {"id": doc.id} for doc in doctors_ref]
        if not doctors:
            print("[AssignmentService] No doctors found.")
            return None

        # ── Score each doctor ─────────────────────────────────────────────────
        scored = []
        for doctor in doctors:
            doc_id = doctor["id"]
            spec   = doctor.get("specialization", "") or ""
            spec_score = _score_specialization(spec, patient_conditions)
            available  = _doctor_has_availability(doc_id, doctor)

            # LLA: count active report assignments (not patient count)
            try:
                active_reports = len(list(
                    db.collection("reports")
                    .where("doctor_id", "==", doc_id)
                    .where("consultation_status", "in", ["assigned", "in_consultation"])
                    .stream()
                ))
            except Exception:
                active_reports = 0

            scored.append({
                "id": doc_id,
                "full_name": doctor.get("full_name", "Unknown"),
                "specialization": spec,
                "spec_score": spec_score,
                "available": available,
                "active_reports": active_reports,
            })

        # ── 4-tier selection ──────────────────────────────────────────────────
        tier1 = [d for d in scored if d["spec_score"] > 0 and d["available"]]
        tier2 = [d for d in scored if d["spec_score"] > 0 and not d["available"]]
        tier3 = [d for d in scored if d["spec_score"] == 0 and d["available"]]
        tier4 = scored  # fallback: any doctor

        for tier in [tier1, tier2, tier3, tier4]:
            if tier:
                tier.sort(key=lambda d: (-d["spec_score"], d["active_reports"]))
                best = tier[0]
                print(
                    f"[AssignmentService] Selected Dr. {best['full_name']} "
                    f"(spec={best['specialization']}, score={best['spec_score']}, "
                    f"active_reports={best['active_reports']}, available={best['available']})"
                )
                return best

        return None

    @staticmethod
    async def assign_doctor_to_report(report_id: str, patient_uid: str) -> Optional[dict]:
        """
        Assigns the best matching doctor to a specific REPORT.
        Writes: report.doctor_id, report.doctor_name, report.consultation_status = 'assigned'
        Also updates user.assigned_doctor (most recent) for chat purposes.
        Creates a per-report relationship record.
        """
        doctor_data = await AssignmentService.get_best_doctor(patient_uid, report_id)
        if not doctor_data:
            return None

        doctor_id   = doctor_data["id"]
        doctor_name = doctor_data["full_name"]
        doctor_spec = doctor_data.get("specialization", "")

        try:
            # ── 1. Write to report document ───────────────────────────────────
            report_ref = db.collection("reports").document(report_id)
            report_doc = report_ref.get()
            if not report_doc.exists:
                print(f"[AssignmentService] Report {report_id} not found.")
                return None

            report_ref.update({
                "doctor_id":              doctor_id,
                "doctor_name":            doctor_name,
                "doctor_specialization":  doctor_spec,
                "consultation_status":    "assigned",
                "assigned_at":            firestore.SERVER_TIMESTAMP,
            })

            # ── 2. Update user.assigned_doctor for chat (latest only) ─────────
            db.collection("users").document(patient_uid).update({
                "assigned_doctor":              doctor_id,
                "assigned_doctor_name":         doctor_name,
                "assigned_doctor_specialization": doctor_spec,
                "assigned_at":                  firestore.SERVER_TIMESTAMP,
            })

            # ── 3. Create per-report relationship record ──────────────────────
            rel_id = f"{doctor_id}_{patient_uid}_{report_id}"
            db.collection("relationships").document(rel_id).set({
                "id":             rel_id,
                "doctor_id":      doctor_id,
                "patient_id":     patient_uid,
                "report_id":      report_id,
                "doctor_name":    doctor_name,
                "specialization": doctor_spec,
                "spec_score":     doctor_data.get("spec_score", 0),
                "status":         "active",
                "created_at":     firestore.SERVER_TIMESTAMP,
            })

            # ── 4. Auto-init chat (if no existing chat for this doctor-patient) ─
            try:
                patient_doc = db.collection("users").document(patient_uid).get()
                patient_name = "Patient"
                if patient_doc.exists:
                    pd = patient_doc.to_dict()
                    patient_name = pd.get("full_name") or pd.get("name", "Patient")
                from app.services.chat_service import chat_service
                await chat_service.initialize_conversation(
                    participant_1_id=patient_uid,
                    participant_2_id=doctor_id,
                    p1_name=patient_name,
                    p1_role="patient",
                    p2_name=doctor_name,
                    p2_role="doctor",
                )
            except Exception as chat_err:
                print(f"[AssignmentService] Chat init failed: {chat_err}")

            # ── 5. Create consultation recommendation for this report ──────────
            try:
                from app.api.consultations import generate_recommendation
                report_data = report_ref.get().to_dict() or {}
                risk = (
                    report_data.get("risk_level")
                    or (report_data.get("analysis") or {}).get("risk_level", "")
                ).lower().strip()

                patient_doc2 = db.collection("users").document(patient_uid).get()
                patient_name2 = patient_doc2.to_dict().get("full_name", "Patient") if patient_doc2.exists else "Patient"

                if risk in ("medium", "high"):
                    summary = (
                        report_data.get("summary")
                        or (report_data.get("analysis") or {}).get("summary", "")
                        or "Your report has been reviewed and a consultation is recommended."
                    )
                    reason_type = "ai_escalation" if risk == "high" else "post_report"
                    generate_recommendation(
                        user_id=patient_uid,
                        doctor_id=doctor_id,
                        report_id=report_id,
                        reason_type=reason_type,
                        risk_level=risk.capitalize(),
                        summary=summary,
                        doctor_name=doctor_name,
                        patient_name=patient_name2,
                    )
                    print(f"[AssignmentService] Recommendation created for report {report_id} (risk={risk})")
            except Exception as rec_err:
                print(f"[AssignmentService] Recommendation creation failed: {rec_err}")

            print(f"[AssignmentService] Report {report_id} → Dr. {doctor_name} ({doctor_spec})")
            return {
                "doctor_id":      doctor_id,
                "doctor_name":    doctor_name,
                "specialization": doctor_spec,
                "spec_score":     doctor_data.get("spec_score", 0),
            }

        except Exception as e:
            print(f"[AssignmentService] Failed to assign: {e}")
            return None

    @staticmethod
    async def complete_report_consultation(report_id: str, doctor_uid: str) -> bool:
        """Mark a report's consultation as completed — frees the doctor's slot."""
        try:
            report_ref = db.collection("reports").document(report_id)
            report_doc = report_ref.get()
            if not report_doc.exists:
                return False
            rd = report_doc.to_dict()
            if rd.get("doctor_id") != doctor_uid:
                return False  # security check

            report_ref.update({
                "consultation_status": "completed",
                "completed_at":        firestore.SERVER_TIMESTAMP,
            })

            # Mark relationship as completed
            patient_uid = rd.get("user_id", "")
            rel_id = f"{doctor_uid}_{patient_uid}_{report_id}"
            rel_ref = db.collection("relationships").document(rel_id)
            if rel_ref.get().exists:
                rel_ref.update({"status": "completed", "completed_at": firestore.SERVER_TIMESTAMP})

            return True
        except Exception as e:
            print(f"[AssignmentService] complete_report_consultation failed: {e}")
            return False


assignment_service = AssignmentService()
