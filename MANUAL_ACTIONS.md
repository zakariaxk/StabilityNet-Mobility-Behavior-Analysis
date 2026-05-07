# Manual Actions

This file lists the things a person needs to do so StabilityNet can run on a
computer. You do not need to understand the code to follow these steps.

## What StabilityNet Needs From You

StabilityNet can now analyze a video file, but it needs a few things from your
computer first:

- Python installed.
- Project dependencies installed.
- A video file to analyze.
- Permission to download the YOLOv8n model the first time the analyzer runs.

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

## 7. Allow The First Model Download

The first time you run the analyzer, it may download the YOLOv8n AI model.

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

## 10. Try The Local API

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

Open a second Terminal window, go to the backend folder again, and run:

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

- Set up PostgreSQL.
- Set up Redis.
- Run a Next.js frontend.
- Deploy anything to the internet.
- Train a custom AI model.

## Current Best Next Step

Install the backend packages and run the analyzer on one short `.mp4` video.

Use this command from the `backend` folder:

```bash
python3 -m app.cli analyze --video samples/test-video.mp4 --output outputs/result.json
```
