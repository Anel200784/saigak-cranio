"""i18n.py — перевод сообщений сервера и PDF (kk / ru / en). Исходные сообщения хранятся по-русски,
перевод — одноразовая подстановка фрагментов (числа остаются нетронутыми)."""
import copy
import re

LANGS = ("kk", "ru", "en")
E = [  # (ru, kk, en)
 ("Чтение файла", "Файлды оқу", "File reading"),
 ("файл не удалось прочитать как STL", "файлды STL ретінде оқу мүмкін болмады", "the file could not be read as STL"),
 ("в файле нет треугольной сетки", "файлда үшбұрышты тор жоқ", "the file contains no triangle mesh"),
 ("координаты содержат NaN/Inf", "координаталарда NaN/Inf бар", "coordinates contain NaN/Inf"),
 ("нулевой габарит модели", "модельдің габариті нөлге тең", "the model has zero size"),
 ("Целостность файла", "Файл тұтастығы", "File integrity"),
 (" вершин, ", " төбе, ", " vertices, "),
 (" граней", " жақ", " faces"),
 (" — слишком грубая сетка", " — тор тым дөрекі", " — mesh is too coarse"),
 ("Вырожденные грани", "Азғындалған жақтар", "Degenerate faces"),
 ("Связность сетки", "Тор байланыстылығы", "Mesh connectivity"),
 ("одна связная поверхность", "бір тұтас бет", "a single connected surface"),
 (" компонент; изолированные фрагменты ", " компонент; оқшауланған фрагменттер ", " components; isolated fragments "),
 (" (удалены автоматически)", " (автоматты түрде жойылды)", " (removed automatically)"),
 (" — грубые артефакты", " — өрескел артефактілер", " — gross artifacts"),
 ("Артефакты (выбросы, растянутые грани)", "Артефактілер (шығарындылар, созылған жақтар)", "Artifacts (spikes, stretched faces)"),
 (" % аномально длинных рёбер", " % ауытқыған ұзын қырлар", " % abnormally long edges"),
 ("Неманифольдные рёбра", "Манифольд емес қырлар", "Non-manifold edges"),
 (" рёбер", " қыр", " edges"),
 ("Замкнутость (watertight)", "Тұйықтық (watertight)", "Watertightness"),
 ("сетка замкнута", "тор тұйық", "the mesh is closed"),
 ("открытая сетка, отверстий: ", "ашық тор, тесік саны: ", "open mesh, holes: "),
 (" (открытое основание/шея допустимо)", " (ашық негіз/мойын рұқсат етіледі)", " (an open base/neck is acceptable)"),
 ("Отверстия поверхности", "Беттегі тесіктер", "Surface holes"),
 ("отсутствует часть поверхности (лоб/затылок/бок): ", "беттің бір бөлігі жоқ (маңдай/желке/бүйір): ", "part of the surface is missing (forehead/occiput/side): "),
 (" крупных отверстий, эквивалентный Ø до ", " ірі тесік, баламалы Ø ≤ ", " large holes, equivalent Ø up to "),
 (" ед. модели", " модель бірлігі", " model units"),
 (" малых отверстий вне основания", " шағын тесік (негізден тыс)", " small holes outside the base"),
 ("крупных отверстий вне основания нет", "негізден тыс ірі тесіктер жоқ", "no large holes outside the base"),
 ("Подтверждённый масштаб", "Расталған масштаб", "Confirmed scale"),
 ("наибольший габарит ", "ең үлкен габарит ", "largest dimension "),
 (" — вне 90–400 мм, проверьте единицы измерения", " — 90–400 мм аралығынан тыс, өлшем бірліктерін тексеріңіз", " — outside 90–400 mm, check the units"),
 ("Размеры сечения", "Қима өлшемдері", "Section dimensions"),
 (" — вне физиологичного диапазона 0–18 мес", " — 0–18 ай үшін физиологиялық диапазоннан тыс", " — outside the physiological range for 0–18 months"),
 ("Согласованность ориентиров", "Бағдар нүктелерінің үйлесімділігі", "Landmark consistency"),
 ("Se→середина TrL–TrR", "Se→TrL–TrR ортасы", "Se→midpoint of TrL–TrR"),
 ("Отверстие и контур Level 3", "Тесік және Level 3 контуры", "Hole and Level 3 contour"),
 ("отверстие пересекает измерительный контур", "тесік өлшеу контурын қиып өтеді", "a hole crosses the measurement contour"),
 ("контур замкнут, отверстий в зоне Level 3 нет", "контур тұйық, Level 3 аймағында тесік жоқ", "the contour is closed, no holes in the Level 3 zone"),
 ("Метки лево/право", "Сол/оң белгілері", "Left/right labels"),
 ("возможна перестановка TrL/TrR (зеркальная модель); индексы не меняются", "TrL/TrR орындары ауысқан болуы мүмкін (айналы модель); индекстер өзгермейді", "TrL/TrR may be swapped (mirrored model); indices are unaffected"),
 ("Измерительный контур Level 3 не замкнут: разрыв или отверстие на поверхности", "Level 3 өлшеу контуры тұйық емес: беттегі үзіліс немесе тесік", "The Level 3 measurement contour is not closed: a gap or hole in the surface"),
 ("Измерительный контур Level 3", "Level 3 өлшеу контуры", "Level 3 measurement contour"),
 ("Ориентиры Se, TrL, TrR совпадают или лежат на одной прямой", "Se, TrL, TrR нүктелері сәйкес келеді немесе бір түзуде жатыр", "Landmarks Se, TrL, TrR coincide or are collinear"),
 ("Высота H от Level 0 до свода равна нулю", "Level 0-ден төбеге дейінгі H биіктігі нөлге тең", "Height H from Level 0 to the vault is zero"),
 ("В плоскости Level 3 несколько крупных контуров (артефакты, посторонние объекты)", "Level 3 жазықтығында бірнеше ірі контур бар (артефактілер, бөгде нысандар)", "Several large contours in the Level 3 plane (artifacts, foreign objects)"),
 ("Точка O лежит вне контура Level 3 — проверьте ориентиры", "O нүктесі Level 3 контурынан тыс жатыр — бағдар нүктелерін тексеріңіз", "Point O lies outside the Level 3 contour — check the landmarks"),
 ("Хорда D1/D2 не пересекает контур Level 3", "D1/D2 хордасы Level 3 контурын қимайды", "Chord D1/D2 does not intersect the Level 3 contour"),
 ("очень тяжёлая", "өте ауыр", "very severe"), ("тяжёлая", "ауыр", "severe"), ("умеренная", "орташа", "moderate"), ("лёгкая", "жеңіл", "mild"),
 ("ниже порога шкалы", "шкала шегінен төмен", "below the scale threshold"),
 ("диагонали равны", "диагональдар тең", "the diagonals are equal"),
 ("короче D2 (передне-правая — задне-левая)", "D2 қысқа (алдыңғы-оң — артқы-сол)", "D2 is shorter (anterior-right — posterior-left)"),
 ("короче D1 (передне-левая — задне-правая)", "D1 қысқа (алдыңғы-сол — артқы-оң)", "D1 is shorter (anterior-left — posterior-right)"),
 ("ручная коррекция врача (привязка к ближайшей вершине)", "дәрігердің қолмен түзетуі (ең жақын төбеге байланған)", "manual correction by the physician (snapped to the nearest vertex)"),
 (" — ML-модель не обучена: выполните python train.py --demo", " — ML-модель оқытылмаған: python train.py --demo орындаңыз", " — ML model is not trained: run python train.py --demo"),
 ("), уверенность ориентации ", "), бағдарлау сенімділігі ", "), orientation confidence "),
 ("ML-модель (", "ML-модель (", "ML model ("),
 ("Baseline (эвристика)", "Baseline (эвристика)", "Baseline (heuristic)"),
 ("Расчёт не выполнялся", "Есептеу орындалған жоқ", "The calculation was not performed"),
 ("Сессия не найдена — загрузите STL заново", "Сессия табылмады — STL-ді қайта жүктеңіз", "Session not found — upload the STL again"),
 ("Сначала подтвердите масштаб (мм / см / м)", "Алдымен масштабты растаңыз (мм / см / м)", "Confirm the scale first (mm / cm / m)"),
 ("Ориентиры не заданы", "Бағдар нүктелері берілмеген", "Landmarks are not set"),
 ("Неверная единица или нет сетки", "Өлшем бірлігі қате немесе тор жоқ", "Invalid unit or no mesh"),
 ("Сетки нет", "Тор жоқ", "No mesh"), ("Нет ориентиров", "Бағдар нүктелері жоқ", "No landmarks"),
 ("Нужны координаты ", "Координаталар қажет: ", "Coordinates required: "),
 ("(число без степени тяжести: пороги не универсальны)", "(ауырлық дәрежесіз сан: шектер әмбебап емес)", "(a plain number without severity grade: thresholds are not universal)"),
 ("Level 3: плоскость ∥ Level 0 на высоте 0.3 · H, H = расстояние от Level 0 до верхней точки свода V", "Level 3: Level 0-ге параллель жазықтық, биіктігі 0.3 · H, H = Level 0-ден қаңқа төбесіндегі V нүктесіне дейінгі қашықтық", "Level 3: plane ∥ Level 0 at height 0.3 · H, H = distance from Level 0 to the top vault point V"),
 ("D1, D2: хорды сечения через O под ±30° к переднезадней оси (O — проекция середины TrL–TrR)", "D1, D2: O арқылы алдыңғы-артқы өске ±30° бұрышпен өтетін қима хордалары (O — TrL–TrR ортасының проекциясы)", "D1, D2: section chords through O at ±30° to the anteroposterior axis (O — projection of the TrL–TrR midpoint)"),
 # PDF
 ("Пациент", "Пациент", "Patient"),
 ("Пациент (код / имя)", "Пациент (коды / аты-жөні)", "Patient (code / name)"),
 ("Дата рождения", "Туған күні", "Date of birth"),
 ("Пол", "Жынысы", "Sex"),
 ("мужской", "ер", "male"), ("женский", "әйел", "female"),
 ("Срок гестации, нед", "Гестация мерзімі, апта", "Gestational age, weeks"),
 ("Врач", "Дәрігер", "Physician"),
 ("Примечание", "Ескертпе", "Notes"),
 ("Возраст, мес", "Жасы, ай", "Age, months"),
 ("Отчёт краниометрии головы", "Бас краниометриясының есебі", "Head craniometry report"),
 ("Анонимный код скана:", "Сканның анонимді коды:", "Anonymous scan code:"),
 ("сформирован", "жасалды", "generated"), ("(локально)", "(жергілікті)", "(locally)"),
 ("Скан пригоден, расчёт выполнен", "Скан жарамды, есептеу орындалды", "Scan is suitable, calculation done"),
 ("Расчёт выполнен с предупреждениями", "Есептеу ескертулермен орындалды", "Calculation done with warnings"),
 ("ОТКАЗ ОТ РАСЧЁТА — скан непригоден", "ЕСЕПТЕУДЕН БАС ТАРТУ — скан жарамсыз", "CALCULATION REFUSED — scan is unsuitable"),
 ("Оценка качества входных данных", "Кіріс деректер сапасын бағалау", "Input data quality assessment"),
 ("Основания для отказа", "Бас тарту негіздері", "Grounds for refusal"),
 ("Индексы не рассчитаны. Выполните повторное сканирование или скорректируйте ориентиры/масштаб и повторите расчёт.", "Индекстер есептелмеді. Қайта сканерлеңіз немесе бағдар нүктелерін/масштабты түзетіп, есептеуді қайталаңыз.", "Indices were not calculated. Rescan, or correct the landmarks/scale and repeat the calculation."),
 ("Разметка (3D) и измерительное сечение Level 3 (2D)", "Белгілеу (3D) және Level 3 өлшеу қимасы (2D)", "Landmarks (3D) and Level 3 measurement section (2D)"),
 ("Показатель", "Көрсеткіш", "Parameter"), ("Значение", "Мәні", "Value"),
 ("L — переднезадний размер", "L — алдыңғы-артқы өлшем", "L — anteroposterior dimension"),
 ("W — поперечная ширина", "W — көлденең ені", "W — transverse width"),
 ("D1 (±30°, передне-левая — задне-правая)", "D1 (±30°, алдыңғы-сол — артқы-оң)", "D1 (±30°, anterior-left — posterior-right)"),
 ("D2 (±30°, передне-правая — задне-левая)", "D2 (±30°, алдыңғы-оң — артқы-сол)", "D2 (±30°, anterior-right — posterior-left)"),
 ("Периметр контура Level 3", "Level 3 контурының периметрі", "Level 3 contour perimeter"),
 ("H (Level 0 → вершина свода V)", "H (Level 0 → төбе нүктесі V)", "H (Level 0 → vault apex V)"),
 ("; Level 3 на ", "; Level 3 биіктігі ", "; Level 3 at "),
 ("  (степень тяжести не присваивается)", "  (ауырлық дәрежесі берілмейді)", "  (no severity grade is assigned)"),
 ("Степень асимметрии (по неокруглённому CVAI)", "Асимметрия дәрежесі (дөңгелектелмеген CVAI бойынша)", "Asymmetry grade (by unrounded CVAI)"),
 ("Размеры и индексы", "Өлшемдер мен индекстер", "Dimensions and indices"),
 ("Шкала по CVAI:", "CVAI шкаласы:", "CVAI scale:"), ("Диагонали: ", "Диагональдар: ", "Diagonals: "),
 ("Ориентиры (мм, система скана): ", "Бағдар нүктелері (мм, скан жүйесі): ", "Landmarks (mm, scan coordinates): "),
 ("Источник: ", "Көзі: ", "Source: "),
 ("Методика, версии и проверка врачом", "Әдістеме, нұсқалар және дәрігер тексеруі", "Method, versions and physician review"),
 ("Методика: ", "Әдістеме: ", "Method: "), (". ML-модель ориентиров: ", ". Бағдар нүктелерінің ML-моделі: ", ". ML landmark model: "),
 ("Воспроизводимость (повторный расчёт): ", "Қайталанғыштық (қайта есептеу): ", "Reproducibility (repeat calculation): "),
 ("Формулы: ", "Формулалар: ", "Formulas: "),
 ("Возраст пациента: ", "Пациент жасы: ", "Patient age: "),
 (" (программа не определяет возраст по форме головы).", " (бағдарлама жасты бас пішінінен анықтамайды).", " (the program does not infer age from head shape)."),
 (" мес (введён врачом вручную)", " ай (дәрігер қолмен енгізген)", " months (entered manually by the physician)"),
 ("не указан", "көрсетілмеген", "not specified"),
 ("Результат проверен врачом", "Нәтижені дәрігер тексерді", "Result reviewed by a physician"),
 ("ФИО / подпись:", "Аты-жөні / қолы:", "Name / signature:"),
 ("Отчёт — вспомогательный измерительный документ. Он не является диагнозом и не назначает шлемотерапию; решение принимает врач.", "Есеп — қосалқы өлшеу құжаты. Ол диагноз емес және дулыға терапиясын тағайындамайды; шешімді дәрігер қабылдайды.", "This report is a supporting measurement document. It is not a diagnosis and does not prescribe helmet therapy; the decision rests with the physician."),
 ("вперёд", "алға", "anterior"), ("вправо", "оңға", "right"),
 (" п.п.", " п.т.", " pp"), (", мм", ", мм", ", mm"), (" мм", " мм", " mm"),
]
_cache = {}


def _rx(lang):
    if lang not in _cache:
        i = 1 if lang == "kk" else 2
        d = {e[0]: e[i] for e in E}
        keys = sorted(d, key=len, reverse=True)
        _cache[lang] = (re.compile("|".join(map(re.escape, keys))), d)
    return _cache[lang]


def tr(text, lang):
    if lang == "ru" or not isinstance(text, str):
        return text
    rx, d = _rx(lang)
    return rx.sub(lambda m: d[m.group(0)], text)


def tr_report(rep, lang):
    r = copy.deepcopy(rep)
    r["reasons"] = [tr(x, lang) for x in r["reasons"]]
    for c in r["checks"]:
        c["name"], c["detail"] = tr(c["name"], lang), tr(c["detail"], lang)
    return r


def tr_result(res, lang):
    if res is None:
        return None
    r = copy.copy(res)
    r["reasons"] = [tr(x, lang) for x in res["reasons"]]
    r["checks"] = [{**c, "name": tr(c["name"], lang), "detail": tr(c["detail"], lang)} for c in res["checks"]]
    r["landmark_source"] = tr(res["landmark_source"], lang)
    if res["metrics"]:
        r["metrics"] = {**res["metrics"], "severity": tr(res["metrics"]["severity"], lang), "shorter_diagonal": tr(res["metrics"]["shorter_diagonal"], lang)}
    return r
