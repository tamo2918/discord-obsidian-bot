"""YouTube utility functions for transcript fetching and metadata retrieval."""
import logging
import re
from typing import Optional

import requests
from youtube_transcript_api import YouTubeTranscriptApi

logger = logging.getLogger(__name__)

MAX_TRANSCRIPT_CHARS = 30000


def extract_video_id(url: str) -> Optional[str]:
    """
    Extract video ID from various YouTube URL formats.

    Supports:
        - youtube.com/watch?v=VIDEO_ID
        - youtu.be/VIDEO_ID
        - youtube.com/embed/VIDEO_ID
        - m.youtube.com/watch?v=VIDEO_ID

    Args:
        url: YouTube URL string

    Returns:
        Video ID string, or None if not found
    """
    patterns = [
        r"(?:youtube\.com/watch\?.*v=|youtu\.be/|youtube\.com/embed/|m\.youtube\.com/watch\?.*v=)"
        r"([a-zA-Z0-9_-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def get_video_title(video_id: str) -> Optional[str]:
    """
    Get video title using YouTube oEmbed API (no auth required).

    Args:
        video_id: YouTube video ID

    Returns:
        Video title string, or None if retrieval failed
    """
    try:
        resp = requests.get(
            "https://www.youtube.com/oembed",
            params={"url": f"https://www.youtube.com/watch?v={video_id}", "format": "json"},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json().get("title")
    except Exception as e:
        logger.warning(f"Failed to fetch video title for {video_id}: {e}")
        return None


def fetch_transcript(video_id: str) -> Optional[str]:
    """
    Fetch transcript text using youtube-transcript-api.

    Language priority: ja → en → any available language.
    Truncates to MAX_TRANSCRIPT_CHARS if exceeded.

    Args:
        video_id: YouTube video ID

    Returns:
        Transcript text string, or None if unavailable
    """
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)

        transcript = None
        # Try Japanese first, then English
        for lang in ("ja", "en"):
            try:
                transcript = transcript_list.find_transcript([lang])
                break
            except Exception:
                continue

        # Fall back to any available language
        if transcript is None:
            try:
                transcript = next(iter(transcript_list))
            except StopIteration:
                logger.warning(f"No transcripts available for {video_id}")
                return None

        entries = transcript.fetch()
        text = " ".join(entry["text"] for entry in entries)

        if len(text) > MAX_TRANSCRIPT_CHARS:
            text = text[:MAX_TRANSCRIPT_CHARS]
            logger.info(
                f"Transcript truncated to {MAX_TRANSCRIPT_CHARS} chars for {video_id}"
            )

        return text

    except Exception as e:
        logger.warning(f"Failed to fetch transcript for {video_id}: {e}")
        return None


def sanitize_title(title: str) -> str:
    """
    Sanitize a string for use as a filename.

    Removes characters invalid in filenames, collapses whitespace,
    and limits length to 100 characters.

    Args:
        title: Raw title string

    Returns:
        Sanitized filename-safe string
    """
    sanitized = re.sub(r'[\\/:*?"<>|]', "", title)
    sanitized = re.sub(r"\s+", " ", sanitized).strip()
    if len(sanitized) > 100:
        sanitized = sanitized[:100].rstrip()
    return sanitized or "Untitled"
