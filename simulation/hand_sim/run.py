"""Interactive MuJoCo viewer for the simulated hand.

Run from simulation/ (macOS needs mjpython for the viewer):
    ../venv/bin/mjpython -m hand_sim.run

Type commands in the terminal while the viewer is open (see HELP). Space pauses the physics.
"""

import argparse
import queue
import sys
import threading
import time

import mujoco
import mujoco.viewer
import numpy as np

from . import config as C
from .episode import HandoverEpisode
from .policy import ScriptedGraspPolicy
from .world import World

HELP = f"""commands:
  obj <id>            switch object ({', '.join(C.OBJECTS)}), hand pre-shapes, object placed at grasp pose
  preshape            fingers open, thumb opposed
  close [force_g]     close all fingers with a force limit (default: object's grasp_force_g)
  open                open all DOFs
  angles a b c d e f  raw ANGLE_SET in DOF order {C.DOF_NAMES} (-1 = keep)
  force  a b c d e f  raw FORCE_SET (grams)
  speed  a b c d e f  raw SPEED_SET (0-1000)
  release             let go of the object (gravity takes over)
  attach              put the object back at its grasp pose
  status               print the register readout
  tactile              print tactile group sums/contacts above the contact threshold
  help | quit
(run with --demo for an automatic loop of random handover episodes instead)"""


def _stdin_reader(q: queue.Queue):
    for line in sys.stdin:
        q.put(line.strip())


def _print_status(world: World):
    r = world.hand.read()
    pos, _ = world.object_pose()
    print(f"t={world.d.time:6.2f}s  object={world.active} pos(mm)={np.round(pos * 1000, 1)}")
    for key in ("angle_set", "angle_act", "force_act", "current", "status"):
        print(f"  {key:10s} {r[key]}")


def _handle(cmd: str, world: World) -> bool:
    parts = cmd.split()
    if not parts:
        return True
    op, args = parts[0], parts[1:]
    hand = world.hand
    try:
        if op in ("quit", "exit"):
            return False
        if op == "help":
            print(HELP)
        elif op == "obj":
            hand.set_angles(C.PRESHAPE_ANGLES)
            world.select(args[0])
        elif op == "preshape":
            hand.set_angles(C.PRESHAPE_ANGLES)
        elif op == "close":
            force = int(args[0]) if args else C.OBJECTS[world.active]["grasp_force_g"]
            hand.set_forces([force] * 6)
            hand.set_angles([0, 0, 0, 0, 0, -1])
        elif op == "open":
            hand.set_angles([C.ANGLE_MAX] * 6)
        elif op in ("angles", "force", "speed"):
            vals = [int(a) for a in args]
            assert len(vals) == 6, "need 6 values"
            {"angles": hand.set_angles, "force": hand.set_forces, "speed": hand.set_speeds}[op](vals)
        elif op == "release":
            world.release()
        elif op == "attach":
            cfg = C.OBJECTS[world.active]
            world.place(world.active, cfg["grasp_pos"], cfg["grasp_quat"])
        elif op == "status":
            _print_status(world)
        elif op == "tactile":
            raw = world.tactile.step(world.d)
            summary = world.tactile.summary(raw)
            active = {k: v for k, v in summary.items() if v["contacts"] > 0}
            print(active or "(no taxel above the contact threshold)")
        else:
            print(f"unknown command {op!r}; type help")
    except (IndexError, ValueError, KeyError, AssertionError) as e:
        print(f"bad command: {e}")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--object", default=next(iter(C.OBJECTS)), choices=list(C.OBJECTS))
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--demo", action="store_true",
                    help="loop random handover episodes (scripted policy) on random objects")
    args = ap.parse_args()

    world = World(seed=args.seed)
    world.hand.set_angles(C.PRESHAPE_ANGLES)
    world.step(int(0.8 / world.m.opt.timestep))
    world.select(args.object)

    commands: queue.Queue = queue.Queue()
    threading.Thread(target=_stdin_reader, args=(commands,), daemon=True).start()
    paused = [False]

    def key_callback(keycode):
        if keycode == 32:
            paused[0] = not paused[0]
            print("[paused]" if paused[0] else "[running]")

    demo_rng = np.random.default_rng(args.seed)
    demo_policy = ScriptedGraspPolicy()
    episode = None
    n_episodes = n_success = 0
    pace = {"steps": 0}

    print(HELP)
    with mujoco.viewer.launch_passive(world.m, world.d, key_callback=key_callback) as viewer:
        viewer.opt.geomgroup[2] = 0  # hand collision meshes
        viewer.opt.geomgroup[3] = 0  # object collision hulls
        viewer.cam.azimuth, viewer.cam.elevation, viewer.cam.distance = 150, -15, 0.45
        viewer.cam.lookat[:] = [0.03, 0.1, 0.12]

        steps_per_frame = max(1, round((1 / 60) / world.m.opt.timestep))

        def paced_step(n):
            """Episode stepper: step under the viewer lock, sync and sleep about once per rendered frame."""
            with viewer.lock():
                world.step(n)
            pace["steps"] += n
            if pace["steps"] >= steps_per_frame:
                pace["steps"] = 0
                viewer.sync()
                time.sleep(steps_per_frame * world.m.opt.timestep)

        while viewer.is_running():
            frame_start = time.perf_counter()
            while not commands.empty():
                with viewer.lock():
                    if not _handle(commands.get(), world):
                        return
            if args.demo:
                if paused[0]:
                    viewer.sync()
                    time.sleep(0.02)
                    continue
                if episode is None:
                    with viewer.lock():
                        episode = HandoverEpisode(world, demo_policy, demo_rng, step_fn=paced_step)
                    print(f"[demo] episode {n_episodes + 1}: {episode.obj_id}, roll {np.degrees(episode.info['roll_rad']):.0f} deg")
                if not episode.tick():
                    res = episode.result
                    n_episodes += 1
                    n_success += res["success"]
                    print(f"[demo]   {'OK' if res['success'] else 'FAILED (' + res['failure'] + ')'}: shift {res['shift_mm']} mm, "
                          f"rot {res['rot_deg']} deg  | {n_success}/{n_episodes} successful")
                    viewer.sync()
                    time.sleep(1.0)
                    episode = None
                continue
            if not paused[0]:
                with viewer.lock():
                    world.step(steps_per_frame)
            viewer.sync()
            time.sleep(max(0.0, steps_per_frame * world.m.opt.timestep - (time.perf_counter() - frame_start)))


if __name__ == "__main__":
    main()
