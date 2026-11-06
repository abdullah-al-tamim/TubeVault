import { useState } from "react";
import { api } from "../api";
import { bytes } from "../lib/utils";
import { Button } from "./ui/button";

type Original = { id: string; path: string; size: number; video_id: string };
type Result = { id: string; ok: boolean; reason?: string };

export function CleanupPanel({ paused }: { paused: boolean }) {
  const [files, setFiles] = useState<Original[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [confirmation, setConfirmation] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const chosen = files.filter(file => selected.includes(file.id));
  const ready = paused && chosen.length > 0 && confirmation === "DELETE ORIGINALS";

  async function review() {
    setBusy(true);
    setNotice("");
    setConfirmation("");
    setSelected([]);
    try {
      const candidates = await api<Original[]>("/cleanup");
      setFiles(candidates);
      if (!candidates.length) setNotice("No eligible local originals found.");
    } catch (error) {
      setFiles([]);
      setNotice(error instanceof Error ? error.message : "Review failed.");
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!ready || busy) return;
    setBusy(true);
    setNotice("");
    setConfirmation("");
    try {
      const results = await api<Result[]>("/cleanup", "POST", { ids: selected, confirmation });
      const deleted = new Set(results.filter(result => result.ok).map(result => result.id));
      const failures = results.filter(result => !result.ok)
        .map(result => `${files.find(file => file.id === result.id)?.path}: ${result.reason}`);
      setFiles(files.filter(file => !deleted.has(file.id)));
      setSelected([]);
      setNotice([`Deleted ${deleted.size} local original(s).`, ...failures].join("\n"));
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Cleanup failed. Refresh the review before retrying.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel queue-panel">
      <div className="panel-heading">
        <h2>Free up space</h2>
        <Button variant="outline" disabled={busy} onClick={review}>Review uploaded originals</Button>
      </div>
      <div className="queue-tools">
        <p>This permanently deletes the selected originals from this PC. YouTube re-encodes videos, so keep another copy if you need the original quality and file metadata.</p>
        <p>Only completed TubeVault archives qualify. Before deleting each file, TubeVault checks that its YouTube copy is processed and that the local original matches the recorded checksum.</p>
        {!paused && <p>Pause the entire upload queue before deleting originals.</p>}
        {notice && <p role="status" style={{ whiteSpace: "pre-wrap" }}>{notice}</p>}
      </div>
      {files.length > 0 && (
        <>
          <div className="queue-tools">
            <Button variant="outline" disabled={busy} onClick={() => { setSelected(files.map(file => file.id)); setConfirmation(""); }}>
              Select all eligible originals
            </Button>
            <span>{chosen.length} selected · {bytes(chosen.reduce((sum, file) => sum + file.size, 0))}</span>
          </div>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Select</th><th>Original file</th><th>Size</th><th>Archive</th></tr></thead>
              <tbody>{files.map(file => (
                <tr key={file.id}>
                  <td><input type="checkbox" aria-label={`Select ${file.path}`} disabled={busy} checked={selected.includes(file.id)}
                    onChange={event => {
                      setConfirmation("");
                      setSelected(event.target.checked ? [...selected, file.id] : selected.filter(id => id !== file.id));
                    }} /></td>
                  <td>{file.path}</td>
                  <td>{bytes(file.size)}</td>
                  <td><a href={`https://www.youtube.com/watch?v=${encodeURIComponent(file.video_id)}`} target="_blank" rel="noreferrer">Open YouTube copy</a></td>
                </tr>
              ))}</tbody>
            </table>
          </div>
          <div className="queue-tools">
            <label>Type DELETE ORIGINALS to confirm
              <input value={confirmation} disabled={busy} onChange={event => setConfirmation(event.target.value)} />
            </label>
            <Button disabled={busy || !ready} onClick={remove}>Permanently delete {chosen.length} original(s)</Button>
          </div>
        </>
      )}
    </section>
  );
}
