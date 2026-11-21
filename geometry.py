"""geometry.py — строго детерминированный протокол краниометрии.

Level 0 строится через Se, TrL, TrR; H — высота до верхней точки свода; Level 3 — плоскость ∥ Level 0 на 0.3·H.
Никакого случайного компонента: один и тот же вход даёт побитово одинаковый результат.
"""
from collections import defaultdict

import numpy as np
from scipy.spatial import cKDTree

METHOD_VERSION = "Saigak-Cranio protocol v1.0 (Level 3 = 0.3·H)"

# (верхняя граница, название, интервал)
SEVERITY_SCALE = [
    (3.5, "ниже порога шкалы", "< 3.50 %"),
    (6.25, "лёгкая", "3.50 – < 6.25 %"),
    (8.75, "умеренная", "6.25 – < 8.75 %"),
    (11.0, "тяжёлая", "8.75 – < 11.00 %"),
    (float("inf"), "очень тяжёлая", "≥ 11.00 %"),
]
FORMULAS = [
    "CI = 100 · W / L  (число без степени тяжести: пороги не универсальны)",
    "CVA = |D1 − D2|, мм",
    "CVAI = 100 · |D1 − D2| / max(D1, D2), %",
    "Level 3: плоскость ∥ Level 0 на высоте 0.3 · H, H = расстояние от Level 0 до верхней точки свода V",
    "D1, D2: хорды сечения через O под ±30° к переднезадней оси (O — проекция середины TrL–TrR)",
]


class GeometryError(Exception):
    def __init__(self, code, msg):
        super().__init__(msg)
        self.code, self.msg = code, msg


def classify_cvai(c):
    """Степень по НЕокруглённому CVAI."""
    for hi, label, _ in SEVERITY_SCALE:
        if c < hi:
            return label


def _unit(v):
    n = np.linalg.norm(v)
    if not np.isfinite(n) or n < 1e-9:
        raise GeometryError("degenerate", "Ориентиры Se, TrL, TrR совпадают или лежат на одной прямой")
    return v / n


def build_frame(V, se, trl, trr):
    """Анатомическая система: n — вверх (к своду), a — вперёд (к Se), b — вправо пациента (TrL→TrR)."""
    n = _unit(np.cross(trr - trl, se - trl))
    d = (V - trl) @ n
    if d.mean() < 0:                       # свод — там, где основная масса вершин
        n, d = -n, -d
    mid = (trl + trr) / 2.0
    a = se - mid
    a = _unit(a - (a @ n) * n)
    b = trr - trl
    b = b - (b @ n) * n
    b = _unit(b - (b @ a) * a)
    return dict(n=n, a=a, b=b, mid=mid, d=d, H=float(d.max()), vi=int(d.argmax()))


def _cross2(p, q):
    return p[..., 0] * q[..., 1] - p[..., 1] * q[..., 0]


def slice_loops(V, F, origin, n):
    """Сечение сетки плоскостью. Возвращает (список замкнутых контуров Nx3, флаг «есть разрывы/неманифольд»)."""
    d = (V - origin) @ n
    d = np.where(np.abs(d) < 1e-9, 1e-9, d)
    pos = d > 0
    e = np.stack([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]], axis=1)
    cr = pos[e[..., 0]] != pos[e[..., 1]]
    fm = cr.sum(1) == 2
    if not fm.any():
        return [], False
    ee, cm = e[fm], cr[fm]
    idx = np.argsort(~cm, axis=1, kind="stable")[:, :2]
    r = np.arange(len(ee))
    e0, e1 = ee[r, idx[:, 0]], ee[r, idx[:, 1]]
    nv = len(V)

    def key(x):
        return np.minimum(x[:, 0], x[:, 1]).astype(np.int64) * nv + np.maximum(x[:, 0], x[:, 1])

    k0, k1 = key(e0), key(e1)
    uk, inv = np.unique(np.concatenate([k0, k1]), return_inverse=True)
    inv = inv.ravel()
    lo, hi = uk // nv, uk % nv
    t = d[lo] / (d[lo] - d[hi])
    P = V[lo] + t[:, None] * (V[hi] - V[lo])
    adj = defaultdict(list)
    for a, b in zip(inv[:len(k0)].tolist(), inv[len(k0):].tolist()):
        adj[a].append(b)
        adj[b].append(a)
    seen, loops, bad = set(), [], False
    for s in sorted(adj):
        if s in seen:
            continue
        comp, stack = [], [s]
        seen.add(s)
        while stack:
            u = stack.pop()
            comp.append(u)
            for w in adj[u]:
                if w not in seen:
                    seen.add(w)
                    stack.append(w)
        if any(len(adj[u]) != 2 for u in comp):
            bad = True
            continue
        path, prev, cur = [s], -1, s
        while True:
            nb = adj[cur]
            nxt = nb[0] if nb[0] != prev else nb[1]
            if nxt == s or len(path) > len(comp):
                break
            path.append(nxt)
            prev, cur = cur, nxt
        loops.append(P[path])
    return loops, bad


def _area(p):
    x, y = p[:, 0], p[:, 1]
    return 0.5 * float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))


def _inside_origin(p):
    x, y = p[:, 0], p[:, 1]
    x2, y2 = np.roll(x, -1), np.roll(y, -1)
    den = np.where(y2 != y, y2 - y, 1.0)
    c = ((y > 0) != (y2 > 0)) & (0 < (x2 - x) * (0 - y) / den + x)
    return bool(c.sum() % 2)


def _ray(p, d):
    """Расстояние от начала координат до самого дальнего пересечения луча d с замкнутой ломаной p."""
    q = np.roll(p, -1, axis=0)
    e = q - p
    dd = np.broadcast_to(d, e.shape)
    den = _cross2(dd, e)
    ok = np.abs(den) > 1e-12
    den = np.where(ok, den, 1.0)
    t = _cross2(p, e) / den
    u = _cross2(p, dd) / den
    m = ok & (t > 1e-9) & (u >= 0) & (u <= 1)
    if not m.any():
        raise GeometryError("chord", "Хорда D1/D2 не пересекает контур Level 3")
    return float(t[m].max())


def compute_metrics(V, F, se, trl, trr):
    """Полный расчёт. V в мм. Бросает GeometryError, если измерение невозможно."""
    fr = build_frame(V, se, trl, trr)
    n, a, b, mid, H = fr["n"], fr["a"], fr["b"], fr["mid"], fr["H"]
    if H < 1e-6:
        raise GeometryError("no_height", "Высота H от Level 0 до свода равна нулю")
    h3 = 0.3 * H
    O = mid + h3 * n
    loops, bad = slice_loops(V, F, O, n)
    if bad or not loops:
        raise GeometryError("open_contour", "Измерительный контур Level 3 не замкнут: разрыв или отверстие на поверхности")
    P2 = [np.c_[(l - O) @ b, (l - O) @ a] for l in loops]
    areas = [abs(_area(p)) for p in P2]
    order = np.argsort(areas)[::-1]
    if len(order) > 1 and areas[order[1]] > 0.05 * areas[order[0]]:
        raise GeometryError("multi_contour", "В плоскости Level 3 несколько крупных контуров (артефакты, посторонние объекты)")
    k = int(order[0])
    p2, p3 = P2[k], loops[k]
    if _area(p2) < 0:
        p2, p3 = p2[::-1], p3[::-1]
    if not _inside_origin(p2):
        raise GeometryError("origin_outside", "Точка O лежит вне контура Level 3 — проверьте ориентиры")
    L = float(p2[:, 1].max() - p2[:, 1].min())
    W = float(p2[:, 0].max() - p2[:, 0].min())
    per = float(np.linalg.norm(np.roll(p2, -1, 0) - p2, axis=1).sum())
    s30, c30 = np.sin(np.pi / 6), np.cos(np.pi / 6)
    ch = {}
    for name, dv in (("D1", np.array([-s30, c30])), ("D2", np.array([s30, c30]))):
        tp, tn = _ray(p2, dv), _ray(p2, -dv)
        ch[name] = (tp + tn, [dv * tp, -dv * tn])
    D1, D2 = ch["D1"][0], ch["D2"][0]
    cva = abs(D1 - D2)
    cvai = 100.0 * cva / max(D1, D2)
    to3 = lambda q: O + q[0] * b + q[1] * a
    if abs(D1 - D2) < 1e-9:
        shorter = "диагонали равны"
    elif D1 > D2:
        shorter = "короче D2 (передне-правая — задне-левая)"
    else:
        shorter = "короче D1 (передне-левая — задне-правая)"
    r3 = lambda x: np.round(x, 3).tolist()
    return dict(
        H=float(H), h3=float(h3), L=L, W=W, D1=float(D1), D2=float(D2), perimeter=per,
        CI=100.0 * W / L, CVA=float(cva), CVAI=float(cvai), severity=classify_cvai(cvai), shorter_diagonal=shorter,
        lr_consistent=bool(np.dot(np.cross(b, a), n) > 0),
        geometry=dict(
            contour2d=r3(p2), contour3d=r3(p3),
            chord1_2d=r3(np.array(ch["D1"][1])), chord2_2d=r3(np.array(ch["D2"][1])),
            chord1_3d=r3(np.array([to3(q) for q in ch["D1"][1]])), chord2_3d=r3(np.array([to3(q) for q in ch["D2"][1]])),
            O=r3(O), axes=dict(n=r3(n), a=r3(a), b=r3(b)), vertex_V=r3(V[fr["vi"]]),
            level0=dict(origin=r3(mid), normal=r3(n)), level3=dict(origin=r3(O), normal=r3(n)),
        ),
    ), fr


def outward_normals(normals, V):
    nrm = np.asarray(normals, float)
    if np.mean(np.einsum("ij,ij->i", nrm, V - V.mean(0))) < 0:
        nrm = -nrm
    return nrm


def asymmetry_map(V, normals, se, trl, trr):
    """Поверхностное отклонение от зеркальной симметрии (мм): >0 — сторона выступает больше зеркальной."""
    fr = build_frame(V, se, trl, trr)
    b, mid = fr["b"], fr["mid"]
    s = (V - mid) @ b
    pos, neg = np.where(s >= 0)[0], np.where(s < 0)[0]
    dev = np.zeros(len(V))
    for src, dst in ((pos, neg), (neg, pos)):
        if len(src) == 0 or len(dst) == 0:
            continue
        m = V[src] - 2.0 * s[src, None] * b
        _, j = cKDTree(V[dst]).query(m)
        u = dst[j]
        dev[src] = np.einsum("ij,ij->i", m - V[u], normals[u])
    return dev.astype(np.float32)
