import { useId, useState } from "react";
import { api } from "../api";
import { emptyFilters, filterFiles } from "../lib/file-filters";
import { FileFilterBar } from "./FileFilterBar";
import { bytes } from "../lib/utils";
import { Button } from "./ui/button";
import { cleanupBlocker, type CleanupPhase } from "../lib/cleanup-readiness";

type Original = { id: string; path: string; size: number; video_id: string };
type Result = { id: string; ok: boolean; reason?: string };

export function CleanupPanel({
  paused,
  activeUploads = 0,
  refresh,
}: {
  paused: boolean;
  activeUploads?: number;
  refresh?: () => Promise<void>;
}) {
  const reasonId = useId();
  const [files, setFiles] = useState<Original[]>([]);
  const [filters, setFilters] = useState(emptyFilters);
  const [reviewed, setReviewed] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);
  const [confirmation, setConfirmation] = useState("");
  const [phase, setPhase] = useState<CleanupPhase>(null);
  const busy = phase !== null;
  const [notice, setNotice] = useState("");
  const visible = filterFiles(files, filters);
  const chosen = visible.filter((file) => selected.includes(file.id));
  const blocker = cleanupBlocker({
    paused,
    activeUploads,
    selectedCount: chosen.length,
    confirmation,
    phase,
  });
  const ready = !blocker;

  async function pauseQueue() {
    setPhase("pause");
    setNotice("");
    try {
      await api("/queue/pause", "POST");
      await refresh?.();
    } catch (error) {
      setNotice(
        error instanceof Error
          ? error.message
          : "Could not pause the upload queue.",
      );
    } finally {
      setPhase(null);
    }
  }

  async function review() {
    setPhase("review");
    setNotice("");
    setConfirmation("");
    setSelected([]);
    try {
      const candidates = await api<Original[]>("/cleanup");
      setFiles(candidates);
      setReviewed(true);
      if (!candidates.length) setNotice("No eligible local originals found.");
    } catch (error) {
      setFiles([]);
      setNotice(error instanceof Error ? error.message : "Review failed.");
    } finally {
      setPhase(null);
    }
  }

  async function remove() {
    if (!ready || busy) return;
    setPhase("delete");
    setNotice("");
    setConfirmation("");
    try {
      const results = await api<Result[]>("/cleanup", "POST", {
        ids: chosen.map((file) => file.id),
        confirmation: confirmation.trim(),
      });
      const deleted = new Set(
        results.filter((result) => result.ok).map((result) => result.id),
      );
      const failures = results
        .filter((result) => !result.ok)
        .map(
          (result) =>
            `${files.find((file) => file.id === result.id)?.path}: ${result.reason}`,
        );
      setFiles(files.filter((file) => !deleted.has(file.id)));
      setSelected([]);
      setNotice(
        [`Deleted ${deleted.size} local original(s).`, ...failures].join("\n"),
      );
    } catch (error) {
      setNotice(
        error instanceof Error
          ? error.message
          : "Cleanup failed. Refresh the review before retrying.",
      );
    } finally {
      setPhase(null);
    }
  }

  return (
    <section className="panel queue-panel">
      <div className="panel-heading">
        <h2>Free up space</h2>
        <Button
          variant="outline"
          disabled={busy}
          aria-busy={phase === "review"}
          onClick={review}
        >
          Review uploaded originals
        </Button>
      </div>
      <div className="queue-tools">
        <p>
          This permanently deletes the selected originals from this PC. YouTube
          re-encodes videos, so keep another copy if you need the original
          quality and file metadata.
        </p>
        <p>
          Only completed TubeVault archives qualify. Before deleting each file,
          TubeVault checks that its YouTube copy is processed and that the local
          original matches the recorded checksum.
        </p>
        {!paused && (
          <p>Pause the entire upload queue before deleting originals.</p>
        )}
        {notice && (
          <p role="status" style={{ whiteSpace: "pre-wrap" }}>
            {notice}
          </p>
        )}
      </div>
      {reviewed && (
        <FileFilterBar
          files={files}
          value={filters}
          shown={visible.length}
          searchLabel="Search uploaded originals"
          disabled={busy}
          onChange={(value) => {
            setFilters(value);
            setSelected([]);
            setConfirmation("");
          }}
        />
      )}
      {files.length > 0 && (
        <>
          <div className="queue-tools">
            <Button
              variant="outline"
              disabled={busy || !visible.length}
              onClick={() => {
                setSelected(visible.map((file) => file.id));
                setConfirmation("");
              }}
            >
              Select all shown originals
            </Button>
            <span>
              {visible.length} shown · {chosen.length} selected ·{" "}
              {bytes(chosen.reduce((sum, file) => sum + file.size, 0))}
            </span>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Select</th>
                  <th>Original file</th>
                  <th>Size</th>
                  <th>Archive</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((file) => (
                  <tr key={file.id}>
                    <td>
                      <input
                        type="checkbox"
                        aria-label={`Select ${file.path}`}
                        disabled={busy}
                        checked={selected.includes(file.id)}
                        onChange={(event) => {
                          setConfirmation("");
                          setSelected(
                            event.target.checked
                              ? [...selected, file.id]
                              : selected.filter((id) => id !== file.id),
                          );
                        }}
                      />
                    </td>
                    <td>{file.path}</td>
                    <td>{bytes(file.size)}</td>
                    <td>
                      <a
                        href={`https://www.youtube.com/watch?v=${encodeURIComponent(file.video_id)}`}
                        target="_blank"
                        rel="noreferrer"
                      >
                        Open YouTube copy
                      </a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!visible.length && (
              <p className="queue-tools">
                No uploaded originals match these filters.
              </p>
            )}
          </div>
          <div className="queue-tools">
            <label>
              Type DELETE ORIGINALS to confirm
              <input
                value={confirmation}
                disabled={busy}
                onChange={(event) => setConfirmation(event.target.value)}
              />
            </label>
            {!paused && (
              <Button
                variant="outline"
                disabled={busy}
                onClick={pauseQueue}
                aria-busy={phase === "pause"}
              >
                {phase === "pause"
                  ? "Pausing queue…"
                  : "Pause queue to enable deletion"}
              </Button>
            )}
            <Button
              disabled={!ready}
              onClick={remove}
              aria-busy={phase === "delete"}
              aria-describedby={reasonId}
            >
              {phase === "delete"
                ? "Verifying and deleting originals…"
                : `Permanently delete ${chosen.length} original(s)`}
            </Button>
            <p id={reasonId} aria-live="polite">
              {blocker ||
                `Ready to permanently delete ${chosen.length} selected original(s).`}
            </p>
          </div>
        </>
      )}
    </section>
  );
}
