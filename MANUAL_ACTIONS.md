# Manual Actions

This file lists the things a person needs to do so StabilityNet can run on a
computer. You do not need to understand the code to follow these steps.

## What StabilityNet Needs From You

StabilityNet can now analyze a video file, but it needs a few things from your
computer first:

- Python installed.
- Project dependencies installed.
- A video file to analyze.
- A local YOLO26n model weights file.

## First Real Demo Test

Use this checklist for the first end-to-end MP4 test.

1. Install backend dependencies:

```bash
cd /Users/zakariakhan/Documents/StabilityNet/backend
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e ".[dev]"
```

Install frontend dependencies:

```bash
cd /Users/zakariakhan/Documents/StabilityNet/frontend
npm install
```

2. Install ffmpeg for browser-playable annotated MP4 output:

```bash
ffmpeg -version
brew install ffmpeg
```

3. Place model weights at:

```text
backend/yolo26n.pt
```

The smoke test can download this file automatically if your computer has
internet access. Manual download URL:

```text
https://github.com/ultralytics/assets/releases/download/v8.4.0/yolo26n.pt
```

Or point the backend at another existing `.pt` file:

```bash
export STABILITYNET_DETECTOR_MODEL=/absolute/path/to/yolo26n.pt
```

Leave the detector on CPU for the first demo:

```bash
export STABILITYNET_DETECTOR_DEVICE=cpu
```

4. Start the backend:

```bash
cd /Users/zakariakhan/Documents/StabilityNet/backend
source .venv/bin/activate
uvicorn app.main:app --reload
```

5. Check `/health`:

```bash
curl http://127.0.0.1:8000/health
```

Confirm it returns `"status":"ok"`. After the smoke test downloads or verifies
weights, it should report `"detector_model_status":"ready"`.

6. Run the smoke test:

```bash
cd /Users/zakariakhan/Documents/StabilityNet/backend
source .venv/bin/activate
python smoke_test.py
```

Confirm these lines appear:

```text
PASS YOLO26n model loaded successfully: /Users/zakariakhan/Documents/StabilityNet/backend/yolo26n.pt
PASS inference device: CPU
PASS YOLO26n tiny inference pass completed
```

7. Upload one MP4 with curl or the helper script:

```bash
curl -X POST http://127.0.0.1:8000/analyses/upload \
  -F "file=@/absolute/path/to/local-video.mp4;type=video/mp4"
```

```bash
python test_video_upload.py /absolute/path/to/local-video.mp4
```

8. Open the returned annotated output URL in the browser:

```text
http://127.0.0.1:8000/outputs/<file>.mp4
```

9. Start the frontend:

```bash
cd /Users/zakariakhan/Documents/StabilityNet/frontend
npm run dev
```

10. Open `http://localhost:3000` and upload the same MP4 through the UI.

11. Verify the summary cards, tracks table, events table, and annotated video
render from the real backend response.

## 1. Install Python

Open Terminal and check whether Python is installed:

```bash
python3 --version
```

If you see a version number, you can continue.

If you see an error, install Python from:

```text
https://www.python.org/downloads/
```

Choose the latest stable Python 3 version.

## 2. Open The Project Folder

Open Terminal and go to the StabilityNet project folder:

```bash
cd /Users/zakariakhan/Documents/StabilityNet
```

Then go into the backend folder:

```bash
cd backend
```

## 3. Create A Private Python Environment

This keeps StabilityNet's Python packages separate from the rest of your
computer.

Run:

```bash
python3 -m venv .venv
```

Then turn it on:

```bash
source .venv/bin/activate
```

When it is on, your Terminal line should start with something like:

```text
(.venv)
```

## 4. Install StabilityNet's Packages

Run this from the `backend` folder:

```bash
python3 -m pip install -e ".[dev]"
```

This may take a few minutes. It installs video and AI packages such as OpenCV
and Ultralytics.

## 5. Prepare A Video File

You need a video file on your computer.

Good first test videos:

- A short `.mp4` file.
- One person walking or standing.
- A clear view of the person's full body.
- A video that is 10 to 30 seconds long.

Avoid for the first test:

- Crowded videos.
- Very dark videos.
- Videos where people are mostly hidden.
- Very long videos.

Create a folder for test videos:

```bash
mkdir -p samples
```

Put your test video in:

```text
backend/samples/
```

Example video path:

```text
backend/samples/test-video.mp4
```

## 6. Run The Analyzer

From the `backend` folder, run:

```bash
python3 -m app.cli analyze --video samples/test-video.mp4 --output outputs/result.json
```

Replace `samples/test-video.mp4` with the name of your real video file.

The analyzer uses YOLO26n by default. To compare another existing Ultralytics
detector weights file, add `--detector-model`, for example:

```bash
python3 -m app.cli analyze \
  --video samples/test-video.mp4 \
  --output outputs/result.json \
  --detector-model yolo26s.pt
```

## 7. Confirm Model Weights

The backend uses Ultralytics YOLO26n detection weights through the
`ultralytics` Python package. A real analysis needs this exact file:

```text
yolo26n.pt
```

The default location is:

```text
backend/yolo26n.pt
```

Run the smoke test from the `backend` folder to auto-download the official file
when internet access is available:

```bash
python smoke_test.py
```

The downloaded file is cached locally at `backend/yolo26n.pt` and is ignored by
git.

If automatic download fails, download this file manually:

```text
https://github.com/ultralytics/assets/releases/download/v8.4.0/yolo26n.pt
```

Or this environment variable must point to an existing `.pt` file:

```bash
export STABILITYNET_DETECTOR_MODEL=/absolute/path/to/yolo26n.pt
```

If the file is missing, `/health`, the smoke test, and analysis responses tell
you the exact expected path and whether automatic download is available.

The backend is CPU-first. Keep this setting for demo runs unless you
intentionally want to use an accelerator:

```bash
export STABILITYNET_DETECTOR_DEVICE=cpu
```

## 8. Check That It Worked

If it worked, Terminal should say something like:

```text
analysis written to outputs/result.json
```

The result file should appear here:

```text
backend/outputs/result.json
```

That file contains the detected people, tracking information, movement features,
and any mobility events found by the first version of StabilityNet.

## 9. Run The Tests

Tests check that the basic movement math is still working.

From the `backend` folder, run:

```bash
python3 -m unittest discover -s tests
```

If everything is okay, you should see:

```text
OK
```

## 10. Try The Local API With Upload

The API is a local web service that lets another program ask StabilityNet to run
an analysis.

From the `backend` folder, turn on your Python environment:

```bash
source .venv/bin/activate
```

Start the API:

```bash
uvicorn app.main:app --reload
```

You can also run this from the `backend` folder:

```bash
uvicorn main:app --reload
```

Leave that Terminal window open.

Open a second Terminal window, go to the backend folder again, and run this with
your MP4 file:

```bash
curl -X POST http://127.0.0.1:8000/analyses/upload \
  -F "file=@samples/test-video.mp4;type=video/mp4"
```

Replace `samples/test-video.mp4` with your real video file name.

If it works, the response will include an `analysis_id`. Keep that ID.

To see the saved result again, run:

```bash
curl http://127.0.0.1:8000/analyses/YOUR_ANALYSIS_ID
```

To view the annotated video from the API, open this in your browser:

```text
http://127.0.0.1:8000/analyses/YOUR_ANALYSIS_ID/video
```

Replace `YOUR_ANALYSIS_ID` with the ID from the earlier response. If annotated
output was created, this route serves the annotated MP4. If not, it falls back
to the uploaded MP4.

## 11. Try The Local API With A Backend Path

This is mostly useful for debugging. The upload flow above is the better user
experience.

From the backend folder, run:

```bash
curl -X POST http://127.0.0.1:8000/analyses \
  -H "Content-Type: application/json" \
  -d '{"video_path":"samples/test-video.mp4"}'
```

Replace `samples/test-video.mp4` with your real video file name.

If it works, the response will include an `analysis_id`. Keep that ID.

To see the saved result again, run:

```bash
curl http://127.0.0.1:8000/analyses/YOUR_ANALYSIS_ID
```

Replace `YOUR_ANALYSIS_ID` with the ID from the earlier response.

## 12. Backend Testing Checklist

From the backend folder, run the smoke test before using real videos:

```bash
source .venv/bin/activate
python smoke_test.py
```

Warnings for a missing YOLO weights file or missing sample video are expected
until the smoke test downloads the weights or you add local files. A real
analysis needs `yolo26n.pt` in the backend folder or
`STABILITYNET_DETECTOR_MODEL` set to an existing `.pt` file.

Manual backend test:

1. Start the backend with `uvicorn app.main:app --reload`.
2. Open `http://127.0.0.1:8000/health` and confirm it returns `{"status":"ok"}`
   with `"detector_model_status":"ready"` after the smoke test has verified the
   model.
3. Upload a small MP4 with the `/analyses/upload` curl command above.
4. Confirm the JSON response includes `status`, `frames_processed`,
   `tracks_count`, `events_count`, `annotated_video_url`, `tracks`, `events`,
   and `message`.
5. Open the returned `annotated_video_url` in the browser, prefixed with the
   backend host, for example `http://127.0.0.1:8000/outputs/FILE.mp4`.
6. Start the frontend and confirm it renders the annotated video after upload.
7. If anything fails, check the backend terminal logs for the request, upload
   save path, video open status, frame count, output write status, and error
   context.

If you send `{}` or an empty path to `/analyses`, the backend should return:

```text
Upload an MP4 file or select a sample video before running analysis.
```

If a selected sample path does not exist, the backend should return:

```text
Video file not found.
```

## 13. Run The Local Frontend

The hosted-style demo uses the Next.js frontend and the FastAPI backend
together.

Keep the backend running in one Terminal window:

```bash
cd /Users/zakariakhan/Documents/StabilityNet/backend
source .venv/bin/activate
uvicorn app.main:app --reload
```

Open another Terminal window and start the frontend:

```bash
cd /Users/zakariakhan/Documents/StabilityNet/frontend
npm install
npm run dev
```

Open the frontend in your browser:

```text
http://localhost:3000
```

The frontend sends uploads and sample analysis requests through its
`/api/stabilitynet` proxy to the FastAPI backend.

## 14. Add Real Sample Videos

Sample videos should be short MP4 files that match the visible sample cards:

- `backend/samples/office-hallway-walk.mp4` for Office Hallway Walk.
- `backend/samples/two-person-approach.mp4` for Two-Person Approach (Side-by-Side).
- `backend/samples/assisted-walk-sit.mp4` for Assisted Walk (Sit Down).
- `backend/samples/warehouse-fall.mp4` for Warehouse Fall Event.

These MP4s are not committed to git. Add them locally or upload them to the
hosted backend storage used by your demo environment.

## 15. Add Sample Thumbnails

The frontend reads sample thumbnails from:

```text
frontend/public/samples/thumbnails/
```

Current placeholder files use these names:

- `office-hallway-walk.jpg`
- `two-person-approach.jpg`
- `assisted-walk-sit.jpg`
- `warehouse-fall.jpg`

For a real demo, replace those files with frame captures from the matching MP4s.
If you use another image extension, update the `thumbnailSrc` values in:

```text
frontend/src/lib/sampleVideos.ts
```

## 16. Annotated Outputs

Uploaded MP4s are stored under:

```text
backend/outputs/uploads/
```

Analysis JSON records are stored under:

```text
backend/outputs/analyses/
```

Annotated videos are stored under:

```text
backend/outputs/videos/
```

The frontend expects the backend response to include an annotated video URL when
an annotated output is available. It checks these fields in order:

```text
annotated_video_url
output_video_url
result.annotated_video_url
result.output_video_url
result.video.annotated_video_url
video_url
```

Relative URLs should point to backend API paths. The frontend will route them
through `/api/stabilitynet`. Annotated backend URLs use:

```text
/outputs/<filename>.mp4
```

The compatibility route `/analyses/<analysis_id>/video` serves the annotated
MP4 when it exists, then falls back to the uploaded MP4.

### Verify An Annotated Output Video

After a completed analysis, check the generated videos folder:

```bash
ls backend/outputs/videos
```

Run ffprobe on the final MP4:

```bash
ffprobe -v error -select_streams v:0 \
  -show_entries stream=codec_name,pix_fmt,codec_tag_string,width,height,duration \
  -of default=noprint_wrappers=1 \
  backend/outputs/videos/<file>.mp4
```

Confirm these lines are present:

```text
codec_name=h264
codec_tag_string=avc1
pix_fmt=yuv420p
```

Open the direct backend video URL in the browser:

```text
http://127.0.0.1:8000/outputs/<file>.mp4
```

## 17. Test A Full Hosted Demo

Before showing the demo:

- Start the FastAPI backend.
- Start the Next.js frontend.
- Upload a short MP4 and confirm `Analyze Video` returns a completed analysis.
- Select each sample card and confirm it calls the backend sample path.
- Confirm the summary cards show frames, tracked subjects, and mobility events.
- Confirm the annotated output video renders when the backend returns a video
  URL.
- Confirm tracks, motion trails, event severity badges, and event markers render
  when those fields are present.

## 18. Explain The Demo Honestly

Use this explanation:

```text
StabilityNet is currently an uploaded-video analysis system. The hosted demo runs a Next.js frontend and FastAPI inference backend. When a user uploads an MP4 or selects a sample, the backend runs YOLO26n, OpenCV, and tracking, then returns mobility events, tracked-subject summaries, and an annotated output video. It is not live webcam inference yet.
```

Do not describe StabilityNet as a medical diagnosis tool. Use phrases like
`mobility events` and `fall-risk indicators`.

## Common Problems

### `python3: command not found`

Python is not installed, or Terminal cannot find it.

Install Python from:

```text
https://www.python.org/downloads/
```

### `No module named cv2`

The video package is not installed yet.

Make sure you are in the `backend` folder and run:

```bash
python3 -m pip install -e ".[dev]"
```

### `No module named ultralytics`

The AI detection package is not installed yet.

Make sure you are in the `backend` folder and run:

```bash
python3 -m pip install -e ".[dev]"
```

### `video file does not exist`

The video path is wrong.

Check that the file is really in the folder you typed.

Example:

```bash
ls samples
```

Then run the analyzer again with the exact file name.

### The First Real Run Is Slow

This is normal. The first real run loads the AI model into memory and processes
every readable frame.

Try again with a short video first.

## What You Do Not Need To Do Yet

These are later project steps and are not required for the current backend
pipeline:

- Deploy anything to the internet.
- Train a custom AI model.
- Add a database, account system, or live webcam inference.

## Current Best Next Step

Install the backend packages and run the local frontend/backend demo with one
short `.mp4` video.

Use these commands in two Terminal windows:

```bash
cd /Users/zakariakhan/Documents/StabilityNet/backend
source .venv/bin/activate
uvicorn app.main:app --reload
```

```bash
cd /Users/zakariakhan/Documents/StabilityNet/frontend
npm run dev
```
