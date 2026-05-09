#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

SAMPLES_DIR="${ROOT_DIR}/backend/samples"
THUMBS_DIR="${ROOT_DIR}/frontend/public/samples/thumbnails"

WIDTH="${WIDTH:-640}"
ASPECT="${ASPECT:-1.55}"
QUALITY="${QUALITY:-3}"

mkdir -p "${THUMBS_DIR}"

height_from_aspect() {
  awk -v w="${WIDTH}" -v a="${ASPECT}" 'BEGIN { printf("%d\n", int((w / a) + 0.5)) }'
}

duration_seconds() {
  local input="$1"
  ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "${input}"
}

midpoint_time() {
  local duration="$1"
  awk -v d="${duration}" 'BEGIN { printf("%.3f\n", d * 0.5) }'
}

extract_jpg() {
  local input="$1"
  local output="$2"
  local t="$3"
  local height="$4"

  ffmpeg -hide_banner -loglevel error -y \
    -ss "${t}" -i "${input}" \
    -frames:v 1 \
    -vf "scale=${WIDTH}:${height}:force_original_aspect_ratio=increase,crop=${WIDTH}:${height}" \
    -q:v "${QUALITY}" \
    "${output}"
}

HEIGHT="$(height_from_aspect)"

echo "Generating thumbnails:"
echo "  samples:   ${SAMPLES_DIR}"
echo "  thumbs:    ${THUMBS_DIR}"
echo "  size:      ${WIDTH}x${HEIGHT} (aspect ${ASPECT})"
echo "  quality:   ${QUALITY} (lower is better for jpg)"
echo

samples=(
  "office-hallway-walk"
  "two-person-approach"
  "assisted-walk-sit"
  "warehouse-fall"
)

for sample_id in "${samples[@]}"; do
  input="${SAMPLES_DIR}/${sample_id}.mp4"
  output="${THUMBS_DIR}/${sample_id}.jpg"

  if [[ ! -f "${input}" ]]; then
    echo "SKIP ${sample_id}: missing ${input}"
    continue
  fi

  dur="$(duration_seconds "${input}")"
  t="$(midpoint_time "${dur}")"

  extract_jpg "${input}" "${output}" "${t}" "${HEIGHT}"
  echo "OK   ${sample_id} -> $(basename "${output}") @ ${t}s"
done
