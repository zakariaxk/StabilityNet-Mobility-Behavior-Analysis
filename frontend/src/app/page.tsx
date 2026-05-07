"use client";

import type { FormEvent, ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";

import {
  AnalysisRecord,
  BehaviorEvent,
  TrackSummary,
  checkHealth,
  createAnalysis,
  getAnalysis
} from "@/lib/stabilityNetApi";

const DEFAULT_VIDEO_PATH = "samples/test-video.mp4";

type HealthState =
  | { state: "checking"; label: "Checking" }
  | { state: "ok"; label: "Online" }
  | { state: "error"; label: "Offline"; detail: string };

export default function ReviewPage() {
  const [videoPath, setVideoPath] = useState(DEFAULT_VIDEO_PATH);
  const [analysis, setAnalysis] = useState<AnalysisRecord | null>(null);
  const [health, setHealth] = useState<HealthState>({
    state: "checking",
    label: "Checking"
  });
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);

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

  const tracks = useMemo(() => safeArray(analysis?.result.tracks), [analysis]);
  const events = useMemo(() => safeArray(analysis?.result.events), [analysis]);
  const framesProcessed = numberOrZero(analysis?.result.frames_processed);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmedPath = videoPath.trim();

    if (!trimmedPath) {
      setError("Video path is required.");
      return;
    }

    setError(null);
    setIsSubmitting(true);

    try {
      const record = await createAnalysis({ video_path: trimmedPath });
      setAnalysis(record);
    } catch (caughtError: unknown) {
      setError(errorMessage(caughtError));
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleRefresh() {
    if (!analysis) {
      return;
    }

    setError(null);
    setIsRefreshing(true);

    try {
      const record = await getAnalysis(analysis.analysis_id);
      setAnalysis(record);
    } catch (caughtError: unknown) {
      setError(errorMessage(caughtError));
    } finally {
      setIsRefreshing(false);
    }
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">StabilityNet</p>
          <h1>Analysis Review</h1>
        </div>
        <div className={`health-pill health-pill--${health.state}`}>
          <span aria-hidden="true" />
          <strong>API {health.label}</strong>
        </div>
      </header>

      <div className="workspace">
        <aside className="control-panel">
          <form onSubmit={handleSubmit} className="analysis-form">
            <label htmlFor="video-path">Local backend video path</label>
            <input
              id="video-path"
              type="text"
              value={videoPath}
              onChange={(event) => setVideoPath(event.target.value)}
              placeholder={DEFAULT_VIDEO_PATH}
              spellCheck={false}
            />
            <button type="submit" disabled={isSubmitting}>
              {isSubmitting ? "Running..." : "Run analysis"}
            </button>
          </form>

          {health.state === "error" ? (
            <StatusMessage tone="warning" title="Backend unavailable">
              {health.detail}
            </StatusMessage>
          ) : null}

          {error ? (
            <StatusMessage tone="danger" title="Analysis error">
              {error}
            </StatusMessage>
          ) : null}

          {analysis ? (
            <StatusMessage tone="success" title="Analysis completed">
              Result {shortId(analysis.analysis_id)} is loaded for review.
            </StatusMessage>
          ) : (
            <div className="empty-note">No analysis loaded.</div>
          )}
        </aside>

        <section className="review-panel" aria-live="polite">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Current Result</p>
              <h2>{analysis ? shortId(analysis.analysis_id) : "Pending analysis"}</h2>
            </div>
            <button
              type="button"
              className="secondary-button"
              onClick={handleRefresh}
              disabled={!analysis || isRefreshing}
            >
              {isRefreshing ? "Refreshing..." : "Refresh result"}
            </button>
          </div>

          <SummaryGrid
            analysis={analysis}
            tracks={tracks}
            events={events}
            framesProcessed={framesProcessed}
          />

          <section className="data-section">
            <div className="section-heading section-heading--compact">
              <h3>Tracks</h3>
              <span>{tracks.length.toLocaleString()} total</span>
            </div>
            {tracks.length > 0 ? <TrackTable tracks={tracks} /> : <EmptyState label="No tracks returned." />}
          </section>

          <section className="data-section">
            <div className="section-heading section-heading--compact">
              <h3>Events</h3>
              <span>{events.length.toLocaleString()} total</span>
            </div>
            {events.length > 0 ? <EventTable events={events} /> : <EmptyState label="No events returned." />}
          </section>
        </section>
      </div>
    </main>
  );
}

function SummaryGrid({
  analysis,
  tracks,
  events,
  framesProcessed
}: {
  analysis: AnalysisRecord | null;
  tracks: TrackSummary[];
  events: BehaviorEvent[];
  framesProcessed: number;
}) {
  const videoPath = analysis?.video_path ?? analysis?.result.video?.path ?? "None";

  return (
    <section className="summary-grid" aria-label="Analysis summary">
      <Metric label="Analysis ID" value={analysis?.analysis_id ?? "None"} isMonospace />
      <Metric label="Status" value={analysis?.status ?? "Not started"} />
      <Metric label="Video path" value={videoPath} isMonospace />
      <Metric label="Frames processed" value={framesProcessed.toLocaleString()} />
      <Metric label="Tracks" value={tracks.length.toLocaleString()} />
      <Metric label="Events" value={events.length.toLocaleString()} />
    </section>
  );
}

function Metric({
  label,
  value,
  isMonospace = false
}: {
  label: string;
  value: string;
  isMonospace?: boolean;
}) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong className={isMonospace ? "mono-value" : undefined}>{value}</strong>
    </div>
  );
}

function TrackTable({ tracks }: { tracks: TrackSummary[] }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Track ID</th>
            <th>Observations</th>
            <th>First seen</th>
            <th>Last seen</th>
            <th>Confirmed</th>
          </tr>
        </thead>
        <tbody>
          {tracks.map((track) => (
            <tr key={track.track_id}>
              <td>{track.track_id}</td>
              <td>{numberOrZero(track.observations).toLocaleString()}</td>
              <td>{formatTimestamp(track.first_timestamp_s)}</td>
              <td>{formatTimestamp(track.last_timestamp_s)}</td>
              <td>{track.is_confirmed ? "Yes" : "No"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function EventTable({ events }: { events: BehaviorEvent[] }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Type</th>
            <th>Severity</th>
            <th>Track ID</th>
            <th>Timestamp</th>
            <th>Reason</th>
          </tr>
        </thead>
        <tbody>
          {events.map((event, index) => (
            <tr key={event.event_id ?? `${event.track_id}-${event.event_type}-${index}`}>
              <td>{humanizeEventType(event.event_type)}</td>
              <td>
                <span className={`severity severity--${severityClass(event.severity)}`}>
                  {event.severity}
                </span>
              </td>
              <td>{event.track_id}</td>
              <td>{formatTimestamp(event.timestamp_s)}</td>
              <td>{event.reason}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function StatusMessage({
  tone,
  title,
  children
}: {
  tone: "success" | "warning" | "danger";
  title: string;
  children: ReactNode;
}) {
  return (
    <div className={`status-message status-message--${tone}`}>
      <strong>{title}</strong>
      <p>{children}</p>
    </div>
  );
}

function EmptyState({ label }: { label: string }) {
  return <div className="empty-state">{label}</div>;
}

function safeArray<T>(value: T[] | undefined): T[] {
  return Array.isArray(value) ? value : [];
}

function numberOrZero(value: number | undefined): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function formatTimestamp(value: number | undefined): string {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "-";
  }

  return `${value.toFixed(value >= 10 ? 1 : 2)}s`;
}

function humanizeEventType(value: string): string {
  return value
    .split("_")
    .filter(Boolean)
    .map((part) => `${part.charAt(0).toUpperCase()}${part.slice(1)}`)
    .join(" ");
}

function severityClass(value: string): string {
  const normalized = value.toLowerCase();
  if (normalized.includes("high") || normalized.includes("critical")) {
    return "high";
  }
  if (normalized.includes("medium") || normalized.includes("moderate")) {
    return "medium";
  }
  return "low";
}

function shortId(value: string): string {
  return value.length > 12 ? `${value.slice(0, 8)}...${value.slice(-4)}` : value;
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Unexpected frontend error.";
}
