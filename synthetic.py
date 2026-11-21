"""synthetic.py — синтетические головы (демо/обучение до разметки реальных STL) и демо-сканы.

Каноническая система синтетики: x — вправо пациента, y — вперёд, z — вверх. Все размеры в мм.
"""
from pathlib import Path

import numpy as np
import trimesh
from scipy.spatial import ConvexHull
from scipy.spatial.transform import Rotation

SE_DIR = np.array([0.0, 1.0, 0.0])
NOSE_DIR = np.array([0.0, 1.0, -0.38])
TR_DIR = {"TrL": np.array([-1.0, -0.12, -0.02]), "TrR": np.array([1.0, -0.12, -0.02])}


def fib_sphere(n):
    i = np.arange(n) + 0.5
    phi, th = np.arccos(1 - 2 * i / n), np.pi * (1 + 5 ** 0.5) * i
    return np.c_[np.cos(th) * np.sin(phi), np.sin(th) * np.sin(phi), np.cos(phi)]


def _sphere_faces(u):
    f = ConvexHull(u).simplices.copy()
    a, b, c = u[f[:, 0]], u[f[:, 1]], u[f[:, 2]]
    flip = np.einsum("ij,ij->i", np.cross(b - a, c - a), a + b + c) < 0
    f[flip] = f[flip][:, [0, 2, 1]]
    return f


def sample_params(rng):
    ay = rng.uniform(68, 88)
    return dict(ay=ay, ax=ay * rng.uniform(0.76, 1.02), az=ay * rng.uniform(0.80, 0.95),
                k=0.0 if rng.random() < 0.15 else float(rng.uniform(0.01, 0.16)), side=int(rng.choice([-1, 1])),
                nose=rng.uniform(0.06, 0.12), dent=rng.uniform(0.02, 0.05), ear=rng.uniform(0.04, 0.09))


def _surface(u, p):
    s, k = p["side"], p["k"]

    def g(c, sig):
        c = np.asarray(c, float)
        return np.exp(-(1 - u @ (c / np.linalg.norm(c))) / sig ** 2)

    sc = np.ones(len(u))
    sc -= k * g([s * 0.65, -0.75, 0.25], 0.35)            # уплощение затылочно-боковой области
    sc += 0.55 * k * g([-s * 0.65, -0.75, 0.25], 0.35)    # компенсаторный выступ
    sc += 0.35 * k * g([-s * 0.55, 0.8, 0.2], 0.40)       # лобный выступ с противоположной стороны
    sc += p["nose"] * g(NOSE_DIR, 0.12) - p["dent"] * g(SE_DIR, 0.08)
    sc += p["ear"] * (g([1, -0.1, -0.25], 0.15) + g([-1, -0.1, -0.25], 0.15))
    return u * np.array([p["ax"], p["ay"], p["az"]]) * sc[:, None]


def make_head(p, n_pts=3000, cut=-0.5):
    """Открытая снизу сетка головы. Возвращает V, F, индексы [Se, TrL, TrR]."""
    u = fib_sphere(int(n_pts / 0.75))
    f = _sphere_faces(u)
    P = _surface(u, p)
    keep = u[:, 2] > cut
    remap = -np.ones(len(u), int)
    remap[keep] = np.arange(keep.sum())
    F = remap[f[keep[f].all(1)]]
    V = P[keep]
    idx = []
    for d in (SE_DIR, TR_DIR["TrL"], TR_DIR["TrR"]):
        t = _surface((d / np.linalg.norm(d))[None], p)[0]
        idx.append(int(np.argmin(np.linalg.norm(V - t, axis=1))))
    return V, F, np.array(idx)


def random_pose(V, rng):
    R = Rotation.random(random_state=int(rng.integers(1 << 31))).as_matrix()
    return V @ R.T + rng.uniform(-80, 80, 3), R


def make_demo_scans(out="demo_scans", seed=7):
    rng = np.random.default_rng(seed)
    out = Path(out)
    out.mkdir(exist_ok=True)
    base = dict(ax=62.0, ay=82.0, az=68.0, nose=0.09, dent=0.035, ear=0.06, side=1)
    for name, k in (("demo_good", 0.02), ("demo_deformity", 0.15)):
        V, F, _ = make_head({**base, "k": k}, 9000)
        V, _ = random_pose(V, rng)
        trimesh.Trimesh(V, F, process=False).export(out / f"{name}.stl")
    # дефектный скан: вырезано отверстие в затылочно-боковой области, пересекающее Level 3
    V, F, _ = make_head({**base, "k": 0.05}, 9000)
    cen = V[F].mean(1)
    cen = (cen - cen.mean(0)) / np.linalg.norm(cen - cen.mean(0), axis=1, keepdims=True)
    c = np.array([0.55, -0.8, 0.1]) / np.linalg.norm([0.55, -0.8, 0.1])
    F = F[(cen @ c) < 0.93]
    V, _ = random_pose(V, rng)
    m = trimesh.Trimesh(V, F, process=False)
    m.remove_unreferenced_vertices()
    m.export(out / "demo_defective.stl")
    return sorted(p.name for p in out.glob("*.stl"))


if __name__ == "__main__":
    print(make_demo_scans())
