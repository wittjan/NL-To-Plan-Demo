"""Voice-recorder widget for the NLP-binder notebook.

Renders a record button and result panels inside JupyterLab. Audio is captured in
the browser, sent to the local Flask server over a WebSocket, and the returned
transcription / plan is displayed.

Public API:
    RECORDER_HTML  # rendered recorder HTML string
"""

import json

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_SERVER_PORT = 5000
_PROXY_PATH = f"/proxy/{_SERVER_PORT}"
_STATUS_ENDPOINT = "/status"
_WS_ENDPOINT = "/ws"

# Timeouts (milliseconds)
_WS_HANDSHAKE_TIMEOUT_MS = 10_000
_WS_RESPONSE_TIMEOUT_MS = 180_000  # 3 min: CPU inference is slow
_STATUS_POLL_INTERVAL_MS = 2_000
_STATUS_ERROR_POLL_INTERVAL_MS = 3_000
_DONE_RESET_DELAY_MS = 2_000
_EXECUTION_STATUS_ENDPOINT = "/execution-status"
_EXECUTION_POLL_INTERVAL_MS = 1_000
_EXECUTION_TIMEOUT_MS = 180_000

# MIME types the browser's MediaRecorder may support, ordered by preference.
_PREFERRED_MIME_TYPES = (
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/mp4",
    "audio/ogg;codecs=opus",
    "audio/ogg",
    "audio/wav",
)

# ---------------------------------------------------------------------------
# Icons (inline SVG so the widget has no external assets)
# ---------------------------------------------------------------------------

_MIC_ICON = """
<svg class="icon icon-mic" width="32" height="32" viewBox="0 0 24 24" fill="none"
     stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M12 2a3 3 0 0 1 3 3v7a3 3 0 0 1-6 0V5a3 3 0 0 1 3-3z"/>
  <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
  <line x1="12" y1="19" x2="12" y2="22"/>
</svg>
"""

_STOP_ICON = """
<svg class="icon icon-stop" width="28" height="28" viewBox="0 0 24 24" fill="white">
  <rect x="6" y="6" width="12" height="12" rx="2"/>
</svg>
"""

_SPIN_ICON = """
<svg class="icon icon-spin" width="32" height="32" viewBox="0 0 24 24" fill="none"
     stroke="white" stroke-width="2.5" stroke-linecap="round">
  <path d="M12 3a9 9 0 1 0 9 9"/>
</svg>
"""

_CHECK_ICON = """
<svg class="icon icon-check" width="32" height="32" viewBox="0 0 24 24" fill="none"
     stroke="white" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
  <polyline points="20 6 9 17 4 12"/>
</svg>
"""

_SPIN_BADGE_ICON = """
<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#6b7280"
     stroke-width="2.5" stroke-linecap="round">
  <path d="M12 3a9 9 0 1 0 9 9"/>
</svg>
"""

# ---------------------------------------------------------------------------
# HTML/CSS/JS template
# ---------------------------------------------------------------------------

_RECORDER_TEMPLATE = """
<div id="nlp-rec" class="state-loading">
<style>
#nlp-rec, #nlp-rec * { box-sizing: border-box; margin: 0; padding: 0; }
#nlp-rec {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
    -webkit-font-smoothing: antialiased;
    padding: 18px 0 0;
}
#nlp-rec .card {
    background: #fff;
    border: 1px solid #e5e7eb;
    border-radius: 16px;
    box-shadow: 0 2px 16px rgba(0, 0, 0, 0.07);
    width: 100%;
    overflow: hidden;
}
#nlp-rec .header {
    padding: 20px 24px;
    border-bottom: 1px solid #f3f4f6;
}
#nlp-rec .title {
    font-size: 16px;
    font-weight: 700;
    color: #111827;
    letter-spacing: -0.2px;
}
#nlp-rec .subtitle {
    font-size: 13px;
    color: #9ca3af;
    margin-top: 2px;
}
#nlp-rec .card-body {
    display: flex;
    flex-direction: row;
    align-items: stretch;
}
#nlp-rec .record-section {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 40px 28px;
    flex: 0 0 clamp(220px, 30%, 340px);
    border-right: 1px solid #f3f4f6;
}
#nlp-rec .btn-wrap {
    position: relative;
    width: 108px;
    height: 108px;
    display: flex;
    align-items: center;
    justify-content: center;
}
#nlp-rec .ring {
    position: absolute;
    inset: 0;
    border-radius: 50%;
    border: 2px solid #dc2626;
    opacity: 0;
    pointer-events: none;
}
@keyframes nlpPulse {
    0%   { transform: scale(1); opacity: 0.5; }
    100% { transform: scale(1.9); opacity: 0; }
}
#nlp-rec.state-recording .ring:nth-child(1) { animation: nlpPulse 2s ease-out infinite; }
#nlp-rec.state-recording .ring:nth-child(2) { animation: nlpPulse 2s ease-out 0.65s infinite; }
#nlp-rec .btn {
    position: relative;
    z-index: 1;
    width: 80px;
    height: 80px;
    border-radius: 50%;
    border: none;
    cursor: pointer;
    background: #2563eb;
    box-shadow: 0 4px 20px rgba(37, 99, 235, 0.4);
    transition: background 0.2s, box-shadow 0.2s, transform 0.1s;
    display: flex;
    align-items: center;
    justify-content: center;
}
#nlp-rec .btn:hover:not(:disabled) { transform: scale(1.05); box-shadow: 0 6px 24px rgba(37, 99, 235, 0.5); }
#nlp-rec .btn:active:not(:disabled) { transform: scale(0.96); }
#nlp-rec .btn:disabled { cursor: default; opacity: 0.5; }
#nlp-rec.state-recording .btn { background: #dc2626; box-shadow: 0 4px 20px rgba(220, 38, 38, 0.4); }
#nlp-rec.state-processing .btn { background: #6b7280; box-shadow: 0 4px 20px rgba(107, 114, 128, 0.3); }
#nlp-rec.state-done .btn { background: #16a34a; box-shadow: 0 4px 20px rgba(22, 163, 74, 0.4); }
#nlp-rec.state-error .btn { background: #d97706; box-shadow: 0 4px 20px rgba(217, 119, 6, 0.4); }
#nlp-rec .icon { display: none; }
#nlp-rec.state-ready .icon-mic,
#nlp-rec.state-loading .icon-mic,
#nlp-rec.state-recording .icon-stop,
#nlp-rec.state-processing .icon-spin,
#nlp-rec.state-done .icon-check,
#nlp-rec.state-error .icon-mic { display: block; }
@keyframes nlpSpin { to { transform: rotate(360deg); } }
#nlp-rec.state-processing .icon-spin { animation: nlpSpin 0.9s linear infinite; }
#nlp-rec .state-label {
    margin-top: 20px;
    font-size: 14px;
    color: #6b7280;
    font-weight: 500;
    text-align: center;
    min-height: 20px;
    transition: color 0.2s;
}
#nlp-rec.state-recording .state-label { color: #dc2626; }
#nlp-rec.state-done .state-label { color: #16a34a; }
#nlp-rec.state-error .state-label { color: #d97706; }
#nlp-rec .results {
    flex: 1;
    padding: 24px 20px;
    display: flex;
    flex-direction: column;
    justify-content: center;
    gap: 10px;
    min-width: 0;
}
#nlp-rec .loading-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    font-weight: 600;
    color: #6b7280;
    margin-bottom: 6px;
}
#nlp-rec .loading-badge svg { animation: nlpSpin 0.9s linear infinite; }
#nlp-rec .loading-badge.hidden { display: none; }
#nlp-rec .result-block {
    background: #f9fafb;
    border: 1px solid #e5e7eb;
    border-radius: 10px;
    padding: 14px 16px;
}
#nlp-rec .result-label {
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.7px;
    color: #9ca3af;
    margin-bottom: 6px;
}
#nlp-rec .result-value {
    font-size: 15px;
    line-height: 1.6;
    color: #1f2937;
    white-space: pre-wrap;
    word-break: break-word;
}
#nlp-rec .result-value.transcript,
#nlp-rec .result-value.plan {
    font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
    font-size: 13px;
    line-height: 1.5;
}
#nlp-rec .result-value.placeholder { color: #d1d5db; font-style: italic; font-size: 13px; }
#nlp-rec .result-value.error { color: #b45309; }
@media (max-width: 620px) {
    #nlp-rec .card-body { flex-direction: column; }
    #nlp-rec .record-section { border-right: none; border-bottom: 1px solid #f3f4f6; }
}
</style>

<div class="card">
    <div class="header">
        <div class="title">Voice Recorder</div>
        <div class="subtitle">Please say what the robot should do</div>
    </div>
    <div class="card-body">
        <div class="record-section">
            <div class="btn-wrap">
                <div class="ring"></div>
                <div class="ring"></div>
                <button class="btn" id="nlp-btn" aria-label="Record" disabled>
                    {mic_icon}
                    {stop_icon}
                    {spin_icon}
                    {check_icon}
                </button>
            </div>
            <div class="state-label" id="nlp-rec-label">Loading model...</div>
        </div>
        <div class="results">
            <div class="result-block">
                <div class="result-label">You said</div>
                <div class="result-value transcript placeholder" id="nlp-transcript">
                    Transcription will appear here after recording.
                </div>
            </div>
            <div class="result-block">
                <div class="result-label">Generated Plan</div>
                <div class="loading-badge" id="nlp-model-loading">
                    {spin_badge_icon} Model loading...
                </div>
                <div class="loading-badge hidden" id="nlp-plan-loading">
                    {spin_badge_icon} Generating plan...
                </div>
                <div class="result-value plan placeholder" id="nlp-plan">
                    Generated plan will appear here after recording.
                </div>
            </div>
        </div>
    </div>
</div>

<script>
(function() {
    "use strict";

    const PREFERRED_MIME_TYPES = {preferred_mime_types_json};
    const WS_HANDSHAKE_TIMEOUT_MS = {ws_handshake_timeout_ms};
    const WS_RESPONSE_TIMEOUT_MS = {ws_response_timeout_ms};
    const STATUS_POLL_INTERVAL_MS = {status_poll_interval_ms};
    const STATUS_ERROR_POLL_INTERVAL_MS = {status_error_poll_interval_ms};
    const DONE_RESET_DELAY_MS = {done_reset_delay_ms};
    const EXECUTION_POLL_INTERVAL_MS = {execution_poll_interval_ms};
    const EXECUTION_TIMEOUT_MS = {execution_timeout_ms};

    function getBasePath() {
        const p = window.location.pathname;
        for (const marker of ["/lab", "/doc", "/voila"]) {
            const idx = p.indexOf(marker);
            if (idx > -1) return p.slice(0, idx);
        }
        return "";
    }

    function serverUrl(path) {
        return window.location.origin + getBasePath() + "{proxy_path}" + path;
    }

    function wsUrl(path) {
        const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
        return proto + "//" + window.location.host + getBasePath() + "{proxy_path}" + path;
    }

    function selectMimeType() {
        for (const t of PREFERRED_MIME_TYPES) {
            if (MediaRecorder.isTypeSupported(t)) return t;
        }
        if (typeof MediaRecorder.isTypeSupported === "function") return "";
        // Very old browsers: assume webm and let the server figure it out.
        return "audio/webm";
    }

    class RecorderUI {
        constructor() {
            this.root = document.getElementById("nlp-rec");
            this.btn = document.getElementById("nlp-btn");
            this.label = document.getElementById("nlp-rec-label");
            this.modelBadge = document.getElementById("nlp-model-loading");
            this.planBadge = document.getElementById("nlp-plan-loading");

            this.modelReady = false;
            this.recorder = null;
            this.audioChunks = [];
            this.ws = null;
            this.resetTimer = null;
            this.responseTimer = null;
            this.executionTimer = null;
            this.state = "loading";

            this.btn.addEventListener("click", () => this.toggleRecord());
            window.addEventListener("beforeunload", () => this.dispose());
        }

        setState(state, message) {
            this.state = state;
            this.root.className = "state-" + state;
            if (this.label) this.label.textContent = message;
            this.updateButton();
            if (this.resetTimer) {
                clearTimeout(this.resetTimer);
                this.resetTimer = null;
            }
        }

        updateButton() {
            if (!this.btn) return;
            const busy = this.state === "processing" || this.state === "loading";
            const canRecord = this.modelReady && !busy;
            this.btn.disabled = !canRecord;
            this.btn.setAttribute("aria-label",
                this.state === "recording" ? "Stop recording" : "Start recording");
        }

        setText(elementId, text, isPlaceholder, isError) {
            const el = document.getElementById(elementId);
            if (!el) return;
            el.textContent = text;
            el.classList.toggle("placeholder", !!isPlaceholder);
            el.classList.toggle("error", !!isError);
        }

        appendText(elementId, text) {
            const el = document.getElementById(elementId);
            if (!el) return;
            if (el.classList.contains("placeholder")) {
                el.classList.remove("placeholder");
                el.classList.remove("error");
                el.textContent = "";
            }
            el.textContent += text;
        }

        setModelReady(ready) {
            this.modelReady = ready;
            if (ready) {
                this.modelBadge.classList.add("hidden");
                if (this.state === "loading") {
                    this.setState("ready", "Tap to record");
                } else {
                    this.updateButton();
                }
            }
        }

        async pollStatus() {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 5000);
            try {
                const resp = await fetch(serverUrl("{status_endpoint}"), {
                    cache: "no-store",
                    signal: controller.signal,
                });
                clearTimeout(timeoutId);
                if (!resp.ok) throw new Error("HTTP " + resp.status);
                const data = await resp.json();
                console.log("NLP recorder: status", data);
                if (data.planner_ready) {
                    this.setModelReady(true);
                    return;
                }
                const reason = data.planner_error
                    ? "Model failed: " + data.planner_error
                    : "Model loading...";
                this._showLoadingStatus(reason);
                setTimeout(() => this.pollStatus(), STATUS_POLL_INTERVAL_MS);
            } catch (err) {
                clearTimeout(timeoutId);
                console.warn("NLP recorder: status poll failed", err);
                this._showLoadingStatus("Connecting to server...");
                setTimeout(() => this.pollStatus(), STATUS_ERROR_POLL_INTERVAL_MS);
            }
        }

        _showLoadingStatus(message) {
            if (this.modelBadge) {
                this.modelBadge.textContent = message;
            }
        }

        async toggleRecord() {
            if (!this.modelReady) return;
            if (this.state === "recording") {
                this.stopRecording();
                return;
            }
            await this.startRecording();
        }

        async startRecording() {
            this.audioChunks = [];
            this.disposeRecorder();
            if (this.executionTimer) {
                clearTimeout(this.executionTimer);
                this.executionTimer = null;
            }

            let stream;
            try {
                stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            } catch (err) {
                const msg = err.name === "NotAllowedError"
                    ? "Microphone access denied."
                    : "Microphone error: " + err.message;
                this.showError(msg);
                return;
            }

            const mimeType = selectMimeType();
            const options = mimeType ? { mimeType } : {};
            try {
                this.recorder = new MediaRecorder(stream, options);
            } catch (err) {
                console.warn("MediaRecorder failed with", mimeType, err);
                this.recorder = new MediaRecorder(stream);
            }

            this.recorder.ondataavailable = (e) => {
                if (e.data && e.data.size > 0) this.audioChunks.push(e.data);
            };

            this.recorder.onstop = () => {
                stream.getTracks().forEach(t => t.stop());
                this.onRecordingStopped(mimeType || "audio/webm");
            };

            this.recorder.onerror = (e) => {
                stream.getTracks().forEach(t => t.stop());
                this.showError("Recording failed: " + (e.message || "unknown"));
            };

            this.recorder.start();
            this.setState("recording", "Recording - tap to stop");
        }

        stopRecording() {
            if (this.recorder && this.recorder.state === "recording") {
                this.recorder.stop();
            }
        }

        onRecordingStopped(mimeType) {
            this.recorder = null;
            if (this.audioChunks.length === 0) {
                this.setState("ready", "Tap to record");
                return;
            }
            this.setState("processing", "Transcribing...");
            this.setText("nlp-transcript", "", false);
            this.setText("nlp-plan", "", false);
            this.planBadge.classList.remove("hidden");
            const blob = new Blob(this.audioChunks, { type: mimeType });
            this.sendAudio(blob);
        }

        sendAudio(blob) {
            if (this.ws) {
                try { this.ws.close(); } catch (e) {}
            }

            const ws = new WebSocket(wsUrl("{ws_endpoint}"));
            ws.binaryType = "arraybuffer";
            this.ws = ws;
            let gotDone = false;

            const handshakeTimer = setTimeout(() => {
                if (ws.readyState !== WebSocket.OPEN) {
                    this.showError("Server did not open WebSocket in time.");
                    try { ws.close(); } catch (e) {}
                }
            }, WS_HANDSHAKE_TIMEOUT_MS);

            const startResponseTimer = () => {
                if (this.responseTimer) clearTimeout(this.responseTimer);
                this.responseTimer = setTimeout(() => {
                    if (!gotDone) {
                        this.showError("No response from server.");
                        try { ws.close(); } catch (e) {}
                    }
                }, WS_RESPONSE_TIMEOUT_MS);
            };

            ws.onopen = () => {
                clearTimeout(handshakeTimer);
                startResponseTimer();
                blob.arrayBuffer().then(buf => ws.send(buf)).catch(err => {
                    this.showError("Could not read audio: " + err.message);
                    ws.close();
                });
            };

            ws.onmessage = (ev) => {
                startResponseTimer();
                if (typeof ev.data !== "string") return;
                let data;
                try {
                    data = JSON.parse(ev.data);
                } catch (e) {
                    console.warn("NLP recorder: non-JSON message", ev.data);
                    return;
                }

                switch (data.type) {
                    case "transcription":
                        this.setText("nlp-transcript", data.text || "", false);
                        this.setState("processing", "Generating plan...");
                        break;
                    case "token":
                        this.appendText("nlp-plan", data.text || "");
                        break;
                    case "done":
                        gotDone = true;
                        this.planBadge.classList.add("hidden");
                        this.handleDone(data);
                        try { ws.close(); } catch (e) {}
                        break;
                    default:
                        console.warn("NLP recorder: unknown event type", data.type);
                }
            };

            ws.onerror = () => {
                clearTimeout(handshakeTimer);
                this.showError("WebSocket error - planner still loading or server down.");
            };

            ws.onclose = () => {
                clearTimeout(handshakeTimer);
                if (this.responseTimer) clearTimeout(this.responseTimer);
                if (!gotDone && this.state === "processing") {
                    this.showError("Connection closed before the plan was received.");
                }
                this.ws = null;
            };
        }

        formatPayload(payload) {
            if (payload === null || payload === undefined) return "";
            if (typeof payload === "object") return JSON.stringify(payload, null, 2);
            return String(payload);
        }

        handleDone(data) {
            if (data.outcome === "plan") {
                this.setText("nlp-plan", this.formatPayload(data.payload), false);
                this.setState("processing", "Executing plan...");
                this.pollExecution();
            } else if (data.outcome === "clarification") {
                const payload = data.payload || data.clarification;
                const text = (payload && typeof payload === "object")
                    ? JSON.stringify({ clarification: payload }, null, 2)
                    : String(payload || "");
                this.setText("nlp-plan", text, false);
                this.setState("ready", "Tap to record");
            } else {
                const detail = this.formatPayload(data.payload || data.error);
                this.showError("Error: " + (detail || "unknown"));
            }
        }

        pollExecution() {
            if (this.executionTimer) clearTimeout(this.executionTimer);
            const deadline = Date.now() + EXECUTION_TIMEOUT_MS;
            const tick = async () => {
                try {
                    const resp = await fetch(serverUrl("{execution_status_endpoint}"), { cache: "no-store" });
                    if (!resp.ok) throw new Error("HTTP " + resp.status);
                    const data = await resp.json();
                    const result = data.result;
                    if (result === null || result === undefined) {
                        const progress = data.progress;
                        if (progress && typeof progress.step_index === "number" && progress.total_steps) {
                            this.setState("processing",
                                "Executing step " + (progress.step_index + 1) + "/" + progress.total_steps + "...");
                        }
                        if (Date.now() > deadline) {
                            this.showError("Execution timed out.");
                            return;
                        }
                        this.executionTimer = setTimeout(tick, EXECUTION_POLL_INTERVAL_MS);
                        return;
                    }
                    if (result.status === "ok") {
                        this.setState("done", "Done");
                        this.resetTimer = setTimeout(() => this.setState("ready", "Tap to record"), DONE_RESET_DELAY_MS);
                    } else {
                        const currentPlan = document.getElementById("nlp-plan").textContent;
                        const phase = result.phase || "execution";
                        const detail = result.grounding_error
                            ? JSON.stringify(result.grounding_error, null, 2)
                            : (result.error || "unknown");
                        this.setText("nlp-plan",
                            currentPlan + "\\n\\n---\\n[ERROR][" + phase + "] " + detail,
                            false, true);
                        this.setState("error", "Tap to record again");
                    }
                } catch (err) {
                    console.warn("NLP recorder: execution poll failed", err);
                    if (Date.now() > deadline) { this.showError("Execution timed out."); return; }
                    this.executionTimer = setTimeout(tick, EXECUTION_POLL_INTERVAL_MS);
                }
            };
            tick();
        }

        showError(message) {
            this.planBadge.classList.add("hidden");
            this.setText("nlp-plan", message, false, true);
            this.setState("error", "Tap to record again");
        }

        disposeRecorder() {
            if (this.recorder && this.recorder.state !== "inactive") {
                try { this.recorder.stop(); } catch (e) {}
            }
            this.recorder = null;
            this.audioChunks = [];
        }

        dispose() {
            this.disposeRecorder();
            if (this.ws) {
                try { this.ws.close(); } catch (e) {}
                this.ws = null;
            }
            if (this.resetTimer) clearTimeout(this.resetTimer);
            if (this.responseTimer) clearTimeout(this.responseTimer);
            if (this.executionTimer) clearTimeout(this.executionTimer);
        }
    }

    const ui = new RecorderUI();
    ui.pollStatus();
})();
</script>
</div>
"""


def _replace_placeholders(template, values):
    """Substitute `{key}` placeholders without interpreting literal braces."""
    result = template
    for key, value in values.items():
        result = result.replace(f"{{{key}}}", str(value))
    return result


def _build_recorder_html():
    """Assemble the final HTML string with all placeholders filled."""
    return _replace_placeholders(
        _RECORDER_TEMPLATE,
        {
            "mic_icon": _MIC_ICON.strip(),
            "stop_icon": _STOP_ICON.strip(),
            "spin_icon": _SPIN_ICON.strip(),
            "check_icon": _CHECK_ICON.strip(),
            "spin_badge_icon": _SPIN_BADGE_ICON.strip(),
            "proxy_path": _PROXY_PATH,
            "status_endpoint": _STATUS_ENDPOINT,
            "ws_endpoint": _WS_ENDPOINT,
            "preferred_mime_types_json": json.dumps(list(_PREFERRED_MIME_TYPES)),
            "ws_handshake_timeout_ms": _WS_HANDSHAKE_TIMEOUT_MS,
            "ws_response_timeout_ms": _WS_RESPONSE_TIMEOUT_MS,
            "status_poll_interval_ms": _STATUS_POLL_INTERVAL_MS,
            "status_error_poll_interval_ms": _STATUS_ERROR_POLL_INTERVAL_MS,
            "done_reset_delay_ms": _DONE_RESET_DELAY_MS,
            "execution_status_endpoint": _EXECUTION_STATUS_ENDPOINT,
            "execution_poll_interval_ms": _EXECUTION_POLL_INTERVAL_MS,
            "execution_timeout_ms": _EXECUTION_TIMEOUT_MS,
        },
    )


# Backward-compatible export used by demo_ui.py.
RECORDER_HTML = _build_recorder_html()
