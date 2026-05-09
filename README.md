# StabilityNet – Mobility Behavior Analysis System

StabilityNet models human mobility behavior from uploaded video to surface motion patterns that may require review.

## Overview

The system analyzes how individuals move over time by extracting temporal features such as dwell time, movement speed, and positional variance. These signals are used to identify abnormal mobility patterns including prolonged immobility, slow movement, and unstable motion.

## Core Features

- Person detection using YOLO26n (PyTorch)
- Multi-object tracking with persistent identities
- Temporal feature extraction (dwell time, speed, position variance)
- Behavior-based anomaly scoring
- Event generation for mobility instability detection

## Tech Stack

- Python, PyTorch, OpenCV
- YOLO26n (Ultralytics)
- FastAPI, Redis, PostgreSQL
- Next.js, TypeScript

## Goal

To develop a research prototype for understanding human movement behavior in video and conservatively flagging review-worthy motion patterns in healthcare and assistive monitoring scenarios. StabilityNet is not a medical device.

## FPS metric interpretation

- **Source Video FPS** = the input video's native frame rate.
- **Effective Analysis FPS** = the sampled analysis cadence after any frame stride.
- **CPU Analysis FPS** = backend throughput during decode, detection, tracking, event scoring, and annotation.
- **End-to-End Processing FPS** = total completed frames divided by full pipeline runtime, including H.264 output writing.
- **Playback FPS** = annotated output playback timing, typically matched to source video FPS.

These values are intentionally separated so source-video frame rate is not misread as measured processing throughput.
