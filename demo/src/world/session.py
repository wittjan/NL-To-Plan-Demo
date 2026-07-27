import fcntl
import json
import os
import subprocess
import sys
import threading
from dataclasses import dataclass

import rclpy
from rclpy.action import ActionClient
from rclpy.executors import SingleThreadedExecutor
from rclpy.qos import DurabilityPolicy, QoSProfile
from std_msgs.msg import String
from thesis_demo_msgs.action import ExecutePlan

from src.demo_path import demo_dir
from src.paths import context_file, log_file, result_file, run_dir, runtime_lock_file
from src.utils import safe_remove

AVAILABLE_ROBOTS = ["hsrb", "tiago", "pr2"]
AVAILABLE_ENVIRONMENTS = ["apartment", "kitchen"]

_executor_process = None
_runtime_lock_file = None
_session_lock = threading.RLock()


@dataclass
class _RosClient:
    node: object = None
    action_client: object = None
    ros_executor: object = None
    spin_thread: object = None
    server_seen: bool = False
    context: dict | None = None
    progress: dict | None = None
    result: dict | None = None
    goal_active: bool = False
    total_steps: int = 0


_client = _RosClient()


def _ensure_client():
    if _client.node is not None:
        return
    rclpy.init()
    _client.node = rclpy.create_node("thesis_demo_bridge")
    _client.node.create_subscription(
        String, "world_context", _store_context, _latched_qos()
    )
    _client.action_client = ActionClient(_client.node, ExecutePlan, "execute_plan")
    _client.ros_executor = SingleThreadedExecutor()
    _client.ros_executor.add_node(_client.node)
    _client.spin_thread = threading.Thread(
        target=_client.ros_executor.spin, daemon=True
    )
    _client.spin_thread.start()


def _latched_qos():
    return QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)


def _store_context(message):
    _client.context = json.loads(message.data)


def _store_feedback(feedback_message):
    feedback = feedback_message.feedback
    _client.progress = {
        "step_index": feedback.step_index,
        "total_steps": _client.total_steps,
        "step": json.loads(feedback.step_json),
    }


def _store_goal_handle(goal_future):
    goal_handle = goal_future.result()
    if not goal_handle.accepted:
        _client.goal_active = False
        _client.result = _error_result("executor", "Executor rejected the plan.")
        return
    result_future = goal_handle.get_result_async()
    result_future.add_done_callback(_store_result)


def _store_result(result_future):
    response = result_future.result()
    try:
        _client.result = json.loads(response.result.result_json)
    except json.JSONDecodeError as error:
        _client.result = _error_result(
            "executor", f"Executor returned invalid result JSON: {error}"
        )
    _client.goal_active = False


def _error_result(phase, error):
    return {"status": "error", "phase": phase, "error": error}


def _reset_client_state():
    _client.server_seen = False
    _client.context = None
    _client.progress = None
    _client.result = None
    _client.goal_active = False
    _client.total_steps = 0


def _acquire_runtime_lock():
    global _runtime_lock_file
    if _runtime_lock_file is not None:
        return

    lock_file = open(runtime_lock_file(), "a+", encoding="utf-8")
    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as error:
        lock_file.close()
        raise RuntimeError(
            f"Runtime directory {os.path.dirname(runtime_lock_file())!r} "
            "is already owned by another executor controller"
        ) from error

    lock_file.seek(0)
    lock_file.truncate()
    lock_file.write(str(os.getpid()))
    lock_file.flush()
    _runtime_lock_file = lock_file


def _release_runtime_lock():
    global _runtime_lock_file
    lock_file = _runtime_lock_file
    _runtime_lock_file = None
    if lock_file is None:
        return
    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
    finally:
        lock_file.close()


def setup_world(robot, environment):
    global _executor_process
    if robot not in AVAILABLE_ROBOTS:
        raise ValueError(f"Unknown robot {robot!r}")
    if environment not in AVAILABLE_ENVIRONMENTS:
        raise ValueError(f"Unknown environment {environment!r}")

    with _session_lock:
        stop_world()
        _acquire_runtime_lock()
        try:
            # Stale logs must not be mistaken for the new executor's state.
            for path in (context_file(), result_file()):
                safe_remove(path)

            env = os.environ.copy()
            env["NLP_WORLD_SELECTION"] = json.dumps(
                {"robot": robot, "environment": environment}
            )
            env["NLP_RUN_DIR"] = str(run_dir())
            pythonpath_entries = [str(demo_dir().parent)]
            for entry in env.get("PYTHONPATH", "").split(os.pathsep):
                if entry:
                    pythonpath_entries.append(entry)
            env["PYTHONPATH"] = os.pathsep.join(pythonpath_entries)

            _ensure_client()
            _reset_client_state()

            with open(log_file(), "w", encoding="utf-8") as log_handle:
                _executor_process = subprocess.Popen(
                    [sys.executable, "-u", "-m", "thesis_demo.action_server"],
                    env=env,
                    stdout=log_handle,
                    stderr=subprocess.STDOUT,
                )
        except Exception:
            _release_runtime_lock()
            raise


def is_world_ready():
    with _session_lock:
        if _executor_process is None or _executor_process.poll() is not None:
            return False
        _ensure_client()
        if not _client.server_seen:
            _client.server_seen = _client.action_client.wait_for_server(timeout_sec=0.2)
        return _client.server_seen and _client.context is not None


def world_context():
    with _session_lock:
        return _client.context


def execution_progress():
    with _session_lock:
        return _client.progress


def execute_plan(plan_dict):
    with _session_lock:
        _require_running_executor()
        if is_execution_in_progress():
            raise RuntimeError("A plan is already executing.")

        if isinstance(plan_dict, dict):
            plan_data = plan_dict
        else:
            plan_data = json.loads(plan_dict)
        steps = plan_data.get("plan")
        if not steps:
            return

        _ensure_client()
        goal = ExecutePlan.Goal()
        goal.plan_json = json.dumps({"plan": steps})
        _client.result = None
        _client.progress = None
        _client.total_steps = len(steps)
        _client.goal_active = True
        goal_future = _client.action_client.send_goal_async(
            goal, feedback_callback=_store_feedback
        )
        goal_future.add_done_callback(_store_goal_handle)


def _require_running_executor():
    if _executor_process is None or _executor_process.poll() is not None:
        result = execution_result()
        if result and result.get("status") == "error":
            raise RuntimeError(
                f"{result['error']} "
                "Re-select a robot/environment to rebuild the world."
            )
        raise RuntimeError("Executor is not running. Select a robot/environment first.")


def is_execution_in_progress():
    with _session_lock:
        if not _client.goal_active:
            return False
        if _executor_process is not None and _executor_process.poll() is not None:
            _client.goal_active = False
            _client.result = _error_result(
                "executor", "Executor stopped while executing the plan."
            )
            return False
        return True


def execution_result():
    with _session_lock:
        if _client.result is not None:
            return _client.result
        try:
            with open(result_file(), encoding="utf-8") as handle:
                return json.load(handle)
        except (OSError, json.JSONDecodeError):
            return None


def stop_world():
    global _executor_process
    with _session_lock:
        process = _executor_process
        _executor_process = None
        _reset_client_state()
        try:
            if process is None or process.poll() is not None:
                return
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        finally:
            _release_runtime_lock()
