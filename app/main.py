from fastapi import FastAPI
from app.core.config import settings
from app.api import patient, doctor, reports, appointments, messages, health, auth, security, consultations, prescriptions, ai_chat, family

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
)

from fastapi.middleware.cors import CORSMiddleware

# Configure CORS Middleware
# Allows frontend applications (e.g. https://aimedimind.vercel.app, localhost) to access the API.
cors_origins = [str(origin).rstrip("/") for origin in settings.BACKEND_CORS_ORIGINS] if settings.BACKEND_CORS_ORIGINS else ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins if "*" not in cors_origins else ["*"],
    allow_origin_regex=r"https://.*\.vercel\.app|https://.*\.asolvitra\.tech|https?://localhost(:\d+)?|https?://127\.0\.0\.1(:\d+)?" if "*" not in cors_origins else None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

@app.get("/")
async def root():
    return {"message": "Welcome to MediMind AI API", "docs": "/docs"}

# Include routers
app.include_router(health.router, prefix=f"{settings.API_V1_STR}", tags=["monitoring"])
app.include_router(reports.router, prefix=f"{settings.API_V1_STR}/reports", tags=["reports"])
app.include_router(auth.router, prefix=f"{settings.API_V1_STR}/auth", tags=["auth"])
app.include_router(patient.router, prefix=f"{settings.API_V1_STR}/patient", tags=["patient"])
app.include_router(doctor.router, prefix=f"{settings.API_V1_STR}/doctor", tags=["doctor"])
app.include_router(appointments.router, prefix=f"{settings.API_V1_STR}/appointments", tags=["appointments"])
app.include_router(messages.router, prefix=f"{settings.API_V1_STR}/messages", tags=["messages"])
app.include_router(security.router, prefix=f"{settings.API_V1_STR}", tags=["security"])
app.include_router(consultations.router, prefix=f"{settings.API_V1_STR}/consultations", tags=["consultations"])
app.include_router(prescriptions.router, prefix=f"{settings.API_V1_STR}/prescriptions", tags=["prescriptions"])
app.include_router(ai_chat.router, prefix=f"{settings.API_V1_STR}/ai-chat", tags=["ai-chat"])
app.include_router(family.router, prefix=f"{settings.API_V1_STR}/family", tags=["family"])
