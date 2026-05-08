"use client";

import type {
  ChangeEvent,
  DragEvent,
  ReactNode,
  SVGProps
} from "react";
import { useEffect, useMemo, useRef, useState } from "react";

import {
  AnalysisRecord,
  BehaviorEvent,
  TrackSummary,
  analysisVideoUrl,
  checkHealth,
  createAnalysis,
  uploadAnalysis
} from "@/lib/stabilityNetApi";

const FALLBACK_ANALYSIS_ERROR =
  "Upload an MP4 file or select a sample video before running analysis.";

const SAMPLE_VIDEOS = [
  {
    id: "hallway-walk",
    title: "Hallway Walk",
    duration: "00:19",
    videoPath: "samples/test-video.mp4",
    variant: "hallway"
  },
  {
    id: "assisted-walking",
    title: "Assisted Walking",
    duration: "00:23",
    videoPath: "samples/assisted-walking.mp4",
    variant: "assisted"
  },
  {
    id: "rehabilitation",
    title: "Rehabilitation",
    duration: "00:27",
    videoPath: "samples/rehabilitation.mp4",
    variant: "rehab"
  },
  {
    id: "imbalance-event",
    title: "Imbalance Event",
    duration: "00:21",
    videoPath: "samples/imbalance-event.mp4",
    variant: "imbalance"
  }
] as const;

type SampleVideo = (typeof SAMPLE_VIDEOS)[number];

type HealthState =
  | { state: "checking"; label: "Checking" }
  | { state: "ok"; label: "Online" }
  | { state: "error"; label: "Offline"; detail: string };

type TrackPoint = {
  x: number;
  y: number;
  confidence?: number;
  timestamp?: number;
};

type TrackRow = {
  id: number;
  durationSeconds?: number;
  frames: number;
  averageConfidence?: number;
  points: TrackPoint[];
};

type IconProps = SVGProps<SVGSVGElement>;

export default function StabilityNetPage() {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [selectedSampleId, setSelectedSampleId] = useState<string | null>(
    SAMPLE_VIDEOS[0].id
  );
  const [videoFile, setVideoFile] = useState<File | null>(null);
  const [analysis, setAnalysis] = useState<AnalysisRecord | null>(null);
  const [health, setHealth] = useState<HealthState>({
    state: "checking",
    label: "Checking"
  });
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isDragging, setIsDragging] = useState(false);

  useEffect(() => {
    let isCurrent = true;

    checkHealth()
      .then(() => {
        if (isCurrent) {
          setHealth({ state: "ok", label: "Online" });
        }
      })
      .catch((caughtError: unknown) => {
        if (isCurrent) {
          setHealth({
            state: "error",
            label: "Offline",
            detail: errorMessage(caughtError)
          });
        }
      });

    return () => {
      isCurrent = false;
    };
  }, []);

  const selectedSample = useMemo(
    () =>
      SAMPLE_VIDEOS.find((sample) => sample.id === selectedSampleId) ?? null,
    [selectedSampleId]
  );
  const tracks = useMemo(() => safeArray(analysis?.result.tracks), [analysis]);
  const events = useMemo(() => safeArray(analysis?.result.events), [analysis]);
  const trackRows = useMemo(
    () => buildTrackRows(tracks, analysis?.result.frames),
    [analysis?.result.frames, tracks]
  );
  const annotatedVideoUrl = analysis ? analysisVideoUrl(analysis) : null;
  const framesProcessed = numberOrZero(
    readNumber(analysis?.summary, "frames_processed") ??
      analysis?.result.frames_processed
  );
  const processingFps = formatOptionalDecimal(
    readNumber(analysis?.summary, "processing_fps") ??
      readNumber(analysis?.result, "processing_fps")
  );

  async function handleAnalyze() {
    if (!videoFile && !selectedSample) {
      setError(FALLBACK_ANALYSIS_ERROR);
      return;
    }

    setError(null);
    setIsSubmitting(true);

    try {
      const record = videoFile
        ? await uploadAnalysis(videoFile)
        : await createAnalysis({ video_path: selectedSample!.videoPath });
      setAnalysis(record);
    } catch (caughtError: unknown) {
      setError(errorMessage(caughtError) || FALLBACK_ANALYSIS_ERROR);
    } finally {
      setIsSubmitting(false);
    }
  }

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    acceptFile(event.target.files?.[0] ?? null);
  }

  function acceptFile(file: File | null) {
    if (!file) {
      return;
    }

    if (!isMp4File(file)) {
      setError("Only MP4 files are supported.");
      setVideoFile(null);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
      return;
    }

    setError(null);
    setAnalysis(null);
    setSelectedSampleId(null);
    setVideoFile(file);
  }

  function handleDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setIsDragging(false);
    acceptFile(event.dataTransfer.files?.[0] ?? null);
  }

  function handleSampleSelect(sampleId: string) {
    setError(null);
    setAnalysis(null);
    setSelectedSampleId(sampleId);
    setVideoFile(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  }

  return (
    <div className="app-shell">
      <Sidebar />
      <main className="main-content">
        <div className="content-inner">
          <Header health={health} />

          <div className="input-grid">
            <UploadCard
              fileName={videoFile?.name}
              inputRef={fileInputRef}
              isDragging={isDragging}
              onBrowse={handleFileChange}
              onDragEnter={() => setIsDragging(true)}
              onDragLeave={() => setIsDragging(false)}
              onDragOver={(event) => event.preventDefault()}
              onDrop={handleDrop}
            />
            <SampleVideos
              selectedSampleId={selectedSampleId}
              onSelect={handleSampleSelect}
            />
          </div>

          <div className="action-row">
            <button
              className="primary-action"
              type="button"
              onClick={handleAnalyze}
              disabled={isSubmitting || (!videoFile && !selectedSample)}
            >
              {isSubmitting ? <SpinnerIcon /> : <PlayIcon />}
              {isSubmitting ? "Analyzing..." : "Analyze Video"}
            </button>
          </div>

          <div className="notice-stack" aria-live="polite">
            {health.state === "error" ? (
              <Alert title="Backend offline" tone="warning">
                {health.detail}
              </Alert>
            ) : null}
            {error ? (
              <Alert title="Analysis failed" tone="danger">
                {error}
              </Alert>
            ) : null}
          </div>

          <SummaryCards
            status={analysis ? humanizeStatus(analysis.status) : "Idle"}
            framesProcessed={framesProcessed}
            trackCount={trackRows.length}
            eventCount={events.length}
            processingFps={processingFps}
          />

          <div className="results-grid">
            <AnnotatedVideo videoUrl={annotatedVideoUrl} />
            <div className="results-side">
              <TracksTable tracks={trackRows} />
              <EventsTable events={events} />
            </div>
          </div>

          <PipelineSection />
        </div>
      </main>
    </div>
  );
}

function Sidebar() {
  return (
    <aside className="sidebar" aria-label="StabilityNet navigation">
      <div className="sidebar-brand">
        <WalkingIcon className="brand-icon" />
        <div>
          <strong>StabilityNet</strong>
          <p>Video-based mobility and fall-risk analysis</p>
        </div>
      </div>

      <nav className="sidebar-nav" aria-label="Primary">
        <SidebarLink active icon={<ChartIcon />} label="Analysis" />
        <SidebarLink icon={<FolderIcon />} label="Samples" />
        <SidebarLink icon={<PanelIcon />} label="Results" />
        <SidebarLink icon={<InfoIcon />} label="About" />
      </nav>

      <div className="prototype-card">
        <strong>Research Prototype</strong>
        <p>
          This system analyzes uploaded videos to extract mobility patterns and
          identify potential fall-risk indicators.
        </p>
        <span>Not a medical device.</span>
      </div>
    </aside>
  );
}

function SidebarLink({
  active = false,
  icon,
  label
}: {
  active?: boolean;
  icon: ReactNode;
  label: string;
}) {
  return (
    <a className={`sidebar-link${active ? " sidebar-link--active" : ""}`} href="#">
      {icon}
      <span>{label}</span>
    </a>
  );
}

function Header({ health }: { health: HealthState }) {
  return (
    <header className="hero-header">
      <div className="hero-copy">
        <h1>StabilityNet</h1>
        <p className="hero-subtitle">
          Video-based mobility and fall-risk analysis
        </p>
        <p className="hero-intro">
          Upload a video or try a sample to analyze human motion, track
          individuals, and detect mobility events that may indicate fall risk.
        </p>
      </div>
      <div className={`online-pill online-pill--${health.state}`}>
        <span aria-hidden="true" />
        <strong>{health.label}</strong>
      </div>
    </header>
  );
}

function UploadCard({
  fileName,
  inputRef,
  isDragging,
  onBrowse,
  onDragEnter,
  onDragLeave,
  onDragOver,
  onDrop
}: {
  fileName?: string;
  inputRef: React.RefObject<HTMLInputElement | null>;
  isDragging: boolean;
  onBrowse: (event: ChangeEvent<HTMLInputElement>) => void;
  onDragEnter: () => void;
  onDragLeave: () => void;
  onDragOver: (event: DragEvent<HTMLLabelElement>) => void;
  onDrop: (event: DragEvent<HTMLLabelElement>) => void;
}) {
  return (
    <section className="panel upload-panel" aria-labelledby="upload-title">
      <h2 id="upload-title">1. Upload Video</h2>
      <label
        className={`dropzone${isDragging ? " dropzone--active" : ""}`}
        htmlFor="video-upload"
        onDragEnter={onDragEnter}
        onDragLeave={onDragLeave}
        onDragOver={onDragOver}
        onDrop={onDrop}
      >
        <input
          ref={inputRef}
          id="video-upload"
          className="sr-only"
          type="file"
          accept="video/mp4,.mp4"
          onChange={onBrowse}
        />
        <UploadIcon className="dropzone-icon" />
        <strong>Drag &amp; drop an MP4 file here</strong>
        <span>or click to browse</span>
        <small>Max file size: 500 MB • Format: MP4</small>
        {fileName ? <em>{fileName}</em> : null}
      </label>
    </section>
  );
}

function SampleVideos({
  selectedSampleId,
  onSelect
}: {
  selectedSampleId: string | null;
  onSelect: (sampleId: string) => void;
}) {
  return (
    <section className="panel samples-panel" aria-labelledby="samples-title">
      <h2 id="samples-title">2. Or Try a Sample Video</h2>
      <div className="sample-grid">
        {SAMPLE_VIDEOS.map((sample) => (
          <button
            key={sample.id}
            className={`sample-card${
              selectedSampleId === sample.id ? " sample-card--selected" : ""
            }`}
            type="button"
            onClick={() => onSelect(sample.id)}
          >
            <SampleThumbnail sample={sample} selected={selectedSampleId === sample.id} />
            <span>{sample.title}</span>
          </button>
        ))}
      </div>
      <p className="sample-note">
        <InfoIcon />
        <span>Sample videos are anonymized and publicly available.</span>
      </p>
    </section>
  );
}

function SampleThumbnail({
  sample,
  selected
}: {
  sample: SampleVideo;
  selected: boolean;
}) {
  return (
    <div className={`sample-thumb sample-thumb--${sample.variant}`}>
      <ClinicalScene variant={sample.variant} />
      <span className="duration-pill">{sample.duration}</span>
      {selected ? (
        <span className="selected-check" aria-label="Selected">
          <CheckIcon />
        </span>
      ) : null}
    </div>
  );
}

function ClinicalScene({ variant }: { variant: SampleVideo["variant"] }) {
  const secondPerson = variant === "assisted" || variant === "rehab";
  const walkingAid = variant === "assisted" || variant === "rehab";
  const imbalance = variant === "imbalance";

  return (
    <svg
      className="clinical-scene"
      viewBox="0 0 240 136"
      aria-hidden="true"
      focusable="false"
    >
      <rect width="240" height="136" rx="10" fill="#ECEAE4" />
      <path d="M0 0h240v36H0z" fill="#D9DED8" />
      <path d="M0 136 88 36h64l88 100Z" fill="#CFC8BC" />
      <path d="M88 36h64v100H88z" fill="#E8E2D8" />
      <path d="M28 38h42v84H28zM170 38h42v84h-42z" fill="#BFC7C1" opacity="0.58" />
      <path d="M87 36 42 136M153 36l45 100" stroke="#AAB6B2" strokeWidth="3" />
      <path d="M96 54h48M92 76h56M88 99h64" stroke="#D5D0C8" strokeWidth="2" />
      <Figure x={imbalance ? 112 : 106} y={48} color="#254F4B" lean={imbalance ? -8 : 0} />
      {secondPerson ? <Figure x={146} y={52} color="#2C6E6A" lean={0} /> : null}
      {walkingAid ? <Walker x={94} y={86} /> : null}
    </svg>
  );
}

function Figure({
  x,
  y,
  color,
  lean
}: {
  x: number;
  y: number;
  color: string;
  lean: number;
}) {
  return (
    <g transform={`translate(${x} ${y}) rotate(${lean} 12 32)`}>
      <circle cx="12" cy="8" r="8" fill="#CFAF92" />
      <path d="M7 19h13l6 37H1z" fill={color} />
      <path d="M6 55 0 91M20 55l10 91" stroke="#2D3634" strokeWidth="6" strokeLinecap="round" />
      <path d="M5 28-9 48M21 28l16 12" stroke={color} strokeWidth="5" strokeLinecap="round" />
    </g>
  );
}

function Walker({ x, y }: { x: number; y: number }) {
  return (
    <g transform={`translate(${x} ${y})`} stroke="#6E7976" strokeWidth="4" fill="none">
      <path d="M0 0h54M8 0v38M46 0v38M8 20h38" strokeLinecap="round" />
    </g>
  );
}

function Alert({
  title,
  tone,
  children
}: {
  title: string;
  tone: "warning" | "danger";
  children: ReactNode;
}) {
  return (
    <div className={`alert alert--${tone}`}>
      <strong>{title}</strong>
      <p>{children}</p>
    </div>
  );
}

function SummaryCards({
  status,
  framesProcessed,
  trackCount,
  eventCount,
  processingFps
}: {
  status: string;
  framesProcessed: number;
  trackCount: number;
  eventCount: number;
  processingFps: string;
}) {
  return (
    <section className="panel summary-panel" aria-labelledby="summary-title">
      <h2 id="summary-title">3. Analysis Summary</h2>
      <div className="metric-grid">
        <MetricCard icon={<ActivityIcon />} label="Status" value={status} />
        <MetricCard
          icon={<FilmIcon />}
          label="Frames Processed"
          value={framesProcessed.toLocaleString()}
        />
        <MetricCard
          icon={<UserIcon />}
          label="Active Tracks"
          value={trackCount.toLocaleString()}
        />
        <MetricCard
          icon={<FlagIcon />}
          label="Events Detected"
          value={eventCount.toLocaleString()}
        />
        <MetricCard icon={<GaugeIcon />} label="Processing FPS" value={processingFps} />
      </div>
    </section>
  );
}

function MetricCard({
  icon,
  label,
  value
}: {
  icon: ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="metric-card">
      <span className="metric-icon">{icon}</span>
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
      </div>
    </div>
  );
}

function AnnotatedVideo({ videoUrl }: { videoUrl: string | null }) {
  return (
    <section className="panel annotated-panel" aria-labelledby="video-title">
      <h2 id="video-title">4. Annotated Output</h2>
      <div className="video-frame">
        {videoUrl ? (
          <video
            className="annotated-video"
            src={videoUrl}
            controls
            preload="metadata"
          />
        ) : (
          <div className="video-empty">
            <VideoIcon />
            <strong>No video to display</strong>
            <span>Run an analysis to view the annotated output.</span>
          </div>
        )}
      </div>
    </section>
  );
}

function TracksTable({ tracks }: { tracks: TrackRow[] }) {
  return (
    <section className="panel table-panel" aria-labelledby="tracks-title">
      <div className="table-heading">
        <h2 id="tracks-title">5. Tracks</h2>
        <span>Total Tracks: {tracks.length.toLocaleString()}</span>
      </div>
      {tracks.length > 0 ? (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>ID</th>
                <th>Duration (s)</th>
                <th>Frames</th>
                <th>Avg. Confidence</th>
                <th>Trajectory</th>
              </tr>
            </thead>
            <tbody>
              {tracks.map((track, index) => (
                <tr key={track.id}>
                  <td>
                    <span className={`track-id track-id--${index % 4}`}>
                      {track.id}
                    </span>
                  </td>
                  <td>{formatOptionalDecimal(track.durationSeconds)}</td>
                  <td>{track.frames.toLocaleString()}</td>
                  <td>{formatOptionalDecimal(track.averageConfidence)}</td>
                  <td>
                    <Trajectory points={track.points} tone={index % 4} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <EmptyState
          title="No tracks available"
          body="Run an analysis to see tracks."
        />
      )}
    </section>
  );
}

function EventsTable({ events }: { events: BehaviorEvent[] }) {
  return (
    <section className="panel table-panel" aria-labelledby="events-title">
      <div className="table-heading">
        <h2 id="events-title">6. Events Timeline</h2>
        <span>Total Events: {events.length.toLocaleString()}</span>
      </div>
      {events.length > 0 ? (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Time (s)</th>
                <th>Event Type</th>
                <th>Description</th>
                <th>Severity</th>
              </tr>
            </thead>
            <tbody>
              {events.map((event, index) => (
                <tr key={event.event_id ?? `${event.track_id}-${event.event_type}-${index}`}>
                  <td>{formatOptionalDecimal(readNumber(event, "timestamp_s"))}</td>
                  <td>{humanizeEventType(readString(event, "event_type") ?? "event")}</td>
                  <td>
                    {readString(event, "reason") ??
                      readString(event, "description") ??
                      "Mobility pattern observed"}
                  </td>
                  <td>
                    <SeverityBadge severity={readString(event, "severity") ?? "low"} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <EmptyState
          title="No events detected"
          body="Run an analysis to see events."
        />
      )}
    </section>
  );
}

function SeverityBadge({ severity }: { severity: string }) {
  const severityTone = severityClass(severity);
  return (
    <span className={`severity severity--${severityTone}`}>
      {capitalize(severityTone)}
    </span>
  );
}

function Trajectory({ points, tone }: { points: TrackPoint[]; tone: number }) {
  if (points.length < 2) {
    return <span className="trajectory-empty">–</span>;
  }

  return (
    <svg
      className={`trajectory trajectory--${tone}`}
      viewBox="0 0 96 28"
      role="img"
      aria-label="Track trajectory"
    >
      <polyline points={trajectoryPolyline(points)} />
      <circle cx="88" cy="14" r="3.5" />
    </svg>
  );
}

function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div className="empty-state">
      <strong>{title}</strong>
      <span>{body}</span>
    </div>
  );
}

function PipelineSection() {
  const steps = [
    {
      title: "MP4 Upload",
      subtitle: "Input video",
      icon: <UploadIcon />
    },
    {
      title: "YOLO26n Detection",
      subtitle: "Detect people",
      icon: <TargetIcon />
    },
    {
      title: "SORT Tracking",
      subtitle: "Track identities",
      icon: <UserIcon />
    },
    {
      title: "Temporal Motion Analysis",
      subtitle: "Analyze patterns",
      icon: <ChartIcon />
    },
    {
      title: "Fall-Risk Indicators",
      subtitle: "Identify risk events",
      icon: <ShieldIcon />
    }
  ];

  return (
    <section className="panel pipeline-panel" aria-labelledby="pipeline-title">
      <h2 id="pipeline-title">7. Analysis Pipeline</h2>
      <div className="pipeline-steps">
        {steps.map((step, index) => (
          <div className="pipeline-item" key={step.title}>
            <div className="pipeline-step">
              <span>{step.icon}</span>
              <strong>{step.title}</strong>
              <small>{step.subtitle}</small>
            </div>
            {index < steps.length - 1 ? <ArrowRightIcon className="pipeline-arrow" /> : null}
          </div>
        ))}
      </div>
    </section>
  );
}

function buildTrackRows(
  tracks: TrackSummary[],
  frames: unknown[] | undefined
): TrackRow[] {
  const observationsByTrack = observationsFromFrames(frames);
  const ids = new Set<number>();

  for (const track of tracks) {
    if (Number.isFinite(track.track_id)) {
      ids.add(track.track_id);
    }
  }
  for (const id of observationsByTrack.keys()) {
    ids.add(id);
  }

  return Array.from(ids)
    .sort((left, right) => left - right)
    .map((id) => {
      const track = tracks.find((candidate) => candidate.track_id === id);
      const points = observationsByTrack.get(id) ?? [];
      const featureRecord = isRecord(track?.features) ? track?.features : undefined;
      const firstTimestamp =
        readNumber(track, "first_timestamp_s") ?? firstPointTimestamp(points);
      const lastTimestamp =
        readNumber(track, "last_timestamp_s") ?? lastPointTimestamp(points);
      const durationSeconds =
        readNumber(featureRecord, "duration_s") ??
        (firstTimestamp !== undefined && lastTimestamp !== undefined
          ? Math.max(0, lastTimestamp - firstTimestamp)
          : undefined);
      const framesCount =
        readNumber(track, "observations") ?? readNumber(featureRecord, "observations");

      return {
        id,
        durationSeconds,
        frames: Math.max(0, Math.round(framesCount ?? points.length)),
        averageConfidence: averageConfidence(points),
        points
      };
    });
}

function observationsFromFrames(
  frames: unknown[] | undefined
): Map<number, TrackPoint[]> {
  const observations = new Map<number, TrackPoint[]>();

  for (const frame of safeUnknownArray(frames)) {
    if (!isRecord(frame)) {
      continue;
    }
    const frameTimestamp = readNumber(frame, "timestamp_s");
    for (const track of safeUnknownArray(frame.tracks)) {
      if (!isRecord(track)) {
        continue;
      }
      const trackId = readNumber(track, "track_id");
      if (trackId === undefined) {
        continue;
      }
      const center = readCenter(track.center) ?? readCenter(readRecord(track, "bbox")?.center);
      if (!center) {
        continue;
      }
      const list = observations.get(trackId) ?? [];
      list.push({
        x: center[0],
        y: center[1],
        confidence: readNumber(track, "confidence"),
        timestamp: readNumber(track, "timestamp_s") ?? frameTimestamp
      });
      observations.set(trackId, list);
    }
  }

  return observations;
}

function trajectoryPolyline(points: TrackPoint[]): string {
  const visiblePoints = points.slice(-24);
  const xValues = visiblePoints.map((point) => point.x);
  const yValues = visiblePoints.map((point) => point.y);
  const minX = Math.min(...xValues);
  const maxX = Math.max(...xValues);
  const minY = Math.min(...yValues);
  const maxY = Math.max(...yValues);
  const xRange = Math.max(1, maxX - minX);
  const yRange = Math.max(1, maxY - minY);

  return visiblePoints
    .map((point, index) => {
      const x =
        visiblePoints.length === 1 ? 8 : 8 + (index / (visiblePoints.length - 1)) * 80;
      const normalizedY = (point.y - minY) / yRange;
      const y = 22 - normalizedY * 16;
      const normalizedX = (point.x - minX) / xRange;
      return `${roundSvg(x + normalizedX * 4)},${roundSvg(y)}`;
    })
    .join(" ");
}

function firstPointTimestamp(points: TrackPoint[]): number | undefined {
  return points.find((point) => point.timestamp !== undefined)?.timestamp;
}

function lastPointTimestamp(points: TrackPoint[]): number | undefined {
  return [...points].reverse().find((point) => point.timestamp !== undefined)?.timestamp;
}

function averageConfidence(points: TrackPoint[]): number | undefined {
  const confidences = points
    .map((point) => point.confidence)
    .filter((value): value is number => typeof value === "number" && Number.isFinite(value));
  if (confidences.length === 0) {
    return undefined;
  }
  return confidences.reduce((sum, value) => sum + value, 0) / confidences.length;
}

function roundSvg(value: number): string {
  return value.toFixed(2).replace(/\.?0+$/, "");
}

function isMp4File(file: File): boolean {
  return file.type === "video/mp4" || file.name.toLowerCase().endsWith(".mp4");
}

function safeArray<T>(value: T[] | undefined): T[] {
  return Array.isArray(value) ? value : [];
}

function safeUnknownArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function numberOrZero(value: number | undefined): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function formatOptionalDecimal(value: number | undefined): string {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "–";
  }

  return value >= 10 ? value.toFixed(1) : value.toFixed(2);
}

function humanizeStatus(value: string): string {
  if (!value) {
    return "Idle";
  }
  return value
    .split(/[_-]+/)
    .filter(Boolean)
    .map(capitalize)
    .join(" ");
}

function humanizeEventType(value: string): string {
  return value
    .split(/[_-]+/)
    .filter(Boolean)
    .map(capitalize)
    .join(" ");
}

function capitalize(value: string): string {
  return `${value.charAt(0).toUpperCase()}${value.slice(1).toLowerCase()}`;
}

function severityClass(value: string): "low" | "medium" | "high" {
  const normalized = value.toLowerCase();
  if (normalized.includes("high") || normalized.includes("critical")) {
    return "high";
  }
  if (normalized.includes("medium") || normalized.includes("moderate")) {
    return "medium";
  }
  return "low";
}

function readRecord(
  value: Record<string, unknown> | undefined,
  key: string
): Record<string, unknown> | undefined {
  const nested = value?.[key];
  return isRecord(nested) ? nested : undefined;
}

function readString(value: unknown, key: string): string | undefined {
  if (!isRecord(value)) {
    return undefined;
  }
  const raw = value[key];
  return typeof raw === "string" && raw.trim() ? raw : undefined;
}

function readNumber(value: unknown, key: string): number | undefined {
  if (!isRecord(value)) {
    return undefined;
  }
  const raw = value[key];
  return typeof raw === "number" && Number.isFinite(raw) ? raw : undefined;
}

function readCenter(value: unknown): [number, number] | undefined {
  if (!Array.isArray(value) || value.length < 2) {
    return undefined;
  }
  const [x, y] = value;
  if (
    typeof x !== "number" ||
    typeof y !== "number" ||
    !Number.isFinite(x) ||
    !Number.isFinite(y)
  ) {
    return undefined;
  }
  return [x, y];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Unexpected frontend error.";
}

function BaseIcon({ children, ...props }: IconProps & { children: ReactNode }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      {...props}
    >
      {children}
    </svg>
  );
}

function WalkingIcon(props: IconProps) {
  return (
    <BaseIcon {...props}>
      <path d="M13 4a2 2 0 1 0-4 0 2 2 0 0 0 4 0Z" />
      <path d="M10 7 7 21" />
      <path d="m11 11 4 4 2 6" />
      <path d="m9 12-4 3" />
      <path d="m12 8 4 2" />
    </BaseIcon>
  );
}

function ChartIcon(props: IconProps) {
  return (
    <BaseIcon {...props}>
      <path d="M4 19V5" />
      <path d="M4 19h16" />
      <path d="m6 15 4-5 4 3 4-7" />
    </BaseIcon>
  );
}

function FolderIcon(props: IconProps) {
  return (
    <BaseIcon {...props}>
      <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z" />
      <path d="m12 11 3 2-3 2Z" />
    </BaseIcon>
  );
}

function PanelIcon(props: IconProps) {
  return (
    <BaseIcon {...props}>
      <rect x="4" y="4" width="16" height="16" rx="2" />
      <path d="M8 16v-4" />
      <path d="M12 16V8" />
      <path d="M16 16v-6" />
    </BaseIcon>
  );
}

function InfoIcon(props: IconProps) {
  return (
    <BaseIcon {...props}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 17v-5" />
      <path d="M12 8h.01" />
    </BaseIcon>
  );
}

function UploadIcon(props: IconProps) {
  return (
    <BaseIcon {...props}>
      <path d="M12 16V4" />
      <path d="m7 9 5-5 5 5" />
      <path d="M20 16v3a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1v-3" />
    </BaseIcon>
  );
}

function PlayIcon(props: IconProps) {
  return (
    <BaseIcon {...props}>
      <path d="m8 5 11 7-11 7Z" />
    </BaseIcon>
  );
}

function SpinnerIcon(props: IconProps) {
  return (
    <BaseIcon className="spinner-icon" {...props}>
      <path d="M21 12a9 9 0 0 1-9 9" />
      <path d="M3 12a9 9 0 0 1 9-9" />
    </BaseIcon>
  );
}

function ActivityIcon(props: IconProps) {
  return (
    <BaseIcon {...props}>
      <path d="M4 13h4l2-7 4 14 2-7h4" />
    </BaseIcon>
  );
}

function FilmIcon(props: IconProps) {
  return (
    <BaseIcon {...props}>
      <rect x="4" y="4" width="16" height="16" rx="2" />
      <path d="M8 4v16" />
      <path d="M16 4v16" />
      <path d="M4 8h4" />
      <path d="M4 16h4" />
      <path d="M16 8h4" />
      <path d="M16 16h4" />
    </BaseIcon>
  );
}

function UserIcon(props: IconProps) {
  return (
    <BaseIcon {...props}>
      <circle cx="12" cy="8" r="4" />
      <path d="M5 20a7 7 0 0 1 14 0" />
    </BaseIcon>
  );
}

function FlagIcon(props: IconProps) {
  return (
    <BaseIcon {...props}>
      <path d="M5 21V4" />
      <path d="M5 5h12l-2 5 2 5H5" />
    </BaseIcon>
  );
}

function GaugeIcon(props: IconProps) {
  return (
    <BaseIcon {...props}>
      <path d="M5 19a9 9 0 1 1 14 0" />
      <path d="m12 14 4-5" />
      <path d="M8 19h8" />
    </BaseIcon>
  );
}

function VideoIcon(props: IconProps) {
  return (
    <BaseIcon {...props}>
      <rect x="3" y="6" width="13" height="12" rx="2" />
      <path d="m16 10 5-3v10l-5-3Z" />
    </BaseIcon>
  );
}

function CheckIcon(props: IconProps) {
  return (
    <BaseIcon {...props}>
      <path d="m5 12 4 4L19 6" />
    </BaseIcon>
  );
}

function TargetIcon(props: IconProps) {
  return (
    <BaseIcon {...props}>
      <circle cx="12" cy="12" r="8" />
      <circle cx="12" cy="12" r="3" />
      <path d="M12 2v3" />
      <path d="M12 19v3" />
      <path d="M2 12h3" />
      <path d="M19 12h3" />
    </BaseIcon>
  );
}

function ShieldIcon(props: IconProps) {
  return (
    <BaseIcon {...props}>
      <path d="M12 3 20 6v6c0 5-3.4 8-8 9-4.6-1-8-4-8-9V6Z" />
    </BaseIcon>
  );
}

function ArrowRightIcon(props: IconProps) {
  return (
    <BaseIcon {...props}>
      <path d="M5 12h14" />
      <path d="m13 6 6 6-6 6" />
    </BaseIcon>
  );
}
