import asyncio
import os
import sys

# Add the backend directory to sys.path
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from app.services.email_service import email_service
from app.core.config import settings

async def test_email_methods():
    print("--- Testing EmailService Methods ---")
    
    # Test alert
    print("\n1. Testing send_login_alert...")
    await email_service.send_login_alert(
        to_email="test@example.com",
        user_name="Test User",
        device="Testing Device",
        ip="127.0.0.1",
        location="Local Test"
    )
    
    # Test confirmation (patient)
    print("\n2. Testing send_appointment_confirmation (Patient)...")
    await email_service.send_appointment_confirmation(
        to_email="patient@example.com",
        user_name="Patient Name",
        doctor_name="Doctor Name",
        date="2026-03-10",
        time="10:00 AM",
        room_url="https://meet.jit.si/medimind-test"
    )
    
    # Test confirmation (doctor)
    print("\n3. Testing send_appointment_confirmation (Doctor)...")
    await email_service.send_appointment_confirmation(
        to_email="doctor@example.com",
        user_name="Patient Name",
        doctor_name="Doctor Name",
        date="2026-03-10",
        time="10:00 AM",
        room_url="https://meet.jit.si/medimind-test",
        is_doctor=True
    )

    print("\nTests completed. Check logs for SMTP warnings (expected if credentials aren't set).")

if __name__ == "__main__":
    if not os.path.exists(".env"):
        print("Warning: No .env file found in backend directory.")
    asyncio.run(test_email_methods())
