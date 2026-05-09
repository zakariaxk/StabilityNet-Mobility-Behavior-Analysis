# Frontend Sample Assets

Sample cards are configured in:

```text
frontend/src/lib/sampleVideos.ts
```

Backend MP4 files belong in:

```text
backend/samples/
```

Thumbnail files belong in:

```text
frontend/public/samples/thumbnails/
```

Filename mapping:

| Card | Backend MP4 | Thumbnail |
| --- | --- | --- |
| Office Hallway Walk | `office-hallway-walk.mp4` | `office-hallway-walk.jpg` |
| Two-Person Approach (Side-by-Side) | `two-person-approach.mp4` | `two-person-approach.jpg` |
| Assisted Walk (Sit Down) | `assisted-walk-sit.mp4` | `assisted-walk-sit.jpg` |
| Warehouse Fall Event | `warehouse-fall.mp4` | `warehouse-fall.jpg` |

If a thumbnail is missing or fails to load, the UI uses a safe visual fallback.
If a backend MP4 is missing, the UI marks the sample card as unavailable after
the backend returns `Video file not found.`
