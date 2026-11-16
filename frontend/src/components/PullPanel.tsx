import { useEffect, useState } from "react";
import { api } from "../api";
import { Button } from "./ui/button";

type Pull = {
  id: string; video_id: string; state: string; format: string;
  height: number | null; path: string | null; error: string;
  title?: string; actual_height?: number; fps?: number;
};
const formats: Record<string, string> = {
  source: "Best available video + audio",
  mp4: "MP4 video (H.264)",
  audio: "Best available audio",
  m4a: "M4A audio",
  mp3: "MP3 audio",
};

export function PullPanel() {
  const [url, setUrl] = useState("");
  const [format, setFormat] = useState("source");
  const [height, setHeight] = useState("");
  const [jobs, setJobs] = useState<Pull[]>([]);
  const [error, setError] = useState("");
  const [listError, setListError] = useState("");
  const [busy, setBusy] = useState(false);
  const [revision, refresh] = useState(0);
  const video = format === "source" || format === "mp4";

  useEffect(() => {
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    async function load() {
      try {
        const rows = await api<Pull[]>("/pulls");
        if (!disposed) { setJobs(rows); setListError(""); }
      } catch (e) {
        if (!disposed) setListError((e as Error).message);
      } finally {
        if (!disposed) timer = setTimeout(load, 3000);
      }
    }
    load();
    return () => { disposed = true; clearTimeout(timer); };
  }, [revision]);

  return <>
    <form className="panel settings-panel" onSubmit={async e => {
      e.preventDefault();
      setBusy(true); setError("");
      try {
        await api("/pulls", "POST", { url, format, height: video && height ? Number(height) : null });
        refresh(r => r + 1);
      } catch (err) { setError((err as Error).message); }
      finally { setBusy(false); }
    }}>
      <label>YouTube link<input type="url" required value={url} onChange={e => setUrl(e.target.value)}
        placeholder="https://www.youtube.com/watch?v=..." /></label>
      <label>Format<select value={format} onChange={e => setFormat(e.target.value)}>
        {Object.entries(formats).map(([id, label]) => <option key={id} value={id}>{label}</option>)}
      </select></label>
      {video && <label>Maximum video height<select value={height} onChange={e => setHeight(e.target.value)}>
        <option value="">Highest available</option>
        {[4320, 2160, 1440, 1080, 720, 480, 360, 240, 144].map(h => <option key={h} value={h}>{h}p</option>)}
      </select></label>}
      <Button disabled={busy || !url.trim()}>Pull media</Button>
      {error && <p role="alert">{error}</p>}
    </form>
    <section className="panel settings-panel"><h2>Recent pulls</h2>
      {listError && <p role="alert">{listError}</p>}
      {!jobs.length && !listError && <p>Your downloaded files will appear here.</p>}
      {jobs.map(j => <article key={j.id} className="pull-result">
        <strong>{j.title || j.video_id}</strong> · {formats[j.format]}
        {j.actual_height ? ` · ${j.actual_height}p` : j.height ? ` · Up to ${j.height}p` : ""}
        {j.fps ? ` · ${j.fps} fps` : ""} · {j.state}
        {j.path && <><p>{j.path}</p><a href={`/api/pulls/${j.id}/file`} download>Download file</a></>}
        {j.error && <p>{j.error}</p>}
      </article>)}
    </section>
  </>;
}
