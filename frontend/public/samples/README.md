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
| Hallway Walk | `test-video.mp4` | `hallway-walk.svg` |
| Assisted Walking | `assisted-walking.mp4` | `assisted-walking.svg` |
| Rehabilitation | `rehabilitation.mp4` | `rehabilitation.svg` |
| Imbalance Event | `imbalance-event.mp4` | `imbalance-event.svg` |

If a thumbnail is missing or fails to load, the UI uses a safe visual fallback.
If a backend MP4 is missing, the UI marks the sample card as unavailable after
the backend returns `Video file not found.`
