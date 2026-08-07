import json
from pathlib import Path

ROOT = Path(__file__).parent
source = ROOT / "transcript.json"
destination = ROOT / "transcript_text.txt"

try:
    with source.open("r", encoding="utf-8") as f:
        data = json.load(f)
    
    # Handle both list of dicts (from get_transcript.py) and nested lists (from CLI)
    if isinstance(data, list) and len(data) > 0 and isinstance(data[0], list):
        items = data[0]
    else:
        items = data

    text = " ".join(item["text"] for item in items if "text" in item)
    destination.write_text(text, encoding="utf-8")
    print(f"Parsed text to {destination.name}")
except Exception as error:
    print(f"Error: {error}")
