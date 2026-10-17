"""
XGBoost trained on 300 simulation sessions (hold-phase only).
Validated on 13 real hardware sessions (contacts > 20 as hold-proxy).

Sim labels:  vegabar_29 (w0-w3) = Sensor A (0)
             vegabar_38 (w4-w7) = Sensor B (1)
Real labels: sessions 6-12     = Sensor A (0)
             sessions 13-18    = Sensor B (1)
"""

from pathlib import Path
import json
import numpy as np
import pandas as pd
import joblib
from xgboost import XGBClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score, classification_report

HERE        = Path(__file__).parent
SIM_DIR     = HERE.parent / "models" / "dataset_sim"
REAL_DIR    = HERE.parent / "models" / "dataset"
MODEL_DIR   = HERE / "model"
MODEL_DIR.mkdir(exist_ok=True)

REAL_SESSIONS_A = [
    "20261016_204344", "20261016_204402", "20261016_204429",
    "20261016_204457", "20261016_204513", "20261016_204524", "20261016_204548",
]
REAL_SESSIONS_B = [
    "20261016_204558", "20261016_204609", "20261016_204619",
    "20261016_204627", "20261016_204637", "20261016_204649",
]

META_COLS     = {"frame", "t_unix", "t_rel"}
ACTUATOR_COLS = [
    "angle_act_little", "angle_act_ring", "angle_act_middle",
    "angle_act_index", "angle_act_thumb_bend", "angle_act_thumb_rot",
]


def get_label_from_meta(session_path: Path) -> int:
    meta = json.loads((session_path / "meta.json").read_text())
    obj  = meta.get("object") or meta.get("episode_info", {}).get("object", "")
    return 0 if "29" in obj else 1


def load_sim_session(session_path: Path) -> pd.DataFrame | None:
    """Load one sim session, keep only hold-phase frames."""
    tac  = pd.read_csv(session_path / "tactile_summary.csv")
    act  = pd.read_csv(session_path / "actuators.csv")[["frame"] + ACTUATOR_COLS]
    pose = pd.read_csv(session_path / "object_pose.csv")[["frame", "phase"]]

    df = tac.merge(act, on="frame").merge(pose, on="frame")
    df = df[df["phase"] == "hold"].drop(columns=["phase"])

    if len(df) < 5:
        return None

    feat_cols = [c for c in df.columns if c not in META_COLS]
    df[feat_cols] = df[feat_cols].fillna(0)
    df["label"]   = get_label_from_meta(session_path)
    return df


def load_real_session(session: str, label: int) -> pd.DataFrame:
    """Load one real session, keep active-contact frames as hold proxy."""
    p   = REAL_DIR / session
    tac = pd.read_csv(p / "tactile_summary.csv")
    act = pd.read_csv(p / "actuators.csv")[["frame"] + ACTUATOR_COLS]
    df  = tac.merge(act, on="frame")

    contact_cols = [c for c in df.columns if c.endswith("_contacts")]
    df = df[df[contact_cols].sum(axis=1) > 20]

    feat_cols = [c for c in df.columns if c not in META_COLS]
    df[feat_cols] = df[feat_cols].fillna(0)
    df["label"]   = label
    df["session"] = session
    return df


# ── Load sim data ─────────────────────────────────────────────────────────────
print("Loading simulation sessions (hold phase)...")
sim_frames = []
skipped = 0
for s in sorted(SIM_DIR.iterdir()):
    df = load_sim_session(s)
    if df is None:
        skipped += 1
        continue
    sim_frames.append(df)

sim_data = pd.concat(sim_frames, ignore_index=True)
feature_cols = [c for c in sim_data.columns if c not in META_COLS | {"label", "session"}]

n_a = (sim_data["label"] == 0).sum()
n_b = (sim_data["label"] == 1).sum()
print(f"  {len(sim_frames)} sessions loaded ({skipped} skipped <5 hold frames)")
print(f"  Sensor A: {n_a} frames  |  Sensor B: {n_b} frames  |  Total: {len(sim_data)}")

# ── Load real data ────────────────────────────────────────────────────────────
print("\nLoading real sessions (contacts > 20)...")
real_frames = []
for s in REAL_SESSIONS_A:
    real_frames.append(load_real_session(s, 0))
for s in REAL_SESSIONS_B:
    real_frames.append(load_real_session(s, 1))
real_data = pd.concat(real_frames, ignore_index=True)
print(f"  {len(real_data)} frames across 13 sessions")

# Align feature cols (sim and real share the same schema)
for col in feature_cols:
    if col not in real_data.columns:
        real_data[col] = 0.0

# ── Train on sim ──────────────────────────────────────────────────────────────
print("\nTraining XGBoost on sim data...")
X_sim = sim_data[feature_cols].values
y_sim = sim_data["label"].values

scaler  = StandardScaler()
X_sim_s = scaler.fit_transform(X_sim)

model = XGBClassifier(
    n_estimators=300,
    max_depth=5,
    learning_rate=0.05,
    subsample=0.8,
    colsample_bytree=0.8,
    eval_metric="logloss",
    verbosity=0,
    random_state=42,
    n_jobs=-1,
)
model.fit(X_sim_s, y_sim)
train_acc = accuracy_score(y_sim, model.predict(X_sim_s))
print(f"  In-sample accuracy (sim): {train_acc:.3f}")

# ── Validate on real ──────────────────────────────────────────────────────────
print("\n" + "="*55)
print("  Sim → Real validation (13 hardware sessions)")
print("="*55)

X_real = real_data[feature_cols].values
y_real = real_data["label"].values
X_real_s = scaler.transform(X_real)
preds = model.predict(X_real_s)

overall_acc = accuracy_score(y_real, preds)
print(f"\n  Overall frame accuracy: {overall_acc:.3f}")
print(f"\n{classification_report(y_real, preds, target_names=['Sensor A','Sensor B'])}")

# Per-session majority vote
print("  Per-session majority vote:")
for s in REAL_SESSIONS_A + REAL_SESSIONS_B:
    mask    = real_data["session"] == s
    y_s     = y_real[mask.values]
    p_s     = preds[mask.values]
    maj     = int(np.bincount(p_s).argmax())
    correct = maj == y_s[0]
    lbl     = "A" if y_s[0] == 0 else "B"
    pred_lbl = "A" if maj == 0 else "B"
    sym     = "✓" if correct else "✗"
    conf    = model.predict_proba(X_real_s[mask.values]).max(axis=1).mean()
    print(f"    {sym} [{lbl}] {s}  → {pred_lbl}  conf={conf:.1%}")

# Session-level accuracy
session_preds = []
for s in REAL_SESSIONS_A + REAL_SESSIONS_B:
    mask = real_data["session"] == s
    p_s  = preds[mask.values]
    maj  = int(np.bincount(p_s).argmax())
    true = int(real_data[mask]["label"].iloc[0])
    session_preds.append(maj == true)
print(f"\n  Session-level accuracy: {np.mean(session_preds):.3f}  ({sum(session_preds)}/13 correct)")

# ── Save ──────────────────────────────────────────────────────────────────────
joblib.dump(model,        MODEL_DIR / "xgb_sim.pkl")
joblib.dump(scaler,       MODEL_DIR / "scaler_sim.pkl")
joblib.dump(feature_cols, MODEL_DIR / "feature_cols.pkl")
print(f"\nSaved → {MODEL_DIR}/xgb_sim.pkl")
