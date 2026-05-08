# Backend Sample Videos

Put short local test videos in this folder. These files are used when the
frontend sample cards call `/analyses` with a `samples/<file>.mp4` path.

Expected demo filenames:

| Frontend card | Backend MP4 |
| --- | --- |
| Hallway Walk | `backend/samples/test-video.mp4` |
| Assisted Walking | `backend/samples/assisted-walking.mp4` |
| Rehabilitation | `backend/samples/rehabilitation.mp4` |
| Imbalance Event | `backend/samples/imbalance-event.mp4` |

Good first sample:

- `.mp4` format
- 10 to 30 seconds long
- one visible person walking or standing
- clear lighting

Example local path:

```text
backend/samples/test-video.mp4
```

Video files in this folder are ignored by git so private or large files are not
committed by accident.

Matching sample thumbnails live in:

```text
frontend/public/samples/thumbnails/
```
