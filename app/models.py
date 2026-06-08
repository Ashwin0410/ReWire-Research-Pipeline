from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Float, Text, Boolean, DateTime
from app.db import Base


class ResearchSession(Base):
    __tablename__ = "research_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(32), unique=True, nullable=False, index=True)
    prolific_id = Column(String(100), nullable=False)
    arm = Column(String(20), nullable=False)
    track_name = Column(String(50))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime)

    # Demographics
    age = Column(String(10))
    gender = Column(String(50))
    ethnicity = Column(String(100))
    depression_dx = Column(String(10))
    medication = Column(String(10))
    medication_text = Column(Text)

    # CTI-9
    cti9_responses_json = Column(Text)
    cti9_total = Column(Integer)
    cti9_classification = Column(String(10))

    # Pre-state (0-10 sliders)
    pre_arousal = Column(Float)
    pre_valence = Column(Float)
    pre_absorption = Column(Float)

    # Schema
    schema_responses_json = Column(Text)
    schema_failure_avg = Column(Float)
    schema_defectiveness_avg = Column(Float)
    schema_dependence_avg = Column(Float)
    dominant_schema = Column(String(30))

    # Personal questions (encrypted)
    q1_low_voice = Column(Text)
    q2_chills = Column(Text)
    q3_unseen = Column(Text)
    q4_know = Column(Text)

    # Generation (speech arm only)
    speech_text = Column(Text)
    speech_format = Column(String(30))
    voice_id = Column(String(50))
    audio_filename = Column(String(200))
    voice_filename = Column(String(200))
    generation_time_seconds = Column(Float)
    stage = Column(String(40), nullable=False, default="consent")
    progress = Column(Integer, nullable=False, default=0)
    gen_error = Column(Text)

    # Post-outcome (Section 6)
    post_chills_yn = Column(String(5))
    post_chills_intensity = Column(Float)
    post_chills_count = Column(Integer)
    post_goosebumps_yn = Column(String(5))
    post_goosebumps_intensity = Column(Float)
    post_tears = Column(Float)
    post_moved_yn = Column(String(5))

    # Attribution (Section 7)
    post_attribution = Column(String(50))
    post_attribution_other = Column(Text)
    post_trigger_moment = Column(Text)

    # Personalization check (Section 8)
    post_what_came_to_mind = Column(Text)
    post_words_personal = Column(Integer)

    # GenAI safety (Section 9, speech arm only)
    post_words_untrue_yn = Column(String(5))
    post_words_untrue_text = Column(Text)
    post_words_upsetting_yn = Column(String(5))
    post_words_upsetting_text = Column(Text)
    flagged = Column(Boolean, default=False)

    # Failure diagnostics (Section 10)
    post_what_felt_off_json = Column(Text)
    post_what_felt_off_other = Column(Text)

    # Post-state (Section 11, 0-10 sliders)
    post_arousal = Column(Float)
    post_valence = Column(Float)
    post_absorption = Column(Float)

    # Experience (Section 12)
    post_experience = Column(Text)
    post_experience_more = Column(Text)

    # Safety close (Section 13)
    post_feeling_now = Column(Text)
    post_distress_yn = Column(String(5))
    distress_flagged = Column(Boolean, default=False)

    # Beta signup (Section 14)
    beta_yn = Column(String(5))
    beta_email = Column(Text)
