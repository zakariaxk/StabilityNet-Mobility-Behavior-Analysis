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
  AnalysisProgress,
  AnalysisRecord,
  BehaviorEvent,
  TrackSummary,
  analysisVideoUrl,
  checkHealth,
  createAnalysis,
  pollAnalysis,
  uploadAnalysis
} from "@/lib/stabilityNetApi";
import {
  SAMPLE_VIDEOS,
  sampleUnavailableMessage
} from "@/lib/sampleVideos";
import type { SampleVideo } from "@/lib/sampleVideos";
import { severityPresentation } from "@/lib/analysisPresentation";

const FALLBACK_ANALYSIS_ERROR =
  "Upload an MP4 file or select a sample video before running analysis.";

/**
 * Labels for the stages the backend actually reports via record.progress.stage.
 * This used to be a five-item list advanced by a 1800ms setInterval with no
 * relationship to the backend at all, so on a slow clip it sat on the last
 * label for minutes.
 */
const STAGE_LABELS: Record<string, string> = {
  queued: "Queued...",
  analyzing: "Running detection and tracking...",
  encoding: "Encoding annotated video...",
  finalizing: "Finalizing analysis...",
  completed: "Complete"
};

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
  points: TrackPoint[];
};

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
  const [progress, setProgress] = useState<AnalysisProgress | null>(null);
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

  const selectedSample = useMemo(
    () =>
      SAMPLE_VIDEOS.find((sample) => sample.id === selectedSampleId) ?? null,
    [selectedSampleId]
  );
  const tracks = useMemo(() => analysisTracks(analysis), [analysis]);
  const events = useMemo(() => analysisEvents(analysis), [analysis]);
  const trackRows = useMemo(
    () => buildTrackRows(tracks, events),
    [events, tracks]
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
    analysis?.tracks_count ??
      readNumber(analysis?.summary, "tracks_count") ??
      readNumber(analysis?.summary, "track_count") ??
      readNumber(analysis?.result, "tracks_count") ??
      readNumber(analysis?.result, "track_count") ??
      analysis?.raw_track_count ??
      readNumber(analysis?.summary, "raw_track_count") ??
      readNumber(analysis?.result, "raw_track_count") ??
      analysis?.qualified_subject_count ??
      readNumber(analysis?.summary, "qualified_subject_count") ??
      readNumber(analysis?.result, "qualified_subject_count") ??
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
  const summaryMetrics = useMemo(
    () => buildSummaryMetrics(analysis),
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
      // Keep selection behavior graceful when autoplay is blocked.
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
    setProgress({ stage: "queued", percent: 0 });
    setIsSubmitting(true);

    try {
      // Submission returns 202 with a queued record; the result arrives by
      // polling. Progress numbers below are the backend's, not a timer's.
      const queued = videoFile
        ? await uploadAnalysis(videoFile)
        : await createAnalysis({ video_path: selectedSample!.videoPath });

      const record = await pollAnalysis(queued.analysis_id, (partial) => {
        if (partial.progress) setProgress(partial.progress);
      });
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
      setProgress(null);
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

          {isSubmitting ? <ProcessingPanel progress={progress} /> : null}

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
          />

          <div className={`results-grid${hasAnalysisResult ? " results-grid--analyzed" : ""}`}>
            <AnnotatedVideo
              events={events}
              hasResult={hasAnalysisResult}
              onSelectEvent={handleEventSelect}
              selectedEventKey={selectedEventKey}
              selectedTrack={selectedTrack}
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
                events={events}
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
          <p>Mobility intelligence workspace</p>
        </div>
      </div>

      <nav className="sidebar-nav" aria-label="Primary">
        <SidebarLink active href="#analysis" icon={<ChartIcon />} label="Analysis" />
        <SidebarLink href="#samples" icon={<FolderIcon />} label="Samples" />
        <SidebarLink href="#results" icon={<PanelIcon />} label="Results" />
        <SidebarLink href="#pipeline" icon={<InfoIcon />} label="Method" />
      </nav>

      <div className="prototype-card">
        <strong>Research use only</strong>
        <p>
          Computer vision signals support review. They do not replace clinical
          judgment.
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
        <span className="hero-kicker">Motion review workspace</span>
        <h1>See the movement.<br />Inspect the evidence.</h1>
        <p className="hero-subtitle">
          Track people, review mobility events, and trace every signal back to
          the annotated frame.
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
      <div className="panel-heading">
        <h2 id="upload-title">Video source</h2>
        <span>MP4 up to 500 MB</span>
      </div>
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
        <strong>Drop a recording here</strong>
        <span>Browse local files</span>
        <small>MP4 format only</small>
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
      <div className="panel-heading">
        <h2 id="samples-title">Reference clips</h2>
        <span>Select one to inspect</span>
      </div>
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
        <span>Samples use local files and never leave this machine.</span>
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

function ProcessingPanel({ progress }: { progress: AnalysisProgress | null }) {
  const stage = progress?.stage ?? "queued";
  const percent = Math.max(0, Math.min(100, progress?.percent ?? 0));
  const frames = progress?.frames_processed ?? 0;
  const total = progress?.total_frames ?? 0;

  return (
    <section className="processing-panel" aria-live="polite" aria-label="Analysis status">
      <div>
        <SpinnerIcon />
        <strong>{STAGE_LABELS[stage] ?? stage}</strong>
      </div>
      <div
        className="processing-progress"
        role="progressbar"
        aria-valuenow={Math.round(percent)}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div className="processing-progress__bar" style={{ width: `${percent}%` }} />
      </div>
      <p className="processing-progress__label">
        {total > 0 ? `${frames} / ${total} frames · ${percent.toFixed(0)}%` : `${percent.toFixed(0)}%`}
      </p>
    </section>
  );
}

function SummaryCards({
  status,
  framesProcessed,
  trackCount,
  eventCount,
  summaryMetrics
}: {
  status: string;
  framesProcessed: number;
  trackCount: number;
  eventCount: number;
  summaryMetrics: MetricItem[];
}) {
  return (
    <section className="panel summary-panel" id="results" aria-labelledby="summary-title">
      <div className="panel-heading">
        <h2 id="summary-title">Run telemetry</h2>
        <span>Current analysis</span>
      </div>
      <div className="metric-grid">
        <MetricCard icon={<ActivityIcon />} label="Status" value={status} />
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
    <div className={`metric-card${label === "Status" ? " metric-card--status" : ""}`}>
      <span className="metric-icon">{icon}</span>
      <div>
        <span>{label}</span>
        <strong className="metric-value">{value}</strong>
      </div>
    </div>
  );
}

function AnnotatedVideo({
  events,
  hasResult,
  onSelectEvent,
  selectedEventKey,
  selectedTrack,
  videoDurationSeconds,
  videoRef,
  videoUrl
}: {
  events: BehaviorEvent[];
  hasResult: boolean;
  onSelectEvent: (event: BehaviorEvent, index: number) => void;
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
        <div>
          <span className="artifact-kicker">Evidence viewer</span>
          <h2 id="video-title">Annotated motion</h2>
        </div>
        {hasResult ? <span>Analysis ready</span> : <span>Awaiting run</span>}
      </div>
      <div className="video-frame">
        {videoUrl && !videoLoadError ? (
          <video
            ref={videoRef}
            className="annotated-video"
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
      {selectedTrack ? (
        <div className="video-selection-hint" aria-live="polite">
          Selected Subject {selectedTrack.id}
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
          const severityTone = severityPresentation(
            readString(event, "severity") ?? ""
          ).tone;
          const left = Math.min(100, Math.max(0, (timestamp / duration) * 100));
          const isSelected = selectedEventKey === key;

          return (
            <button
              aria-label={`${humanizeEventType(
                readString(event, "event_type") ?? "event"
              )} at ${formatOptionalDecimal(timestamp)} seconds`}
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
      <span>Event positions in source time</span>
    </div>
  );
}

function TracksTable({
  onSelectTrack,
  selectedTrackId,
  tracks
}: {
  onSelectTrack: (trackId: number) => void;
  selectedTrackId: number | null;
  tracks: TrackRow[];
}) {
  return (
    <section className="panel table-panel" aria-labelledby="tracks-title">
      <div className="table-heading">
        <h2 id="tracks-title">Subjects</h2>
        <span>{tracks.length.toLocaleString()} tracked</span>
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
              onKeyDown={(event) => activateOnCardKey(event, () => onSelectTrack(track.id))}
              role="button"
              tabIndex={0}
            >
              <div className="subject-row-main">
                <span className={`track-id track-id--${index % 4}`}>{track.id}</span>
                <div>
                  <strong>Subject {track.id}</strong>
                  <span>
                    {track.frames.toLocaleString()} frames / {track.motionSummary}
                  </span>
                </div>
              </div>
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
                  <dt>Events</dt>
                  <dd>{track.eventCount.toLocaleString()}</dd>
                </div>
                <div>
                  <dt>Motion</dt>
                  <dd>{track.motionSummary}</dd>
                </div>
              </dl>
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
  onSelectEvent,
  selectedEventKey
}: {
  events: BehaviorEvent[];
  onSelectEvent: (event: BehaviorEvent, index: number) => void;
  selectedEventKey: string | null;
}) {
  return (
    <section className="panel table-panel" aria-labelledby="events-title">
      <div className="table-heading">
        <h2 id="events-title">Review queue</h2>
        <span>{events.length.toLocaleString()} events</span>
      </div>
      {events.length > 0 ? (
        <div className="event-list">
          {events.map((event, index) => {
            const timestamp = formatOptionalDecimal(readNumber(event, "timestamp_s"));
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
                  activateOnCardKey(keyboardEvent, () => onSelectEvent(event, index))
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
                  {timestamp}s / Subject {event.track_id}
                </span>
              </article>
            );
          })}
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
  const presentation = severityPresentation(severity);
  return (
    <span className={`severity severity--${presentation.tone}`}>
      {presentation.label}
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
    return <span className="trajectory-empty">-</span>;
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
  icon: ReactNode;
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

function buildSummaryMetrics(analysis: AnalysisRecord | null): MetricItem[] {
  return [
    {
      icon: <GaugeIcon />,
      label: "Source Video FPS",
      value: formatMetricNumber(
        readAnalysisMetric(analysis, ["source_video_fps", "source_fps", "fps"])
      )
    },
    {
      icon: <GaugeIcon />,
      label: "CPU Analysis Throughput",
      value: formatMetricNumber(
        readAnalysisMetric(analysis, [
          "cpu_analysis_throughput_fps",
          "analysis_throughput_fps"
        ])
      )
    },
    {
      icon: <GaugeIcon />,
      label: "End-to-End Processing FPS",
      value: formatMetricNumber(
        readAnalysisMetric(analysis, [
          "end_to_end_processing_fps",
          "end_to_end_throughput_fps",
          "processing_fps"
        ])
      )
    },
    {
      icon: <GaugeIcon />,
      label: "Playback FPS",
      value: formatMetricNumber(
        readAnalysisMetric(analysis, ["playback_fps", "source_video_fps", "fps"])
      )
    }
  ];
}

function readAnalysisMetric(
  analysis: AnalysisRecord | null,
  keys: string[]
): number | undefined {
  if (!analysis) {
    return undefined;
  }
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
      title: "Mobility Review",
      subtitle: "Flag review events",
      icon: <ShieldIcon />
    }
  ];

  return (
    <section className="panel pipeline-panel" id="pipeline" aria-labelledby="pipeline-title">
      <div className="panel-heading">
        <h2 id="pipeline-title">How the analysis runs</h2>
        <span>Local processing pipeline</span>
      </div>
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
        <span>Uploaded-video inference / YOLO26n / OpenCV / SORT tracking</span>
        <span>Research prototype. Not a medical device.</span>
      </div>
    </section>
  );
}

// Trajectories come from tracks[].trajectory, which the pipeline already
// populates. The previous implementation reconstructed them by walking the
// per-frame trace, which is why the API had to ship several megabytes of
// frames to the browser on every analysis.
function buildTrackRows(tracks: TrackSummary[], events: BehaviorEvent[]): TrackRow[] {
  const observationsByTrack = new Map<number, TrackPoint[]>();
  const eventCounts = eventCountsByTrack(events);
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
      const motionSummary =
        readString(track, "motion_state") ??
        readString(track, "status") ??
        summarizeTrackMotion(featureRecord, points);

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
        motionSummary,
        points
      };
    });
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

function summarizeTrackMotion(
  featureRecord: Record<string, unknown> | undefined,
  points: TrackPoint[]
): string {
  const speed = readNumber(featureRecord, "average_speed_px_s");
  const variance =
    readNumber(featureRecord, "position_variance_px2") ??
    readNumber(featureRecord, "path_variance_px2");
  if (variance !== undefined && variance > 900) {
    return "unstable";
  }
  if (speed !== undefined) {
    if (speed < 2) {
      return "stationary";
    }
    if (speed < 18) {
      return "slow walking";
    }
    return "walking";
  }
  return points.length > 1 ? "walking" : "tracking";
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


function numberOrZero(value: number | undefined): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function formatOptionalDecimal(value: number | undefined): string {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "-";
  }

  return value >= 10 ? value.toFixed(1) : value.toFixed(2);
}

function formatMetricNumber(value: number | undefined): string {
  return typeof value === "number" && Number.isFinite(value)
    ? formatOptionalDecimal(value)
    : "-";
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

function activateOnCardKey(
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
