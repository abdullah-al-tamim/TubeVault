import { useEffect, useState } from "react";
import { api } from "../api";
import { Button } from "./ui/button";

type Network = { address: string; name: string };
type Status = { active: boolean; paired: boolean; completed: number; expires: number; pair_expires: number; collection: string; queue_paused?: boolean; folder?: string };
type Invitation = Status & { url: string; qr: string };

export function PhoneReceiverPanel({ refresh }: { refresh: () => Promise<void> }) {
  const [networks, setNetworks] = useState<Network[]>([]);
  const [address, setAddress] = useState("");
  const [collection, setCollection] = useState("iPhone memories");
  const [trusted, setTrusted] = useState(false);
  const [status, setStatus] = useState<Status | null>(null);
  const [invitation, setInvitation] = useState<Invitation | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function loadStatus() {
    const result = await api<Status>("/phone/status");
    setStatus(result);
    return result;
  }

  async function loadNetworks() {
    const list = await api<Network[]>("/phone/networks");
    setNetworks(list);
    setAddress(current => list.some(item => item.address === current) ? current : list[0]?.address || "");
  }

  useEffect(() => {
    let alive = true;
    api<Status>("/phone/status").then(value => { if (alive) setStatus(value); }).catch(error => { if (alive) setError(error.message); });
    loadNetworks().catch(error => { if (alive) setError(error.message); });
    const interval = window.setInterval(() => {
      if (alive) loadStatus().catch(() => {});
    }, 2500);
    return () => { alive = false; window.clearInterval(interval); };
  }, []);

  async function run(action: () => Promise<void>) {
    setBusy(true); setError("");
    try { await action(); await loadStatus(); }
    catch (error) { setError(error instanceof Error ? error.message : "Could not start receiving"); }
    finally { setBusy(false); }
  }

  return <section className="panel">
    <div className="panel-heading"><h2>Receive from iPhone</h2></div>
    <div className="queue-tools">
      <p>1. Connect your iPhone and PC to the same trusted Wi-Fi. The PC can also use Ethernet on that network.</p>
      <p>2. Start receiving, then scan the QR code with your iPhone Camera and open the link in Safari.</p>
      <p>3. Tap Choose videos, select from your photo library, then tap Send to PC. Keep Safari open until copying finishes.</p>
      {error && <p role="alert">{error}</p>}
      {!status?.active ? <>
        <label>PC connection
          <select aria-label="PC connection" value={address} disabled={busy} onChange={event => setAddress(event.target.value)}>
            {networks.map(network => <option key={network.address} value={network.address}>{network.name} · {network.address}</option>)}
            {!networks.length && <option value="">Connect to Wi-Fi first</option>}
          </select>
        </label>
        <Button variant="outline" disabled={busy} onClick={() => run(loadNetworks)}>Refresh connections</Button>
        <label>Destination collection
          <input value={collection} disabled={busy} onChange={event => setCollection(event.target.value)} />
        </label>
        <label className="check">
          <input type="checkbox" checked={trusted} disabled={busy} onChange={event => setTrusted(event.target.checked)} />
          I trust this Wi-Fi. Local transfers use HTTP and are not encrypted.
        </label>
        <Button disabled={busy || !trusted || !address || !collection.trim()} onClick={() => run(async () => {
          const result = await api<Invitation>("/phone/start", "POST", { address, collection: collection.trim(), trusted_wifi: true });
          setInvitation(result);
        })}>Start receiving</Button>
      </> : <>
        <p role="status">{status.paired ? "iPhone paired" : "Waiting for your iPhone"} · {status.completed} video(s) saved to PC · Collection {status.collection}</p>
        {!status.paired && invitation && status.pair_expires > Date.now() / 1000 && <>
          <img src={invitation.qr} alt="Scan with your iPhone Camera to pair with TubeVault" width={260} height={260} />
          <div><p>Scan within 10 minutes. Keep this link private.</p><a href={invitation.url} target="_blank" rel="noreferrer">Open transfer page</a><p>{invitation.url.split("/#")[0]}</p></div>
        </>}
        {!status.paired && (!invitation || status.pair_expires <= Date.now() / 1000) && <p>Stop receiving and start again to show a fresh QR code.</p>}
        <p>Receiving ends at {new Date(status.expires * 1000).toLocaleTimeString()}. Use Stop receiving when you finish.</p>
        <Button variant="outline" disabled={busy} onClick={() => run(async () => { await api("/phone/stop", "POST"); setInvitation(null); })}>Stop receiving</Button>
      </>}
      <p>Videos stay on this PC in the iPhone inbox. Complete transfers enter the upload queue automatically.</p>
      {status?.queue_paused ? <>
        <p>The YouTube queue is paused. Starting it will also allow existing queued videos to upload.</p>
        <Button disabled={busy} onClick={() => run(async () => { await api("/queue/resume", "POST"); await refresh(); })}>Start YouTube queue</Button>
      </> : <p>The YouTube queue is enabled and will use your current upload limits and schedule.</p>}
      <details><summary>Phone cannot connect?</summary>
        <p>Check that both devices use the same home network and disconnect any VPN that blocks local connections. Guest Wi-Fi can block devices from reaching one another. If Windows asks, allow TubeVault on Private networks only. Stop receiving before changing networks. No router setup is required.</p>
      </details>
      <p>Originals remain locally until you choose cleanup in Archive History after verified uploading.</p>
    </div>
  </section>;
}
