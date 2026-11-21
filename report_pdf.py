"""report_pdf.py — клинический PDF-отчёт (в т.ч. отказ при непригодном скане). Полностью локально, ReportLab."""
import io
from datetime import datetime
from pathlib import Path

from reportlab.graphics.shapes import Circle, Drawing, Line, Polygon, Rect, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

import geometry
from i18n import tr

TEAL, BLUE, INK = colors.HexColor("#0e9aa7"), colors.HexColor("#1d6fb8"), colors.HexColor("#12303b")
FONTS = [(Path(__file__).parent / "fonts" / "DejaVuSans.ttf", Path(__file__).parent / "fonts" / "DejaVuSans-Bold.ttf"),
         (Path("C:/Windows/Fonts/arial.ttf"), Path("C:/Windows/Fonts/arialbd.ttf")),
         (Path("/Library/Fonts/Arial.ttf"), Path("/Library/Fonts/Arial Bold.ttf")),
         (Path("/System/Library/Fonts/Supplemental/Arial.ttf"), Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf")),
         (Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"), Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"))]


def _register():
    if "UI" in pdfmetrics.getRegisteredFontNames():
        return
    for reg, bold in FONTS:
        if reg.exists():
            pdfmetrics.registerFont(TTFont("UI", str(reg)))
            pdfmetrics.registerFont(TTFont("UI-B", str(bold if bold.exists() else reg)))
            return
    raise RuntimeError("Не найден шрифт с кириллицей. Положите DejaVuSans.ttf и DejaVuSans-Bold.ttf в папку fonts/.")


def _section_drawing(g, size=230, T=lambda s: s):
    pts = g["contour2d"]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    ext = max(max(xs) - min(xs), max(ys) - min(ys)) * 1.15
    k = size / ext
    cx, cy = size / 2, size / 2
    Pt = lambda p: (cx + p[0] * k, cy + p[1] * k)
    d = Drawing(size, size)
    d.add(Rect(0, 0, size, size, fillColor=colors.HexColor("#f6fbfc"), strokeColor=colors.HexColor("#dbe8ed")))
    d.add(Line(cx, 6, cx, size - 6, strokeColor=colors.HexColor("#b8ccd3"), strokeDashArray=[3, 3]))
    d.add(Line(6, cy, size - 6, cy, strokeColor=colors.HexColor("#b8ccd3"), strokeDashArray=[3, 3]))
    flat = [c for p in pts for c in Pt(p)]
    d.add(Polygon(flat, fillColor=colors.Color(0.05, 0.6, 0.65, alpha=0.14), strokeColor=TEAL, strokeWidth=1.6))
    for key, col, name in (("chord1_2d", colors.HexColor("#e07b1f"), "D1"), ("chord2_2d", colors.HexColor("#7a4fd0"), "D2")):
        (x1, y1), (x2, y2) = Pt(g[key][0]), Pt(g[key][1])
        d.add(Line(x1, y1, x2, y2, strokeColor=col, strokeWidth=1.6))
        d.add(String(x1 + 3, y1 + 3, name, fontName="UI-B", fontSize=8, fillColor=col))
    d.add(Circle(cx, cy, 2.6, fillColor=INK, strokeColor=INK))
    d.add(String(cx + 5, cy - 10, "O", fontName="UI-B", fontSize=8, fillColor=INK))
    d.add(String(cx + 4, size - 12, T("вперёд"), fontName="UI", fontSize=7, fillColor=INK))
    d.add(String(size - 34, cy + 4, T("вправо"), fontName="UI", fontSize=7, fillColor=INK))
    return d


def _scale_drawing(cvai, w=470, h=34):
    d = Drawing(w, h)
    cols = ["#9fd8c8", "#f3dc8a", "#f0b565", "#e98466", "#c8454a"]
    edges = [0, 3.5, 6.25, 8.75, 11.0, 14.0]
    for i in range(5):
        x0, x1 = edges[i] / 14 * w, edges[i + 1] / 14 * w
        d.add(Rect(x0, 12, x1 - x0, 14, fillColor=colors.HexColor(cols[i]), strokeColor=colors.white))
        d.add(String(x0, 2, f"{edges[i]:g}", fontName="UI", fontSize=7, fillColor=INK))
    d.add(String(w - 12, 2, "14+", fontName="UI", fontSize=7, fillColor=INK))
    x = min(cvai, 14.0) / 14 * w
    d.add(Polygon([x - 5, 33, x + 5, 33, x, 24], fillColor=INK, strokeColor=INK))
    return d


def build_pdf(res, screenshot=None, lang="ru"):
    _register()
    T = lambda s: tr(s, lang)
    P = lambda text, style: Paragraph(T(text), style)
    st = lambda n, **k: ParagraphStyle(n, **{"fontName": "UI", "textColor": INK, **k})
    H1, H2 = st("h1", fontName="UI-B", fontSize=17, leading=21), st("h2", fontName="UI-B", fontSize=11.5, leading=15, spaceBefore=8, spaceAfter=3)
    B, S = st("b", fontSize=9, leading=12.5), st("s", fontSize=7.8, leading=10.5, textColor=colors.HexColor("#5d7983"))
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=14 * mm, bottomMargin=14 * mm,
                            title=f"Краниометрия {res['scan_code']}")
    status = res["status"]
    sc = {"ok": ("#1a9d6b", "Скан пригоден, расчёт выполнен"), "warn": ("#d9922b", "Расчёт выполнен с предупреждениями"),
          "reject": ("#d64545", "ОТКАЗ ОТ РАСЧЁТА — скан непригоден")}[status]
    story = [P("Отчёт краниометрии головы · Saigak-Orto", H1),
             P(f"Анонимный код скана: <b>{res['scan_code']}</b> &nbsp;·&nbsp; сформирован {datetime.now():%d.%m.%Y %H:%M} (локально)", B), Spacer(1, 5)]
    banner = Table([[P(f"<font color='white'><b>{sc[1]}</b></font>", st("bn", fontName="UI-B", fontSize=11, leading=14))]], colWidths=[178 * mm])
    banner.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(sc[0])), ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    story += [banner, Spacer(1, 4)]
    mt0 = res.get("meta", {})
    sexv = {"m": "мужской", "f": "женский"}.get(mt0.get("sex"), "")
    prow = [(k, v) for k, v in (("Пациент (код / имя)", mt0.get("patient")), ("Дата рождения", mt0.get("birth_date")), ("Пол", sexv),
            ("Срок гестации, нед", mt0.get("gest_weeks")), ("Врач", mt0.get("doctor")), ("Примечание", mt0.get("notes"))) if v not in (None, "")]
    if prow:
        story.append(P("Пациент", H2))
        pt = Table([[P(f"<b>{k}</b>", B), P(str(v), B)] for k, v in prow], colWidths=[58 * mm, 120 * mm])
        pt.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#dbe8ed")), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        story.append(pt)
    story.append(P("Оценка качества входных данных", H2))
    icon = {"ok": "✓", "warn": "!", "fail": "✕"}
    rows = [[icon[c["status"]], P(f"<b>{c['name']}</b>", B), P(c["detail"], B)] for c in res["checks"]]
    t = Table(rows, colWidths=[8 * mm, 52 * mm, 118 * mm])
    ts = [("FONT", (0, 0), (0, -1), "UI-B", 10), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#dbe8ed")),
          ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]
    for i, c in enumerate(res["checks"]):
        ts.append(("TEXTCOLOR", (0, i), (0, i), colors.HexColor({"ok": "#1a9d6b", "warn": "#d9922b", "fail": "#d64545"}[c["status"]])))
    t.setStyle(TableStyle(ts))
    story.append(t)
    m, g = res.get("metrics"), res.get("geometry")
    if status == "reject" or not m:
        story += [P("Основания для отказа", H2)] + [P(f"• {r}", B) for r in res["reasons"]]
        story.append(P("Индексы не рассчитаны. Выполните повторное сканирование или скорректируйте ориентиры/масштаб и повторите расчёт.", B))
    else:
        imgs = []
        if screenshot:
            ir = ImageReader(io.BytesIO(screenshot))
            w0, h0 = ir.getSize()
            imgs.append(Image(io.BytesIO(screenshot), width=86 * mm, height=86 * mm * h0 / w0))
        imgs.append(_section_drawing(g, 230, T))
        story += [P("Разметка (3D) и измерительное сечение Level 3 (2D)", H2), Table([imgs], colWidths=[90 * mm, 88 * mm] if len(imgs) == 2 else [178 * mm])]
        L = res["landmarks"]
        mt = [["Показатель", "Значение"],
              ["L — переднезадний размер", f"{m['L']:.2f} мм"], ["W — поперечная ширина", f"{m['W']:.2f} мм"],
              ["D1 (±30°, передне-левая — задне-правая)", f"{m['D1']:.2f} мм"], ["D2 (±30°, передне-правая — задне-левая)", f"{m['D2']:.2f} мм"],
              ["Периметр контура Level 3", f"{m['perimeter']:.2f} мм"], ["H (Level 0 → вершина свода V)", f"{m['H']:.2f} мм; Level 3 на {m['h3']:.2f} мм"],
              ["CI = 100·W/L", f"{m['CI']:.2f}  (степень тяжести не присваивается)"], ["CVA = |D1 − D2|", f"{m['CVA']:.2f} мм"],
              ["CVAI = 100·|D1 − D2| / max(D1, D2)", f"{m['CVAI']:.2f} %"], ["Степень асимметрии (по неокруглённому CVAI)", m["severity"]]]
        mt = [[T(c) for c in r] for r in mt]
        tb = Table(mt, colWidths=[100 * mm, 78 * mm])
        tb.setStyle(TableStyle([("FONT", (0, 0), (-1, -1), "UI", 9), ("FONT", (0, 0), (-1, 0), "UI-B", 9), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e3f3f5")),
                                ("FONT", (0, 9), (-1, 10), "UI-B", 9.5), ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#dbe8ed")),
                                ("TEXTCOLOR", (0, 0), (-1, -1), INK), ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
        story += [P("Размеры и индексы", H2), tb, Spacer(1, 5), _scale_drawing(m["CVAI"]),
                  P("Шкала по CVAI: &lt; 3.5 % — ниже порога шкалы; 3.5–&lt;6.25 % — лёгкая; 6.25–&lt;8.75 % — умеренная; 8.75–&lt;11 % — тяжёлая; ≥ 11 % — очень тяжёлая. "
                            f"Диагонали: {m['shorter_diagonal']}.", S),
                  P(f"Ориентиры (мм, система скана): Se = {L['Se'][0]:.1f}, {L['Se'][1]:.1f}, {L['Se'][2]:.1f}; TrL = {L['TrL'][0]:.1f}, {L['TrL'][1]:.1f}, {L['TrL'][2]:.1f}; "
                            f"TrR = {L['TrR'][0]:.1f}, {L['TrR'][1]:.1f}, {L['TrR'][2]:.1f}. Источник: {res['landmark_source']}.", S)]
    meta = res.get("meta", {})
    age = f"{meta['age_months']:g} мес (введён врачом вручную)" if meta.get("age_months") not in (None, "") else "не указан"
    story += [P("Методика, версии и проверка врачом", H2),
              P(f"Методика: {res['versions']['method']}. ML-модель ориентиров: {res['versions']['model']}. "
                        f"Воспроизводимость (повторный расчёт): Δ ≤ {res['repro']['max_diff_mm']:.4f} мм / {res['repro']['max_diff_pp']:.4f} п.п.", B),
              P("Формулы: " + "; ".join(geometry.FORMULAS[:3]) + ".", S), Spacer(1, 3),
              P(f"Возраст пациента: <b>{age}</b> (программа не определяет возраст по форме головы).", B),
              P(f"{'☑' if meta.get('doctor_checked') else '☐'} Результат проверен врачом &nbsp;&nbsp;&nbsp; ФИО / подпись: ______________________", B), Spacer(1, 4),
              P("Отчёт — вспомогательный измерительный документ. Он не является диагнозом и не назначает шлемотерапию; решение принимает врач.", S)]
    doc.build(story)
    return buf.getvalue()
