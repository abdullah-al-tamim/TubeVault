let csrf = "";
let sessionRequest: Promise<any> | undefined;
type NativeWindow = Window & { pywebview?: { api?: { recover_session: () => Promise<{ticket:string}> } } };
export async function recoverDesktopSession() {
  const bridge = (window as NativeWindow).pywebview?.api;
  if (!bridge) throw new Error("Open TubeVault from its desktop shortcut or tray, then choose Recover access. For a browser-only installation, ask the PC owner to reset TUBEVAULT_PASSWORD in its local configuration and restart the server.");
  const {ticket} = await bridge.recover_session();
  return api<{csrf:string}>('/desktop/session', 'POST', {ticket});
}
export function restoreSession() {
  if (!sessionRequest) {
    const ticket = new URLSearchParams(location.hash.slice(1)).get('desktop');
    if (ticket) history.replaceState(null, '', location.pathname + location.search);
    sessionRequest = (ticket ? api('/desktop/session', 'POST', {ticket}) : api('/session'))
      .catch(async error => {
        if ((window as NativeWindow).pywebview?.api) return recoverDesktopSession();
        throw error;
      });
    sessionRequest.catch(() => { sessionRequest = undefined; });
  }
  return sessionRequest;
}
export function setCsrf(value: string) {
  csrf = value;
}
export async function api<T = any>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  const response = await fetch("/api" + path, {
    method,
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const data = await response.json();
      message =
        typeof data.detail === "string"
          ? data.detail
          : JSON.stringify(data.detail);
    } catch {}
    throw new Error(message);
  }
  return response.json();
}
export async function transfer(
  file: File,
  collection: string,
  onProgress: (n: number) => void,
) {
  const key = `tv-import:${collection}:${file.name}:${file.size}:${file.lastModified}`;
  let id = localStorage.getItem(key);
  if (!id) {
    id = (
      await api("/imports", "POST", {
        filename: file.name,
        collection,
        size: file.size,
      })
    ).id;
    localStorage.setItem(key, id!);
  }
  let status = await api(`/imports/${id}`);
  if (status.state === "INGESTED") {
    onProgress(100);
    return;
  }
  let offset = status.offset;
  while (offset < file.size) {
    const chunk = file.slice(offset, offset + 4 * 1024 * 1024);
    await new Promise<void>((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("PUT", `/api/imports/${id}?offset=${offset}`);
      xhr.setRequestHeader("X-CSRF-Token", csrf);
      xhr.upload.onprogress = (e) =>
        onProgress(((offset + e.loaded) / file.size) * 100);
      xhr.onload = () =>
        xhr.status === 200
          ? resolve()
          : reject(
              new Error(
                "Transfer interrupted. Select the same original file to resume.",
              ),
            );
      xhr.onerror = () =>
        reject(new Error("Connection lost. Select the same file to resume."));
      xhr.send(chunk);
    });
    offset += chunk.size;
    onProgress((offset / file.size) * 100);
  }
  await api(`/imports/${id}/finish`, "POST");
  localStorage.removeItem(key);
}
