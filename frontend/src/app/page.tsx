"use client";

import type {
  ChangeEvent,
  DragEvent,
  KeyboardEvent,
  ReactNode,
  SVGProps
} from "react";
import Image from "next/image";
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
import {
  SAMPLE_VIDEOS,
  sampleUnavailableMessage
} from "@/lib/sampleVideos";
import type { SampleVideo } from "@/lib/sampleVideos";

const FALLBACK_ANALYSIS_ERROR =
  "Upload an MP4 file or select a sample video before running analysis.";

const PROCESSING_STAGES = [
  "Uploading video...",
  "Running person detection...",
  "Tracking subjects...",
  "Analyzing motion events...",
  "Preparing annotated output..."
] as const;

const MAX_VISIBLE_EVENTS = 12;

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
  pathStability?: number;
  eventCount: number;
  motionSummary: string;
  riskTone: SeverityTone;
  points: TrackPoint[];
};

type SeverityTone = "normal" | "review" | "high" | "unknown";

type IconProps = SVGProps<SVGSVGElement>;

export default function StabilityNetPage() {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [selectedSampleId, setSelectedSampleId] = useState<string | null>(
    SAMPLE_VIDEOS[0].id
  );
  const [videoFile, setVideoFile] = useState<File | null>(null);
  const [analysis, setAnalysis] = useState<AnalysisRecord | null>(null);
  const [health, setHealth] = useState<HealthState>({
    state: "checking",
    label: "Checking"
  });
  const [unavailableSampleIds, setUnavailableSampleIds] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [processingStageIndex, setProcessingStageIndex] = useState(0);
  const [selectedTrackId, setSelectedTrackId] = useState<number | null>(null);
  const [selectedEventKey, setSelectedEventKey] = useState<string | null>(null);

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

  useEffect(() => {
    if (!isSubmitting) {
      return;
    }

    const intervalId = window.setInterval(() => {
      setProcessingStageIndex((currentIndex) =>
        Math.min(currentIndex + 1, PROCESSING_STAGES.length - 1)
      );
    }, 1800);

    return () => window.clearInterval(intervalId);
  }, [isSubmitting]);

  const selectedSample = useMemo(
    () =>
      SAMPLE_VIDEOS.find((sample) => sample.id === selectedSampleId) ?? null,
    [selectedSampleId]
  );
  const tracks = useMemo(() => analysisTracks(analysis), [analysis]);
  const events = useMemo(() => analysisEvents(analysis), [analysis]);
  const visibleEvents = useMemo(() => visibleTimelineEvents(events), [events]);
  const trackRows = useMemo(
    () => buildTrackRows(tracks, analysis?.result?.frames, events),
    [analysis?.result?.frames, events, tracks]
  );
  const annotatedVideoUrl = analysis ? analysisVideoUrl(analysis) : null;
  const hasAnalysisResult = analysis !== null;
  const videoDurationSeconds = readNumber(analysis?.result?.video, "duration_s");
  const framesProcessed = numberOrZero(
    analysis?.frames_processed ??
      readNumber(analysis?.summary, "frames_processed") ??
      analysis?.result?.frames_processed
  );
  const trackCount = numberOrZero(
    analysis?.qualified_subject_count ??
      readNumber(analysis?.summary, "qualified_subject_count") ??
      readNumber(analysis?.result, "qualified_subject_count") ??
      analysis?.tracks_count ??
      readNumber(analysis?.summary, "tracks_count") ??
      readNumber(analysis?.summary, "track_count") ??
      trackRows.length
  );
  const eventCount = numberOrZero(
    analysis?.mobility_event_count ??
      readNumber(analysis?.summary, "mobility_event_count") ??
      readNumber(analysis?.result, "mobility_event_count") ??
      analysis?.events_count ??
      readNumber(analysis?.summary, "events_count") ??
      readNumber(analysis?.summary, "event_count") ??
      events.length
  );
  const selectedTrack = useMemo(
    () => trackRows.find((track) => track.id === selectedTrackId) ?? null,
    [selectedTrackId, trackRows]
  );
  const selectedEvent = useMemo(
    () =>
      events.find((event, index) => eventCardKey(event, index) === selectedEventKey) ??
      null,
    [events, selectedEventKey]
  );
  const summaryMetrics = useMemo(
    () => buildSummaryMetrics(analysis),
    [analysis]
  );
  const diagnosticMetrics = useMemo(
    () => buildDiagnosticMetrics(analysis),
    [analysis]
  );

  function seekToTimestamp(timestamp: number | undefined): void {
    if (timestamp === undefined) {
      return;
    }
    const player = videoRef.current;
    if (!player) {
      return;
    }
    player.currentTime = Math.max(0, timestamp);
    void player.play().catch(() => {
      // Keep seeking behavior graceful when autoplay is blocked.
    });
  }

  function handleTrackSelect(trackId: number): void {
    setSelectedTrackId(trackId);
  }

  function handleEventSelect(event: BehaviorEvent, index: number): void {
    setSelectedEventKey(eventCardKey(event, index));
    const trackId = readNumber(event, "track_id");
    if (trackId !== undefined) {
      setSelectedTrackId(trackId);
    }
    seekToTimestamp(readNumber(event, "timestamp_s"));
  }

  async function handleAnalyze() {
    if (!videoFile && !selectedSample) {
      setError(FALLBACK_ANALYSIS_ERROR);
      return;
    }

    setError(null);
    setProcessingStageIndex(videoFile ? 0 : 1);
    setIsSubmitting(true);

    try {
      const record = videoFile
        ? await uploadAnalysis(videoFile)
        : await createAnalysis({ video_path: selectedSample!.videoPath });
      setSelectedTrackId(null);
      setSelectedEventKey(null);
      setAnalysis(record);
      if (selectedSample) {
        setUnavailableSampleIds((sampleIds) =>
          sampleIds.filter((sampleId) => sampleId !== selectedSample.id)
        );
      }
    } catch (caughtError: unknown) {
      const message = errorMessage(caughtError) || FALLBACK_ANALYSIS_ERROR;
      if (!videoFile && selectedSample && isMissingSampleError(message)) {
        setUnavailableSampleIds((sampleIds) =>
          sampleIds.includes(selectedSample.id)
            ? sampleIds
            : [...sampleIds, selectedSample.id]
        );
        setError(sampleUnavailableMessage(selectedSample));
      } else {
        setError(message);
      }
    } finally {
      setIsSubmitting(false);
      setProcessingStageIndex(0);
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
    setSelectedTrackId(null);
    setSelectedEventKey(null);
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
    setSelectedTrackId(null);
    setSelectedEventKey(null);
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

          <div className="input-grid" id="analysis">
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
              unavailableSampleIds={unavailableSampleIds}
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

          {isSubmitting ? (
            <ProcessingPanel activeStageIndex={processingStageIndex} />
          ) : null}

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
            trackCount={trackCount}
            eventCount={eventCount}
            summaryMetrics={summaryMetrics}
            diagnosticMetrics={diagnosticMetrics}
          />

          <div className={`results-grid${hasAnalysisResult ? " results-grid--analyzed" : ""}`}>
            <AnnotatedVideo
              events={visibleEvents}
              hasResult={hasAnalysisResult}
              selectedEventKey={selectedEventKey}
              selectedTrack={selectedTrack}
              selectedEvent={selectedEvent}
              onSelectEvent={handleEventSelect}
              videoDurationSeconds={videoDurationSeconds}
              videoRef={videoRef}
              videoUrl={annotatedVideoUrl}
            />
            <div className="results-side">
              <TracksTable
                onSelectTrack={handleTrackSelect}
                selectedTrackId={selectedTrackId}
                tracks={trackRows}
              />
              <EventsTable
                events={visibleEvents}
                totalEventsCount={events.length}
                onSelectEvent={handleEventSelect}
                selectedEventKey={selectedEventKey}
              />
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
          <p>Uploaded-video mobility review analysis</p>
        </div>
      </div>

      <nav className="sidebar-nav" aria-label="Primary">
        <SidebarLink active href="#analysis" icon={<ChartIcon />} label="Analysis" />
        <SidebarLink href="#samples" icon={<FolderIcon />} label="Samples" />
        <SidebarLink href="#results" icon={<PanelIcon />} label="Results" />
        <SidebarLink href="#pipeline" icon={<InfoIcon />} label="About" />
      </nav>

      <div className="prototype-card">
        <strong>Research Prototype</strong>
        <p>
          This system analyzes uploaded videos to extract mobility patterns and
          surface motion events that require review.
        </p>
        <span>Not a medical device.</span>
      </div>
    </aside>
  );
}

function SidebarLink({
  active = false,
  href,
  icon,
  label
}: {
  active?: boolean;
  href: string;
  icon: ReactNode;
  label: string;
}) {
  return (
    <a className={`sidebar-link${active ? " sidebar-link--active" : ""}`} href={href}>
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
          Uploaded-video mobility review analysis
        </p>
        <p className="hero-intro">
          Upload a video or try a sample to analyze human motion, track
          individuals, and flag motion patterns for conservative review.
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
  unavailableSampleIds,
  onSelect
}: {
  selectedSampleId: string | null;
  unavailableSampleIds: string[];
  onSelect: (sampleId: string) => void;
}) {
  return (
    <section className="panel samples-panel" id="samples" aria-labelledby="samples-title">
      <h2 id="samples-title">2. Or Try a Sample Video</h2>
      <div className="sample-grid">
        {SAMPLE_VIDEOS.map((sample) => {
          const isUnavailable = unavailableSampleIds.includes(sample.id);

          return (
            <button
              key={sample.id}
              className={`sample-card${
                selectedSampleId === sample.id ? " sample-card--selected" : ""
              }${isUnavailable ? " sample-card--unavailable" : ""}`}
              type="button"
              onClick={() => onSelect(sample.id)}
            >
              <SampleThumbnail
                sample={sample}
                selected={selectedSampleId === sample.id}
                unavailable={isUnavailable}
              />
              <span>{sample.title}</span>
              {isUnavailable ? <small>Sample unavailable</small> : null}
            </button>
          );
        })}
      </div>
      <p className="sample-note">
        <InfoIcon />
        <span>Add MP4s locally with the documented sample filenames.</span>
      </p>
    </section>
  );
}

function SampleThumbnail({
  sample,
  selected,
  unavailable
}: {
  sample: SampleVideo;
  selected: boolean;
  unavailable: boolean;
}) {
  const [imageFailed, setImageFailed] = useState(false);
  const showImage = Boolean(sample.thumbnailSrc) && !imageFailed;

  return (
    <div className={`sample-thumb sample-thumb--${sample.variant}`}>
      {showImage ? (
        <Image
          src={sample.thumbnailSrc}
          alt={`${sample.title} sample thumbnail`}
          fill
          onError={() => setImageFailed(true)}
          sizes="(max-width: 640px) 100vw, (max-width: 900px) 45vw, 14vw"
        />
      ) : (
        <ThumbnailFallback variant={sample.variant} />
      )}
      <span className="duration-pill">{sample.duration}</span>
      {unavailable ? <span className="unavailable-pill">Unavailable</span> : null}
      {selected ? (
        <span className="selected-check" aria-label="Selected">
          <CheckIcon />
        </span>
      ) : null}
    </div>
  );
}

function ThumbnailFallback({ variant }: { variant: SampleVideo["variant"] }) {
  return (
    <div className={`thumbnail-fallback thumbnail-fallback--${variant}`}>
      <VideoIcon />
      <span>Sample MP4</span>
    </div>
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

function ProcessingPanel({ activeStageIndex }: { activeStageIndex: number }) {
  return (
    <section className="processing-panel" aria-live="polite" aria-label="Analysis status">
      <div>
        <SpinnerIcon />
        <strong>{PROCESSING_STAGES[activeStageIndex]}</strong>
      </div>
      <ol>
        {PROCESSING_STAGES.map((stage, index) => (
          <li
            className={index <= activeStageIndex ? "processing-stage--active" : ""}
            key={stage}
          >
            {stage}
          </li>
        ))}
      </ol>
    </section>
  );
}

function SummaryCards({
  status,
  framesProcessed,
  trackCount,
  eventCount,
  summaryMetrics,
  diagnosticMetrics
}: {
  status: string;
  framesProcessed: number;
  trackCount: number;
  eventCount: number;
  summaryMetrics: MetricItem[];
  diagnosticMetrics: MetricItem[];
}) {
  return (
    <section className="panel summary-panel" id="results" aria-labelledby="summary-title">
      <h2 id="summary-title">3. Analysis Summary</h2>
      <div className="metric-grid metric-grid--primary">
        <MetricCard
          className="metric-card--status"
          icon={<ActivityIcon />}
          label="Status"
          value={status}
        />
        <MetricCard
          icon={<FilmIcon />}
          label="Frames Processed"
          value={framesProcessed.toLocaleString()}
        />
        <MetricCard
          icon={<UserIcon />}
          label="Tracked Subjects"
          value={trackCount.toLocaleString()}
        />
        <MetricCard
          icon={<FlagIcon />}
          label="Mobility Events"
          value={eventCount.toLocaleString()}
        />
        {summaryMetrics.map((metric) => (
          <MetricCard
            key={metric.label}
            icon={metric.icon}
            label={metric.label}
            value={metric.value}
          />
        ))}
      </div>
      <DiagnosticsSection metrics={diagnosticMetrics} />
    </section>
  );
}

function MetricCard({
  className,
  icon,
  label,
  value
}: {
  className?: string;
  icon: ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className={`metric-card${className ? ` ${className}` : ""}`}>
      <span className="metric-icon">{icon}</span>
      <div className="metric-copy">
        <span className="metric-label">{label}</span>
        <strong className="metric-value">{value}</strong>
      </div>
    </div>
  );
}

function DiagnosticsSection({ metrics }: { metrics: MetricItem[] }) {
  if (metrics.length === 0) {
    return null;
  }

  return (
    <details className="diagnostics-panel">
      <summary>Diagnostics</summary>
      <dl className="diagnostics-grid">
        {metrics.map((metric) => (
          <div key={metric.label} className="diagnostic-row">
            <dt>{metric.label}</dt>
            <dd>{metric.value}</dd>
          </div>
        ))}
      </dl>
    </details>
  );
}

function AnnotatedVideo({
  events,
  hasResult,
  onSelectEvent,
  selectedEvent,
  selectedEventKey,
  selectedTrack,
  videoDurationSeconds,
  videoRef,
  videoUrl
}: {
  events: BehaviorEvent[];
  hasResult: boolean;
  onSelectEvent: (event: BehaviorEvent, index: number) => void;
  selectedEvent: BehaviorEvent | null;
  selectedEventKey: string | null;
  selectedTrack: TrackRow | null;
  videoDurationSeconds?: number;
  videoRef: React.RefObject<HTMLVideoElement | null>;
  videoUrl: string | null;
}) {
  const [failedVideoUrl, setFailedVideoUrl] = useState<string | null>(null);
  const isDevelopment = process.env.NODE_ENV !== "production";
  const videoLoadError = videoUrl !== null && failedVideoUrl === videoUrl;

  function handleVideoError() {
    if (isDevelopment && videoUrl) {
      console.error("Annotated video failed to load:", videoUrl);
    }
    setFailedVideoUrl(videoUrl);
  }

  return (
    <section
      className={`panel annotated-panel${hasResult ? " annotated-panel--result" : ""}`}
      aria-labelledby="video-title"
    >
      <div className="artifact-heading">
        <h2 id="video-title">4. Annotated Output</h2>
        {hasResult ? (
          <span>
            {selectedTrack
              ? `Subject ${selectedTrack.id} selected`
              : selectedEvent
                ? "Event selected"
                : "Primary Analysis View"}
          </span>
        ) : null}
      </div>
      <div className="video-frame">
        {videoUrl && !videoLoadError ? (
          <video
            className="annotated-video"
            ref={videoRef}
            src={videoUrl}
            controls
            onError={handleVideoError}
            preload="metadata"
          />
        ) : videoUrl ? (
          <div className="video-empty video-empty--error" role="alert">
            <VideoIcon />
            <strong>Annotated video failed to load</strong>
            <span>
              The backend returned a video URL, but the browser could not play
              it.
            </span>
            {isDevelopment ? (
              <a className="video-debug-link" href={videoUrl} target="_blank" rel="noreferrer">
                Open video
              </a>
            ) : null}
          </div>
        ) : (
          <div className="video-empty">
            <VideoIcon />
            <strong>No video to display</strong>
            <span>Run an analysis to view the annotated output.</span>
          </div>
        )}
      </div>
      <EventMarkers
        events={events}
        onSelectEvent={onSelectEvent}
        selectedEventKey={selectedEventKey}
        videoDurationSeconds={videoDurationSeconds}
      />
      {selectedTrack || selectedEvent ? (
        <div className="video-selection-hint" aria-live="polite">
          {selectedTrack
            ? `Selected Subject ${selectedTrack.id} • Motion: ${selectedTrack.motionSummary} • Status: ${severityLabel(selectedTrack.riskTone)}`
            : `Selected event at ${formatOptionalDecimal(readNumber(selectedEvent, "timestamp_s"))}s`}
        </div>
      ) : null}
    </section>
  );
}

function EventMarkers({
  events,
  onSelectEvent,
  selectedEventKey,
  videoDurationSeconds
}: {
  events: BehaviorEvent[];
  onSelectEvent: (event: BehaviorEvent, index: number) => void;
  selectedEventKey: string | null;
  videoDurationSeconds?: number;
}) {
  const timedEvents = events
    .map((event, index) => ({
      event,
      index,
      key: eventCardKey(event, index),
      timestamp: readNumber(event, "timestamp_s")
    }))
    .filter(
      (entry): entry is {
        event: BehaviorEvent;
        index: number;
        key: string;
        timestamp: number;
      } =>
        entry.timestamp !== undefined
    );

  if (timedEvents.length === 0) {
    return null;
  }

  const maxEventTime = Math.max(...timedEvents.map((entry) => entry.timestamp));
  const duration = Math.max(videoDurationSeconds ?? maxEventTime, maxEventTime, 1);

  return (
    <div className="event-marker-strip" aria-label="Video event markers">
      <div className="event-marker-track">
        {timedEvents.map(({ event, index, key, timestamp }) => {
          const severityTone = severityClass(readString(event, "severity") ?? "low");
          const left = Math.min(100, Math.max(0, (timestamp / duration) * 100));
          const isSelected = selectedEventKey === key;

          return (
            <button
              aria-label={`Seek to ${formatOptionalDecimal(timestamp)} seconds`}
              className={`event-marker event-marker--${severityTone}${
                isSelected ? " event-marker--selected" : ""
              }`}
              key={key}
              onClick={() => onSelectEvent(event, index)}
              type="button"
              style={{ left: `${left}%` }}
              title={`${formatOptionalDecimal(timestamp)}s: ${humanizeEventType(
                readString(event, "event_type") ?? "event"
              )}`}
            />
          );
        })}
      </div>
      <span>Mobility event markers</span>
    </div>
  );
}

function TracksTable({
  tracks,
  selectedTrackId,
  onSelectTrack
}: {
  tracks: TrackRow[];
  selectedTrackId: number | null;
  onSelectTrack: (trackId: number) => void;
}) {
  return (
    <section className="panel table-panel" aria-labelledby="tracks-title">
      <div className="table-heading">
        <h2 id="tracks-title">Tracked Subjects</h2>
        <span>Total: {tracks.length.toLocaleString()}</span>
      </div>
      {tracks.length > 0 ? (
        <div className="subject-list">
          {tracks.map((track, index) => {
            const isSelected = selectedTrackId === track.id;
            return (
              <article
                aria-pressed={isSelected}
                className={`subject-row subject-row--interactive${
                  isSelected ? " subject-row--selected" : ""
                }`}
                key={track.id}
                onClick={() => onSelectTrack(track.id)}
                onKeyDown={(event) => activateOnKey(event, () => onSelectTrack(track.id))}
                role="button"
                tabIndex={0}
              >
              <div className="subject-row-main">
                <span className={`track-id track-id--${index % 4}`}>{track.id}</span>
                <div>
                  <strong>Subject {track.id}</strong>
                  <span>
                    {track.frames.toLocaleString()} frames • {track.motionSummary}
                  </span>
                </div>
              </div>
              {isSelected ? (
                <dl className="subject-stats">
                  <div>
                    <dt>Duration</dt>
                    <dd>{formatOptionalDecimal(track.durationSeconds)}s</dd>
                  </div>
                  <div>
                    <dt>Confidence</dt>
                    <dd>{formatOptionalDecimal(track.averageConfidence)}</dd>
                  </div>
                  <div>
                    <dt>Frame Count</dt>
                    <dd>{track.frames.toLocaleString()}</dd>
                  </div>
                  <div>
                    <dt>Events</dt>
                    <dd>{track.eventCount.toLocaleString()}</dd>
                  </div>
                  <div>
                    <dt>Motion Summary</dt>
                    <dd>{track.motionSummary}</dd>
                  </div>
                  <div>
                    <dt>Status</dt>
                    <dd>{severityLabel(track.riskTone)}</dd>
                  </div>
                </dl>
              ) : null}
              <TrajectoryCell track={track} tone={index % 4} />
              </article>
            );
          })}
        </div>
      ) : (
        <EmptyState
          title="No tracked subjects available"
          body="Run an analysis to see tracked subjects."
        />
      )}
    </section>
  );
}

function EventsTable({
  events,
  totalEventsCount,
  selectedEventKey,
  onSelectEvent
}: {
  events: BehaviorEvent[];
  totalEventsCount: number;
  selectedEventKey: string | null;
  onSelectEvent: (event: BehaviorEvent, index: number) => void;
}) {
  return (
    <section className="panel table-panel" aria-labelledby="events-title">
      <div className="table-heading">
        <h2 id="events-title">Events Timeline</h2>
        <span>
          {events.length < totalEventsCount
            ? `Showing ${events.length.toLocaleString()} of ${totalEventsCount.toLocaleString()}`
            : `Total: ${events.length.toLocaleString()}`}
        </span>
      </div>
      {events.length > 0 ? (
        <div className="event-list">
          {events.map((event, index) => {
            const timestamp = formatOptionalDecimal(readNumber(event, "timestamp_s"));
            const trackId = readNumber(event, "track_id");
            const eventType = humanizeEventType(
              readString(event, "event_type") ?? "event"
            );
            const description =
              readString(event, "reason") ??
              readString(event, "description") ??
              "Mobility pattern observed";
            const key = eventCardKey(event, index);
            const isSelected = selectedEventKey === key;

            return (
              <article
                aria-pressed={isSelected}
                className={`event-row event-row--interactive${
                  isSelected ? " event-row--selected" : ""
                }`}
                key={key}
                onClick={() => onSelectEvent(event, index)}
                onKeyDown={(keyboardEvent) =>
                  activateOnKey(keyboardEvent, () => onSelectEvent(event, index))
                }
                role="button"
                tabIndex={0}
              >
                <div className="event-row-top">
                  <strong>{eventType}</strong>
                  <SeverityBadge severity={readString(event, "severity") ?? "low"} />
                </div>
                <p>{description}</p>
                <span>
                  {timestamp}s • {trackId !== undefined ? `Track ${trackId}` : "Track unlinked"}
                </span>
                {isSelected ? (
                  <div className="event-expanded">
                    <span>Seeked to {timestamp}s</span>
                    <span>
                      {trackId !== undefined
                        ? `Linked subject: ${trackId}`
                        : "No linked subject for this event"}
                    </span>
                  </div>
                ) : null}
              </article>
            );
          })}
        </div>
      ) : (
        <EmptyState
          title="No high-confidence events"
          body="No strong mobility events were detected in this analysis."
        />
      )}
    </section>
  );
}

function SeverityBadge({ severity }: { severity: string }) {
  const severityTone = severityClass(severity);
  return (
    <span className={`severity severity--${severityTone}`}>
      {severityLabel(severityTone)}
    </span>
  );
}

function TrajectoryCell({ track, tone }: { track: TrackRow; tone: number }) {
  return (
    <div className="trajectory-cell">
      <Trajectory points={track.points} tone={tone} />
      {track.pathStability !== undefined ? (
        <small>Path Stability {formatOptionalDecimal(track.pathStability)}</small>
      ) : null}
    </div>
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

type MetricItem = {
  icon?: ReactNode;
  label: string;
  value: string;
};

function analysisTracks(analysis: AnalysisRecord | null): TrackSummary[] {
  return safeArray(analysis?.tracks).length > 0
    ? safeArray(analysis?.tracks)
    : safeArray(analysis?.result?.tracks);
}

function analysisEvents(analysis: AnalysisRecord | null): BehaviorEvent[] {
  return safeArray(analysis?.events).length > 0
    ? safeArray(analysis?.events)
    : safeArray(analysis?.result?.events);
}

function visibleTimelineEvents(events: BehaviorEvent[]): BehaviorEvent[] {
  const prioritized = [...events].sort((left, right) => {
    const leftPriority = readNumber(left, "display_priority") ?? severityPriority(left);
    const rightPriority = readNumber(right, "display_priority") ?? severityPriority(right);
    if (leftPriority !== rightPriority) {
      return leftPriority - rightPriority;
    }
    return (readNumber(left, "timestamp_s") ?? 0) - (readNumber(right, "timestamp_s") ?? 0);
  });

  return prioritized
    .slice(0, MAX_VISIBLE_EVENTS)
    .sort(
      (left, right) =>
        (readNumber(left, "timestamp_s") ?? 0) - (readNumber(right, "timestamp_s") ?? 0)
    );
}

function severityPriority(event: BehaviorEvent): number {
  const tone = severityClass(readString(event, "severity") ?? "normal");
  if (tone === "high") {
    return 10;
  }
  if (tone === "review") {
    return 35;
  }
  if (tone === "unknown") {
    return 65;
  }
  return 85;
}

function buildSummaryMetrics(analysis: AnalysisRecord | null): MetricItem[] {
  if (!analysis) {
    return [];
  }

  return [
    {
      icon: <ShieldIcon />,
      label: "Scene Reliability",
      value:
        readAnalysisText(analysis, ["scene_reliability"]) ??
        "Unavailable"
    },
    {
      icon: <GaugeIcon />,
      label: "End-to-End FPS",
      value: formatOptionalDecimal(
        readAnalysisMetric(analysis, [
          "end_to_end_processing_fps",
          "end_to_end_throughput_fps",
          "processing_fps"
        ])
      )
    },
    {
      icon: <GaugeIcon />,
      label: "CPU FPS",
      value: formatOptionalDecimal(
        readAnalysisMetric(analysis, [
          "cpu_analysis_throughput_fps",
          "analysis_throughput_fps"
        ])
      )
    }
  ];
}

function buildDiagnosticMetrics(analysis: AnalysisRecord | null): MetricItem[] {
  if (!analysis) {
    return [];
  }

  const metrics = [
    {
      label: "Analyzed Frames",
      value: readAnalysisMetric(analysis, ["frames_analyzed", "analyzed_frames_count"])
    },
    {
      label: "Source Video FPS",
      value: readAnalysisMetric(analysis, ["source_video_fps", "source_fps", "fps"])
    },
    {
      label: "Effective Analysis FPS",
      value: readAnalysisMetric(analysis, [
        "effective_analysis_fps",
        "sampled_analysis_fps"
      ])
    },
    {
      label: "Raw Tracks",
      value: readAnalysisMetric(analysis, ["raw_track_count"])
    },
    {
      label: "Decode Time (ms)",
      value: readAnalysisMetric(analysis, ["decode_time_ms"])
    },
    {
      label: "Inference Time (ms)",
      value: readAnalysisMetric(analysis, ["inference_time_ms"])
    },
    {
      label: "Tracking Time (ms)",
      value: readAnalysisMetric(analysis, ["tracking_time_ms"])
    },
    {
      label: "Event Time (ms)",
      value: readAnalysisMetric(analysis, ["event_time_ms"])
    },
    {
      label: "Annotation Time (ms)",
      value: readAnalysisMetric(analysis, ["annotation_time_ms"])
    },
    {
      label: "Encode Time (ms)",
      value: readAnalysisMetric(analysis, ["encode_time_ms"])
    },
    {
      label: "Total Time (ms)",
      value: readAnalysisMetric(analysis, ["total_time_ms"])
    }
  ];

  return metrics
    .filter((metric) => metric.value !== undefined)
    .map((metric) => ({
      label: metric.label,
      value:
        typeof metric.value === "number"
          ? formatOptionalDecimal(metric.value)
          : String(metric.value)
    }));
}

function readAnalysisText(
  analysis: AnalysisRecord,
  keys: string[]
): string | undefined {
  const sources = [
    analysis.summary,
    analysis.result,
    readRecord(analysis.summary, "metrics"),
    readRecord(analysis.result, "metrics"),
    readRecord(analysis.result, "summary")
  ];

  for (const source of sources) {
    for (const key of keys) {
      const value = readString(source, key);
      if (value !== undefined) {
        return value;
      }
    }
  }

  return undefined;
}

function readAnalysisMetric(
  analysis: AnalysisRecord,
  keys: string[]
): number | undefined {
  const sources = [
    analysis.summary,
    analysis.result,
    readRecord(analysis.summary, "metrics"),
    readRecord(analysis.result, "metrics"),
    readRecord(analysis.result, "summary")
  ];

  for (const source of sources) {
    for (const key of keys) {
      const value = readNumber(source, key);
      if (value !== undefined) {
        return value;
      }
    }
  }

  return undefined;
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
      title: "Mobility Review Events",
      subtitle: "Flag review events",
      icon: <ShieldIcon />
    }
  ];

  return (
    <section className="panel pipeline-panel" id="pipeline" aria-labelledby="pipeline-title">
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
      <div className="technical-metadata">
        <span>Uploaded-video inference • YOLO26n • OpenCV • SORT tracking</span>
        <span>Research prototype. Not a medical device.</span>
      </div>
    </section>
  );
}

function buildTrackRows(
  tracks: TrackSummary[],
  frames: unknown[] | undefined,
  events: BehaviorEvent[]
): TrackRow[] {
  const observationsByTrack = observationsFromFrames(frames);
  const eventCounts = eventCountsByTrack(events);
  const riskByTrack = highestRiskByTrack(events);
  const hasQualification = tracks.some((track) => typeof track.qualified === "boolean");
  const displayTracks = hasQualification
    ? tracks.filter((track) => track.qualified === true)
    : tracks;
  const ids = new Set<number>();

  for (const track of displayTracks) {
    if (Number.isFinite(track.track_id)) {
      ids.add(track.track_id);
    }
  }
  if (!hasQualification) {
    for (const id of observationsByTrack.keys()) {
      ids.add(id);
    }
  }

  return Array.from(ids)
    .sort((left, right) => left - right)
    .map((id) => {
      const track = displayTracks.find((candidate) => candidate.track_id === id);
      const featureRecord = isRecord(track?.features) ? track?.features : undefined;
      const explicitTrajectory = trajectoryPointsFromTrack(track, featureRecord);
      const observedPoints = observationsByTrack.get(id) ?? [];
      const points = explicitTrajectory.length > 0 ? explicitTrajectory : observedPoints;
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
        averageConfidence:
          readNumber(track, "average_confidence") ??
          readNumber(track, "avg_confidence") ??
          averageConfidence(points),
        pathStability:
          readNumber(track, "path_stability") ??
          readNumber(track, "mobility_stability") ??
          readNumber(featureRecord, "path_stability") ??
          readNumber(featureRecord, "mobility_stability"),
        eventCount: eventCounts.get(id) ?? 0,
        motionSummary: summarizeTrackMotion(track, featureRecord, points),
        riskTone:
          normalizeTone(readString(track, "risk_level")) ??
          riskByTrack.get(id) ??
          "normal",
        points
      };
    });
}

function normalizeTone(value: string | undefined): SeverityTone | undefined {
  if (!value) {
    return undefined;
  }
  const normalized = value.toLowerCase();
  if (normalized === "normal" || normalized === "stable" || normalized === "low") {
    return "normal";
  }
  if (normalized === "review" || normalized === "review_needed" || normalized === "medium") {
    return "review";
  }
  if (normalized === "unknown" || normalized === "insufficient_evidence") {
    return "unknown";
  }
  if (normalized === "high") {
    return "high";
  }
  return undefined;
}

function eventCountsByTrack(events: BehaviorEvent[]): Map<number, number> {
  const counts = new Map<number, number>();
  for (const event of events) {
    const trackId = readNumber(event, "track_id");
    if (trackId === undefined) {
      continue;
    }
    counts.set(trackId, (counts.get(trackId) ?? 0) + 1);
  }
  return counts;
}

function highestRiskByTrack(events: BehaviorEvent[]): Map<number, SeverityTone> {
  const risk = new Map<number, SeverityTone>();
  for (const event of events) {
    const trackId = readNumber(event, "track_id");
    if (trackId === undefined) {
      continue;
    }
    const tone = severityClass(readString(event, "severity") ?? "low");
    const existing = risk.get(trackId);
    if (!existing || riskRank(tone) > riskRank(existing)) {
      risk.set(trackId, tone);
    }
  }
  return risk;
}

function summarizeTrackMotion(
  track: TrackSummary | undefined,
  featureRecord: Record<string, unknown> | undefined,
  points: TrackPoint[]
): string {
  const explicitState =
    readString(track, "motion_state") ??
    readString(track, "status");
  if (explicitState) {
    return explicitState.toLowerCase();
  }
  const variance = readNumber(featureRecord, "position_variance_px2");
  if (variance !== undefined && variance >= 1125) {
    return "review";
  }

  const dwellTime = readNumber(featureRecord, "dwell_time_s");
  if (dwellTime !== undefined && dwellTime >= 8) {
    return "prolonged stop";
  }

  const recentSpeed = readNumber(featureRecord, "recent_speed_px_s");
  const meanSpeed = readNumber(featureRecord, "mean_speed_px_s");
  const speed = recentSpeed ?? meanSpeed;
  if (speed !== undefined && speed <= 18) {
    return "slow walking";
  }

  if (points.length < 2) {
    return "acquiring";
  }
  return "walking";
}

function trajectoryPointsFromTrack(
  track: TrackSummary | undefined,
  featureRecord: Record<string, unknown> | undefined
): TrackPoint[] {
  const candidates = [
    track?.trajectory,
    track?.motion_trail,
    track?.motionTrail,
    track?.path,
    track?.points,
    featureRecord?.trajectory,
    featureRecord?.motion_trail,
    featureRecord?.path
  ];

  for (const candidate of candidates) {
    const points = parseTrajectoryPoints(candidate);
    if (points.length > 0) {
      return points;
    }
  }

  return [];
}

function parseTrajectoryPoints(value: unknown): TrackPoint[] {
  if (isRecord(value)) {
    return parseTrajectoryPoints(value.points ?? value.centers ?? value.samples);
  }
  if (!Array.isArray(value)) {
    return [];
  }

  return value
    .map((point) => parseTrajectoryPoint(point))
    .filter((point): point is TrackPoint => point !== undefined);
}

function parseTrajectoryPoint(value: unknown): TrackPoint | undefined {
  if (Array.isArray(value) && value.length >= 2) {
    const [x, y, timestamp] = value;
    if (isFiniteNumber(x) && isFiniteNumber(y)) {
      return {
        x,
        y,
        timestamp: isFiniteNumber(timestamp) ? timestamp : undefined
      };
    }
  }

  if (!isRecord(value)) {
    return undefined;
  }

  const center = readCenter(value.center) ?? readCenter(value.xy);
  const x = readNumber(value, "x") ?? center?.[0];
  const y = readNumber(value, "y") ?? center?.[1];
  if (x === undefined || y === undefined) {
    return undefined;
  }

  return {
    x,
    y,
    confidence: readNumber(value, "confidence"),
    timestamp:
      readNumber(value, "timestamp_s") ??
      readNumber(value, "timestamp") ??
      readNumber(value, "time_s")
  };
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

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
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

function severityClass(value: string): SeverityTone {
  const normalized = value.toLowerCase();
  if (normalized.includes("high") || normalized.includes("critical")) {
    return "high";
  }
  if (
    normalized.includes("review") ||
    normalized.includes("medium") ||
    normalized.includes("moderate") ||
    normalized.includes("uncertain")
  ) {
    return "review";
  }
  if (
    normalized.includes("unknown") ||
    normalized.includes("insufficient") ||
    normalized.includes("evidence")
  ) {
    return "unknown";
  }
  return "normal";
}

function riskRank(value: SeverityTone): number {
  if (value === "high") {
    return 3;
  }
  if (value === "review") {
    return 2;
  }
  if (value === "unknown") {
    return 1;
  }
  return 0;
}

function severityLabel(value: SeverityTone): string {
  if (value === "review") {
    return "Review";
  }
  if (value === "unknown") {
    return "Unknown";
  }
  return capitalize(value);
}

function activateOnKey(
  event: KeyboardEvent<HTMLElement>,
  action: () => void
): void {
  if (event.key !== "Enter" && event.key !== " ") {
    return;
  }
  event.preventDefault();
  action();
}

function eventCardKey(event: BehaviorEvent, index: number): string {
  return (
    readString(event, "event_id") ??
    `${readNumber(event, "track_id") ?? "na"}-${readString(event, "event_type") ?? "event"}-${index}`
  );
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

function isMissingSampleError(message: string): boolean {
  return message.toLowerCase().includes("video file not found");
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
