# SchnittmAIster

SchnittmAIster turns your videos into a cut proposal. You describe a task, e.g. "make a 30-second trailer", Gemini selects the clips that fit, and the service writes them into an XMEML file. Import that file into Adobe Premiere Pro (or any editor that reads Final Cut Pro 7 XML) and you get a sequence with the proposed clips on the timeline, ready to refine. The service also renders the cut as an MP4, for a quick check or for anyone without an editing program.

This is a minimal, runnable example of the approach, not a finished product.

## How it works

1. You call the HTTP endpoint with one or more local videos and a task.
2. The service reads the videos with `ffprobe`, checks that they fit into the model's context window, finds their cuts with ffmpeg and uploads them to the Gemini Files API.
3. Gemini gets the videos and the task's prompt from [`prompts/`](prompts/) and answers with a list of clips: source file, start, end, label, description and reasoning.
4. The service converts the clips into frames, moves boundaries that just miss a cut onto it, and writes the XMEML and the preview video. The uploads are deleted.

## Requirements

- [uv](https://docs.astral.sh/uv/getting-started/installation/) for Python and the dependencies. uv uses the Python version in `.python-version` (3.12) and downloads it if it is not installed.
- [ffmpeg](https://ffmpeg.org/) for reading the videos and rendering the preview: `brew install ffmpeg` on macOS, `sudo apt install ffmpeg` on Debian and Ubuntu, for other systems see the [download page](https://ffmpeg.org/download.html).
- A Gemini API key. Open [Google AI Studio](https://aistudio.google.com/), click "Get API key" and create a key; this needs a Google account, no Google Cloud project and no billing. The free tier is enough to try the service (a paid tier, after setting up billing in AI Studio, has higher rate limits and adds the models that need billing, see [Models and limits](#models-and-limits)).

## Setup

1. Clone the repository and install the dependencies:

   ```bash
   git clone https://github.com/br-data/schnittmaister-service.git
   cd schnittmaister-service
   uv sync
   ```

2. Create the `.env` file and put your Gemini API key into it. Without it, the service does not start.

   ```bash
   cp .env.example .env
   ```

   ```text
   GEMINI_API_KEY=your-key
   ```

3. Start the service from the repository root:

   ```bash
   uv run python api.py
   ```

4. Open <http://127.0.0.1:3000/docs> for the interactive API documentation.

## Usage

`POST /xmeml/create` takes query parameters and returns the XMEML document:

| Parameter | Required | Description |
| --- | --- | --- |
| `video_paths` | yes | Local paths of the videos, with distinct file names. Formats Gemini reads: MP4, MPEG, MOV, WebM, AVI, FLV, WMV, 3GPP |
| `task_name` | yes | `scene_detection`, `nif` or `generic`, see [Tasks](#tasks) |
| `user_text_input` | for `nif` and `generic` | The voice-over script for `nif`, the task description for `generic`; empty for `scene_detection` |
| `gemini_model` | no | Gemini model (default `gemini-3.8-flash`), see [Models and limits](#models-and-limits) |
| `fps_analysis` | no | Frames per second Gemini samples, 1 to 24 (default 1, for `nif` 2) |
| `media_resolution` | no | Resolution at which Gemini reads each sampled frame: `low` (default) or `high`, which reads small text and details |
| `render_preview` | no | Render a preview video of the cut (default `true`) |

A higher `fps_analysis` or the high `media_resolution` raise the token use considerably and shorten the maximum video length. Keep the defaults unless a result misses fast action or details in the picture.

Example with curl:

```bash
curl -G -X POST "http://127.0.0.1:3000/xmeml/create" \
  --data-urlencode "video_paths=/Users/me/videos/interview.mp4" \
  --data-urlencode "task_name=generic" \
  --data-urlencode "user_text_input=Find every statement about the new bridge, with the whole sentence." \
  -o interview_cut.xml
```

Errors come back with an HTTP status code and a message. In the free tier, Gemini is often busy (503) or a quota is used up (429); then try again later or choose another model.

In Premiere Pro, import the XML with File → Import. It creates a sequence with one clip per proposal, linked to the videos at their local paths. Each clip carries a marker with Gemini's label, description and reasoning.

## Results

Every job saves the XMEML, and the preview video unless it is switched off or there are no clips, to a folder in `output/` of the repository:

```text
output/SchnittmAIster_generic_2026-10-30_15-12-03_3f9a2c/
├── SchnittmAIster_generic_2026-10-30_15-12-03_3f9a2c.xml   # the XMEML, also returned by the endpoint
└── SchnittmAIster_generic_2026-10-30_15-12-03_3f9a2c.mp4   # the preview video
```

## Tasks

| Task | What it does | Text input |
| --- | --- | --- |
| `scene_detection` | Lists every shot of the video with a short description | none |
| `nif` | Cuts a short news piece to a voice-over script: one clip per unit of meaning, in script order. Clips are limited to 60 seconds, the video is sampled at 2 fps | the voice-over script |
| `generic` | Does what the task description says, see the examples below | the task description |

Example tasks for `generic`:

> Find every passage in which the following quote is said, in any language, also in the original language of the speaker: '…'

> Make a 30-second cinema trailer.

> Show every passage in which a tram can be seen or is talked about.

The prompts are plain text files in [`prompts/`](prompts/): one per task, plus [`output_format.md`](prompts/output_format.md) with the output fields and timestamp rules that every task shares.

## Models and limits

| Model | Free tier |
| --- | --- |
| `gemini-3.8-flash` (default for all tasks) | yes |
| `gemini-3.7-flash`, `gemini-3.6-flash` | yes |
| `gemini-3.1-pro-preview`, `gemini-4-argon` | no, needs billing enabled for your API key |

The older Flash models are fallbacks for when the default answers with 503 "high demand". The free tier rate limits per model are shown in AI Studio.

**Video length.** All videos of a request go to Gemini in one call and have to fit into the model's context window. The service estimates their tokens from the costs in Google's [video understanding docs](https://ai.google.dev/gemini-api/docs/video-understanding) and rejects videos that would not fit before uploading them. With the defaults that is roughly 2.5 hours of video, 1.5 hours for `nif`; a higher `fps_analysis` or the high `media_resolution` shorten it considerably. Gemini's actual count may differ from the estimate.

**Uploads.** The videos go to Gemini through the free [Files API](https://ai.google.dev/gemini-api/docs/files): up to 2 GB per file in the free tier and 20 GB per project. The service deletes its uploads at the end of every job, also on failure; Google deletes anything left after 48 hours.

**Data use.** In the free tier, Google may use your prompts, videos and responses to improve its products, including review by humans. Check the [Gemini API terms](https://ai.google.dev/gemini-api/terms) before sending confidential material.

**Security.** This is a minimal demo for local use. The service has no authentication and accepts any file path. Anyone who can reach it can have it analyse any video your user account can read, read the results and use your Gemini API key. Do not expose it to a network. To run it as a shared service, add authentication, restrict video paths to one media folder, and check the Host and Origin headers of incoming requests.

## Contact

- <martin.burghart@br.de>

## License

MIT, see [LICENSE](LICENSE). Copyright Bayerischer Rundfunk, AI+Automation Lab.
