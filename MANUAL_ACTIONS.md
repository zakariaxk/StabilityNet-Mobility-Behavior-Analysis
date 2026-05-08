# Manual Actions

This file lists the things a person needs to do so StabilityNet can run on a
computer. You do not need to understand the code to follow these steps.

## What StabilityNet Needs From You

StabilityNet can now analyze a video file, but it needs a few things from your
computer first:

- Python installed.
- Project dependencies installed.
- A video file to analyze.
- Permission to download the YOLO26n model the first time the analyzer runs.

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

The analyzer uses YOLO26n by default. To compare another Ultralytics detector
model, add `--detector-model`, for example:

```bash
python3 -m app.cli analyze \
  --video samples/test-video.mp4 \
  --output outputs/result.json \
  --detector-model yolo26s.pt
```

## 7. Allow The First Model Download

The first time you run the analyzer, it may download the YOLO26n AI model.

This is expected.

You need an internet connection for this first run. After the model is
downloaded, later runs may not need to download it again.

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

To view the uploaded video from the API, open this in your browser:

```text
http://127.0.0.1:8000/analyses/YOUR_ANALYSIS_ID/video
```

Replace `YOUR_ANALYSIS_ID` with the ID from the earlier response.

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

## 12. Run The Local Frontend

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

## 13. Add Real Sample Videos

Sample videos should be short MP4 files that match the visible sample cards:

- `backend/samples/test-video.mp4` for Hallway Walk.
- `backend/samples/assisted-walking.mp4` for Assisted Walking.
- `backend/samples/rehabilitation.mp4` for Rehabilitation.
- `backend/samples/imbalance-event.mp4` for Imbalance Event.

These MP4s are not committed to git. Add them locally or upload them to the
hosted backend storage used by your demo environment.

## 14. Add Sample Thumbnails

The frontend reads sample thumbnails from:

```text
frontend/public/samples/thumbnails/
```

Current placeholder files use these names:

- `hallway-walk.svg`
- `assisted-walking.svg`
- `rehabilitation.svg`
- `imbalance-event.svg`

For a real demo, replace those files with frame captures from the matching MP4s.
If you use `.png`, `.jpg`, or `.webp` instead of `.svg`, update the
`thumbnailSrc` values in:

```text
frontend/src/app/page.tsx
```

## 15. Annotated Outputs

Uploaded MP4s are stored under:

```text
backend/outputs/uploads/
```

Analysis JSON records are stored under:

```text
backend/outputs/analyses/
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
through `/api/stabilitynet`. The current upload flow still works with
`video_url`, which serves the uploaded MP4.

## 16. Test A Full Hosted Demo

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

## 17. Explain The Demo Honestly

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

### The First Run Is Slow

This is normal. The first run may download the AI model and load it into memory.

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
