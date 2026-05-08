# StabilityNet Frontend

Next.js + TypeScript review interface for the local StabilityNet API.

## Run locally

From this folder:

```bash
npm install
npm run dev
```

Open:

```text
http://localhost:3000
```

The frontend proxies backend calls through Next route handlers. By default it
expects the FastAPI backend at:

```text
http://127.0.0.1:8000
```

Override that when needed:

```bash
STABILITYNET_API_BASE_URL=http://127.0.0.1:8000 npm run dev
```

The first screen supports direct `.mp4` upload and also keeps the backend-path
debug workflow. A backend video path looks like:

```text
samples/test-video.mp4
```

## Validation

```bash
npm run lint
npm run typecheck
npm run build
```
