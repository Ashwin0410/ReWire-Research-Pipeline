import os
from pathlib import Path


class Config:

    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    ELEVENLABS_API_KEY: str = os.getenv("ELEVENLABS_API_KEY", "")

    CLAUDE_MODEL: str = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514")

    FFMPEG_BIN: str = os.getenv("FFMPEG_BIN", "ffmpeg")
    FFPROBE_BIN: str = os.getenv("FFPROBE_BIN", "ffprobe")

    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    ASSETS_DIR: Path = BASE_DIR / "assets"
    OUT_DIR: str = os.getenv("OUT_DIR", "/tmp/audio")

    @property
    def out_dir_path(self) -> Path:
        p = Path(self.OUT_DIR)
        p.mkdir(parents=True, exist_ok=True)
        return p

    # Track registry
    # total_duration_sec: full file length
    # content_duration_sec: actual music content (before trailing silence/fade)
    # target_words: word count for speech generation, calibrated to content_duration_sec
    #               accounting for ~15-20% TTS overhead (pauses, chunk gaps, tag-driven
    #               delivery slowdowns). Effective WPM with ElevenLabs v3 at these
    #               voice settings is ~110-120 wpm, not the raw 135 wpm baseline.
    # voice_settings: per-voice ElevenLabs synthesis parameters
    TRACKS = {
        "hallelujah": {
            "file": "a_thousand_hearts.mpeg",
            "voice_id": "lMILJ9d29MrRXy9BIgcz",
            "total_duration_sec": 129,
            "content_duration_sec": 126,
            "target_words": 250,
            "voice_settings": {
                "stability": 0.30,
                "similarity_boost": 0.70,
                "style": 1.0,
                "use_speaker_boost": True,
            },
        },
        "suuvi": {
            "file": "ad_infinitum.mpeg",
            "voice_id": "lMILJ9d29MrRXy9BIgcz",
            "total_duration_sec": 264,
            "content_duration_sec": 259,
            "target_words": 500,
            "voice_settings": {
                "stability": 0.30,
                "similarity_boost": 0.70,
                "style": 1.0,
                "use_speaker_boost": True,
            },
        },
        "ww2": {
            "file": "heroes_wwii.mp3",
            "voice_id": "0yXkuUWXDHdmdQJugJLb",
            "total_duration_sec": 353,
            "content_duration_sec": 333,
            "target_words": 630,
            "voice_settings": {
                "stability": 0.45,
                "similarity_boost": 0.70,
                "style": 0.85,
                "use_speaker_boost": True,
            },
        },
    }

    TRACK_NAMES = list(TRACKS.keys())

    def get_track(self, track_name: str = None) -> dict:
        track = self.TRACKS.get(track_name)
        if not track:
            track = self.TRACKS["hallelujah"]
            track_name = "hallelujah"
        return {
            "name": track_name,
            "file": self.ASSETS_DIR / track["file"],
            "voice_id": track["voice_id"],
            "total_duration_sec": track["total_duration_sec"],
            "content_duration_sec": track["content_duration_sec"],
            "target_words": track["target_words"],
            "voice_settings": track["voice_settings"],
        }

    MEDITATION_FILE: str = "christian_meditation.mpeg"

    @property
    def meditation_path(self) -> Path:
        return self.ASSETS_DIR / self.MEDITATION_FILE

    DB_URL: str = os.getenv("DB_URL", "sqlite:///./research.db")

    ALLOWED_ORIGINS: list = os.getenv("ALLOWED_ORIGINS", "*").split(",")

    PUBLIC_BASE_URL: str = os.getenv("PUBLIC_BASE_URL", "")

    ENCRYPTION_KEY: str = os.getenv("ENCRYPTION_KEY", "")


cfg = Config()
