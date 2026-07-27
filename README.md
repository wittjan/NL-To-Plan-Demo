# Natural-Language Robot-Action-Planner Demo

[![Binder](https://binder.intel4coro.de/badge_logo.svg)](https://binder.intel4coro.de/v2/gh/wittjan/NL-To-Plan-Demo/HEAD?urlpath=lab/workspaces/new-workspace)

This repository provides the browser interface and reproducible runtime for a natural-language robot-action-planning demo. A user selects a robot and a simulated world, records a household command, and watches the robot executing the task.

```text
speech
  -> Whisper transcription
  -> LLM planner
  -> validation
  -> ROS 2 ExecutePlan action
  -> grounding and execution
```

## Start the demo

### Option 1: Start the hosted Binder demo

Click the **Launch Binder** badge above. Binder builds or restores the demo image and opens the prepared JupyterLab workspace.
Startup can take several minutes when the image or models are not cached.

When JupyterLab appears:

1. Open `demo/demo.ipynb` if it is not already open.
2. Run its final code cell if the interface did not start automatically.
3. Wait until the planner reports that the GGUF model is ready.
4. Select a robot and a world.
5. Wait for the world to appear in RViz.
6. Press the record button, speak a command, and stop the recording.
7. Wait until the plan is generated and watch the robot execute it. (This can take several minutes).

### Option 2: Start it locally with Docker

#### CPU

Start Docker from the `binder` directory:

```
docker compose --profile cpu up --build
```

Open `http://localhost:8888` after the build.

#### NVIDIA (experimental)

Start Docker from the `binder` directory:

```
docker compose --profile nvidia up --build
```

It should automatically install the right dependencies with the right CUDA index.

To use a particular compatible PyTorch CUDA wheel, set `CUDA_INDEX`, for
example:

```bash
CUDA_INDEX=cu124 ./binder/run.sh
```

#### Stop container

Stop the foreground process with `Ctrl+C`, then remove the containers with:

```bash
docker compose --profile cpu down
```

## Available worlds

The tables below show the initial movable-object inventory.

### Apartment

The apartment contains a kitchen and living room. Its relevant landmarks include an island countertop, a regular countertop, a dining table, a coffee
table, a bedside table, a sink, an oven, and a dishwasher.

| Object | Initial placement |
|---|---|
| Bowl | On the island countertop |
| Breakfast cereal | On the island countertop |
| Milk | On the island countertop |
| Coke bottle | On the regular countertop |
| Mug | On the regular countertop |
| Mug | On the dining table |
| Plate | On the dining table |
| Plate | On the regular countertop |
| Apple | On the dining table |
| Apple | On the island countertop |
| Spoon | In the top cutlery drawer |
| Fork | In the top cutlery drawer |
| Knife | In the top cutlery drawer |

The duplicated mugs, plates, and apples deliberately make commands such as
“pick up the apple” ambiguous. A correct planner can ask whether the user means
the apple on the dining table or the one on the island.

Example commands:

```text
Put the milk next to the cereal.
Pick up the apple on the dining table.
Take the fork from the drawer and place it on the table.
```

### Kitchen

The kitchen contains a kitchen island, sink counter, table, sink, oven, fridge,
trash can, and several drawers.

| Object | Initial placement |
|---|---|
| Wine bottle | On the table |
| Soap bottle | On the sink counter |
| Kettle | On the table |
| Cheez-It box | On the kitchen island |
| Gelatin box | On the kitchen island |
| Tuna can | On the table |
| Pringles can | On the table |
| Gelatin box | On the sink counter |
| Tuna can | In the upper-left drawer of the sink unit |
| Salt container | In the middle-left drawer of the sink unit |
| Mustard bottle | In the fridge |
| Tomato soup | In the fridge |
| Spoon | In the upper-left drawer of the kitchen island |
| Fork | In the upper-left drawer of the kitchen island |
| Knife | In the upper-left drawer of the kitchen island |

This world contains two gelatin boxes and two tuna cans at different
locations. Their placement is therefore relevant when a command does not
identify which instance should be used.

Example commands:

```text
Open the fridge.
Take the mustard bottle from the fridge and put it on the table.
Pick up the tuna can from the drawer.
```
