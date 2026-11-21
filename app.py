"""app.py — локальный FastAPI-сервер краниометрии. Слушает только 127.0.0.1, ничего не отправляет наружу.

Запуск: python app.py  →  http://127.0.0.1:8000
"""
import base64
import csv
import hashlib
import io
import json
import urllib.request
import uuid
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from scipy.spatial import cKDTree

import geometry
import i18n
import model as mdl
import report_pdf
import validator

ROOT = Path(__file__).parent
app = FastAPI(title="Saigak-Cranio (local)")
SESSIONS: Dict[str, dict] = {}
UNITS = {"mm": 1.0, "cm": 10.0, "m": 1000.0}
VENDOR = {"three.min.js": "https://cdn.jsdelivr.net/npm/three@0.128.0/build/three.min.js",
          "OrbitControls.js": "https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"}


def ensure_vendor():
    """Только библиотеки интерфейса (один раз, если файлов нет). Данные пациентов никогда не покидают машину."""
    d = ROOT / "static" / "vendor"
    d.mkdir(parents=True, exist_ok=True)
    for name, url in VENDOR.items():
        if not (d / name).exists():
            urllib.request.urlretrieve(url, d / name)


ensure_vendor()
(ROOT / "demo_scans").mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
app.mount("/demo", StaticFiles(directory=ROOT / "demo_scans"), name="demo")


class ScaleBody(BaseModel):
    scan_id: str
    unit: str


class AnalyzeBody(BaseModel):
    scan_id: str
    method: str = "ml"
    landmarks: Optional[Dict[str, List[float]]] = None


class MetaBody(BaseModel):
    scan_id: str
    age_months: Optional[float] = None
    doctor_checked: bool = False
    patient: str = ""
    birth_date: str = ""
    sex: str = ""
    gest_weeks: Optional[float] = None
    doctor: str = ""
    notes: str = ""


class ShotBody(BaseModel):
    scan_id: str
    data_url: str


def sess(sid):
    if sid not in SESSIONS:
        raise HTTPException(404, "Сессия не найдена — загрузите STL заново")
    return SESSIONS[sid]


def LG(request):
    l = request.query_params.get("lang") or request.headers.get("x-lang") or "kk"
    return l if l in i18n.LANGS else "kk"


@app.exception_handler(HTTPException)
async def _http_err(request: Request, exc: HTTPException):
    return JSONResponse({"detail": i18n.tr(str(exc.detail), LG(request))}, status_code=exc.status_code)


def b64(a):
    return base64.b64encode(np.ascontiguousarray(a).tobytes()).decode()


@app.get("/", response_class=HTMLResponse)
def index():
    return (ROOT / "templates" / "index.html").read_text(encoding="utf-8")


@app.get("/api/config")
def config(request: Request):
    lg = LG(request)
    return {"method": geometry.METHOD_VERSION, "model": mdl.MODEL_VERSION, "model_ready": mdl.get_model() is not None,
            "formulas": [i18n.tr(f, lg) for f in geometry.FORMULAS],
            "scale": [{"label": i18n.tr(l, lg), "range": r} for _, l, r in geometry.SEVERITY_SCALE]}


@app.post("/api/upload")
async def upload(request: Request, file: UploadFile = File(...)):
    raw = await file.read()
    sid = uuid.uuid4().hex[:12]
    S = dict(id=sid, code="SCAN-" + hashlib.sha256(raw).hexdigest()[:8].upper(), filename=file.filename, mesh=None, holes=[], unit=None,
             V=None, F=None, tree=None, normals=None, lm_idx=None, lm_src="", result=None, shot=None, meta={"age_months": None, "doctor_checked": False})
    try:
        mesh = validator.load_stl(raw)
        S["mesh"], S["report"], S["holes"] = validator.validate_mesh(mesh)
    except ValueError as e:
        S["report"] = validator.fail_report(str(e))
    SESSIONS[sid] = S
    ext = S["report"]["stats"].get("extent_raw")
    return {"scan_id": sid, "code": S["code"], "filename": file.filename, "validation": i18n.tr_report(S["report"], LG(request)),
            "suggested_unit": validator.suggest_unit(max(ext)) if ext else None, "extent_raw": ext, "has_mesh": S["mesh"] is not None}


@app.post("/api/scale")
def set_scale(b: ScaleBody):
    S = sess(b.scan_id)
    if b.unit not in UNITS or S["mesh"] is None:
        raise HTTPException(400, "Неверная единица или нет сетки")
    S["unit"] = b.unit
    S["V"] = np.asarray(S["mesh"].vertices, float) * UNITS[b.unit]
    S["F"] = np.asarray(S["mesh"].faces)
    S["tree"] = cKDTree(S["V"])
    S["normals"] = geometry.outward_normals(S["mesh"].vertex_normals, S["V"])
    S["lm_idx"], S["result"] = None, None
    return {"ok": True, "unit": b.unit}


@app.get("/api/mesh/{sid}")
def get_mesh(sid: str):
    S = sess(sid)
    if S["mesh"] is None:
        raise HTTPException(404, "Сетки нет")
    V = S["V"] if S["V"] is not None else np.asarray(S["mesh"].vertices, float)
    return {"v": b64(V.astype(np.float32)), "f": b64(np.asarray(S["mesh"].faces, np.uint32)), "n_v": len(V), "n_f": len(S["mesh"].faces), "mm": S["V"] is not None}


def _result(S, status, reasons, checks, metrics=None, geom=None, repro=None):
    lm = None
    if S["lm_idx"] is not None:
        P = S["V"][S["lm_idx"]]
        lm = {n: np.round(P[i], 3).tolist() for i, n in enumerate(mdl.LM_NAMES)}
    return {"scan_code": S["code"], "filename": S["filename"], "status": status, "reasons": reasons, "checks": checks, "unit": S["unit"],
            "landmarks": lm, "landmark_source": S["lm_src"], "metrics": metrics, "geometry": geom,
            "repro": repro or {"max_diff_mm": 0.0, "max_diff_pp": 0.0}, "versions": {"method": geometry.METHOD_VERSION, "model": mdl.MODEL_VERSION},
            "meta": S["meta"]}


def measure(S):
    pre = S["report"]
    if pre["status"] == "reject":
        return _result(S, "reject", pre["reasons"], pre["checks"])
    V, F = S["V"], S["F"]
    i = S["lm_idx"]
    pts = [V[i[0]], V[i[1]], V[i[2]]]
    try:
        m, fr = geometry.compute_metrics(V, F, *pts)
        m2, _ = geometry.compute_metrics(V, F, *pts)               # повторный независимый расчёт — контроль воспроизводимости
    except geometry.GeometryError as e:
        chk = validator.chk("Измерительный контур Level 3", "fail", e.msg)
        checks = pre["checks"] + [chk]
        return _result(S, "reject", validator.finalize(checks)[1], checks)
    mm_keys = ("L", "W", "D1", "D2", "perimeter", "CVA", "H", "h3")
    repro = {"max_diff_mm": float(max(abs(m[k] - m2[k]) for k in mm_keys)), "max_diff_pp": float(max(abs(m["CI"] - m2["CI"]), abs(m["CVAI"] - m2["CVAI"])))}
    checks = pre["checks"] + validator.validate_measurement(V, m, S["holes"], fr, *pts)
    status, reasons = validator.finalize(checks)
    if status == "reject":
        return _result(S, status, reasons, checks)
    geom = m.pop("geometry")
    return _result(S, status, reasons, checks, m, geom, repro)


@app.post("/api/analyze")
def analyze(b: AnalyzeBody, request: Request):
    S = sess(b.scan_id)
    if S["V"] is None:
        raise HTTPException(409, "Сначала подтвердите масштаб (мм / см / м)")
    if b.landmarks:
        idx = []
        for n in mdl.LM_NAMES:
            if n not in b.landmarks or len(b.landmarks[n]) != 3:
                raise HTTPException(400, f"Нужны координаты {n}")
            idx.append(int(S["tree"].query(np.array(b.landmarks[n], float))[1]))     # привязка к ближайшей вершине
        S["lm_idx"], S["lm_src"] = np.array(idx), "ручная коррекция врача (привязка к ближайшей вершине)"
    elif S["report"]["status"] != "reject":
        m = mdl.get_model() if b.method == "ml" else None
        if m is not None:
            S["lm_idx"], conf = m.predict(S["V"])
            S["lm_src"] = f"ML-модель ({mdl.MODEL_VERSION}), уверенность ориентации {conf:.2f}"
        else:
            S["lm_idx"], _ = mdl.baseline_predict(S["V"])
            S["lm_src"] = "Baseline (эвристика)" + ("" if b.method != "ml" else " — ML-модель не обучена: выполните python train.py --demo")
    S["result"] = measure(S) if (S["lm_idx"] is not None or S["report"]["status"] == "reject") else None
    if S["result"] is None:
        raise HTTPException(400, "Ориентиры не заданы")
    return i18n.tr_result(S["result"], LG(request))


@app.get("/api/asymmetry/{sid}")
def asymmetry(sid: str):
    S = sess(sid)
    if S["lm_idx"] is None or S["V"] is None:
        raise HTTPException(409, "Нет ориентиров")
    P = S["V"][S["lm_idx"]]
    try:
        dev = geometry.asymmetry_map(S["V"], S["normals"], *P)
    except geometry.GeometryError as e:
        raise HTTPException(422, e.msg)
    return {"values": b64(dev), "p95": float(np.percentile(np.abs(dev), 95)), "max": float(np.abs(dev).max())}


@app.post("/api/meta")
def set_meta(b: MetaBody):
    S = sess(b.scan_id)
    S["meta"] = b.dict(exclude={"scan_id"})
    return {"ok": True}


@app.get("/api/state/{sid}")
def state(sid: str, request: Request):
    S = sess(sid)
    lg = LG(request)
    return {"validation": i18n.tr_report(S["report"], lg), "result": i18n.tr_result(S["result"], lg)}


@app.post("/api/screenshot")
def set_shot(b: ShotBody):
    S = sess(b.scan_id)
    S["shot"] = base64.b64decode(b.data_url.split(",", 1)[1])
    return {"ok": True}


def current(S):
    r = S["result"]
    if r is None:
        r = _result(S, "reject", S["report"]["reasons"] or ["Расчёт не выполнялся"], S["report"]["checks"])
    r["meta"] = S["meta"]
    return r


@app.get("/api/report/{sid}.pdf")
def report(sid: str, request: Request):
    S = sess(sid)
    lg = LG(request)
    r = i18n.tr_result(current(S), lg)
    return Response(report_pdf.build_pdf(r, S["shot"] if r["status"] != "reject" else None, lg), media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{S["code"]}_report.pdf"'})


@app.get("/api/export/{sid}.json")
def export_json(sid: str, request: Request):
    r = i18n.tr_result(current(sess(sid)), LG(request))
    r = {**r, "geometry": None}
    return Response(json.dumps(r, ensure_ascii=False, indent=2), media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="{r["scan_code"]}.json"'})


@app.get("/api/export/{sid}.csv")
def export_csv(sid: str, request: Request):
    r = i18n.tr_result(current(sess(sid)), LG(request))
    rows = [("scan_code", r["scan_code"], ""), ("status", r["status"], ""), ("unit_confirmed", r["unit"] or "", "")]
    for k, u in (("L", "mm"), ("W", "mm"), ("D1", "mm"), ("D2", "mm"), ("perimeter", "mm"), ("H", "mm"), ("CI", ""), ("CVA", "mm"), ("CVAI", "%"), ("severity", "")):
        if r["metrics"]:
            v = r["metrics"][k]
            rows.append((k, f"{v:.2f}" if isinstance(v, float) else v, u))
    for n, p in (r["landmarks"] or {}).items():
        rows.append((n, " ".join(f"{c:.3f}" for c in p), "mm"))
    rows += [("method_version", r["versions"]["method"], ""), ("model_version", r["versions"]["model"], ""), ("landmark_source", r["landmark_source"], ""),
             ("age_months_manual", r["meta"]["age_months"] if r["meta"].get("age_months") is not None else "", "mo"),
             *[(k, r["meta"].get(k, ""), "") for k in ("patient", "birth_date", "sex", "gest_weeks", "doctor", "notes")],
             ("doctor_checked", r["meta"].get("doctor_checked", False), ""), ("rejection_reasons", " | ".join(r["reasons"]), "")]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(("parameter", "value", "unit"))
    w.writerows(rows)
    return Response("\ufeff" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{r["scan_code"]}.csv"'})


if __name__ == "__main__":
    import uvicorn
    print("→ http://127.0.0.1:8000   (всё работает локально)")
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")
