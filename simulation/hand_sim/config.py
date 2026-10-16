from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent.parent
HAND_XML = SIM_DIR / "Inspire_hand" / "xml" / "inspire_hand_right.xml"
CAD_DIR = SIM_DIR / "assets"
OBJECTS_DIR = SIM_DIR / "objects"

# DOF order of the real hand registers (ANGLE_SET(0..5) etc.) and of models/dataset.
DOF_NAMES = ["little", "ring", "middle", "index", "thumb_bend", "thumb_rot"]
DOF_JOINTS = [
    "right_pinky_proximal_joint",
    "right_ring_proximal_joint",
    "right_middle_proximal_joint",
    "right_index_proximal_joint",
    "right_thumb_proximal_pitch_joint",
    "right_thumb_proximal_yaw_joint",
]
# Body whose tip defines the lever arm used to convert actuator torque to fingertip force (grams).
DOF_TIP_BODIES = [
    "right_pinky_intermediate",
    "right_ring_intermediate",
    "right_middle_intermediate",
    "right_index_intermediate",
    "right_thumb_distal",
    "right_thumb_distal",
]

# Hand register limits (docs/internal/hand_manual.pdf, section 2.6).
ANGLE_MAX = 1000  # 1000 = open (joint at 0 rad), 0 = closed (joint at upper range limit)
FORCE_SET_MAX = 3000  # grams at the fingertip
SPEED_MAX = 1000  # 1000 = full stroke in FULL_STROKE_TIME_S without load
FULL_STROKE_TIME_S = 0.6
FORCE_ACT_IDLE_G = 77.0  # idle FORCE_ACT reading observed in models/dataset

# STATUS codes as observed in models/dataset (not documented in the manual).
STATUS_RELEASING = 0
STATUS_GRASPING = 1
STATUS_FORCE_STOP = 2

# Collision bit masks: hand collides with objects (and floor), not with itself.
HAND_CONTYPE, HAND_CONAFFINITY = 2, 1
OBJECT_CONTYPE, OBJECT_CONAFFINITY = 1, 3

# Grasp objects prepared from CAD by `python -m hand_sim.assets`.
# Masses are placeholders until confirmed from the VEGA datasheets.
# grasp_pos/grasp_quat: default object pose (world frame) for a power grasp in front of the palm;
# the hand's palm faces +x, fingers point +z, thumb is on the +y side.
OBJECTS = {
    "vegabar_29": {
        "cad": "0edecf86-fa9a-4a2b-9fc1-a49439372a67-VEGABAR_29_STL.stl",
        "mass_kg": 0.25,
        "rgba": [0.75, 0.75, 0.78, 1.0],
        "grasp_pos": [0.044, 0.09, 0.11],
        "grasp_quat": [1.0, 0.0, 0.0, 0.0],
        "grasp_force_g": 1000,
        # Point (object frame) on the long axis that random rotations pivot around.
        "pivot": [0.0, 0.0, 0.0],
        # Random handover offsets of the pivot (world frame, metres): (min, max) per axis.
        "offset_range": [[0.0, 0.008], [-0.015, 0.015], [-0.012, 0.012]],
    },
    "vegabar_38": {
        "cad": "f8a929b6-d3c2-485c-9162-e154690c0d41-VEGABAR_38.stl",
        "mass_kg": 0.6,
        "rgba": [0.55, 0.6, 0.7, 1.0],
        # Shaft across the fingers, heavy head just past the little finger (close to the COM).
        "grasp_pos": [0.030, 0.076, 0.11],
        "grasp_quat": [0.0, 0.0, 0.0, 1.0],
        "grasp_force_g": 2500,
        "pivot": [-0.014, 0.0, 0.0],  # shaft axis
        "offset_range": [[0.0, 0.008], [0.0, 0.015], [-0.012, 0.012]],
    },
}

# Random handover orientation (applied about the object's pivot).
ROLL_RANGE_RAD = (-3.14159, 3.14159)  # about the object's long axis (object y)
TILT_X_RANGE_RAD = (-0.35, 0.35)  # long axis tilts within the palm plane
TILT_Z_RANGE_RAD = (-0.17, 0.17)  # long axis tilts toward/away from the palm

# Episode timing (seconds of sim time) and rates.
CONTROL_HZ = 20  # policy / register update rate, matches hardware/logger.py target_hz
APPROACH_DIST_M = 0.08
APPROACH_TIME_S = 0.6
GRASP_TIMEOUT_S = 2.0
RELEASE_RAMP_S = 0.3  # after release the carried weight is handed over gradually
HOLD_TIME_S = 2.0
# Success after the hold phase: pivot moved less than this, rotated less than this, no floor contact.
SUCCESS_MAX_SHIFT_M = 0.015
SUCCESS_MAX_ROT_RAD = 0.26

# Pre-grasp posture: fingers open, thumb rotated into opposition (ANGLE_SET order = DOF_NAMES).
PRESHAPE_ANGLES = [1000, 1000, 1000, 1000, 1000, 0]
