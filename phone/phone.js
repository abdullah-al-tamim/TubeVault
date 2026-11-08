"use strict";
const connection = document.querySelector("#connection");
const sender = document.querySelector("#sender");
const videos = document.querySelector("#videos");
const send = document.querySelector("#send");
const cancel = document.querySelector("#cancel");
const progress = document.querySelector("#progress");
const testConnection = document.querySelector("#test-connection");
const connectionResult = document.querySelector("#connection-result");
const invitation = new URLSearchParams(location.hash.slice(1)).get("pair");
history.replaceState(null, "", "/");
let token = sessionStorage.getItem("tubevault-phone-session") || "";
let paused = false;
let running = false;
let currentRequest;
const selected = () => Array.from(videos.files || []);
function text(element, message) { element.textContent = message; }
function megabytes(bytes) { return (bytes / 1024 / 1024).toFixed(1) + " MB"; }
async function request(path, method = "GET", body) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), path.endsWith("/finish") ? 120000 : 10000);
  let response;
  try {
    response = await fetch(path, {
      method, signal: controller.signal,
      headers: {Authorization: "Bearer " + token, "Content-Type": "application/json"},
      body: body === undefined ? undefined : JSON.stringify(body)
    });
  } finally { clearTimeout(timer); }
  if (!response.ok) {
    let message = "Connection interrupted. Select the same videos to resume.";
    try { message = (await response.json()).detail || message; } catch {}
    const error = new Error(message);
    error.status = response.status;
    throw error;
  }
  return response.json();
}
async function pair() {
  try {
    if (invitation) {
      const response = await request("/pair", "POST", {invitation});
      token = response.token;
      sessionStorage.setItem("tubevault-phone-session", token);
    }
    const state = await request("/status");
    text(connection, state.queue_paused ? "Connected. Videos will be saved to your PC. Start the upload queue on the PC when ready."
      : "Connected. Completed videos will be queued for YouTube.");
    text(document.querySelector("#collection"), "Collection · " + state.collection);
    sender.hidden = false;
  } catch (error) { text(connection, error.message); }
}
videos.addEventListener("change", () => {
  const files = selected();
  send.disabled = running || !files.length;
  text(document.querySelector("#selection"), files.length + " video(s) selected");
});
function copyChunk(id, offset, block, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    let settled = false;
    let pollTimer;
    const finish = (error, result) => {
      if (settled) return;
      settled = true; clearTimeout(pollTimer);
      if (currentRequest === xhr) currentRequest = undefined;
      if (error) reject(error); else resolve(result);
    };
    const poll = async () => {
      try {
        const state = await request("/files/" + encodeURIComponent(id));
        if (settled) return;
        if (state.offset >= offset + block.byteLength) {
          // The disk/DB commit is authoritative even if its PUT response was lost.
          finish(null, {offset: state.offset}); xhr.abort(); return;
        }
        onProgress(0, state.receiving);
      } catch { /* The upload's timeout and resume check handle a lost connection. */ }
      if (!settled) pollTimer = setTimeout(poll, 2000);
    };
    currentRequest = xhr;
    xhr.open("PUT", "/files/" + encodeURIComponent(id) + "?offset=" + offset);
    xhr.setRequestHeader("Authorization", "Bearer " + token);
    xhr.setRequestHeader("Content-Type", "application/octet-stream");
    xhr.timeout = 30000;
    xhr.upload.onprogress = event => { if (!settled) onProgress(event.loaded); };
    xhr.ontimeout = () => finish(new Error("The connection stalled for 30 seconds."));
    xhr.onload = () => {
      if (xhr.status === 200) {
        try { finish(null, JSON.parse(xhr.responseText)); }
        catch { finish(new Error("The PC response was interrupted.")); }
      }
      else {
        let message = "Copy interrupted. Tap Send to PC to resume.";
        try { message = JSON.parse(xhr.responseText).detail || message; } catch {}
        const error = new Error(message); error.status = xhr.status;
        finish(error);
      }
    };
    xhr.onerror = () => finish(new Error("Connection lost."));
    xhr.onabort = () => finish(new Error("Transfer paused. Tap Send to PC to continue."));
    pollTimer = setTimeout(poll, 2000);
    xhr.send(block);
  });
}
testConnection.addEventListener("click", async () => {
  testConnection.disabled = true;
  videos.disabled = true; send.disabled = true;
  text(connectionResult, "Testing phone → PC with a 1 MB sample…");
  const xhr = new XMLHttpRequest();
  const sample = new Uint8Array(1024 * 1024);
  // Random bytes avoid compression making the link appear faster than it is.
  for (let offset = 0; offset < sample.length; offset += 65536) {
    crypto.getRandomValues(sample.subarray(offset, offset + 65536));
  }
  const started = performance.now();
  xhr.open("POST", "/connection-test");
  xhr.setRequestHeader("Authorization", "Bearer " + token);
  xhr.timeout = 60000;
  xhr.onload = () => {
    if (xhr.status !== 200) {
      text(connectionResult, "Test could not finish. Check the PC receiving session and try again.");
    } else {
      const seconds = Math.max(.01, (performance.now() - started) / 1000);
      text(connectionResult, "Phone → PC: " + (1 / seconds).toFixed(2) + " MB/s (1 MB in "
        + seconds.toFixed(1) + " seconds). " + (seconds > 5
          ? "The local connection is slow. Keep Safari open; check both devices use the same main Wi-Fi and temporarily disconnect any VPN."
          : "Sample transfer is quick. If videos are slow, check whether Photos is downloading originals from iCloud or preparing the selected videos."));
    }
  };
  xhr.onerror = xhr.ontimeout = () => text(connectionResult,
    "Connection test stalled. Keep Safari open and check both devices are on the same main Wi-Fi.");
  xhr.onloadend = () => {
    testConnection.disabled = running; videos.disabled = running;
    send.disabled = running || !selected().length;
  };
  xhr.send(sample);
});
cancel.addEventListener("click", () => { paused = true; if (currentRequest) currentRequest.abort(); });
send.addEventListener("click", async () => {
  if (running) return;
  running = true; paused = false; send.disabled = true; videos.disabled = true; cancel.hidden = false;
  testConnection.disabled = true;
  progress.replaceChildren();
  for (const file of selected()) {
    if (paused) break;
    const row = document.createElement("article");
    const title = document.createElement("strong");
    const detail = document.createElement("small");
    const bar = document.createElement("progress");
    bar.max = file.size; bar.value = 0;
    title.textContent = file.name;
    row.append(title, detail, bar); progress.append(row);
    const started = performance.now();
    let initialOffset = 0;
    const key = "tubevault-copy:" + JSON.stringify([file.name, file.size, file.lastModified]);
    try {
      let id = sessionStorage.getItem(key);
      if (!id) {
        id = (await request("/files", "POST", {filename: file.name, size: file.size})).id;
        sessionStorage.setItem(key, id);
      }
      let state = await request("/files/" + encodeURIComponent(id));
      let offset = state.offset;
      initialOffset = offset;
      bar.value = offset;
      text(detail, "Preparing to copy " + megabytes(file.size) + "…");
      if (state.state !== "INGESTED") {
        let failures = 0;
        while (offset < file.size) {
          if (paused) throw new Error("Transfer paused. Tap Send to PC to continue.");
          // Materialize a small slice first so Photos/file reading is separate
          // from sending. Never hold the full video in phone memory.
          text(detail, "Reading next part from the phone…");
          const block = await file.slice(offset, offset + 512 * 1024).arrayBuffer();
          if (paused) throw new Error("Transfer paused. Tap Send to PC to continue.");
          try {
            const result = await copyChunk(id, offset, block, (loaded, remote) => {
              const received = remote && remote.chunk_offset === offset ? remote.received : loaded;
              bar.value = offset + received;
              const copied = offset + received;
              const seconds = Math.max(.1, (performance.now() - started) / 1000);
              const speed = megabytes((copied - initialOffset) / seconds) + "/s";
              let stage = "Sending next part to PC…";
              if (remote && remote.chunk_offset === offset) {
                stage = remote.stage === "saving" ? "PC is saving received bytes…"
                  : "PC has received " + megabytes(remote.received) + " of this part…";
              } else if (loaded === block.byteLength) {
                stage = "Sent by browser · checking PC receipt…";
              }
              text(detail, Math.min(100, Math.floor(copied / file.size * 100)) + "% · "
                + megabytes(copied) + " / " + megabytes(file.size) + " · " + speed
                + " · " + stage);
            });
            if (!Number.isInteger(result.offset) || result.offset <= offset || result.offset > file.size) {
              throw new Error("PC returned an invalid saved position.");
            }
            offset = result.offset;
            bar.value = offset; failures = 0;
          } catch (error) {
            if (paused || [400,401,403,404,413].includes(error.status)) throw error;
            failures += 1;
            if (failures > 3) throw new Error(error.message + " Copy paused after three retries. Tap Send to PC to resume.");
            text(detail, error.message + " Checking saved position and retrying (" + failures + "/3)…");
            await new Promise(resolve => setTimeout(resolve, failures * 1000));
            if (paused) throw new Error("Transfer paused. Tap Send to PC to continue.");
            const saved = await request("/files/" + encodeURIComponent(id));
            if (!Number.isInteger(saved.offset) || saved.offset < offset || saved.offset > file.size) throw error;
            offset = saved.offset; bar.value = offset;
          }
        }
        if (paused) throw new Error("Transfer paused. Tap Send to PC to finish saving.");
        text(detail, "Copied to PC · verifying and preparing the YouTube queue…");
        state = await request("/files/" + encodeURIComponent(id) + "/finish", "POST");
      }
      bar.value = file.size;
      const seconds = Math.max(1, Math.round((performance.now() - started) / 1000));
      text(detail, "Saved on PC · queued for YouTube");
      const timing = document.createElement("small");
      text(timing, "Transfer completed in " + seconds + " seconds");
      row.append(timing);
    } catch (error) {
      text(detail, error.message);
      if (/expired|ended|not found/i.test(error.message)) sessionStorage.removeItem(key);
      paused = true;
      break;
    }
  }
  currentRequest = undefined; running = false; cancel.hidden = true; videos.disabled = false; send.disabled = false;
  testConnection.disabled = false;
});
pair();
