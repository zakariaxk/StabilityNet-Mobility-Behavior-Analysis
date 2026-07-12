export type SeverityTone =
  | "normal"
  | "review"
  | "medium"
  | "insufficient"
  | "high";

export type SeverityPresentation = Readonly<{
  tone: SeverityTone;
  label: string;
}>;

const REVIEW_PRESENTATION: SeverityPresentation = {
  tone: "review",
  label: "Movement Under Review"
};

const SEVERITY_PRESENTATIONS: Readonly<Record<string, SeverityPresentation>> = {
  normal: { tone: "normal", label: "Stable" },
  review_needed: REVIEW_PRESENTATION,
  medium: { tone: "medium", label: "Postural Transition" },
  insufficient_evidence: {
    tone: "insufficient",
    label: "Insufficient Evidence"
  },
  high: { tone: "high", label: "High Mobility Risk" }
};

export function severityPresentation(severity: string): SeverityPresentation {
  return SEVERITY_PRESENTATIONS[severity.trim().toLowerCase()] ?? REVIEW_PRESENTATION;
}
