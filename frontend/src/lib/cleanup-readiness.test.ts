import { describe, expect, it } from "vitest";
import { cleanupBlocker } from "./cleanup-readiness";

const ready = {
  paused: true,
  activeUploads: 0,
  selectedCount: 1,
  phase: null,
};
describe("cleanup readiness", () => {
  it("explains the running-queue blocker even after selecting and confirming", () => {
    expect(cleanupBlocker({ ...ready, paused: false })).toContain(
      "Pause the upload queue",
    );
    expect(cleanupBlocker(ready)).toBe("");
  });
  it("waits for claimed operations to drain after the queue is paused", () => {
    expect(cleanupBlocker({ ...ready, activeUploads: 2 })).toContain(
      "Waiting for 2 active upload operation(s)",
    );
  });
  it("requires selection", () => {
    expect(cleanupBlocker({ ...ready, selectedCount: 0 })).toContain(
      "Select at least one",
    );
  });
  it("describes real pending work separately from ineligible actions", () => {
    expect(cleanupBlocker({ ...ready, phase: "delete" })).toContain(
      "Large files can take several minutes",
    );
    expect(cleanupBlocker({ ...ready, phase: "review" })).toContain(
      "Reviewing",
    );
    expect(cleanupBlocker({ ...ready, phase: "pause" })).toContain("Pausing");
  });
});
