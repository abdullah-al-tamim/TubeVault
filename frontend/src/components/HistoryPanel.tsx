import { useState, type ReactNode } from "react";
import { api } from "../api";
import { emptyFilters, filterFiles } from "../lib/file-filters";
import { FileFilterBar } from "./FileFilterBar";
import { bytes } from "../lib/utils";
import { Button } from "./ui/button";

type ArchiveJob = {
  id: string;
  title: string;
  playlist: string;
  path: string;
  sha256: string;
  size: number;
  history_hidden?: boolean;
};

export function HistoryPanel({
  jobs,
  refresh,
  details,
}: {
  jobs: ArchiveJob[];
  refresh: () => Promise<void>;
  details: (id: string) => ReactNode;
}) {
  const [filters, setFilters] = useState(emptyFilters);
  const [removed, setRemoved] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const inView = jobs.filter((j) => !!j.history_hidden === removed);
  const visible = filterFiles(inView, filters);
  const ids = visible.map((j) => j.id);
  const picked = selected.filter((id) => ids.includes(id));
  async function change(targets: string[]) {
    const action = removed ? "restore" : "remove";
    if (
      !removed &&
      !confirm(
        `Remove ${targets.length} archive entry/entries from history? Source files and YouTube videos are kept. Entries can be restored from Removed entries.`,
      )
    )
      return;
    setBusy(true);
    setNotice("");
    try {
      const response = await api("/history/bulk", "POST", {
        ids: targets,
        action,
      });
      const failed = response.results.filter((r: { ok: boolean }) => !r.ok);
      setNotice(
        failed.length
          ? `${failed.length} unchanged: ${failed.map((r: { error: string }) => r.error).join("; ")}`
          : `${targets.length} archive entry/entries ${removed ? "restored" : "removed"}.`,
      );
      setSelected([]);
      await refresh();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Operation failed");
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="panel">
      <FileFilterBar
        files={inView}
        value={filters}
        shown={visible.length}
        disabled={busy}
        searchLabel="Search archive history"
        onChange={(value) => {
          setFilters(value);
          setSelected([]);
        }}
      />
      <div className="queue-tools">
        <select
          aria-label="Archive history filter"
          value={removed ? "removed" : "history"}
          onChange={(e) => {
            setRemoved(e.target.value === "removed");
            setSelected([]);
          }}
        >
          <option value="history">Archive entries</option>
          <option value="removed">Removed entries</option>
        </select>
        <span>
          {visible.length} shown · {picked.length} selected
        </span>
        <Button
          disabled={busy || !picked.length}
          onClick={() => change(picked)}
        >
          {removed ? "Restore selected" : "Remove selected"}
        </Button>
        <p>
          Removing entries keeps your source files and YouTube videos. Upload
          verification is retained to prevent duplicates.
        </p>
      </div>
      {notice && (
        <p className="queue-tools" role="status">
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
                  aria-label="Select all shown archive entries"
                  disabled={busy}
                  checked={ids.length > 0 && picked.length === ids.length}
                  onChange={(e) => setSelected(e.target.checked ? ids : [])}
                />
              </th>
              <th>Video / folder</th>
              <th>Size</th>
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
                    disabled={busy}
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
                  <small className="path">{j.path}</small>
                </td>
                <td>{bytes(j.size)}</td>
                <td>
                  <Button
                    variant="outline"
                    disabled={busy}
                    onClick={() => change([j.id])}
                  >
                    {removed ? "Restore" : "Remove"}
                  </Button>
                  {details(j.id)}
                  <details>
                    <summary>Checksum and source</summary>
                    <code>{j.sha256}</code>
                    <p>{j.path}</p>
                  </details>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!visible.length && (
          <p className="queue-tools">No archive entries match this view.</p>
        )}
      </div>
    </section>
  );
}
