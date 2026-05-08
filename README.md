# StabilityNet – Mobility Behavior Analysis System

StabilityNet models human mobility behavior from video to detect instability patterns and potential fall risk using temporal analysis.

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

To develop a system for understanding human movement behavior in video and detecting early indicators of instability in healthcare and assistive monitoring scenarios.
