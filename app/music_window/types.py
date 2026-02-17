"""Shared types for music window."""
from __future__ import annotations

from pathlib import Path
from typing import NamedTuple


class TrackInfo(NamedTuple):
    path: Path
    title: str
    artist: str
    album: str
