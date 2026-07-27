import json
import logging
import threading
import time

from flask import Flask, jsonify, request
from flask_sock import Sock
import src.demo_path

from thesis_demo.audio.transcriber import transcribe_bytes
from thesis_demo.planner.llm import get_error as planner_error
from thesis_demo.planner.llm import is_planner_ready, plan, plan_stream
from src.paths import run_dir
from src.world.session import (
    AVAILABLE_ENVIRONMENTS,
    AVAILABLE_ROBOTS,
    execute_plan,
    execution_progress,
    execution_result,
    is_execution_in_progress,
    is_world_ready,
    setup_world,
    world_context,
)

app = Flask(__name__)
sock = Sock(app)

# In-memory conversation history for the current notebook session.
_conversation = None

_selection = dict(robot=None, environment=None)
_planning_lock = threading.Lock()
_world_setup_lock = threading.Lock()

MAX_AUDIO_BYTES = 10 * 1024 * 1024
WORLD_SETUP_TIMEOUT_S = 120

LOGGER = logging.getLogger(__name__)


# ----- helpers -----


def _compact_history(history):
    conversation_pairs = []
    index = 0
    while index < len(history) - 1:
        if (
            history[index].get("role") == "user"
            and history[index + 1].get("role") == "assistant"
        ):
            conversation_pairs.append((history[index], history[index + 1]))
            index += 2
        else:
            index += 1

    compacted_history = []
    for user_message, assistant_message in conversation_pairs[-2:]:
        compacted_history.extend([user_message, assistant_message])
    return compacted_history


def _update_conversation(history):
    global _conversation
    if history:
        history = _compact_history(history)
    _conversation = history or []


def _try_acquire_planning_lock():
    if not is_planner_ready():
        return "planner not ready", 503
    if _world_setup_lock.locked() or not is_world_ready():
        return "world not ready", 503
    if is_execution_in_progress():
        return "A plan is executing.", 409
    if not _planning_lock.acquire(blocking=False):
        return "Planning is in progress.", 409
    return None, None


def _validated_audio(audio_data):
    if not isinstance(audio_data, bytes) or not audio_data:
        raise ValueError("Audio payload is empty or invalid.")
    if len(audio_data) > MAX_AUDIO_BYTES:
        raise ValueError("Audio payload exceeds the 10 MiB limit.")
    return audio_data


def _setup_selected_world(robot, environment):
    try:
        setup_world(robot, environment)
        deadline = time.monotonic() + WORLD_SETUP_TIMEOUT_S
        while time.monotonic() < deadline:
            if is_world_ready():
                return
            result = execution_result()
            if result and result.get("status") == "error":
                return
            time.sleep(0.2)
        LOGGER.error("World setup timed out for %s/%s", robot, environment)
    except Exception:
        LOGGER.exception("World setup failed for %s/%s", robot, environment)
    finally:
        _world_setup_lock.release()


def _ws_send(ws, event):
    ws.send(json.dumps(event, default=str))


def _ws_done(ws, outcome, payload):
    _ws_send(ws, {"type": "done", "outcome": outcome, "payload": payload})


def _no_store_json(payload):
    response = jsonify(payload)
    response.headers["Cache-Control"] = "no-store"
    return response


# ----- server routes -----


@app.route("/status", methods=["GET"])
def get_status():
    return _no_store_json(
        {
            "planner_ready": is_planner_ready(),
            "planner_error": planner_error(),
            "world_ready": is_world_ready(),
            "execution_running": is_execution_in_progress(),
            "progress": execution_progress(),
            "robots": AVAILABLE_ROBOTS,
            "environments": AVAILABLE_ENVIRONMENTS,
            "selection": _selection,
        }
    )


@app.route("/select", methods=["POST"])
def post_select():
    global _conversation
    request_body = request.get_json(silent=True) or {}
    robot = request_body.get("robot")
    environment = request_body.get("environment")
    if robot not in AVAILABLE_ROBOTS or environment not in AVAILABLE_ENVIRONMENTS:
        return (
            jsonify(
                {
                    "status": "invalid_selection",
                    "error": "Select one supported robot and environment.",
                }
            ),
            400,
        )
    if _planning_lock.locked() or is_execution_in_progress():
        return jsonify({"status": "busy", "error": "Planner or executor is busy."}), 409
    if not _world_setup_lock.acquire(blocking=False):
        return jsonify({"status": "busy", "error": "World setup is in progress."}), 409

    _selection.update(robot=robot, environment=environment)
    _conversation = []

    try:
        threading.Thread(
            target=_setup_selected_world,
            args=(robot, environment),
            daemon=True,
        ).start()
    except Exception:
        _world_setup_lock.release()
        raise

    return jsonify({"status": "ok", "selection": _selection})


@app.route("/user-input", methods=["POST"])
def post_user_input():
    error, code = _try_acquire_planning_lock()
    if error is not None:
        if code == 503:
            return jsonify({"status": "not_ready"}), 503
        return jsonify({"status": "busy", "error": error}), 409

    try:
        transcript = transcribe_bytes(
            _validated_audio(request.data), run_dir() / "recordings"
        )
        planner_result = plan(
            transcript,
            conversation=_conversation,
            context=world_context(),
        )
        _update_conversation(planner_result.history)
        if planner_result.outcome == "plan":
            execute_plan(planner_result.payload)
    except ValueError as exc:
        return jsonify({"status": "invalid_audio", "error": str(exc)}), 400
    except Exception:
        LOGGER.exception("HTTP planning request failed")
        return jsonify({"status": "error", "error": "Planning request failed."}), 500
    finally:
        _planning_lock.release()

    return jsonify(
        {
            "outcome": planner_result.outcome,
            "payload": planner_result.payload,
            "transcription": transcript,
            "selection": _selection,
        }
    )


@app.route("/execution-status", methods=["GET"])
def get_execution_status():
    """Return the latest executor result and step progress as JSON."""
    return _no_store_json(
        {"result": execution_result(), "progress": execution_progress()}
    )


@sock.route("/ws")
def ws_user_input(ws):
    try:
        audio_data = ws.receive()
        if audio_data is None:
            return

        error, _ = _try_acquire_planning_lock()
        if error is not None:
            _ws_done(ws, "error", error)
            return

        try:
            transcript = transcribe_bytes(
                _validated_audio(audio_data), run_dir() / "recordings"
            )
            _ws_send(ws, {"type": "transcription", "text": transcript})

            for event in plan_stream(
                transcript, conversation=_conversation, context=world_context()
            ):
                if event["type"] == "done":
                    _update_conversation(event.get("history"))
                    if event["outcome"] == "plan":
                        execute_plan(event["payload"])
                    _ws_done(ws, event["outcome"], event["payload"])
                else:
                    _ws_send(ws, event)
        finally:
            _planning_lock.release()

    except Exception:
        LOGGER.exception("WebSocket planning request failed")
        try:
            _ws_done(ws, "error", "Planning request failed.")
        except Exception:
            pass


def run(port=5000):
    print(f"[server] Server listening on http://127.0.0.1:{port}", flush=True)
    try:
        app.run(port=port, debug=False, use_reloader=False, threaded=True)
    except Exception as exc:
        print(f"[server] Failed to start on port {port}: {exc!r}", flush=True)
        raise
