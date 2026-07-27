"""NLP-binder UI: robot/env selectors. Talks to the Flask server. Recorder card lives in recorder_ui.py."""

import json
import shutil
import subprocess
import threading
import time
import urllib.request

from base64 import b64encode
from pathlib import Path

import ipywidgets as widgets
from IPython.display import HTML, display
from recorder_ui import RECORDER_HTML
from src.world.session import AVAILABLE_ENVIRONMENTS, AVAILABLE_ROBOTS

VIDEO_FILES = (
    ("PR2 Real", "assets/cuttin_real_pr2.mp4"),
    ("G1 Simulation", "assets/g1_simu.mp4"),
    ("Multiple Robots", "assets/all_robots.mp4"),
)

FAQ_ITEMS = (
    (
        "How do I start the demo?",
        "Choose a robot and environment, then click the Record button and speak.",
    ),
    (
        "Why do I see multiple items?",
        "When multiple items appear, select a different environment to reset the publisher.",
    ),
    (
        "Why does the demo take a moment to appear?",
        "RViz and the underlying demo process need a few seconds to start.",
    ),
    (
        "Why is the camera wrong?",
        "The camera is attached to a link, so you may need to adjust it slightly yourself. "
        "When you choose a different environment, it will jump again.",
    ),
)

BACKGROUND_IMAGE_PATH = (
    Path(__file__).resolve().parent.parent.joinpath("img", "aicor-background.png")
)
LOGO_IMAGE_PATH = (
    Path(__file__).resolve().parent.parent.joinpath("img", "aicor-logo.png")
)

# ---------------------------------------------------------------------------
# RViz config switching
# ---------------------------------------------------------------------------

RVIZ_CONFIG_DIRECTORY = Path(__file__).resolve().parent / "rviz"
ACTIVE_RVIZ_CONFIG_PATH = Path("/home/jovyan/.rviz2/default.rviz")
_RVIZ_CONFIGS = {
    "apartment": RVIZ_CONFIG_DIRECTORY / "apartment.rviz",
    "kitchen": RVIZ_CONFIG_DIRECTORY / "kitchen.rviz",
}


def _rviz_pids():
    result = subprocess.run(
        ["pgrep", "-f", "(^|/)rviz2($| )"], capture_output=True, text=True, check=False
    )
    return [int(line.strip()) for line in result.stdout.splitlines() if line.strip()]


def _is_rviz_running():
    return bool(_rviz_pids())


def _reload_rviz_for_environment(environment):
    config_path = _RVIZ_CONFIGS.get(environment)
    if config_path is None or not config_path.is_file():
        raise FileNotFoundError(
            f"RViz config not found for environment {environment!r}: {config_path}"
        )

    ACTIVE_RVIZ_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(config_path, ACTIVE_RVIZ_CONFIG_PATH)

    if _is_rviz_running():
        subprocess.run(["pkill", "-f", "rviz2"], check=False)
        return "restarted"
    return "seeded"


def _style_label(value):
    return value.replace("_", " ").title()


def _inject_styles():
    background_image = ""
    if BACKGROUND_IMAGE_PATH.exists():
        background_image = b64encode(BACKGROUND_IMAGE_PATH.read_bytes()).decode("ascii")

    style_template = """
            <style>
            .demo-shell {
                --demo-ink: #17324d;
                --demo-muted: #64748b;
                --demo-accent: #2f6fa3;
                --demo-accent-soft: #e9f3fb;
                --demo-card: #ffffff;
                --demo-line: #e7edf3;
                --demo-surface: #f7fafc;
                font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
                color: var(--demo-ink);
                position: relative;
                background:
                    linear-gradient(180deg, rgba(251, 253, 255, 0.96) 0%, rgba(244, 248, 251, 0.97) 100%);
                border: 1px solid var(--demo-line);
                border-radius: 24px;
                box-shadow: 0 16px 36px rgba(31, 52, 84, 0.08);
                padding: 30px;
                overflow: hidden;
            }
            .demo-shell::before {
                content: "";
                position: absolute;
                inset: 0;
                background:
                    linear-gradient(180deg, rgba(255, 255, 255, 0.78) 0%, rgba(247, 250, 252, 0.84) 100%);
                background-position: center top;
                background-repeat: no-repeat;
                background-size: auto;
                opacity: 0.72;
                pointer-events: none;
            }
            .demo-shell.demo-has-background::before {
                background:
                    linear-gradient(180deg, rgba(255, 255, 255, 0.78) 0%, rgba(247, 250, 252, 0.84) 100%),
                    url("data:image/png;base64,__BACKGROUND_IMAGE__");
                background-position: center top, calc(50% + 240px) -56px;
                background-repeat: no-repeat;
                background-size: auto, 112% auto;
            }
            .demo-shell > * {
                position: relative;
                z-index: 1;
            }
            .demo-shell h1,
            .demo-shell h2,
            .demo-shell h3,
            .demo-shell p {
                margin: 0;
            }
            .demo-hero {
                display: grid;
                gap: 10px;
                margin-bottom: 24px;
                width: min(100%, 520px);
            }
            .demo-logo-wrap {
                display: flex;
                justify-content: center;
                margin-bottom: 22px;
            }
            .demo-logo {
                width: min(100%, 360px);
                height: auto;
                display: block;
                filter: drop-shadow(0 10px 20px rgba(23, 50, 77, 0.12));
            }
            .demo-kicker {
                display: inline-flex;
                width: fit-content;
                padding: 7px 13px;
                border-radius: 999px;
                background: #edf3f8;
                color: #6a7f93;
                font-size: 12px;
                font-weight: 700;
                letter-spacing: 0.08em;
                text-transform: uppercase;
            }
            .demo-title {
                font-size: 26px;
                font-weight: 700;
                line-height: 1.08;
                letter-spacing: -0.03em;
                max-width: none;
            }
            .demo-copy {
                max-width: 64ch;
                color: var(--demo-muted);
                line-height: 1.55;
                font-size: 15px;
            }
            .demo-card {
                background: var(--demo-card);
                border: 1px solid var(--demo-line);
                border-radius: 20px;
                padding: 20px;
                box-shadow: 0 8px 20px rgba(30, 58, 95, 0.04);
            }
            .demo-controls {
                width: min(100%, 560px);
            }
            .demo-scenario-card {
                width: min(100%, 520px);
            }
            .demo-card-title {
                font-size: 18px;
                font-weight: 700;
                margin-bottom: 6px;
            }
            .demo-card-copy {
                color: var(--demo-muted);
                font-size: 14px;
                line-height: 1.5;
                margin-bottom: 14px;
            }
            .demo-ui .widget-label {
                color: var(--demo-muted);
                font-size: 13px;
                font-weight: 600;
                min-width: 90px;
            }
            .demo-ui .widget-dropdown select,
            .demo-ui .widget-select select {
                border-radius: 12px;
                border: 1px solid var(--demo-line);
                box-shadow: none;
                background: var(--demo-surface);
                font-size: 14px;
                color: var(--demo-ink);
            }
            .demo-ui .widget-toggle-buttons {
                width: 100%;
            }
            .demo-ui .widget-toggle-buttons .widget-toggle-button {
                display: inline-flex !important;
                align-items: center !important;
                justify-content: center !important;
                border-radius: 999px !important;
                border: 1px solid var(--demo-line) !important;
                margin-right: 8px;
                margin-bottom: 8px;
                background: #f7fafc;
                color: var(--demo-ink);
                font-weight: 600;
                padding: 7px 15px;
                text-align: center !important;
                line-height: 1.2 !important;
                min-height: 40px;
                transition: transform 160ms ease, box-shadow 160ms ease, background 160ms ease, border-color 160ms ease;
            }
            .demo-ui .widget-toggle-buttons .widget-toggle-button.mod-active {
                background: linear-gradient(135deg, #2f6fa3 0%, #4d8fc4 100%);
                color: white;
                border-color: transparent !important;
                box-shadow: 0 10px 20px rgba(47, 111, 163, 0.22);
                transform: translateY(-1px);
            }
            .demo-summary {
                display: grid;
                gap: 10px;
            }
            .demo-note {
                padding: 12px 14px;
                border-radius: 14px;
                background: var(--demo-accent-soft);
                color: #244f74;
                font-size: 13px;
                line-height: 1.5;
            }
            .demo-running-note {
                margin-top: 14px;
                padding: 16px 18px;
                border-radius: 16px;
                background: linear-gradient(135deg, #fff4df 0%, #ffe8bf 100%);
                border: 1px solid #f1c97a;
                color: #7a4b00;
                font-size: 17px;
                font-weight: 700;
                line-height: 1.4;
            }
            .demo-subtle-list {
                display: grid;
                gap: 10px;
                margin-top: 14px;
            }
            .demo-subtle-row {
                display: grid;
                grid-template-columns: 14px 1fr;
                gap: 10px;
                align-items: start;
                color: var(--demo-muted);
                font-size: 13px;
                line-height: 1.45;
            }
            .demo-subtle-dot {
                width: 10px;
                height: 10px;
                margin-top: 4px;
                border-radius: 999px;
                background: linear-gradient(135deg, #2f6fa3 0%, #4d8fc4 100%);
            }
            .demo-stack {
                display: grid;
                gap: 18px;
                margin-top: 18px;
                width: min(100%, 860px);
            }
            .demo-section-title {
                font-size: 18px;
                font-weight: 700;
                margin-bottom: 6px;
            }
            .demo-section-copy {
                color: var(--demo-muted);
                font-size: 14px;
                line-height: 1.5;
                margin-bottom: 14px;
            }
            .demo-video {
                width: 100%;
                border-radius: 16px;
                border: 1px solid var(--demo-line);
                background: #000;
            }
            .demo-faq .widget-accordion {
                border: 1px solid var(--demo-line);
                border-radius: 16px;
                overflow: hidden;
            }
            .demo-faq .widget-accordion .p-Accordion-child {
                border-top: 1px solid var(--demo-line);
            }
            .demo-faq-button .widget-button {
                display: inline-flex !important;
                align-items: center !important;
                justify-content: center !important;
                width: auto;
                min-width: 240px;
                border: 0;
                border-radius: 14px;
                padding: 12px 18px;
                background: linear-gradient(135deg, #2f6fa3 0%, #4d8fc4 100%);
                color: white;
                font-weight: 700;
                text-align: center !important;
                line-height: 1.2 !important;
                box-shadow: 0 12px 22px rgba(47, 111, 163, 0.24);
            }
            @media (max-width: 900px) {
                .demo-logo {
                    width: min(100%, 280px);
                }
                .demo-title {
                    max-width: none;
                }
            }
            </style>
            """

    display(HTML(style_template.replace("__BACKGROUND_IMAGE__", background_image)))


def _logo_header():
    if not LOGO_IMAGE_PATH.exists():
        return None

    logo_data = b64encode(LOGO_IMAGE_PATH.read_bytes()).decode("ascii")
    return widgets.HTML(value=f"""
        <div class="demo-logo-wrap">
          <img
            class="demo-logo"
            src="data:image/png;base64,{logo_data}"
            alt="AICOR"
          />
        </div>
        """)


# ---------------------------------------------------------------------------
# FAQ + video sections (kept from template)
# ---------------------------------------------------------------------------


def _available_videos():
    base_dir = Path(__file__).resolve().parent
    videos = []
    for title, relative_path in VIDEO_FILES:
        video_path = base_dir / relative_path
        if video_path.is_file():
            videos.append((title, video_path))
    return videos


def _video_card_html(title, video_path):
    video_data = b64encode(video_path.read_bytes()).decode("ascii")
    return f"""
    <div class="demo-card">
      <div class="demo-section-title">{title}</div>
      <div class="demo-section-copy">
        Recorded example run from the notebook assets directory.
      </div>
      <video class="demo-video" controls autoplay muted preload="metadata">
        <source src="data:video/mp4;base64,{video_data}" type="video/mp4">
        Your browser does not support the video tag.
      </video>
    </div>
    """


def _faq_section():
    video_entries = _available_videos()

    answers = []
    for _, answer in FAQ_ITEMS:
        answers.append(widgets.HTML(value=f"""
                <div class="demo-section-copy" style="margin: 0; padding: 2px 0 8px 0;">
                  {answer}
                </div>
                """))

    accordion = widgets.Accordion(children=answers, selected_index=None)
    for index, (question, _) in enumerate(FAQ_ITEMS):
        accordion.set_title(index, question)

    video_buttons = []

    if not video_entries:
        video_panel = widgets.HTML(value="""
            <div class="demo-card">
              <div class="demo-section-copy" style="margin-bottom: 0;">
                No recorded demo video was found in the notebook assets directory.
              </div>
            </div>
            """)
    else:
        video_panel = widgets.HTML(value="")

        for title, video_path in video_entries:
            button = widgets.Button(
                description=f"Video: {title}",
                icon="play",
            )
            button.add_class("demo-faq-video-button")

            def _show_video(_, current_title=title, current_video_path=video_path):
                video_panel.value = _video_card_html(current_title, current_video_path)

            button.on_click(_show_video)
            video_buttons.append(button)

    video_button_box = widgets.Box(video_buttons)
    video_button_box.add_class("demo-faq-button")

    wrapper = widgets.VBox(
        [
            widgets.HTML(value="""
                <div class="demo-card">
                  <div class="demo-section-title">FAQ</div>
                  <div class="demo-section-copy">
                    Short answers to common setup issues. Use the buttons below to launch the recorded demos inline.
                  </div>
                </div>
                """),
            video_button_box,
            accordion,
            video_panel,
        ]
    )
    wrapper.add_class("demo-faq")
    return wrapper


# ---------------------------------------------------------------------------
# NLP planner UI: robot/env + record button
# ---------------------------------------------------------------------------


def _select_on_server(selection):
    payload = json.dumps(selection).encode()

    def _post():
        for _ in range(20):
            try:
                resp = urllib.request.urlopen(
                    urllib.request.Request(
                        "http://localhost:5000/select",
                        data=payload,
                        headers={"Content-Type": "application/json"},
                    )
                )
                if resp.status == 200:
                    return
            except Exception:
                pass
            time.sleep(0.5)

    threading.Thread(target=_post, daemon=True).start()


def run_ui():
    """Render the robot, environment, and recorder controls."""
    _inject_styles()

    selection = {
        "robot": "hsrb",
        "environment": AVAILABLE_ENVIRONMENTS[0],
    }

    # --- selectors ---

    robot = widgets.ToggleButtons(
        options=[(_style_label(value), value) for value in AVAILABLE_ROBOTS],
        value=selection["robot"],
        description="Robot",
    )

    environment = widgets.ToggleButtons(
        options=[(_style_label(value), value) for value in AVAILABLE_ENVIRONMENTS],
        value=selection["environment"],
        description="Env",
    )

    def _update_selection(change):
        key = "robot" if change["owner"].description == "Robot" else "environment"
        selection[key] = change["new"]
        _select_on_server(selection)
        if key == "environment":
            _reload_rviz_for_environment(change["new"])

    robot.observe(_update_selection, names="value")
    environment.observe(_update_selection, names="value")

    _select_on_server(selection)

    # --- layout ---

    controls = widgets.VBox([robot, environment])
    controls.add_class("demo-card")
    controls.add_class("demo-ui")
    controls.add_class("demo-controls")

    children = []
    logo_header = _logo_header()
    if logo_header is not None:
        children.append(logo_header)
    children.append(controls)
    container = widgets.VBox(children, layout=widgets.Layout(width="100%"))
    container.add_class("demo-shell")
    container.add_class("demo-has-background")
    display(container)
    display(HTML(RECORDER_HTML))


def run_info_ui():
    """Render the demo FAQ and available example videos."""
    _inject_styles()
    children = [_faq_section()]
    container = widgets.VBox(children, layout=widgets.Layout(width="100%"))
    container.add_class("demo-shell")
    container.add_class("demo-stack")
    display(container)
