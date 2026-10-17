"""
Train the same XGBoost sensor A/B classifier as train.py, but on simulator-generated sessions
(simulation/hand_sim/generate_dataset.py) instead of the 13 real hardware recordings.

Ground truth comes straight from each session's meta.json["object"] field (the simulator knows
exactly what it grasped), mapped via OBJECT_TO_LABEL below:
    vegabar_29 (Sensor A) = 0, vegabar_38 (Sensor B) = 1
confirmed against the real dataset's 13 labeled sessions (2026-10-17).

Splits by SESSION, not by frame, for train/val (frames within a session are highly correlated;
a frame-level split would leak information and overstate accuracy).

Usage (from repo root):
    venv/bin/python classifier/train_sim.py --dataset models/dataset_sim --val-frac 0.2
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import joblib
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

HERE = Path(__file__).parent
MODEL_DIR = HERE / "model"

META_COLS = {"frame", "t_unix", "t_rel"}
ACTUATOR_COLS = [
    "angle_act_little", "angle_act_ring", "angle_act_middle",
    "angle_act_index", "angle_act_thumb_bend", "angle_act_thumb_rot",
]
OBJECT_TO_LABEL = {"vegabar_29": 0, "vegabar_38": 1}  # 0 = Sensor A, 1 = Sensor B
LABEL_NAMES = {0: "Sensor A", 1: "Sensor B"}


def load_session(session_dir: Path) -> pd.DataFrame | None:
    meta = json.loads((session_dir / "meta.json").read_text())
    obj = meta.get("object")
    if obj not in OBJECT_TO_LABEL:
        return None
    tac = pd.read_csv(session_dir / "tactile_summary.csv")
    act = pd.read_csv(session_dir / "actuators.csv")[["frame"] + ACTUATOR_COLS]
    df = tac.merge(act, on="frame")
    df["label"] = OBJECT_TO_LABEL[obj]
    df["session"] = session_dir.name
    feat_cols = [c for c in df.columns if c not in META_COLS | {"label", "session"}]
    df[feat_cols] = df[feat_cols].fillna(0)
    return df


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", default=str(HERE.parent / "models" / "dataset_sim"))
    ap.add_argument("--val-frac", type=float, default=0.2, help="fraction of sessions held out, per class")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--suffix", default="_sim", help="model files are saved as xgb_sensor<suffix>.pkl etc.")
    args = ap.parse_args()

    session_dirs = sorted(p.parent for p in Path(args.dataset).glob("*/meta.json"))
    print(f"Loading {len(session_dirs)} sessions from {args.dataset} ...")
    frames = [df for d in session_dirs if (df := load_session(d)) is not None]
    data = pd.concat(frames, ignore_index=True)
    feature_cols = [c for c in data.columns if c not in META_COLS | {"label", "session"}]

    rng = np.random.default_rng(args.seed)
    sessions = data[["session", "label"]].drop_duplicates()
    val_sessions = set()
    for label in sessions["label"].unique():
        s = sessions.loc[sessions.label == label, "session"].tolist()
        rng.shuffle(s)
        val_sessions.update(s[: max(1, round(len(s) * args.val_frac))])
    is_val = data["session"].isin(val_sessions)
    train_df, val_df = data[~is_val], data[is_val]

    print(f"  {len(data)} frames from {sessions.shape[0]} sessions | {len(feature_cols)} features")
    print(f"  train: {len(train_df)} frames / {sessions.shape[0] - len(val_sessions)} sessions | "
          f"val: {len(val_df)} frames / {len(val_sessions)} sessions")
    for label, name in LABEL_NAMES.items():
        print(f"  {name}: {(data.label == label).sum()} frames total "
              f"({(sessions.label == label).sum()} sessions)")

    scaler = StandardScaler()
    X_train = scaler.fit_transform(train_df[feature_cols].values)
    X_val = scaler.transform(val_df[feature_cols].values)

    model = XGBClassifier(
        n_estimators=200, max_depth=4, learning_rate=0.1,
        subsample=0.8, colsample_bytree=0.8, eval_metric="logloss",
        verbosity=0, random_state=args.seed, n_jobs=-1,
    )
    model.fit(X_train, train_df["label"].values)

    train_acc = (model.predict(X_train) == train_df["label"].values).mean()
    val_pred = model.predict(X_val)
    val_acc = (val_pred == val_df["label"].values).mean()
    print(f"\n  Train accuracy (frame-level): {train_acc:.3f}")
    print(f"  Val accuracy   (frame-level): {val_acc:.3f}  (held-out sessions, not frames)")

    # Session-level majority vote, closer to how predict.py is actually used.
    val_df = val_df.assign(pred=val_pred)
    votes = val_df.groupby("session").apply(
        lambda g: (g["pred"].mode()[0] == g["label"].iloc[0]), include_groups=False
    )
    print(f"  Val accuracy   (session majority vote): {votes.mean():.3f} ({votes.sum()}/{len(votes)} sessions)")

    MODEL_DIR.mkdir(exist_ok=True)
    joblib.dump(model, MODEL_DIR / f"xgb_sensor{args.suffix}.pkl")
    joblib.dump(scaler, MODEL_DIR / f"scaler{args.suffix}.pkl")
    joblib.dump(feature_cols, MODEL_DIR / f"feature_cols{args.suffix}.pkl")
    print(f"\nSaved to {MODEL_DIR}/*{args.suffix}.pkl")


if __name__ == "__main__":
    main()
