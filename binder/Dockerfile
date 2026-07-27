FROM intel4coro/jupyter-ros2:jazzy-py3.12

USER root

RUN apt update && apt install -y --no-install-recommends \
    graphviz \
    libgraphviz-dev \
    pkg-config \
    python3-dev \
    build-essential \
    ffmpeg \
    nodejs \
    npm \
    wmctrl && \
    rm -rf /var/lib/apt/lists/*

RUN apt update && apt install -y --no-install-recommends \
    ros-jazzy-ros2-control \
    ros-jazzy-ros2-controllers \
    ros-jazzy-hardware-interface \
    ros-jazzy-controller-manager \
    ros-jazzy-control-msgs \
    ros-jazzy-xacro \
    ros-jazzy-rqt-joint-trajectory-controller \
    ros-jazzy-rclpy \
    ros-jazzy-rclpy-message-converter \
    python3-vcstool && \
    rm -rf /var/lib/apt/lists/*

ARG ROS_DISTRO=jazzy
ENV ROS_DISTRO=${ROS_DISTRO}

RUN pip install uv poetry

ARG CRAM_REVISION=e8d906b665d158318df2917df21bf3ee8841c78b
ENV CRAM_REPOSITORY=/home/jovyan/libs/cognitive_robot_abstract_machine
ENV NLP_DEMO_DIR=${CRAM_REPOSITORY}/pycram/demos/thesis_demo
ENV PYTHONPATH=${CRAM_REPOSITORY}/pycram/demos

RUN set -ex && \
    poetry config virtualenvs.create false && \
    git config --global http.postBuffer 524288000 && \
    git config --global http.version HTTP/1.1 && \
    mkdir -p /home/jovyan/libs && \
    git init ${CRAM_REPOSITORY} && \
    cd ${CRAM_REPOSITORY} && \
    git remote add origin https://github.com/wittjan/cognitive_robot_abstract_machine.git && \
    for i in 1 2 3; do \
      git fetch --depth 1 origin ${CRAM_REVISION} && break || \
      (echo "fetch failed (attempt $i), retrying..." && sleep 10); \
    done && \
    git checkout --detach FETCH_HEAD && \
    sed -i '/^[[:space:]]*random_events[[:space:]]*=.*$/d' pyproject.toml && \
    poetry install && \
    git checkout -- pyproject.toml && \
    mkdir -p /workspace/ros/src && \
    cd /workspace/ros/src && \
    git clone --depth 1 -b ros-jazzy --single-branch https://github.com/code-iai/iai_maps.git && \
    git clone --depth 1 -b ros-jazzy-main --single-branch https://github.com/code-iai/iai_pr2.git && \
    git clone --depth 1 -b ros-jazzy --single-branch https://github.com/code-iai/iai_robots.git && \
    git clone --depth 1 -b ros2-jazzy --single-branch https://github.com/code-iai/hsr_description.git && \
    git clone --depth 1 -b ros2-main --single-branch https://github.com/code-iai/iai_tiago_description.git && \
    git clone --depth 1 -b ros2-master --single-branch https://github.com/realsenseai/realsense-ros.git && \
    git clone --depth 1 -b jazzy --single-branch https://github.com/UniversalRobots/Universal_Robots_ROS2_Description.git && \
    git clone --depth 1 https://github.com/maltehue/ros2_robotiq_gripper.git && \
    rm -rf ros2_robotiq_gripper/robotiq_driver \
           ros2_robotiq_gripper/robotiq_drivers \
           ros2_robotiq_gripper/robotiq_controllers \
           ros2_robotiq_gripper/robotiq_hardware_tests  \
           realsense-ros/realsense2_ros_mqtt_bridge  \
           realsense-ros/realsense2_rgbd_plugin  \
           realsense-ros/realsense2_camera_msgs \
           realsense-ros/realsense2_camera && \
    find /workspace/ros/src -type f -name package.xml -path '*/robotiq_driver/package.xml' -execdir touch COLCON_IGNORE \; && \
    # git clone https://github.com/sunava/isr_testbed.git && \
    git clone --depth 1 https://github.com/ipa320/cob_simulation.git && \
    cd /workspace/ros && \
    . /opt/ros/${ROS_DISTRO}/setup.sh && \
    colcon build --symlink-install \
      --packages-skip cob_gazebo_tools cob_gazebo_objects cob_gazebo_worlds cob_gazebo cob_bringup_sim cob_simulation && \
    echo "source /workspace/ros/install/setup.bash" >> /root/.bashrc

RUN pip install xacro "setuptools<81"

ARG CUDA_INDEX=cpu
# Install torch CPU-only in its own layer to spread memory usage.
RUN uv pip install --system --torch-backend ${CUDA_INDEX} torch

COPY requirements.txt /tmp/requirements.txt
# Try avoiding OOM issues
RUN UV_CONCURRENT_BUILDS=1 UV_CONCURRENT_DOWNLOADS=8 \
    CMAKE_BUILD_PARALLEL_LEVEL=1 MAKEFLAGS="-j1" \
    uv pip install --system --torch-backend ${CUDA_INDEX} -r /tmp/requirements.txt

RUN pip install --no-deps --force-reinstall \
    ${CRAM_REPOSITORY}/random_events

ENV HF_HOME=/root/.cache/huggingface
ENV HF_HUB_DISABLE_PROGRESS_BARS=0
ENV HF_XET_HIGH_PERFORMANCE=1
RUN python3 -c "from faster_whisper import WhisperModel; WhisperModel('small')"
ARG PLANNER_GGUF_MODEL=wijan/Robot-Action-Planner-GGUF
ENV PLANNER_GGUF_MODEL=${PLANNER_GGUF_MODEL}
ARG PLANNER_GGUF_REVISION=e3ffdd293a59bda6fa13756ab2cc47ee7eb9e90b
ENV PLANNER_GGUF_REVISION=${PLANNER_GGUF_REVISION}
ENV PLANNER_GGUF_DIR=/opt/planner-model
ENV PLANNER_GGUF_FILE=/opt/planner-model/meta-llama-3.1-8b-instruct.Q4_K_M.gguf
ARG PLANNER_MODEL=wijan/Robot-Action-Planner
ENV PLANNER_MODEL=${PLANNER_MODEL}
RUN python3 -c "\
	from huggingface_hub import snapshot_download; \
	import os; \
	snapshot_download( \
	    os.environ['PLANNER_GGUF_MODEL'], \
	    revision=os.environ['PLANNER_GGUF_REVISION'], \
	    local_dir=os.environ['PLANNER_GGUF_DIR'], \
	    allow_patterns=[os.path.basename(os.environ['PLANNER_GGUF_FILE'])])"

# Optionally also bake the merged (non-GGUF) model so PLANNER_USE_GGUF=0 stays fast.
ARG BAKE_MERGED=0
RUN if [ "${BAKE_MERGED}" = "1" ]; then python3 -c "\
	from huggingface_hub import snapshot_download; \
	import os; \
	snapshot_download(os.environ['PLANNER_MODEL'])"; fi

USER root
ENV REPO_DIR=/home/repo
RUN mkdir -p ${REPO_DIR}
COPY . ${REPO_DIR}/
RUN git config --global --add safe.directory ${REPO_DIR}

# The demo's action interface, built into the existing colcon workspace.
RUN cp -r ${REPO_DIR}/binder/ros_ws/src/thesis_demo_msgs /workspace/ros/src/ && \
    cd /workspace/ros && \
    . /opt/ros/${ROS_DISTRO}/setup.sh && \
    colcon build --symlink-install --packages-select thesis_demo_msgs

WORKDIR ${REPO_DIR}
ENV CODE_WORKING_DIRECTORY=${REPO_DIR}

COPY default.rviz /home/jovyan/.rviz2/default.rviz
RUN mkdir -p /home/jovyan/.ipython/profile_default/startup /root/.ipython/profile_default/startup

RUN cd ${REPO_DIR}/binder/desktop-widget && \
    npm install && \
    npm run build && \
    jupyter labextension install . --no-build && \
    jupyter lab build --minimize=False

COPY binder/entrypoint.sh /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
