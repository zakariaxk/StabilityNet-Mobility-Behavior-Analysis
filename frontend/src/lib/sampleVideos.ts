const SAMPLE_THUMBNAIL_BASE_PATH = "/samples/thumbnails";

export type SampleVideoVariant = "hallway" | "assisted" | "rehab" | "imbalance";

export interface SampleVideo {
  id: string;
  title: string;
  duration: string;
  videoPath: string;
  thumbnailSrc: string;
  variant: SampleVideoVariant;
}

export const SAMPLE_VIDEOS: readonly SampleVideo[] = [
  {
    id: "office-hallway-walk",
    title: "Office Hallway Walk",
    duration: "00:19",
    videoPath: "samples/office-hallway-walk.mp4",
    thumbnailSrc: `${SAMPLE_THUMBNAIL_BASE_PATH}/office-hallway-walk.jpg`,
    variant: "hallway"
  },
  {
    id: "assisted-walk-sit",
    title: "Assisted Walk (Sit Down)",
    duration: "00:23",
    videoPath: "samples/assisted-walk-sit.mp4",
    thumbnailSrc: `${SAMPLE_THUMBNAIL_BASE_PATH}/assisted-walk-sit.jpg`,
    variant: "assisted"
  },
  {
    id: "two-person-approach",
    title: "Two-Person Approach (Side-by-Side)",
    duration: "00:27",
    videoPath: "samples/two-person-approach.mp4",
    thumbnailSrc: `${SAMPLE_THUMBNAIL_BASE_PATH}/two-person-approach.jpg`,
    variant: "rehab"
  },
  {
    id: "warehouse-fall",
    title: "Warehouse Fall Event",
    duration: "00:21",
    videoPath: "samples/warehouse-fall.mp4",
    thumbnailSrc: `${SAMPLE_THUMBNAIL_BASE_PATH}/warehouse-fall.jpg`,
    variant: "imbalance"
  }
];

export function sampleUnavailableMessage(sample: SampleVideo): string {
  return (
    `Sample unavailable. Place the MP4 at backend/${sample.videoPath} ` +
    "or upload a local MP4 instead."
  );
}
