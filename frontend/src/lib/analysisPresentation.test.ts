import { describe, expect, it } from "vitest";

import { severityPresentation } from "./analysisPresentation";

describe("severityPresentation", () => {
  it.each([
    ["normal", { tone: "normal", label: "Stable" }],
    ["review_needed", { tone: "review", label: "Movement Under Review" }],
    ["medium", { tone: "medium", label: "Postural Transition" }],
    ["insufficient_evidence", { tone: "insufficient", label: "Insufficient Evidence" }],
    ["high", { tone: "high", label: "High Mobility Risk" }],
    ["unexpected_value", { tone: "review", label: "Movement Under Review" }]
  ] as const)("maps %s without understating risk", (severity, expected) => {
    expect(severityPresentation(severity)).toEqual(expected);
  });
});
