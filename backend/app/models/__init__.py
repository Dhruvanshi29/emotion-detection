"""Import all models here so Alembic autogenerate sees them."""

from app.models.user import User, UserPreferences, UserProfile  # noqa: F401
from app.models.chat import (  # noqa: F401
    Conversation,
    Message,
    RiskAssessment,
    SafetyEvent,
)
from app.models.emotion import EmotionEvent, EmotionScore  # noqa: F401
from app.models.journal import JournalAnalysis, JournalEntry  # noqa: F401
from app.models.voice import VoiceAnalysis  # noqa: F401
from app.models.facial import FacialAnalysis  # noqa: F401
from app.models.wellness import (  # noqa: F401
    ExerciseSession,
    UserGoal,
    WellnessExercise,
)
from app.models.therapist import (  # noqa: F401
    Therapist,
    TherapistAvailability,
    TherapistLanguage,
    TherapistReport,
    TherapistSpecialization,
    TherapistVerification,
)
from app.models.reminder import Notification, Reminder  # noqa: F401
from app.models.memory import ConversationSummary, UserMemory  # noqa: F401
from app.models.audit import AuditEvent, ConsentEvent  # noqa: F401
from app.models.refresh_token import RefreshToken  # noqa: F401
from app.models.auth_identity import AuthIdentity  # noqa: F401

__all__ = [
    "User",
    "UserProfile",
    "UserPreferences",
    "Conversation",
    "Message",
    "RiskAssessment",
    "SafetyEvent",
    "EmotionEvent",
    "EmotionScore",
    "JournalEntry",
    "JournalAnalysis",
    "VoiceAnalysis",
    "FacialAnalysis",
    "WellnessExercise",
    "ExerciseSession",
    "UserGoal",
    "Therapist",
    "TherapistSpecialization",
    "TherapistLanguage",
    "TherapistAvailability",
    "TherapistVerification",
    "TherapistReport",
    "Reminder",
    "Notification",
    "UserMemory",
    "ConversationSummary",
    "AuditEvent",
    "ConsentEvent",
    "RefreshToken",
    "AuthIdentity",
]
