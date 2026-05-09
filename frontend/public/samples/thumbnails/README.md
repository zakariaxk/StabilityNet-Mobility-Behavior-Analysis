# Sample Thumbnails

Replace these default thumbnails with exported still frames from the matching
sample MP4s when real demo media is available.

The frontend loads thumbnails based on `SAMPLE_VIDEOS` in:

```text
frontend/src/lib/sampleVideos.ts
```

Current expected demo filenames (JPG):

- `office-hallway-walk.jpg`
- `two-person-approach.jpg`
- `assisted-walk-sit.jpg`
- `warehouse-fall.jpg`

The matching MP4 files belong in `backend/samples/`; see
`frontend/public/samples/README.md` for the full mapping.
