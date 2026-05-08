# Sample Thumbnails

Replace these default SVG files with exported still frames from the matching
sample MP4s when real demo media is available.

Use the same filenames so the frontend can load them without code changes:

- `hallway-walk.svg`
- `assisted-walking.svg`
- `rehabilitation.svg`
- `imbalance-event.svg`

PNG, JPG, or WebP captures are also fine, but update `SAMPLE_VIDEOS` in
`frontend/src/lib/sampleVideos.ts` if the extension changes.

The matching MP4 files belong in `backend/samples/`; see
`frontend/public/samples/README.md` for the full mapping.
