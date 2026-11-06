import { useState, type ReactNode } from "react";
import { Button } from "./ui/button";
import { api } from "../api";
import { bytes, percent } from "../lib/utils";

type QueueJob = {
  id: string;
  title: string;
  state: string;
  size: number;
  progress: number;
  playlist: string;
  error: string;
  claimed?: boolean;
  control_requested?: string;
};
export function QueuePanel({
  jobs,
  settings,
  desktop,
  refresh,
  details,
}: {
  jobs: QueueJob[];
  settings: any;
  desktop: boolean;
  refresh: () => Promise<void>;
  details: (id: string) => ReactNode;
}) {
  const [selected, setSelected] = useState<string[]>([]),
    [search, setSearch] = useState(""),
    [filter, setFilter] = useState("queue"),
    [paths, setPaths] = useState(""),
    [busy, setBusy] = useState(false),
    [notice, setNotice] = useState("");
  const removed = new Set(["SKIPPED", "CANCELLED", "REMOVED"]);
  const visible = jobs.filter(
    (j) =>
      j.state !== "COMPLETED" &&
      (filter === "all" ||
        (filter === "queue" ? !removed.has(j.state) : j.state === filter)) &&
      (j.title + " " + j.playlist).toLowerCase().includes(search.toLowerCase()),
  );
  const ids = visible.map((j) => j.id),
    picked = selected.filter((id) => ids.includes(id));
  async function run(action: () => Promise<void>) {
    setBusy(true);
    setNotice("");
    try {
      await action();
      await refresh();
    } catch (e) {
      setNotice(e instanceof Error ? e.message : "Operation failed");
    } finally {
      setBusy(false);
    }
  }
  async function control(action: string, targets = picked) {
    await run(async () => {
      const response = await api("/queue/bulk", "POST", {
        ids: targets,
        action,
      });
      const failed = response.results.filter((r: any) => !r.ok);
      setNotice(
        failed.length
          ? `${failed.length} unchanged: ${failed.map((r: any) => r.error).join("; ")}`
          : `${targets.length} video(s): ${action} requested.`,
      );
      setSelected([]);
    });
  }
  return (
    <section className="panel queue-panel">
      <div className="panel-heading">
        <div>
          <h2>Upload Queue</h2>
          <p>
            {jobs.filter((j) => j.claimed).length} active · Up to{" "}
            {settings?.concurrency || 1} at a time. Other videos wait their
            turn.
          </p>
        </div>
        <Button
          disabled={busy}
          onClick={() =>
            run(async () => {
              await api(
                `/queue/${settings?.paused ? "resume" : "pause"}`,
                "POST",
              );
            })
          }
        >
          {settings?.paused ? "Start queue" : "Pause entire queue"}
        </Button>
      </div>
      <div className="queue-tools">
        <Button
          disabled={busy}
          onClick={() =>
            run(async () => {
              const result = await api("/queue/check-duplicates", "POST");
              setNotice(
                `Checked ${result.checked} YouTube videos. Held ${result.held} queued videos with matching titles. Found ${result.duplicate_titles.length} repeated titles already on YouTube.`,
              );
            })
          }
        >
          Check YouTube for duplicates
        </Button>
        <p>
          Before each new upload, TubeVault checks your channel for the same
          title (ignoring capitalization and extra spaces). Matches are held for
          review, not marked as archived. No videos are deleted.
        </p>
      </div>
      <div className="queue-tools">
        <label>
          Simultaneous uploads
          <select
            aria-label="Simultaneous uploads"
            value={settings?.concurrency || 1}
            disabled={busy}
            onChange={(e) => {
              const concurrency = Number(e.target.value);
              run(async () => {
                await api("/queue/concurrency", "PUT", { concurrency });
              });
            }}
          >
            {[1, 2, 3, 4].map((n) => (
              <option key={n} value={n}>
                {n}
                {n === 1 ? " — one by one" : " at a time"}
              </option>
            ))}
          </select>
        </label>
        <p>
          One at a time is the default. Lowering the limit lets current uploads
          finish before starting more.
        </p>
      </div>
      <details className="queue-tools">
        <summary>Add selected videos manually</summary>
        <p>
          Choose individual files without watching their whole folder. Existing
          content is not uploaded twice.
        </p>
        {desktop && (
          <Button
            disabled={busy}
            onClick={() =>
              run(async () => {
                const result = await api("/desktop/files", "POST");
                setPaths(result.paths.join("\n"));
              })
            }
          >
            Browse videos
          </Button>
        )}
        <label>
          Video paths (one per line)
          <textarea
            aria-label="Video paths (one per line)"
            rows={3}
            value={paths}
            onChange={(e) => setPaths(e.target.value)}
          />
        </label>
        <Button
          disabled={busy || !paths.trim()}
          onClick={() =>
            run(async () => {
              const result = await api("/queue/add-files", "POST", {
                paths: paths
                  .split(/\r?\n/)
                  .map((p) => p.trim())
                  .filter(Boolean),
              });
              setNotice(
                result.results
                  .map((r: any) => `${r.path}: ${r.message}`)
                  .join("\n"),
              );
              if (result.results.every((r: any) => r.ok)) setPaths("");
            })
          }
        >
          Add videos to queue
        </Button>
      </details>
      <div className="queue-tools">
        <input
          aria-label="Search queue"
          placeholder="Search videos or collections"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <select
          aria-label="Queue status filter"
          value={filter}
          onChange={(e) => {
            setFilter(e.target.value);
            setSelected([]);
          }}
        >
          <option value="queue">Current queue</option>
          <option value="PAUSED">Paused</option>
          <option value="DUPLICATE_TITLE">Matching YouTube title</option>
          <option value="SKIPPED">Skipped</option>
          <option value="CANCELLED">Cancelled</option>
          <option value="REMOVED">Removed</option>
          <option value="all">All unfinished videos</option>
        </select>
        <span>
          {visible.length} shown · {picked.length} selected
        </span>
      </div>
      <div className="queue-tools">
        {["pause", "resume", "skip", "cancel", "remove"].map((action) => (
          <Button
            key={action}
            variant="outline"
            disabled={busy || !picked.length}
            onClick={() => control(action)}
          >
            {action[0].toUpperCase() + action.slice(1)} selected
          </Button>
        ))}
        <p>
          Pause holds progress. Skip sets a video aside. Cancel stops its
          upload. Remove hides it from the current queue. These actions keep
          your source files and any YouTube video; use the filters to restore
          items. Active requests stop after the current operation.
        </p>
      </div>
      {notice && (
        <p
          className="queue-tools"
          role="status"
          style={{ whiteSpace: "pre-wrap" }}
        >
          {notice}
        </p>
      )}
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>
                <input
                  type="checkbox"
                  aria-label="Select all shown videos"
                  checked={ids.length > 0 && picked.length === ids.length}
                  onChange={(e) => setSelected(e.target.checked ? ids : [])}
                />
              </th>
              <th>Video / collection</th>
              <th>Status</th>
              <th>Progress</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((j) => (
              <tr key={j.id}>
                <td>
                  <input
                    type="checkbox"
                    aria-label={`Select ${j.title}`}
                    checked={picked.includes(j.id)}
                    onChange={(e) =>
                      setSelected(
                        e.target.checked
                          ? [...selected, j.id]
                          : selected.filter((id) => id !== j.id),
                      )
                    }
                  />
                </td>
                <td>
                  <strong>{j.title}</strong>
                  <small>{j.playlist}</small>
                </td>
                <td>
                  {j.control_requested && j.claimed
                    ? `${j.control_requested} requested…`
                    : j.state}
                  {j.error && <small>{j.error}</small>}
                </td>
                <td>
                  {percent(j.progress, j.size)}% · {bytes(j.progress)} /{" "}
                  {bytes(j.size)}
                </td>
                <td>
                  <div className="row-actions">
                    {["pause", "resume", "skip", "cancel", "remove"].map(
                      (action) => (
                        <Button
                          key={action}
                          variant="ghost"
                          disabled={busy}
                          onClick={() => control(action, [j.id])}
                        >
                          {action[0].toUpperCase() + action.slice(1)}
                        </Button>
                      ),
                    )}
                  </div>
                  <details>
                    <summary>Metadata / recovery</summary>
                    {details(j.id)}
                  </details>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!visible.length && (
          <p className="queue-tools">No videos in this view.</p>
        )}
      </div>
    </section>
  );
}
