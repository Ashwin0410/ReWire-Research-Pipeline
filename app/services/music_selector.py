import random
from app.core.config import cfg


def select_track() -> str:
    """
    Randomly select one of the 3 research tracks.
    Returns the track name (hallelujah, suuvi, or ww2).
    """
    track = random.choice(cfg.TRACK_NAMES)
    print(f"[MusicSelector] -> {track}")
    return track