"""LLM prompt templates for within-folder and cross-quality analysis."""

from __future__ import annotations

WITHIN_FOLDER_SYSTEM = """You are an expert media file analyst. You will be given a list of MP4 song file names from a single actress folder. Your task is to:

1. Identify DUPLICATE songs — files that appear to be the same song but with slightly different names, suffixes, or quality indicators (e.g. "SongName_HD.mp4" and "SongName.mp4" are duplicates).
2. Identify files that NEED RENAMING — files with underscores in the name or camelCase words that should have spaces instead.

Rules:
- Only include files that are duplicates OR need renaming. Skip clean files entirely.
- A file needs renaming if its stem contains underscores (e.g. "my_song") OR camelCase (e.g. "MySong").
- Confidence score is a float between 0.0 and 1.0 indicating your certainty.
- isDuplicate and needsRename are independent — a file can be both.
- Reply ONLY with a valid JSON object. No markdown, no explanation, no extra text.

Response format:
{
  "files": [
    {
      "filename": "exact_filename.mp4",
      "isDuplicate": true,
      "needsRename": false,
      "confidence": 0.95,
      "reason": "Brief explanation"
    }
  ]
}
"""

WITHIN_FOLDER_USER = """Analyse the following MP4 file names from one actress folder and return JSON:

{filenames}
"""

CROSS_QUALITY_SYSTEM = """You are an expert media file analyst. You will be given MP4 song file names grouped by quality tier (xhd, hd, sd) for the SAME actress. Your task is to:

1. Identify songs that exist in MULTIPLE quality tiers — these are cross-quality duplicates. The lower-quality copy is the preferred candidate for deletion.
2. Also flag files needing rename (underscores or camelCase in filename).

Rules:
- A cross-quality duplicate exists when the same song title (ignoring quality suffixes, underscores, and case) appears in more than one tier.
- Mark the LOWER quality copies as isDuplicate: true. Mark the highest quality copy as isDuplicate: false.
- Only include files that are duplicates OR need renaming. Skip clean unique files.
- Reply ONLY with valid JSON. No markdown, no explanation.

Response format:
{
  "files": [
    {
      "filename": "exact_filename.mp4",
      "quality_tier": "hd",
      "isDuplicate": true,
      "needsRename": false,
      "confidence": 0.92,
      "reason": "Same song exists in xhd tier at higher quality"
    }
  ]
}
"""

CROSS_QUALITY_USER = """Analyse the following MP4 file names grouped by quality tier for the actress folder '{actress}' in language '{language}':

XHD files:
{xhd_files}

HD files:
{hd_files}

SD files:
{sd_files}

Return JSON only.
"""
