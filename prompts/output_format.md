# Output format

Use the following file names to reference the video a clip comes from in the "source_filename" field. Always use the exact spelling of the file name:
{{video_filenames}}

Return one JSON object per clip of the cut proposal, with these fields:

- "source_filename": the exact file name of the video the clip comes from
- "start_timestamp": the exact start of the clip in the format MM:SS.sss, or H:MM:SS.sss from one hour on (inclusive)
- "end_timestamp": the exact end of the clip in the same format (exclusive)
- "label": a short, human-readable label for the clip (e.g. "Intro", "Closing quote")
- "description": what happens in the clip
- "reasoning": why this clip was selected

The order of the "clips" list is the cut order: the clips are placed on the timeline one after another in this order.

IMPORTANT - timestamp format:

- ALWAYS use the format MM:SS.sss (minutes:seconds.milliseconds), or H:MM:SS.sss from one hour on
- Use a PERIOD (.) before the milliseconds, NEVER a colon
- Milliseconds always have 3 digits (e.g. .000, .500, .999)
- Seconds and minutes are always < 60
- CORRECT examples: "01:23.456", "00:05.000", "30:00.750", "1:05:23.456"
- WRONG examples: "01:23:456" (colon instead of period before the milliseconds), "01:23.4" (too few digits for milliseconds), "01:60.000" (60 seconds is invalid)
- Time reference: all timestamps are relative to the start of the file the clip comes from. EVERY file starts at 00:00.000. Ignore clocks or timecodes burnt into the picture and spoken time references in the audio; use only the technical running time of the file in front of you, starting at zero.

IMPORTANT - completeness:

- Analyse EVERY video file COMPLETELY from beginning to end
- Do not skip relevant clips, not even at the end of a file or in the last file

IMPORTANT - relevance:

- Select only clips that clearly meet the defined criteria
- Use the "reasoning" field to make the relevance of each clip traceable

IMPORTANT - accuracy:

- Use exactly the given file names in "source_filename"
- Stick strictly to the timestamp format MM:SS.sss (H:MM:SS.sss from one hour on) with a PERIOD before the milliseconds
- Every relevant clip is its own JSON object in the "clips" list

Your answer must be valid JSON with a "clips" list, where each JSON object represents a single clip.

Example of a valid answer:

```json
{
  "clips": [
    {
      "source_filename": "example_video_1.mp4",
      "start_timestamp": "00:32.500",
      "end_timestamp": "00:41.000",
      "label": "Opening scene",
      "description": "A wide shot of a valley at sunrise. Fog lies over the trees.",
      "reasoning": "Establishes the setting and the mood."
    },
    {
      "source_filename": "example_video_1.mp4",
      "start_timestamp": "00:41.000",
      "end_timestamp": "00:55.250",
      "label": "Interview close-up",
      "description": "Close-up of person A talking about the economic consequences.",
      "reasoning": "Key statement on the main topic."
    },
    {
      "source_filename": "example_video_2.mp4",
      "start_timestamp": "01:02.000",
      "end_timestamp": "01:15.750",
      "label": "Factory machine",
      "description": "A machine in a factory hall punches metal parts. Sparks fly.",
      "reasoning": "Visual support for the interview with person A."
    }
  ]
}
```
