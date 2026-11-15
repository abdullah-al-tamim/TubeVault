export const cleanupConfirmation = "DELETE ORIGINALS";
export type CleanupPhase = "review" | "pause" | "delete" | null;

export function cleanupBlocker({
  paused,
  activeUploads,
  selectedCount,
  confirmation,
  phase,
}: {
  paused: boolean;
  activeUploads: number;
  selectedCount: number;
  confirmation: string;
  phase: CleanupPhase;
}): string {
  if (phase === "delete")
    return "Verifying YouTube copies and original-file checksums before deletion. Large files can take several minutes. Keep this window open.";
  if (phase === "review") return "Reviewing uploaded originals…";
  if (phase === "pause") return "Pausing the upload queue…";
  if (!paused) return "Pause the upload queue to enable permanent deletion.";
  if (activeUploads > 0)
    return `Waiting for ${activeUploads} active upload operation(s) to stop. The queue is paused; deletion will become available when they finish.`;
  if (!selectedCount) return "Select at least one original file to delete.";
  if (confirmation.trim() !== cleanupConfirmation)
    return "Type DELETE ORIGINALS exactly to enable permanent deletion.";
  return "";
}
