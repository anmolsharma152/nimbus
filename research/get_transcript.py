import json
from pathlib import Path
from youtube_transcript_api import YouTubeTranscriptApi

VIDEO_ID = "Ak_edo5Z9YM"
OUTPUT_PATH = Path(__file__).with_name("transcript.json")

try:
    transcript = YouTubeTranscriptApi.get_transcript(VIDEO_ID)
    with OUTPUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(transcript, f, ensure_ascii=False, indent=2)
    print(f"Saved transcript to {OUTPUT_PATH.name}")
except Exception as error:
    print(f"Error: {error}")
