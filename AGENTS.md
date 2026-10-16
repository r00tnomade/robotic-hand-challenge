# AGENTS.md

Hackathon repo (Black Forest Hackathon 2026): estimate the pose and slip of a grasped object from the tactile sensors on an Inspire RH56DFTP hand. The full brief is in `docs/internal/challenge_description.md`.

## What actually exists (don't trust the scaffold)
- `backend/`, `emulator/`, `frontend/` are **empty stubs**. Every `src/*`, `Dockerfile`, `requirements.txt` and `package.json` is 0 bytes, and so is root `pyproject.toml`. `docker compose up` will not build. If a task needs one of these services, you have to write it from scratch.
- The only working code is:
  - `hardware/tools/hand_gui.py`: Tkinter slider control plus a tactile heatmap, talking to the real hand over Modbus TCP.
  - `hardware/logger.py`: `HardwareLogger` class that writes threaded JSONL logs. It is a library with no `__main__`.
  - `simulation/example/control_inspire_hand.py`: MuJoCo PD-control demo.
  - `simulation/hand_sim/`: grasp simulation that emulates the hand's registers (see Simulation below).
- There are no tests, linters, formatters or CI.

## Environment
- Use the root `venv/` (Python 3.11 with mujoco 3.16, numpy 2.x, pymodbus 3.16, pillow, trimesh, coacd). Run things with `venv/bin/python`. Only the simulation has a requirements file (`simulation/requirements.txt`).
- On macOS, the MuJoCo viewer (`launch_passive`) must run under `venv/bin/mjpython`, not `python`: `venv/bin/mjpython simulation/example/control_inspire_hand.py`.
- The team's hand runs at `192.168.123.211:6000`, Modbus device id 1. This IP is hardcoded in the GUI, the logger and the dataset `meta.json`. `192.168.11.210`, used in `.env.example` and `hardware/register_map.json`, is the factory default from the manual, not this hand's address. `docker-compose.yml` gives the emulator port 5020 while `.env` says 6000, and nothing reads `.env` yet.

## Modbus / hardware gotchas
- The source of truth for hand registers is `docs/internal/hand_manual.pdf` (RH56DFTP user manual, PRJ-02-TS-U-010). It has the register table on p. 16–17 and the tactile layout on p. 26–27. The wrist manual is a separate PDF in the same folder.
- pymodbus 3.16 takes `device_id=`, not `slave=`. `hardware/logger.py` still passes `slave=1`, and its blanket `except Exception` hides the resulting `TypeError`, so it silently logs zeros. `hand_gui.py` uses the correct form.
- Register reads are chunked at 120 registers or fewer. Copy the `safe_read` pattern.
- `hardware/register_map.json` is **not valid JSON** because it contains stray `[cite: N]` annotations. Clean it before calling `json.load`. Its `size` fields are in **bytes**: a 3x3 tactile pad is `size: 18`, which is 9 registers. Code reads `rows*cols` registers.
- 6 DOFs. On the hardware and in the dataset, the order is `little, ring, middle, index, thumb_bend, thumb_rot`. The MuJoCo actuator order is different: `thumb_yaw, thumb_pitch, index, middle, ring, pinky`. Remap when converting between them.
- `1486` is `angle_set` (the commanded setpoint) and `1546` is `angle_act` (the measured angle). `logger.py` records 1486 as "joints", so it captures setpoints, not measurements.
- Angles run 0–1000, with 1000 = open. In physical terms: fingers 20°–176°, thumb bend −13°–70°, thumb rotation 90°–165°. `FORCE_SET` is the fingertip force in grams (0–3000); the finger stops moving once `FORCE_ACT` reaches it. Speed 1000 means a full stroke in about 600 ms. `ERROR` bits: 0 locked rotor, 1 over-temperature, 2 overcurrent, 3 motor fault, 4 comms. `STATUS` is at register 1612 (6 bytes, 1 per DOF). It's missing from `register_map.json` and the manual gives no meaning for its values. Inferred from the dataset: `0` = releasing/open (target ≥ actual), `1` = closing or holding at a closed target, `2` = stopped by the force limit while closing (force around 1900 g), `255` = only in session `20261016_201150`, where the hand wasn't moving (likely not initialised).
- Palm tactile data (8×14) is column-major and bottom-to-top: data point k is row `7 - k%8`, col `k//8`. Fingers are row-major. `hand_gui.py`, and the `palm_r*_c*` labels in the dataset, use a plain `reshape(8, 14)`, so the palm row/column labels don't match the physical layout.
- Tactile layout: 17 groups at registers 3000–4900. The same table appears in `hand_gui.py`, `logger.py` and every `meta.json`. Raw values are 0–4095. The tools subtract a per-taxel baseline recorded at startup and treat values above 50 as contact.
- Wrist registers (1020–1042, 100 units/deg) are documented in `docs/internal/wrist_module_relevant_information.md`. Nothing in the code uses them yet.

## Dataset (`models/dataset/<YYYYMMDD_HHMMSS>/`)
- Each session holds `actuators.csv` (`angle_set_*`, `angle_act_*`, `force_act_*`, `current_*`, `error_*`, `status_*` per DOF), `tactile_raw.csv` (`<group>_r<row>_c<col>`), `tactile_summary.csv` (per-group sum/max/contacts/centroid/force) and `meta.json` (sensor layout plus calibration `offsets`). Join the CSVs on `frame` or `t_unix`.
- The recorder script that produced this data is **not in the repo**. `logger.py` writes a different JSONL format. The summary uses the same logic as `draw()` in `hand_gui.py`, checked against the data: values = raw minus baseline, clipped at 0. `contacts` = number of taxels above 50. `cy`/`cx` = mean row/column index of those taxels and `force` = their mean value, but only when contacts ≥ 2; otherwise both are blank and `force` is 0.0. Rounding: `sum` to an integer, `force` to 1 decimal, `cy`/`cx` to 2 decimals. About 5% of summary values differ by ±1 from what `tactile_raw.csv` gives, most likely because the summary was computed before the raw values were rounded.
- `models/dataset/logs/*.log` are CAD STEP-export logs, not sensor logs.
- The `.gitignore` rule `models/dataset/*.csv` only matches the top level, so the session subfolders are committed.

## Simulation
- `scene.xml` includes only the right hand; the left-hand files were deleted. The hand materials now live in `inspire_hand_right.xml`, because they used to be defined in the left-hand file.
- `hand_sim` must run from `simulation/` as a module: `../venv/bin/python -m hand_sim.assets` regenerates `simulation/objects/<id>/` from the STLs (mm → m, CoACD convex parts), and `../venv/bin/mjpython -m hand_sim.run` opens the viewer with terminal commands. MuJoCo's own viewer shortcuts use most letter and digit keys, so the viewer takes its commands from stdin instead.
- `scene.py` patches the vendor XML at load time through `MjSpec`; the XML itself still has the old torque motors and collisions off. The patches: hand collision geoms (group 2) get contype 2 / conaffinity 1 so the hand never collides with itself; object hulls (group 3) get 1/3; the torque motors become position servos per DOF, in register DOF order, named `act_<dof>`.
- Hand frame: palm faces +x, fingers point +z, thumb is on the +y side. Joint position 0 = open = angle 1000 for every DOF, and thumb yaw at its maximum = opposed thumb.
- In `hand.py`, `FORCE_ACT` comes from contact torques about each DOF's joint divided by the fingertip lever arm, not from actuator torque, so free motion reads idle (77 g). `CURRENT` is still a placeholder model. Objects hang from a mocap "carrier" through a weld (`<id>_weld`); setting `eq_active = 0` releases them.
- Object masses in `config.py` (0.25 / 0.6 kg) are placeholders. VEGABAR 38 must be grasped on its shaft next to the head, near its centre of mass, or it rotates out of the grasp.
- `simulation/simulation/` is an untracked duplicate copy. Ignore it, and don't edit it by mistake.
- The Inspire hand assets are licensed CC BY-NC-SA 4.0 (from dex-urdf). Keep the attribution.

## Conventions
- The hardware tools have German comments and UI strings. Match the surrounding language when editing them.
