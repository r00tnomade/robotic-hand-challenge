"""Convert the CAD STL files into MuJoCo-ready meshes.

Writes simulation/objects/<id>/ with a visual mesh, convex collision parts and object.json.
STL input is in millimetres; output is in metres, centred on the bounding-box centre.

Usage (from simulation/):  ../venv/bin/python -m hand_sim.assets [--threshold 0.04] [object_id ...]
"""

import argparse
import json
import time

import coacd
import numpy as np
import trimesh

from .config import CAD_DIR, OBJECTS, OBJECTS_DIR


def prepare(obj_id: str, threshold: float, max_hulls: int) -> None:
    cfg = OBJECTS[obj_id]
    mesh = trimesh.load(CAD_DIR / cfg["cad"], force="mesh")
    mesh.apply_scale(0.001)
    offset = -mesh.bounds.mean(axis=0)
    mesh.apply_translation(offset)

    out = OBJECTS_DIR / obj_id
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("collision_*.obj"):
        old.unlink()
    mesh.export(out / "visual.obj")

    t0 = time.time()
    parts = coacd.run_coacd(
        coacd.Mesh(mesh.vertices, mesh.faces),
        threshold=threshold,
        max_convex_hull=max_hulls,
        preprocess_mode="auto",
    )
    hull_files = []
    for i, (verts, faces) in enumerate(parts):
        name = f"collision_{i:02d}.obj"
        trimesh.Trimesh(verts, faces).export(out / name)
        hull_files.append(name)

    meta = {
        "id": obj_id,
        "cad_file": cfg["cad"],
        "cad_to_object_offset_m": offset.tolist(),
        "extents_m": mesh.extents.tolist(),
        "watertight": bool(mesh.is_watertight),
        "collision_parts": hull_files,
        "coacd_threshold": threshold,
    }
    (out / "object.json").write_text(json.dumps(meta, indent=2))
    print(f"{obj_id}: {len(hull_files)} convex parts in {time.time() - t0:.1f}s, extents {np.round(mesh.extents, 4)} m")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("objects", nargs="*", default=list(OBJECTS))
    ap.add_argument("--threshold", type=float, default=0.04, help="CoACD concavity threshold (lower = more parts)")
    ap.add_argument("--max-hulls", type=int, default=32)
    args = ap.parse_args()
    for obj_id in args.objects:
        prepare(obj_id, args.threshold, args.max_hulls)


if __name__ == "__main__":
    main()
