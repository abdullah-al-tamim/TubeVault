"use strict";
const connection = document.querySelector("#connection");
const sender = document.querySelector("#sender");
const videos = document.querySelector("#videos");
const send = document.querySelector("#send");
const cancel = document.querySelector("#cancel");
const progress = document.querySelector("#progress");
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
  const response = await fetch(path, {
    method, headers: {Authorization: "Bearer " + token, "Content-Type": "application/json"},
    body: body === undefined ? undefined : JSON.stringify(body)
  });
  if (!response.ok) {
    let message = "Connection interrupted. Select the same videos to resume.";
    try { message = (await response.json()).detail || message; } catch {}
    throw new Error(message);
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
    currentRequest = xhr;
    xhr.open("PUT", "/files/" + encodeURIComponent(id) + "?offset=" + offset);
    xhr.setRequestHeader("Authorization", "Bearer " + token);
    xhr.timeout = 120000;
    xhr.upload.onprogress = event => onProgress(event.loaded);
    xhr.ontimeout = () => reject(new Error("The PC did not respond for two minutes. Tap Send to PC to resume from its saved position."));
    xhr.onload = () => {
      if (xhr.status === 200) resolve(JSON.parse(xhr.responseText));
      else {
        let message = "Copy interrupted. Tap Send to PC to resume.";
        try { message = JSON.parse(xhr.responseText).detail || message; } catch {}
        reject(new Error(message));
      }
    };
    xhr.onerror = () => reject(new Error("Connection lost. Keep both devices on the same Wi-Fi and tap Send to PC again."));
    xhr.onabort = () => reject(new Error("Transfer paused. Tap Send to PC to continue."));
    xhr.send(block);
  });
}
cancel.addEventListener("click", () => { paused = true; if (currentRequest) currentRequest.abort(); });
send.addEventListener("click", async () => {
  if (running) return;
  running = true; paused = false; send.disabled = true; videos.disabled = true; cancel.hidden = false;
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
        while (offset < file.size) {
          if (paused) throw new Error("Transfer paused. Tap Send to PC to continue.");
          const block = file.slice(offset, offset + 4 * 1024 * 1024);
          const result = await copyChunk(id, offset, block, loaded => {
            bar.value = offset + loaded;
            const copied = offset + loaded;
            const seconds = Math.max(.1, (performance.now() - started) / 1000);
            const speed = megabytes((copied - initialOffset) / seconds) + "/s";
            text(detail, Math.min(100, Math.floor(copied / file.size * 100)) + "% · "
              + megabytes(copied) + " / " + megabytes(file.size) + " · " + speed
              + (loaded === block.size ? " · Waiting for PC to save this chunk…" : ""));
          });
          offset = result.offset;
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
});
pair();
