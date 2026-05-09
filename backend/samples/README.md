# Backend Sample Videos

Put short local test videos in this folder. These files are used when the
frontend sample cards call `/analyses` with a `samples/<file>.mp4` path.

Expected demo filenames:

| Frontend card | Backend MP4 |
| --- | --- |
| Office Hallway Walk | `backend/samples/office-hallway-walk.mp4` |
| Two-Person Approach (Side-by-Side) | `backend/samples/two-person-approach.mp4` |
| Assisted Walk (Sit Down) | `backend/samples/assisted-walk-sit.mp4` |
| Warehouse Fall Event | `backend/samples/warehouse-fall.mp4` |

Good first sample:

- `.mp4` format
- 10 to 30 seconds long
- one visible person walking or standing
- clear lighting

Example local path:

```text
backend/samples/office-hallway-walk.mp4
```

Video files in this folder are ignored by git so private or large files are not
committed by accident.

Matching sample thumbnails live in:

```text
frontend/public/samples/thumbnails/
```
