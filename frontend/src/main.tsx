import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Archive,
  ArrowUpRight,
  Check,
  CloudUpload,
  Folder,
  HardDrive,
  LayoutDashboard,
  ListVideo,
  LoaderCircle,
  Menu,
  Moon,
  Pause,
  Play,
  Plus,
  RefreshCw,
  Search,
  Settings,
  ShieldCheck,
  Smartphone,
  Sun,
  Terminal,
  Video,
  X,
} from "lucide-react";
import { Button } from "./components/ui/button";
import { api, setCsrf, transfer, restoreSession, recoverDesktopSession } from "./api";
import { PhoneReceiverPanel } from "./components/PhoneReceiverPanel";
import { CleanupPanel } from "./components/CleanupPanel";
import { QueuePanel } from "./components/QueuePanel";
import { SetupGuide, type SetupStatus } from './components/SetupGuide';
import { bytes, percent } from "./lib/utils";
import "./styles.css";

type Job = {
  id: string;
  title: string;
  state: string;
  size: number;
  progress: number;
  speed: number;
  playlist: string;
  privacy: string;
  retries: number;
  video_id: string | null;
  error: string;
  sha256: string;
  path: string;
  created: number;
  description: string;
  tags: string[];
  made_for_kids: boolean;
};
type Snapshot = {
  preview?: boolean;
  stats?: { discovered: number; archived: number; queued: number; failed: number; bytes: number };
  jobs: Job[];
  watches: any[];
  mappings: any[];
  instances: any[];
  events: any[];
  imports: any[];
  account: any;
  settings: any;
};
const pages = [
  ["Overview", LayoutDashboard],
  ["Upload Queue", CloudUpload],
  ["Watch Folders", Folder],
  ["Playlists", ListVideo],
  ["Archive History", Archive],
  ["iPhone Imports", Smartphone],
  ["Settings", Settings],
  ["Diagnostics", Terminal],
] as const;
function App() {
  const [setupStatus, setSetupStatus] = useState<SetupStatus|null>(null);
  const [showGuide, setShowGuide] = useState(false);
  const [signed, setSigned] = useState(false),
    [password, setPassword] = useState(""),
    [data, setData] = useState<Snapshot | null>(null),
    [page, setPage] = useState("Overview"),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [search, setSearch] = useState(""),
    [light, setLight] = useState(localStorage.getItem("tv-light") === "true"),
    [menu, setMenu] = useState(false),
    [add, setAdd] = useState(false),
    [path, setPath] = useState(""),
    [collection, setCollection] = useState("iPhone memories"),
    [progress, setProgress] = useState<Record<string, number>>({}),
    [edit, setEdit] = useState<Job | null>(null);
  const load = async () => setData(await api("/snapshot"));
  useEffect(() => {
    restoreSession()
      .then((s) => {
        setCsrf(s.csrf);
        setSigned(true);
      })
      .catch(() => {});
  }, []);
  useEffect(() => {
    if (!signed) return;
    api<SetupStatus>('/setup/status').then(s=>{setSetupStatus(s);if(!s.completed)setShowGuide(true);}).catch(()=>{});
    load().catch((e) => setError(e.message));
    const stream = new EventSource("/api/events");
    stream.onmessage = (e) => setData(JSON.parse(e.data));
    stream.onerror = () => {
      api("/session").catch(() => {
        recoverDesktopSession().then(session => {
          setCsrf(session.csrf);
          load().catch(error => setError(error.message));
        }).catch(() => setSigned(false));
      });
    };
    return () => stream.close();
  }, [signed]);
  useEffect(() => {
    document.documentElement.classList.toggle("light", light);
    localStorage.setItem("tv-light", String(light));
  }, [light]);
  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    setError("");
    try {
      await action();
      if (signed) await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Operation failed");
    } finally {
      setBusy(false);
    }
  }
  const jobs = data?.jobs || [],
    done = jobs.filter((j) => j.state === "COMPLETED"),
    queued = jobs.filter((j) =>
      [
        "QUEUED",
        "PAUSED",
        "UPLOADING",
        "PROCESSING",
        "PLAYLIST_PENDING",
      ].includes(j.state),
    ),
    failed = jobs.filter(
      (j) => j.state.startsWith("FAILED") || j.state === "UPLOAD_UNCERTAIN",
    ),
    active = jobs.find((j) => j.state === "UPLOADING"),
    settings = data?.settings;
  const actions = (j: Job) => (
    <div className="row-actions">
      {j.video_id && (
        <a
          href={`https://www.youtube.com/watch?v=${j.video_id}`}
          target="_blank"
          rel="noreferrer"
          aria-label="Open video"
        >
          <ArrowUpRight size={17} />
        </a>
      )}
      {["QUEUED", "PAUSED", "DUPLICATE_TITLE"].includes(j.state) && (
        <Button variant="ghost" onClick={() => setEdit({ ...j })}>
          Edit
        </Button>
      )}
      {j.state === "UPLOAD_UNCERTAIN" ? (
        <Button variant="outline" onClick={() => run(() => api(`/jobs/${j.id}/retry`, "POST"))}>
          Check again
        </Button>
      ) : (
        j.state !== "COMPLETED" && (
          <>
            <Button
              variant="ghost"
              onClick={() =>
                run(() =>
                  api(
                    `/jobs/${j.id}/${["QUEUED", "UPLOADING", "PROCESSING", "PLAYLIST_PENDING"].includes(j.state) ? "pause" : "retry"}`,
                    "POST",
                  ),
                )
              }
            >
              {["QUEUED", "UPLOADING", "PROCESSING", "PLAYLIST_PENDING"].includes(j.state) ? "Pause" : "Resume"}
            </Button>
            <Button
              variant="ghost"
              onClick={() => run(() => api(`/jobs/${j.id}/exclude`, "POST"))}
            >
              Skip
            </Button>
          </>
        )
      )}
    </div>
  );
  const table = (items: Job[]) => (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Video</th>
            <th>Collection</th>
            <th>Status</th>
            <th>Size / progress</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {items.map((j) => (
            <tr key={j.id}>
              <td>
                <div className="file-title">
                  <span className="file-icon">
                    <Video size={19} />
                  </span>
                  <span>
                    <strong>{j.title}</strong>
                    <small>
                      {j.privacy} · {j.retries} retries
                    </small>
                    {j.error && <small className="error-text">{j.error}</small>}
                  </span>
                </div>
              </td>
              <td>{j.playlist}</td>
              <td>
                <span
                  className={`badge ${j.state === "COMPLETED" ? "green" : j.state.startsWith("FAILED") || j.state === "UPLOAD_UNCERTAIN" ? "red" : ""}`}
                >
                  {(j.state === "UPLOAD_UNCERTAIN" ? "Waiting to check YouTube" : j.state.replaceAll("_", " ")).toLowerCase()}
                </span>
              </td>
              <td>
                {bytes(j.size)}
                {j.state === "UPLOADING" && (
                  <>
                    <progress value={j.progress} max={j.size} />
                    <small>
                      {bytes(j.speed)}/s · ETA{" "}
                      {j.speed
                        ? Math.ceil((j.size - j.progress) / j.speed / 60)
                        : "—"}{" "}
                      min
                    </small>
                  </>
                )}
              </td>
              <td>{actions(j)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {!items.length && (
        <Empty
          title="Your next memory starts here"
          text="Add a watch folder or import original videos from your iPhone."
        />
      )}
    </div>
  );
  if (!signed)
    return (
      <main className="login">
        <div className="login-card">
          <div className="brand">
            <span>
              <Archive />
            </span>
            TubeVault
          </div>
          <h1>
            Your memories.
            <br />
            Your private archive.
          </h1>
          <p>Sign in to the vault running on your Windows PC.</p>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              run(async () => {
                const s = await api("/login", "POST", { password });
                setCsrf(s.csrf);
                setSigned(true);
                setPassword("");
              });
            }}
          >
            <label>
              Vault password
              <input
                autoComplete="current-password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </label>
            <Button disabled={busy}>
              Unlock vault <ArrowUpRight size={17} />
            </Button>
          </form>
          <Button variant="outline" disabled={busy} onClick={() => run(async () => {
            const session = await recoverDesktopSession();
            setCsrf(session.csrf);
            setSigned(true);
            setPassword("");
          })}>Forgot password? Recover access</Button>
          <p>The installed desktop app uses your Windows account to recover access. Reopen it from the tray if sign-in expires.</p>
          {error && (
            <p role="alert" className="error-text">
              {error}
            </p>
          )}
          <small>
            <ShieldCheck size={15} /> Local-first. Original files stay
            untouched.
          </small>
        </div>
      </main>
    );
  return (
    <div className="app">
      <aside className={menu ? "open" : ""}>
        <div className="brand">
          <span>
            <Archive size={23} />
          </span>
          TubeVault<span className="version">LOCAL</span>
        </div>
        <div className="nav-label">WORKSPACE</div>
        <nav>
          {pages.map(([name, Icon]) => (
            <button
              key={name}
              className={page === name ? "selected" : ""}
              onClick={() => {
                setPage(name);
                setMenu(false);
                setSearch("");
              }}
            >
              <Icon size={19} />
              {name}
              {name === "Upload Queue" && queued.length > 0 && (
                <b>{queued.length}</b>
              )}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <ShieldCheck size={19} />
          <div>
            <strong>Originals stay original</strong>
            <small>No compression or automatic deletion.</small>
          </div>
        </div>
        <div className="account">
          <div className="avatar">TV</div>
          <div>
            <strong>{data?.account?.name || "Personal vault"}</strong>
            <small>
              {data?.account?.connected
                ? "YouTube channel linked"
                : "YouTube not connected"}
            </small>
          </div>
          <button
            aria-label="Toggle color theme"
            onClick={() => setLight(!light)}
          >
            {light ? <Moon size={17} /> : <Sun size={17} />}
          </button>
        </div>
      </aside>
      <main className="workspace">
        <header>
          <button
            className="mobile-menu"
            aria-label="Open navigation"
            onClick={() => setMenu(!menu)}
          >
            <Menu />
          </button>
          <span>
            Personal workspace <span className="crumb">/ {page}</span>
          </span>
          <div className="local-status">
            <i /> Running locally <span>·</span> Windows PC
          </div>
        </header>
          <div className="content">
            {data?.preview && <div className="alert" role="status">UI preview · Sample data only · No real files or YouTube uploads</div>}
          <div className="page-heading">
            <div>
              <div className="eyebrow">YOUR PERSONAL VIDEO ARCHIVE</div>
              <h1>{page === "Overview" ? "A home for every memory." : page}</h1>
              <p>
                {page === "Overview"
                  ? "Keep the moments. Let TubeVault handle the archiving."
                  : (
                      {
                        "Upload Queue":
                          "Review, prioritize and follow your original uploads.",
                        "Watch Folders":
                          "One parent folder. A collection for every child directory.",
                        Playlists:
                          "Durable connections between your folders and YouTube.",
                        "Archive History":
                          "A lasting record of every verified upload.",
                        "iPhone Imports":
                          "From your camera roll to your own PC, in original quality.",
                        Settings: "Make the vault work on your terms.",
                        Diagnostics: "Understand the health of your archive.",
                      } as Record<string, string>
                    )[page]}
              </p>
            </div>
            <div className="heading-actions">
              <Button
                variant="outline"
                disabled={busy}
                onClick={() => run(() => api("/scan", "POST"))}
              >
                <RefreshCw size={16} /> Scan now
              </Button>
              <Button
                onClick={() => {
                  setPage("Watch Folders");
                  setAdd(true);
                }}
              >
                <Plus size={17} /> Add folder
              </Button>
            </div>
          </div>
          {error && (
            <div className="alert" role="alert">
              {error}
              <button aria-label="Dismiss error" onClick={() => setError("")}>
                <X size={16} />
              </button>
            </div>
          )}
          {busy && (
            <div className="working">
              <LoaderCircle size={15} /> Working…
            </div>
          )}
          {page === "Overview" && (
            <>
              <section className="stats">
                {[
                  [
                    Video,
                    "Videos discovered",
                    String(data?.stats?.discovered ?? data?.instances.length ?? 0),
                    "Across your watched folders",
                  ],
                  [
                    ShieldCheck,
                    "Safely archived",
                    String(data?.stats?.archived ?? done.length),
                    "Processing and playlist verified",
                  ],
                  [
                    CloudUpload,
                    "In the queue",
                    String(data?.stats?.queued ?? queued.length),
                    settings?.paused
                      ? "Paused · ready when you are"
                      : "Uploads enabled",
                  ],
                  [
                    HardDrive,
                    "Source bytes archived",
                    bytes(data?.stats?.bytes ?? done.reduce((n, j) => n + j.size, 0)),
                    "Original source file sizes",
                  ],
                ].map(([Icon, label, value, hint]) => {
                  const I = Icon as typeof Video;
                  return (
                    <article key={String(label)}>
                      <div>
                        <span>{String(label)}</span>
                        <I size={19} />
                      </div>
                      <strong>{String(value)}</strong>
                      <small>{String(hint)}</small>
                    </article>
                  );
                })}
              </section>
              <div className="overview-grid">
                <section className="panel upload-panel">
                  <div className="panel-heading">
                    <h2>
                      <CloudUpload size={18} /> Upload activity
                    </h2>
                    <span className="badge">
                      {settings?.paused ? "Queue paused" : "Queue enabled"}
                    </span>
                  </div>
                  {active ? (
                    <>
                      <h3>{active.title}</h3>
                      <p>{active.playlist}</p>
                      <progress value={active.progress} max={active.size} />
                      <div className="between">
                        <span>
                          {bytes(active.progress)} of {bytes(active.size)}
                        </span>
                        <strong>
                          {percent(active.progress, active.size)}%
                        </strong>
                      </div>
                    </>
                  ) : (
                    <div className="upload-empty">
                      <div className="orbit">
                        <CloudUpload size={29} />
                      </div>
                      <h3>
                        {queued.length
                          ? "Your videos are ready when you are."
                          : "Ready for your next adventure."}
                      </h3>
                      <p>
                        {queued.length
                          ? "Review the queue, then start archiving."
                          : "Add a folder to begin building your personal archive."}
                      </p>
                    </div>
                  )}
                  <div className="upload-footer">
                    <span>
                      <ShieldCheck size={15} /> Private by default · Original
                      quality
                    </span>
                    <Button
                      variant="outline"
                      onClick={() =>
                        run(() =>
                          api(
                            `/queue/${settings?.paused ? "resume" : "pause"}`,
                            "POST",
                          ),
                        )
                      }
                    >
                      {settings?.paused ? (
                        <Play size={15} />
                      ) : (
                        <Pause size={15} />
                      )}{" "}
                      {settings?.paused ? "Start queue" : "Pause queue"}
                    </Button>
                  </div>
                </section>
                <section className="panel phone-card">
                  <div className="phone-top">
                    <Smartphone size={25} />
                    <span className="badge">ON YOUR WI-FI</span>
                  </div>
                  <h2>
                    Big memories.
                    <br />
                    Small screen.
                  </h2>
                  <p>
                    Bring your iPhone videos into the vault. No cables. No
                    re-encoding.
                  </p>
                  <Button
                    variant="outline"
                    onClick={() => setPage("iPhone Imports")}
                  >
                    Import from iPhone <ArrowUpRight size={16} />
                  </Button>
                </section>
              </div>
              <section className="panel">
                <div className="panel-heading">
                  <h2>Recent videos</h2>
                  <button
                    className="text-link"
                    onClick={() => setPage("Upload Queue")}
                  >
                    View queue <ArrowUpRight size={15} />
                  </button>
                </div>
                {active && <div className="queue-tools"><strong>Current upload: {active.title}</strong><Button onClick={()=>run(()=>api(`/jobs/${active.id}/pause`,"POST"))}>Pause this video</Button><Button onClick={()=>run(()=>api(`/jobs/${active.id}/cancel`,"POST"))}>Cancel this video</Button><small>The next eligible video continues while this one is held.</small></div>}
                {table(jobs.slice(0, 5))}
              </section>
              <div className="overview-grid lower">
                <section className="panel">
                  <div className="panel-heading">
                    <h2>Recent activity</h2>
                    <span className="muted">Live</span>
                  </div>
                  <Activity events={data?.events.slice(0, 5) || []} />
                </section>
                <section className="panel health">
                  <h2>Vault at a glance</h2>
                  <p>
                    <span>Watched folders</span>
                    <strong>{data?.watches.length || 0}</strong>
                  </p>
                  <p>
                    <span>Needs attention</span>
                    <strong>{failed.length}</strong>
                  </p>
                  <p>
                    <span>Skipped files</span>
                    <strong>
                      {data?.instances.filter(
                        (i) =>
                          i.reason !== "QUEUED" && i.reason !== "STABILIZING",
                      ).length || 0}
                    </strong>
                  </p>
                  <p>
                    <span>YouTube connection</span>
                    <span className="badge">
                      {data?.account?.connected ? "Linked" : "Not connected"}
                    </span>
                  </p>
                </section>
              </div>
            </>
          )}
          {page === "Upload Queue" && <QueuePanel jobs={jobs} settings={settings} desktop={!!setupStatus?.desktop} refresh={load} details={id=>actions(jobs.find(j=>j.id===id)!)}/>}
          {page === "Archive History" && !data?.preview && <CleanupPanel paused={!!settings?.paused} />}
          {page === "Archive History" && (
            <section className="panel">
              <div className="panel-heading">
                <label className="search">
                  <Search size={17} />
                  <input
                    placeholder="Search videos or collections"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                  />
                </label>
              </div>
              {table(
                (page === "Archive History"
                  ? done
                  : jobs.filter((j) => j.state !== "COMPLETED")
                ).filter((j) =>
                  (j.title + j.playlist + j.sha256)
                    .toLowerCase()
                    .includes(search.toLowerCase()),
                ),
              )}
              {page === "Archive History" &&
                done.map((j) => (
                  <details key={j.id} className="details">
                    <summary>{j.title} · checksum and source</summary>
                    <code>{j.sha256}</code>
                    <p>{j.path}</p>
                    <Button
                      variant="outline"
                      onClick={() => {
                        if (
                          confirm(
                            "Upload this completed video again? This explicitly creates a duplicate on YouTube.",
                          )
                        )
                          run(() => api(`/jobs/${j.id}/force`, "POST"));
                      }}
                    >
                      Force another upload
                    </Button>
                  </details>
                ))}
            </section>
          )}
          {page === "Watch Folders" && (
            <>
              <div className="cards">
                {data?.watches.map((w) => (
                  <section className="panel folder-card" key={w.id}>
                    <Folder size={29} />
                    <h2>{w.path.split(/[\\/]/).pop()}</h2>
                    <p className="path">{w.path}</p>
                    <WatchForm
                      watch={w}
                      save={(v) => run(() => api(`/watches/${w.id}`, "PUT", v))}
                    />
                  </section>
                ))}
              </div>
              <section className="panel">
                <div className="panel-heading">
                  <h2>Discovery preview & exclusions</h2>
                </div>
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Source</th>
                        <th>Discovery result</th>
                        <th>Size</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data?.instances.map((i) => (
                        <tr key={i.id}>
                          <td className="path">{i.path}</td>
                          <td>{i.reason}</td>
                          <td>{bytes(i.size)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            </>
          )}
          {page === "Playlists" && (
            <div className="cards">
              {data?.mappings.map((m) => (
                <section className="panel folder-card" key={m.id}>
                  <ListVideo size={28} />
                  <h2>{m.title}</h2>
                  <p className="path">{m.path}</p>
                  <form
                    onSubmit={(e) => {
                      e.preventDefault();
                      const f = new FormData(e.currentTarget);
                      run(() =>
                        api(`/mappings/${m.id}`, "PUT", {
                          title: f.get("title"),
                          privacy: f.get("privacy"),
                          playlist_id: f.get("playlist") || null,
                        }),
                      );
                    }}
                  >
                    <label>
                      Local display name
                      <input name="title" defaultValue={m.title} />
                    </label>
                    <label>
                      Privacy for new uploads
                      <PrivacySelect name="privacy" defaultValue={m.privacy} />
                    </label>
                    <label>
                      YouTube playlist ID
                      <input
                        name="playlist"
                        defaultValue={m.playlist_id || ""}
                        placeholder="Auto-create or paste an owned playlist ID"
                      />
                    </label>
                    <small>
                      Existing YouTube privacy and titles are never changed
                      silently.
                    </small>
                    <Button variant="outline">Save mapping</Button>
                  </form>
                </section>
              ))}
              {!data?.mappings.length && (
                <Empty
                  title="Collections appear after a scan"
                  text="Each child folder receives a durable playlist mapping."
                />
              )}
            </div>
          )}
          {page === "iPhone Imports" && (
            <>
              {setupStatus?.desktop && <PhoneReceiverPanel refresh={load} />}
              <details className="panel"><summary className="queue-tools">Import videos selected on this PC</summary>
              <section className="import-panel">
                <Smartphone size={36} />
                <h2>Keep the original. Bring it home.</h2>
                <p>
                  Keep Safari open and your PC reachable throughout the
                  transfer.
                </p>
                <label>
                  Destination collection
                  <input
                    value={collection}
                    onChange={(e) => setCollection(e.target.value)}
                  />
                </label>
                <label className="dropzone">
                  <CloudUpload size={32} />
                  <strong>Select original videos</strong>
                  <span>MP4, MOV, MKV and other supported containers</span>
                  <input
                    type="file"
                    multiple
                    accept="video/*,.mkv,.mts,.m2ts"
                    disabled={busy}
                    onChange={(e) => {
                      const files = Array.from(e.target.files || []);
                      run(async () => {
                        for (const f of files)
                          await transfer(f, collection, (n) =>
                            setProgress((p) => ({ ...p, [f.name]: n })),
                          );
                      });
                    }}
                  />
                </label>
                {Object.entries(progress).map(([name, n]) => (
                  <div key={name}>
                    <div className="between">
                      <span>{name}</span>
                      <span>{Math.round(n)}%</span>
                    </div>
                    <progress value={n} max={100} />
                  </div>
                ))}
                <p className="muted">
                  Select the same file and collection to resume an interrupted copy.
                </p>
              </section>
              </details>
              <section className="panel">
                <div className="panel-heading">
                  <h2>Incoming transfers</h2>
                </div>
                {data?.imports.map((t) => (
                  <div key={t.id} className="transfer">
                    <span>
                      {t.filename}
                      <small>
                        {t.collection} · {bytes(t.size)}
                      </small>
                    </span>
                    <span className="badge">{t.state.toLowerCase()}</span>
                    <progress value={t.offset} max={t.size} />
                  </div>
                ))}
              </section>
            </>
          )}
          {page === "Settings" && settings && (
            <div className="settings-grid">
              <section className="panel settings-panel"><h2>Getting started & desktop</h2><p>Connect Google, choose folders and configure automatic backups with the setup guide.</p><Button onClick={()=>setShowGuide(true)}>Open setup guide</Button>{setupStatus?.desktop&&<label className="check" style={{marginTop:20}}><input type="checkbox" checked={setupStatus.startup_enabled} onChange={e=>run(async()=>{await api('/desktop/startup','PUT',{enabled:e.target.checked});setSetupStatus(await api('/setup/status'));})}/> Start at Windows sign-in</label>}</section>
              <section className="panel settings-panel">
                <h2>YouTube account</h2>
                <p>{data?.account?.name || "No channel connected"}</p>
                <code>
                  {data?.account?.id ||
                    "Google Desktop OAuth credentials required"}
                </code>
                <p>
                  Connect on the Windows PC. Consent opens in your system
                  browser.
                </p>
                <div className="heading-actions">
                  <Button
                    disabled={busy}
                    onClick={() => run(() => api("/account/connect", "POST"))}
                  >
                    Connect / reconnect
                  </Button>
                  <Button
                    variant="outline"
                    onClick={() =>
                      run(() => api("/account/disconnect", "POST"))
                    }
                  >
                    Disconnect
                  </Button>
                </div>
              </section>
              <SettingsForm
                settings={settings}
                save={(v) => run(() => api("/settings", "PUT", v))}
              />
              <section className="panel settings-panel">
                <h2>Security & access</h2>
                <p>The desktop window signs in securely using your Windows account. Browser access requires a separate session. The desktop server listens on localhost only.</p>
                <Button
                  variant="outline"
                  onClick={() =>
                    run(async () => {
                      await api("/logout", "POST");
                      setSigned(false);
                    })
                  }
                >
                  Sign out
                </Button>
              </section>
            </div>
          )}
          {page === "Diagnostics" && (
            <>
              <section className="stats">
                <article>
                  <span>Queue state</span>
                  <strong>{settings?.paused ? "Paused" : "Enabled"}</strong>
                </article>
                <article>
                  <span>Quota cooldown</span>
                  <strong>
                    {settings?.cooldown > Date.now() / 1000
                      ? "Waiting"
                      : "Clear"}
                  </strong>
                  <small>
                    {settings?.cooldown > Date.now() / 1000
                      ? new Date(settings.cooldown * 1000).toLocaleString()
                      : "Actual quota is managed by Google"}
                  </small>
                </article>
                <article>
                  <span>Attention required</span>
                  <strong>{failed.length}</strong>
                </article>
              </section>
              <section className="panel">
                <div className="panel-heading">
                  <h2>Audit & synchronization events</h2>
                </div>
                <Activity events={data?.events || []} />
              </section>
            </>
          )}
          <footer>
            <span>
              <ShieldCheck size={14} /> Your files stay yours. Always.
            </span>
            <span>TubeVault · Local-first archiving</span>
          </footer>
        </div>
      </main>
      {showGuide && <SetupGuide onClose={()=>{setShowGuide(false);api<SetupStatus>('/setup/status').then(setSetupStatus).catch(()=>{});}} onChange={load}/>}
      {add && (
        <div
          className="modal"
          role="dialog"
          aria-modal="true"
          aria-label="Add watch folder"
        >
          <div className="panel">
            <div className="panel-heading">
              <h2>Add a watch folder</h2>
              <button aria-label="Close dialog" onClick={() => setAdd(false)}>
                <X />
              </button>
            </div>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                run(async () => {
                  await api("/watches", "POST", {
                    path,
                    privacy: settings?.privacy || "private",
                  });
                  setAdd(false);
                  setPath("");
                });
              }}
            >
              <label>
                Absolute Windows directory
                <input
                  autoFocus
                  placeholder="D:\ACTION Camera"
                  value={path}
                  onChange={(e) => setPath(e.target.value)}
                  required
                />
              </label>
              <p>
                Child folders become collections. Root videos go to an Unsorted
                collection. The queue starts paused for review.
              </p>
              <Button disabled={busy}>Add folder</Button>
            </form>
          </div>
        </div>
      )}
      {edit && (
        <div
          className="modal"
          role="dialog"
          aria-modal="true"
          aria-label="Edit video metadata"
        >
          <form
            className="panel"
            onSubmit={(e) => {
              e.preventDefault();
              run(async () => {
                await api(`/jobs/${edit.id}/metadata`, "PUT", edit);
                setEdit(null);
              });
            }}
          >
            <h2>Video metadata</h2>
            <label>
              Title
              <input
                value={edit.title}
                onChange={(e) => setEdit({ ...edit, title: e.target.value })}
              />
            </label>
            <label>
              Description
              <textarea
                value={edit.description}
                onChange={(e) =>
                  setEdit({ ...edit, description: e.target.value })
                }
              />
            </label>
            <label>
              Privacy
              <PrivacySelect
                value={edit.privacy}
                onChange={(e) => setEdit({ ...edit, privacy: e.target.value })}
              />
            </label>
            <label>
              Tags, comma separated
              <input
                value={edit.tags.join(",")}
                onChange={(e) =>
                  setEdit({
                    ...edit,
                    tags: e.target.value.split(",").filter(Boolean),
                  })
                }
              />
            </label>
            <label className="check">
              <input
                type="checkbox"
                checked={edit.made_for_kids}
                onChange={(e) =>
                  setEdit({ ...edit, made_for_kids: e.target.checked })
                }
              />{" "}
              Made for kids
            </label>
            <div className="heading-actions">
              <Button>Save metadata</Button>
              <Button
                type="button"
                variant="outline"
                onClick={() => setEdit(null)}
              >
                Cancel
              </Button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
function Empty({ title, text }: { title: string; text: string }) {
  return (
    <div className="empty">
      <Archive size={27} />
      <h3>{title}</h3>
      <p>{text}</p>
    </div>
  );
}
function PrivacySelect(props: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select {...props}>
      <option value="private">Private</option>
      <option value="unlisted">Unlisted</option>
      <option value="public">Public</option>
    </select>
  );
}
function Activity({ events }: { events: any[] }) {
  return (
    <div className="activity">
      {events.length ? (
        events.map((e) => (
          <div key={e.id}>
            <span className="event-dot" />
            <div>
              <p>{e.message}</p>
              <small>{new Date(e.at * 1000).toLocaleString()}</small>
            </div>
          </div>
        ))
      ) : (
        <p className="muted">Activity will appear as your archive grows.</p>
      )}
    </div>
  );
}
function WatchForm({ watch, save }: { watch: any; save: (v: any) => void }) {
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        const f = new FormData(e.currentTarget);
        save({
          ...watch,
          enabled: f.has("enabled"),
          automatic: f.has("automatic"),
          unsorted: f.has("unsorted"),
          depth: Number(f.get("depth")),
          stability: Number(f.get("stability")),
          privacy: f.get("privacy"),
          excludes: String(f.get("excludes")).split("\n").filter(Boolean),
        });
      }}
    >
      <div className="form-pair">
        <label>
          Scan depth
          <input
            type="number"
            min="0"
            max="50"
            name="depth"
            defaultValue={watch.depth}
          />
        </label>
        <label>
          Stable for (seconds)
          <input
            type="number"
            min="1"
            name="stability"
            defaultValue={watch.stability}
          />
        </label>
      </div>
      <label>
        Privacy
        <PrivacySelect name="privacy" defaultValue={watch.privacy} />
      </label>
      <label>
        Exclude patterns (one per line)
        <textarea
          name="excludes"
          defaultValue={watch.excludes.join("\n")}
          placeholder="*.tmp&#10;Private/*"
        />
      </label>
      {[
        ["enabled", "Watch enabled"],
        ["automatic", "Scan automatically"],
        ["unsorted", "Include root videos"],
      ].map(([key, label]) => (
        <label className="check" key={key}>
          <input type="checkbox" name={key} defaultChecked={watch[key]} />
          {label}
        </label>
      ))}
      <Button variant="outline">Save folder</Button>
    </form>
  );
}
function SettingsForm({
  settings,
  save,
}: {
  settings: any;
  save: (v: any) => void;
}) {
  return (
    <form
      className="panel settings-panel"
      onSubmit={(e) => {
        e.preventDefault();
        const f = new FormData(e.currentTarget);
        save({
          ...settings,
          mode: f.get("mode"),
          timezone: f.get("timezone"),
          start_hour: Number(f.get("start")),
          end_hour: Number(f.get("end")),
          concurrency: Number(f.get("concurrency")),
          bandwidth_kbps: Number(f.get("bandwidth")),
          pause_metered: f.has("metered"),
          privacy: f.get("privacy"),
          title_template: f.get("title"),
          description_template: f.get("description"),
          sort: f.get("sort"),
          notifications: f.has("notifications"),
        });
      }}
    >
      <h2>Upload preferences</h2>
      <label>
        Upload mode
        <select name="mode" defaultValue={settings.mode}>
          <option value="manual">Manual — wait for Start queue</option>
          <option value="automatic">Automatic</option>
          <option value="scheduled">Scheduled</option>
        </select>
      </label>
      <div className="form-pair">
        <label>
          Start hour
          <input
            name="start"
            type="number"
            min="0"
            max="23"
            defaultValue={settings.start_hour}
          />
        </label>
        <label>
          End hour
          <input
            name="end"
            type="number"
            min="0"
            max="23"
            defaultValue={settings.end_hour}
          />
        </label>
      </div>
      <label>
        Timezone
        <input name="timezone" defaultValue={settings.timezone} />
      </label>
      <div className="form-pair">
        <label>
          Concurrent uploads
          <input
            name="concurrency"
            type="number"
            min="1"
            max="4"
            defaultValue={settings.concurrency}
          />
        </label>
        <label>
          KB/s per worker (0 = unlimited)
          <input
            name="bandwidth"
            type="number"
            min="0"
            defaultValue={settings.bandwidth_kbps}
          />
        </label>
      </div>
      <label>
        Default privacy
        <PrivacySelect name="privacy" defaultValue={settings.privacy} />
      </label>
      <label>
        Title template
        <input name="title" defaultValue={settings.title_template} />
      </label>
      <label>
        Description template
        <textarea
          name="description"
          defaultValue={settings.description_template}
        />
      </label>
      <small>
        Available tokens: {"{filename}"} and {"{folder}"}
      </small>
      <label>
        Discovery order
        <select name="sort" defaultValue={settings.sort}>
          <option value="name">Filename</option>
          <option value="date">File modification date</option>
        </select>
      </label>
      <label className="check">
        <input
          name="metered"
          type="checkbox"
          defaultChecked={settings.pause_metered}
        />{" "}
        Pause on metered or unknown networks
      </label>
      <label className="check">
        <input
          name="notifications"
          type="checkbox"
          defaultChecked={settings.notifications}
        />{" "}
        Record archive notifications
      </label>
      <Button>Save preferences</Button>
    </form>
  );
}
createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
