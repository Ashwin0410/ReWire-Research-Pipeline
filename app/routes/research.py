import uuid
import json
import time
import csv
import io
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import cfg
from app.db import get_db, SessionLocal
from app.models import ResearchSession
from app.services.prompt import build_user_prompt
from app.services.llm import generate_speech

# Limit concurrent generations to prevent server overload
# Each generation runs Claude + TTS + ffmpeg. 8 concurrent is safe for a Standard Render instance.
_gen_pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="gen")
from app.services.tts import synth
from app.services.mix import mix as mix_audio
from app.services.music_selector import select_track
from app.services.scoring import score_cti9, score_schema
from app.utils.encryption import encrypt_field, decrypt_field, encrypt_file, decrypt_file_to_bytes

r = APIRouter(prefix="/api/research", tags=["research"])


# --- Request Schemas ---

class StartRequest(BaseModel):
    prolific_id: str
    arm: str

class DemographicsRequest(BaseModel):
    age: str
    gender: str
    ethnicity: str
    depression_dx: str = ""
    medication: str = ""
    medication_text: str = ""

class CTI9Request(BaseModel):
    responses: List[int]

class PreStateRequest(BaseModel):
    arousal: float
    valence: float
    absorption: float

class SchemaRequest(BaseModel):
    failure: List[int]
    defectiveness: List[int]
    dependence: List[int]

class PersonalRequest(BaseModel):
    q1_low_voice: str = ""
    q2_chills: str = ""
    q3_unseen: str = ""
    q4_know: str = ""

class ChillsRequest(BaseModel):
    chills_timestamps_json: str = "[]"
    chills_count: int = 0

class PostOutcomeRequest(BaseModel):
    chills_yn: str
    chills_intensity: float = 0
    chills_count: int = 0
    goosebumps_yn: str
    goosebumps_intensity: float = 0
    tears: float = 0
    moved_yn: str = ""

class AttributionRequest(BaseModel):
    attribution: str
    attribution_other: str = ""
    trigger_moment: str = ""

class PersonalizationRequest(BaseModel):
    what_came_to_mind: str = ""
    words_personal: Optional[int] = None

class SafetyRequest(BaseModel):
    words_untrue_yn: str
    words_untrue_text: str = ""
    words_upsetting_yn: str
    words_upsetting_text: str = ""

class DiagnosticsRequest(BaseModel):
    what_felt_off_json: str = "[]"
    what_felt_off_other: str = ""

class PostStateRequest(BaseModel):
    arousal: float
    valence: float
    absorption: float

class ExperienceRequest(BaseModel):
    experience: str
    experience_more: str = ""

class SafetyCloseRequest(BaseModel):
    feeling_now: str
    distress_yn: str = ""

class BetaRequest(BaseModel):
    beta_yn: str
    beta_email: str = ""

class StatusResponse(BaseModel):
    status: str

class StartResponse(BaseModel):
    session_id: str

class PersonalResponse(BaseModel):
    session_id: str
    meditation_url: str

class GenerationStatusResponse(BaseModel):
    session_id: str
    stage: str
    progress: int
    audio_url: Optional[str] = None
    error: Optional[str] = None


# --- Helpers ---

def _get_session(session_id: str, db: Session) -> ResearchSession:
    session = db.query(ResearchSession).filter(
        ResearchSession.session_id == session_id
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


def _update_job_db(session_id: str, **kwargs):
    db = SessionLocal()
    try:
        row = db.query(ResearchSession).filter(
            ResearchSession.session_id == session_id
        ).first()
        if row:
            for key, value in kwargs.items():
                if hasattr(row, key):
                    setattr(row, key, value)
            db.commit()
    except Exception as e:
        print(f"[Research] Job status update error: {e}")
        try:
            db.rollback()
        except Exception:
            pass
    finally:
        db.close()


# --- Background Generation (speech arm only) ---

def _run_generate(
    session_id: str,
    q1_low_voice: str,
    q2_chills: str,
    q3_unseen: str,
    dominant_schema: str,
    track_name: str,
):
    try:
        start_time = time.time()
        track_info = cfg.get_track(track_name)
        voice_id = track_info["voice_id"]
        target_words = track_info["target_words"]
        music_path = track_info["file"]

        # Stage 1: Generate speech text
        _update_job_db(session_id, stage="generating", progress=20)
        print(f"[Research] Generating speech for {session_id}, track={track_name}, words={target_words}")

        user_prompt = build_user_prompt(
            q1_low_voice=q1_low_voice,
            q2_chills=q2_chills,
            q3_unseen=q3_unseen,
            dominant_schema=dominant_schema,
            target_words=target_words,
        )

        speech_text = generate_speech(user_prompt)
        _update_job_db(
            session_id,
            speech_text=encrypt_field(speech_text),
            stage="synthesizing",
            progress=40,
        )
        print(f"[Research] Speech generated for {session_id}, len={len(speech_text.split())} words")

        # Stage 2: TTS
        _update_job_db(session_id, stage="synthesizing", progress=50)
        voice_wav = synth(speech_text, voice_id, cfg.ELEVENLABS_API_KEY)
        _update_job_db(session_id, stage="mixing", progress=70)
        print(f"[Research] TTS complete for {session_id}")

        # Save raw voice file
        voice_out_filename = f"{session_id}_voice.wav"
        voice_out_path = cfg.out_dir_path / voice_out_filename
        shutil.copy2(voice_wav, str(voice_out_path))
        encrypt_file(str(voice_out_path))

        # Stage 3: Mix voice over music
        out_filename = f"{session_id}.mp3"
        out_path = cfg.out_dir_path / out_filename

        mix_audio(
            voice_path=voice_wav,
            music_path=str(music_path),
            out_path=str(out_path),
            ffmpeg_bin=cfg.FFMPEG_BIN,
            voice_target_dbfs=-12.5,
            music_target_dbfs=-17.0,
            duck_db=5.0,
        )

        encrypt_file(str(out_path))

        elapsed = round(time.time() - start_time, 1)

        _update_job_db(
            session_id,
            audio_filename=out_filename,
            voice_filename=voice_out_filename,
            voice_id=voice_id,
            generation_time_seconds=elapsed,
            stage="done",
            progress=100,
        )

        print(f"[Research] Session {session_id} complete in {elapsed}s")

    except Exception as e:
        print(f"[Research] Generation error for {session_id}: {e}")
        _update_job_db(session_id, stage="error", gen_error=str(e))


# --- Endpoints ---

@r.post("/start", response_model=StartResponse)
def start_session(req: StartRequest, db: Session = Depends(get_db)):
    if req.arm not in ("music_only", "music_speech"):
        raise HTTPException(status_code=400, detail="arm must be music_only or music_speech")

    session_id = uuid.uuid4().hex[:16]
    track_name = select_track()

    session = ResearchSession(
        session_id=session_id,
        prolific_id=req.prolific_id,
        arm=req.arm,
        track_name=track_name,
        stage="consent",
        progress=0,
    )
    db.add(session)
    db.commit()

    return StartResponse(session_id=session_id)


@r.post("/{session_id}/demographics", response_model=StatusResponse)
def submit_demographics(session_id: str, req: DemographicsRequest, db: Session = Depends(get_db)):
    session = _get_session(session_id, db)
    session.age = req.age
    session.gender = req.gender
    session.ethnicity = req.ethnicity
    session.depression_dx = req.depression_dx
    session.medication = req.medication
    session.medication_text = encrypt_field(req.medication_text)
    db.commit()
    return StatusResponse(status="ok")


@r.post("/{session_id}/cti9", response_model=StatusResponse)
def submit_cti9(session_id: str, req: CTI9Request, db: Session = Depends(get_db)):
    session = _get_session(session_id, db)

    result = score_cti9(req.responses)
    session.cti9_responses_json = json.dumps(req.responses)
    session.cti9_total = result["total"]
    session.cti9_classification = result["classification"]
    db.commit()

    return StatusResponse(status="ok")


@r.post("/{session_id}/pre-state", response_model=StatusResponse)
def submit_pre_state(session_id: str, req: PreStateRequest, db: Session = Depends(get_db)):
    session = _get_session(session_id, db)
    session.pre_arousal = req.arousal
    session.pre_valence = req.valence
    session.pre_absorption = req.absorption
    db.commit()
    return StatusResponse(status="ok")


@r.post("/{session_id}/schema", response_model=StatusResponse)
def submit_schema(session_id: str, req: SchemaRequest, db: Session = Depends(get_db)):
    session = _get_session(session_id, db)

    responses = {
        "failure": req.failure,
        "defectiveness": req.defectiveness,
        "dependence": req.dependence,
    }
    result = score_schema(responses)

    session.schema_responses_json = json.dumps(responses)
    session.schema_failure_avg = result["domain_scores"]["failure"]
    session.schema_defectiveness_avg = result["domain_scores"]["defectiveness"]
    session.schema_dependence_avg = result["domain_scores"]["dependence"]
    session.dominant_schema = result["dominant_schema"]
    db.commit()

    return StatusResponse(status="ok")


@r.post("/{session_id}/personal", response_model=PersonalResponse)
def submit_personal(session_id: str, req: PersonalRequest, db: Session = Depends(get_db)):
    session = _get_session(session_id, db)

    session.q1_low_voice = encrypt_field(req.q1_low_voice)
    session.q2_chills = encrypt_field(req.q2_chills)
    session.q3_unseen = encrypt_field(req.q3_unseen)
    session.q4_know = encrypt_field(req.q4_know)
    db.commit()

    base = cfg.PUBLIC_BASE_URL.rstrip("/") if cfg.PUBLIC_BASE_URL else ""
    meditation_url = f"{base}/assets/{cfg.MEDITATION_FILE}"

    if session.arm == "music_speech":
        _update_job_db(session_id, stage="queued", progress=10)

        _gen_pool.submit(
            _run_generate,
            session_id,
            req.q1_low_voice,
            req.q2_chills,
            req.q3_unseen,
            session.dominant_schema or "",
            session.track_name,
        )
    else:
        _update_job_db(session_id, stage="done", progress=100)

    return PersonalResponse(session_id=session_id, meditation_url=meditation_url)


@r.get("/{session_id}/status", response_model=GenerationStatusResponse)
def get_status(session_id: str, db: Session = Depends(get_db)):
    session = _get_session(session_id, db)

    audio_url = None
    base = cfg.PUBLIC_BASE_URL.rstrip("/") if cfg.PUBLIC_BASE_URL else ""

    if session.arm == "music_only" and session.stage == "done":
        track_info = cfg.get_track(session.track_name)
        track_filename = cfg.TRACKS[session.track_name]["file"]
        audio_url = f"{base}/assets/{track_filename}"
    elif session.arm == "music_speech" and session.audio_filename:
        audio_url = f"{base}/api/research/audio/{session.audio_filename}"

    return GenerationStatusResponse(
        session_id=session_id,
        stage=session.stage,
        progress=session.progress,
        audio_url=audio_url,
        error=session.gen_error,
    )


@r.get("/audio/{filename}")
def serve_audio(filename: str):
    filepath = cfg.out_dir_path / filename
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Audio not found")

    audio_bytes = decrypt_file_to_bytes(str(filepath))
    return Response(
        content=audio_bytes,
        media_type="audio/mpeg",
        headers={
            "Content-Disposition": f"inline; filename={filename}",
            "Accept-Ranges": "bytes",
        },
    )


@r.get("/voice/{filename}")
def serve_voice(filename: str):
    filepath = cfg.out_dir_path / filename
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Voice file not found")

    audio_bytes = decrypt_file_to_bytes(str(filepath))
    return Response(
        content=audio_bytes,
        media_type="audio/wav",
        headers={
            "Content-Disposition": f"inline; filename={filename}",
            "Accept-Ranges": "bytes",
        },
    )


@r.post("/{session_id}/chills", response_model=StatusResponse)
def submit_chills(session_id: str, req: ChillsRequest, db: Session = Depends(get_db)):
    session = _get_session(session_id, db)
    session.chills_timestamps_json = req.chills_timestamps_json
    session.chills_count = req.chills_count
    db.commit()
    return StatusResponse(status="ok")


@r.post("/{session_id}/post-outcome", response_model=StatusResponse)
def submit_post_outcome(session_id: str, req: PostOutcomeRequest, db: Session = Depends(get_db)):
    session = _get_session(session_id, db)
    session.post_chills_yn = req.chills_yn
    session.post_chills_intensity = req.chills_intensity
    session.post_chills_count = req.chills_count
    session.post_goosebumps_yn = req.goosebumps_yn
    session.post_goosebumps_intensity = req.goosebumps_intensity
    session.post_tears = req.tears
    session.post_moved_yn = req.moved_yn
    db.commit()
    return StatusResponse(status="ok")


@r.post("/{session_id}/attribution", response_model=StatusResponse)
def submit_attribution(session_id: str, req: AttributionRequest, db: Session = Depends(get_db)):
    session = _get_session(session_id, db)
    session.post_attribution = req.attribution
    session.post_attribution_other = encrypt_field(req.attribution_other)
    session.post_trigger_moment = encrypt_field(req.trigger_moment)
    db.commit()
    return StatusResponse(status="ok")


@r.post("/{session_id}/personalization", response_model=StatusResponse)
def submit_personalization(session_id: str, req: PersonalizationRequest, db: Session = Depends(get_db)):
    session = _get_session(session_id, db)
    session.post_what_came_to_mind = encrypt_field(req.what_came_to_mind)
    session.post_words_personal = req.words_personal
    db.commit()
    return StatusResponse(status="ok")


@r.post("/{session_id}/safety", response_model=StatusResponse)
def submit_safety(session_id: str, req: SafetyRequest, db: Session = Depends(get_db)):
    session = _get_session(session_id, db)
    session.post_words_untrue_yn = req.words_untrue_yn
    session.post_words_untrue_text = encrypt_field(req.words_untrue_text)
    session.post_words_upsetting_yn = req.words_upsetting_yn
    session.post_words_upsetting_text = encrypt_field(req.words_upsetting_text)
    if req.words_upsetting_yn.lower() == "yes":
        session.flagged = True
    db.commit()
    return StatusResponse(status="ok")


@r.post("/{session_id}/diagnostics", response_model=StatusResponse)
def submit_diagnostics(session_id: str, req: DiagnosticsRequest, db: Session = Depends(get_db)):
    session = _get_session(session_id, db)
    session.post_what_felt_off_json = req.what_felt_off_json
    session.post_what_felt_off_other = req.what_felt_off_other
    db.commit()
    return StatusResponse(status="ok")


@r.post("/{session_id}/post-state", response_model=StatusResponse)
def submit_post_state(session_id: str, req: PostStateRequest, db: Session = Depends(get_db)):
    session = _get_session(session_id, db)
    session.post_arousal = req.arousal
    session.post_valence = req.valence
    session.post_absorption = req.absorption
    db.commit()
    return StatusResponse(status="ok")


@r.post("/{session_id}/experience", response_model=StatusResponse)
def submit_experience(session_id: str, req: ExperienceRequest, db: Session = Depends(get_db)):
    session = _get_session(session_id, db)
    session.post_experience = encrypt_field(req.experience)
    session.post_experience_more = encrypt_field(req.experience_more)
    db.commit()
    return StatusResponse(status="ok")


@r.post("/{session_id}/safety-close", response_model=StatusResponse)
def submit_safety_close(session_id: str, req: SafetyCloseRequest, db: Session = Depends(get_db)):
    session = _get_session(session_id, db)
    session.post_feeling_now = encrypt_field(req.feeling_now)
    session.post_distress_yn = req.distress_yn
    if req.distress_yn and req.distress_yn.lower() == "yes":
        session.distress_flagged = True
    db.commit()
    return StatusResponse(status="ok")


@r.post("/{session_id}/beta", response_model=StatusResponse)
def submit_beta(session_id: str, req: BetaRequest, db: Session = Depends(get_db)):
    session = _get_session(session_id, db)
    session.beta_yn = req.beta_yn
    session.beta_email = encrypt_field(req.beta_email)
    db.commit()
    return StatusResponse(status="ok")


@r.post("/{session_id}/complete", response_model=StatusResponse)
def complete_session(session_id: str, db: Session = Depends(get_db)):
    session = _get_session(session_id, db)
    session.completed_at = datetime.now(timezone.utc)
    db.commit()
    return StatusResponse(status="ok")


# --- CSV Export ---

@r.get("/export/csv")
def export_csv(db: Session = Depends(get_db)):
    sessions = db.query(ResearchSession).order_by(ResearchSession.created_at.desc()).all()

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "session_id",
        "prolific_id",
        "arm",
        "track_name",
        "created_at",
        "completed_at",
        "age",
        "gender",
        "ethnicity",
        "depression_dx",
        "medication",
        "medication_text",
        "cti9_responses",
        "cti9_total",
        "cti9_classification",
        "pre_arousal",
        "pre_valence",
        "pre_absorption",
        "schema_responses",
        "schema_failure_avg",
        "schema_defectiveness_avg",
        "schema_dependence_avg",
        "dominant_schema",
        "q1_low_voice",
        "q2_chills",
        "q3_unseen",
        "q4_know",
        "speech_format",
        "speech_text",
        "voice_id",
        "audio_filename",
        "voice_filename",
        "generation_time_seconds",
        "chills_timestamps",
        "chills_count",
        "post_chills_yn",
        "post_chills_intensity",
        "post_chills_count",
        "post_goosebumps_yn",
        "post_goosebumps_intensity",
        "post_tears",
        "post_moved_yn",
        "post_attribution",
        "post_attribution_other",
        "post_trigger_moment",
        "post_what_came_to_mind",
        "post_words_personal",
        "post_words_untrue_yn",
        "post_words_untrue_text",
        "post_words_upsetting_yn",
        "post_words_upsetting_text",
        "flagged",
        "post_what_felt_off",
        "post_what_felt_off_other",
        "post_arousal",
        "post_valence",
        "post_absorption",
        "post_experience",
        "post_experience_more",
        "post_feeling_now",
        "post_distress_yn",
        "distress_flagged",
        "beta_yn",
        "beta_email",
    ])

    for s in sessions:
        writer.writerow([
            s.session_id,
            s.prolific_id,
            s.arm,
            s.track_name,
            s.created_at,
            s.completed_at,
            s.age,
            s.gender,
            s.ethnicity,
            s.depression_dx,
            s.medication,
            decrypt_field(s.medication_text),
            s.cti9_responses_json,
            s.cti9_total,
            s.cti9_classification,
            s.pre_arousal,
            s.pre_valence,
            s.pre_absorption,
            s.schema_responses_json,
            s.schema_failure_avg,
            s.schema_defectiveness_avg,
            s.schema_dependence_avg,
            s.dominant_schema,
            decrypt_field(s.q1_low_voice),
            decrypt_field(s.q2_chills),
            decrypt_field(s.q3_unseen),
            decrypt_field(s.q4_know),
            s.speech_format,
            decrypt_field(s.speech_text),
            s.voice_id,
            s.audio_filename,
            s.voice_filename,
            s.generation_time_seconds,
            s.chills_timestamps_json,
            s.chills_count,
            s.post_chills_yn,
            s.post_chills_intensity,
            s.post_chills_count,
            s.post_goosebumps_yn,
            s.post_goosebumps_intensity,
            s.post_tears,
            s.post_moved_yn,
            s.post_attribution,
            decrypt_field(s.post_attribution_other),
            decrypt_field(s.post_trigger_moment),
            decrypt_field(s.post_what_came_to_mind),
            s.post_words_personal,
            s.post_words_untrue_yn,
            decrypt_field(s.post_words_untrue_text),
            s.post_words_upsetting_yn,
            decrypt_field(s.post_words_upsetting_text),
            s.flagged,
            s.post_what_felt_off_json,
            s.post_what_felt_off_other,
            s.post_arousal,
            s.post_valence,
            s.post_absorption,
            decrypt_field(s.post_experience),
            decrypt_field(s.post_experience_more),
            decrypt_field(s.post_feeling_now),
            s.post_distress_yn,
            s.distress_flagged,
            s.beta_yn,
            decrypt_field(s.beta_email),
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=rewire_research_sessions.csv"},
    )
