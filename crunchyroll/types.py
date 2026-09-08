from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class DubVersion:
    audio_locale: str = ""
    guid: str = ""
    media_guid: str = ""
    season_guid: str = ""
    locale: str = ""



@dataclass
class EpisodeMetadata:
    audio_locale: str
    episode_number: int
    season_number: int
    series_title: str
    availability_starts: str
    versions: List[DubVersion] = field(default_factory=list)


@dataclass
class EpisodeInfo:
    episode_metadata: EpisodeMetadata
    title: str
    subtitles: Dict[str, Subtitle] = field(default_factory=dict)



@dataclass
class Subtitle:
    language: str
    url: str


@dataclass
class Episode:
    manifest_url: str
    subtitles: Dict[str, Subtitle] = field(default_factory=dict)
    token: str = ""
    error: Optional[str] = None

PlaybackStream = Episode



@dataclass
class SeasonEpisode:
    id: str
    versions: List[DubVersion]
    season_number: int
    episode_number: int
    series_title: str
    audio_locale: str
    title: str
    availability_starts: str
    season_id: str = ""


@dataclass
class Season:
    id: str
    season_number: int
    audio_locale: str = ""
    title: str = ""



@dataclass
class MediaTrack:
    file: str
    locale: str
    is_default: bool = False
