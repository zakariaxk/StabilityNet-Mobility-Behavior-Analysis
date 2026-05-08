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
    id: "hallway-walk",
    title: "Hallway Walk",
    duration: "00:19",
    videoPath: "samples/test-video.mp4",
    thumbnailSrc: `${SAMPLE_THUMBNAIL_BASE_PATH}/hallway-walk.svg`,
    variant: "hallway"
  },
  {
    id: "assisted-walking",
    title: "Assisted Walking",
    duration: "00:23",
    videoPath: "samples/assisted-walking.mp4",
    thumbnailSrc: `${SAMPLE_THUMBNAIL_BASE_PATH}/assisted-walking.svg`,
    variant: "assisted"
  },
  {
    id: "rehabilitation",
    title: "Rehabilitation",
    duration: "00:27",
    videoPath: "samples/rehabilitation.mp4",
    thumbnailSrc: `${SAMPLE_THUMBNAIL_BASE_PATH}/rehabilitation.svg`,
    variant: "rehab"
  },
  {
    id: "imbalance-event",
    title: "Imbalance Event",
    duration: "00:21",
    videoPath: "samples/imbalance-event.mp4",
    thumbnailSrc: `${SAMPLE_THUMBNAIL_BASE_PATH}/imbalance-event.svg`,
    variant: "imbalance"
  }
];

export function sampleUnavailableMessage(sample: SampleVideo): string {
  return (
    `Sample unavailable. Place the MP4 at backend/${sample.videoPath} ` +
    "or upload a local MP4 instead."
  );
}
