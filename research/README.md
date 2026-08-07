# Source Research

This directory preserves the material used to shape the initial project brief.
It is separate from product code and design decisions.

- `transcript.json` is the captured transcript source.
- `transcript_text.txt` is the derived plain-text artifact.
- `get_transcript.py` fetches the configured YouTube video transcript.
- `parse_transcript.py` transforms `transcript.json` into readable plain text.

Run the utilities from the repository root or this directory:

```bash
python3 research/parse_transcript.py
python3 research/get_transcript.py
```

`get_transcript.py` requires the `youtube-transcript-api` dependency and updates
`transcript_text.txt` in this directory. Preserve the source and derived files
when changing parsing behavior so findings remain reproducible.
