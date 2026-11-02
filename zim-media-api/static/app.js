const state = {
  key: "",
  extraction: null,
  ticket: null,
};

const statusEl = document.querySelector("#status");
const resultEl = document.querySelector("#result");
const deliveryEl = document.querySelector("#delivery");

function setStatus(message, isError) {
  statusEl.textContent = message || "";
  statusEl.classList.toggle("error", Boolean(isError));
}

async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (state.key) headers["X-API-Key"] = state.key;
  if (options.body) headers["Content-Type"] = "application/json";
  const response = await fetch(path, { ...options, headers });
  const payload = await response.json().catch(() => null);
  if (!response.ok || (payload && payload.success === false)) {
    const error = payload && payload.error ? payload.error : { code: "UPSTREAM_ERROR", message: "Request failed." };
    const wrapped = new Error(error.message);
    wrapped.code = error.code;
    throw wrapped;
  }
  return payload.data;
}

function cell(text) {
  const td = document.createElement("td");
  td.textContent = text || "—";
  return td;
}

function renderFormats(data) {
  resultEl.hidden = false;
  document.querySelector("#platform").textContent = data.platform || "Source";
  document.querySelector("#title").textContent = data.title || "Untitled";
  const minutes = data.duration ? `${Math.floor(data.duration / 60)}m ${data.duration % 60}s` : "Duration unknown";
  document.querySelector("#meta").textContent = `${minutes} · ${data.extraction_id}`;
  const thumb = document.querySelector("#thumb");
  if (data.thumbnail) {
    thumb.src = data.thumbnail;
    thumb.hidden = false;
  } else {
    thumb.hidden = true;
  }
  const note = document.querySelector("#selection-note");
  if (data.selection && data.selection.note) {
    note.hidden = false;
    note.textContent = data.selection.note;
  } else {
    note.hidden = true;
  }
  const body = document.querySelector("#formats");
  body.replaceChildren();
  for (const format of data.formats) {
    const row = document.createElement("tr");
    if (data.selection && format.format_id === data.selection.recommended_format_id) {
      row.style.background = "#2a2418";
    }
    row.append(
      cell(format.quality),
      cell(format.ext),
      cell(format.has_video ? format.video_codec : "none"),
      cell(format.has_audio ? format.audio_codec : "none"),
      cell(format.requires_merge ? "Required" : "No"),
    );
    const action = document.createElement("td");
    const button = document.createElement("button");
    button.className = "ghost";
    button.type = "button";
    button.textContent = format.delivery_compatible ? "Deliver" : "Check";
    button.addEventListener("click", () => createTicket(format.format_id));
    action.append(button);
    row.append(action);
    body.append(row);
  }
}

function renderTicket(ticket) {
  deliveryEl.hidden = false;
  state.ticket = ticket;
  document.querySelector("#delivery-mode").textContent = ticket.delivery;
  document.querySelector("#filename").textContent = ticket.filename;
  document.querySelector("#delivery-copy").textContent =
    ticket.delivery === "direct"
      ? "Direct URL from the original host. ZIM is not in the media path."
      : ticket.delivery === "redirect"
        ? "This ticket redirects to the host. The media URL stays on the server."
        : "Proxy streaming was explicitly enabled for this ticket.";
  const box = document.querySelector("#url-box");
  if (ticket.url) {
    box.hidden = false;
    document.querySelector("#direct-url").textContent = ticket.url;
  } else {
    box.hidden = true;
  }
  const open = document.querySelector("#open-download");
  if (ticket.download_url) {
    open.hidden = false;
    open.href = ticket.download_url;
    open.textContent = ticket.delivery === "direct" ? "Open redirect too" : "Open download";
  }
  const constraint = document.querySelector("#constraint");
  constraint.textContent = ticket.constraints && ticket.constraints.note
    ? ticket.constraints.note
    : `Expires in ${ticket.expires_in}s.`;
}

async function createTicket(formatId) {
  setStatus("Creating a ticket…");
  try {
    const ticket = await api("/api/v1/download-link", {
      method: "POST",
      body: JSON.stringify({
        extraction_id: state.extraction.extraction_id,
        format_id: formatId,
        delivery: "auto",
      }),
    });
    renderTicket(ticket);
    setStatus("");
  } catch (error) {
    deliveryEl.hidden = true;
    setStatus(`${error.code || "ERROR"} — ${error.message}`, true);
  }
}

document.querySelector("#extract-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = document.querySelector("#extract-btn");
  button.disabled = true;
  deliveryEl.hidden = true;
  setStatus("Reading the source. The file is not downloaded here.");
  state.key = document.querySelector("#api-key").value.trim();
  try {
    const data = await api("/api/v1/extract", {
      method: "POST",
      body: JSON.stringify({
        url: document.querySelector("#url").value.trim(),
        media_type: document.querySelector("#media-type").value,
        preferred_format: document.querySelector("#preferred-format").value,
        preferred_quality: document.querySelector("#preferred-quality").value,
      }),
    });
    state.extraction = data;
    renderFormats(data);
    setStatus(data.selection && data.selection.substituted ? "The closest real file is shown, not a silent substitution." : "");
  } catch (error) {
    resultEl.hidden = true;
    setStatus(`${error.code || "ERROR"} — ${error.message}`, true);
  } finally {
    button.disabled = false;
  }
});

document.querySelector("#use-sample").addEventListener("click", () => {
  document.querySelector("#url").value = "https://archive.org/details/BigBuckBunny_124";
  document.querySelector("#preferred-format").value = "mp4";
});

document.querySelector("#copy-url").addEventListener("click", async () => {
  const value = document.querySelector("#direct-url").textContent;
  try {
    await navigator.clipboard.writeText(value);
    setStatus("Copied the source URL.");
  } catch {
    setStatus("Select the URL and copy it manually.", true);
  }
});

document.querySelector("#revoke").addEventListener("click", async () => {
  if (!state.ticket) return;
  try {
    await api(`/api/v1/download/${state.ticket.ticket}`, { method: "DELETE" });
    setStatus("Ticket revoked.");
    deliveryEl.hidden = true;
  } catch (error) {
    setStatus(`${error.code || "ERROR"} — ${error.message}`, true);
  }
});

async function boot() {
  try {
    const health = await fetch("/health").then((response) => response.json());
    const pill = document.querySelector("#health-pill");
    pill.textContent = health.data && health.data.status === "ok" ? "Healthy" : "Unhealthy";
    pill.classList.add(health.data && health.data.status === "ok" ? "ok" : "bad");
  } catch {
    document.querySelector("#health-pill").textContent = "Offline";
  }
  try {
    const caps = await fetch("/api/v1/capabilities").then((response) => response.json());
    const proxy = document.querySelector("#proxy-pill");
    proxy.textContent = caps.data.proxy_enabled ? "Proxy on" : "Proxy off";
    proxy.classList.add(caps.data.proxy_enabled ? "warn" : "ok");
  } catch {
    /* capabilities are optional for the header */
  }
  try {
    const platforms = await fetch("/api/v1/platforms").then((response) => response.json());
    const names = platforms.data.platforms.map((item) => item.name).join(" · ");
    document.querySelector("#platforms").textContent = names;
  } catch {
    document.querySelector("#platforms").textContent = "Platform list unavailable.";
  }
  try {
    const session = await fetch("/api/v1/developer/dev-session").then((response) => response.json());
    if (session.success) {
      state.key = session.data.api_key;
      document.querySelector("#api-key").value = session.data.api_key;
      document.querySelector("#form-hint").textContent =
        `Development key ${session.data.key_prefix}… is filled in for this console only.`;
    }
  } catch {
    document.querySelector("#form-hint").textContent = "Paste an API key to call the extraction desk.";
  }
}

boot();
