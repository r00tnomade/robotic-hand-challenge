import mujoco
import mujoco.viewer
import numpy as np
import os
import time


# PD gains per joint (6 per hand: thumb_yaw, thumb_pitch, index, middle, ring, pinky)
#                    thumb_yaw  thumb_pitch  index  middle  ring  pinky
KP_SINGLE_HAND = [    0.1,       0.1,        0.5,   0.5,   0.5,  0.5]
KD_SINGLE_HAND = [    0.01,      0.01,       0.01,  0.01,  0.01, 0.01]
# Both hands
KP = np.array(KP_SINGLE_HAND + KP_SINGLE_HAND)
KD = np.array(KD_SINGLE_HAND + KD_SINGLE_HAND)

# Actuated joint names (6 DOF per hand)
ACTUATED_JOINTS = [
    "left_thumb_proximal_yaw_joint",
    "left_thumb_proximal_pitch_joint",
    "left_index_proximal_joint",
    "left_middle_proximal_joint",
    "left_ring_proximal_joint",
    "left_pinky_proximal_joint",
    "right_thumb_proximal_yaw_joint",
    "right_thumb_proximal_pitch_joint",
    "right_index_proximal_joint",
    "right_middle_proximal_joint",
    "right_ring_proximal_joint",
    "right_pinky_proximal_joint",
]


def generate_target_trajectory(joint_ranges, loop_steps: int):
    """Generate target position trajectory over joint ranges."""
    trajectory_via_points = np.stack(
        [joint_ranges[:, 0], joint_ranges[:, 1], joint_ranges[:, 0]], axis=1
    )
    times = np.linspace(0.0, 1.0, int(loop_steps))
    bins = np.arange(3) / 2.0

    inds = np.digitize(times, bins, right=True)
    inds[inds == 0] = 1
    alphas = (bins[inds] - times) / (bins[inds] - bins[inds - 1])

    trajectory = alphas * trajectory_via_points[:, inds - 1] + (1.0 - alphas) * trajectory_via_points[:, inds]
    return trajectory.T


def main():
    scene_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "Inspire_hand", "xml", "scene.xml")
    model = mujoco.MjModel.from_xml_path(os.path.abspath(scene_path))
    data = mujoco.MjData(model)

    # Map actuator index -> joint qpos/qvel index
    act_joint_ids = []
    for i in range(model.nu):
        act_name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_ACTUATOR, i)
        # Find corresponding joint
        jnt_name = ACTUATED_JOINTS[i] if i < len(ACTUATED_JOINTS) else None
        if jnt_name:
            jnt_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, jnt_name)
            act_joint_ids.append(jnt_id)
            print(f"  [{i}] {act_name} -> joint {jnt_name} (id={jnt_id})")

    # Get joint ranges for actuated joints
    joint_ranges = np.array([model.jnt_range[jid] for jid in act_joint_ids])

    # Generate target trajectory
    loop_steps = 600
    trajectory = generate_target_trajectory(joint_ranges, loop_steps=loop_steps)
    step = 0
    cam_step = 0

    # Camera orbit: azimuth 180 ± 30 degrees, one full cycle over cam_loop_steps
    cam_base_azimuth = 180
    cam_amplitude = 30
    cam_loop_steps = 2400  # slow orbit

    # Debug: print trajectory range for each actuator
    print(f"\nTrajectory ranges:")
    for i in range(len(act_joint_ids)):
        print(f"  [{i}] {ACTUATED_JOINTS[i]}: target {trajectory[:, i].min():.4f} ~ {trajectory[:, i].max():.4f}, "
              f"kp={KP[i]}, kd={KD[i]}")

    print(f"\nActuators: {model.nu}, Joints: {model.njnt}")

    paused = [False]

    def key_callback(keycode):
        if keycode == 32:  # Space bar to pause/resume
            paused[0] = not paused[0]
            print(f"{'[Paused]' if paused[0] else '[Resumed]'}")

    with mujoco.viewer.launch_passive(model, data, key_callback=key_callback) as viewer:
        viewer.cam.azimuth = 180
        viewer.cam.elevation = -20
        viewer.cam.distance = 0.8
        viewer.cam.lookat[:] = [0, 0, 0.1]
        viewer.opt.geomgroup[2] = 0

        while viewer.is_running():
            if paused[0]:
                viewer.sync()
                time.sleep(0.01)
                continue

            # Target positions for this step
            q_target = trajectory[step]
            step = (step + 1) % loop_steps

            # PD torque: tau = kp * (q_target - q) - kd * qdot
            for i, jid in enumerate(act_joint_ids):
                qpos_adr = model.jnt_qposadr[jid]
                qvel_adr = model.jnt_dofadr[jid]
                pos_error = q_target[i] - data.qpos[qpos_adr]
                vel = data.qvel[qvel_adr]
                torque = KP[i] * pos_error -  KD[i] * vel
                # torque = 0.1 * pos_error - 0.01 * vel
                data.ctrl[i] = np.clip(torque, -1, 1)

            # Camera orbit
            viewer.cam.azimuth = cam_base_azimuth + cam_amplitude * np.sin(2 * np.pi * cam_step / cam_loop_steps)
            cam_step = (cam_step + 1) % cam_loop_steps

            mujoco.mj_step(model, data)
            viewer.sync()
            time.sleep(model.opt.timestep)


if __name__ == "__main__":
    main()
