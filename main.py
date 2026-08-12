import os
import math
import time
import threading
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import telebot
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image as RLImage
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

# ============================================================
# SERVIDOR HTTP (PARA RENDER / KEEP-ALIVE)
# ============================================================
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        pass


def run_health_check_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    server.serve_forever()


threading.Thread(target=run_health_check_server, daemon=True).start()

# ============================================================
# CONFIGURACION DEL BOT
# ============================================================
TOKEN = os.environ.get("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError(
        "Falta la variable de entorno BOT_TOKEN. Configúrala antes de ejecutar el bot."
    )
bot = telebot.TeleBot(TOKEN, parse_mode=None)

ENGINEER_NAME = os.environ.get("ENGINEER_NAME", "")
ENGINEER_CIP = os.environ.get("ENGINEER_CIP", "")

# ============================================================
# DATOS DE REFERENCIA
# ============================================================
EJEMPLOS_MORALES = {
    "viga-simple":    {"b": 25, "h": 50, "fc": 210, "fy": 4200, "Mu": 12, "Vu": 8},
    "viga-doble":     {"b": 30, "h": 60, "fc": 210, "fy": 4200, "Mu": 35, "Vu": 15},
    "viga-confinada": {"b": 30, "h": 70, "fc": 280, "fy": 4200, "Mu": 25, "Vu": 25},
}

DIAMETROS = {'3/8': 0.95, '1/2': 1.27, '5/8': 1.59, '3/4': 1.91, '1': 2.54}
AREAS = {'3/8': 0.71, '1/2': 1.29, '5/8': 1.99, '3/4': 2.85, '1': 5.10}

REC = 4.0             # recubrimiento libre asumido (cm)
DB_ESTRIBO = '3/8'     # diametro de estribo asumido
DB_LONG_MIN = '5/8'    # diametro longitudinal asumido, para chequeo de zona confinada
D_PRIMA = 5.0          # recubrimiento a centroide del acero en compresion asumido (cm)

DOSIFICACIONES = {
    '140': {'cemento': 7.01, 'arena': 0.51, 'piedra': 0.64, 'agua': 0.184},
    '175': {'cemento': 8.43, 'arena': 0.54, 'piedra': 0.55, 'agua': 0.185},
    '210': {'cemento': 9.73, 'arena': 0.52, 'piedra': 0.53, 'agua': 0.186},
    '280': {'cemento': 13.34, 'arena': 0.45, 'piedra': 0.51, 'agua': 0.189},
    '350': {'cemento': 15.80, 'arena': 0.43, 'piedra': 0.50, 'agua': 0.190},
    '450': {'cemento': 18.50, 'arena': 0.40, 'piedra': 0.48, 'agua': 0.195},
}

# ============================================================
# CALCULOS ESTRUCTURALES (E.060)
# ============================================================
def peralte_efectivo(h):
    return h - REC - DIAMETROS[DB_ESTRIBO] - DIAMETROS[DB_LONG_MIN] / 2.0


def beta1(fc):
    if fc <= 280:
        return 0.85
    b1 = 0.85 - 0.05 * ((fc - 280) / 70.0)
    return max(b1, 0.65)


def cuantia_balanceada(fc, fy):
    b1 = beta1(fc)
    return 0.85 * b1 * (fc / fy) * (6000.0 / (6000.0 + fy))


def seleccionar_acero(As_cm2, min_barras=2, max_barras=6):
    """Elige diametro x cantidad de barras que cubra As con menor exceso."""
    opciones = []
    for diam, area in AREAS.items():
        for n in range(min_barras, max_barras + 1):
            area_provista = n * area
            if area_provista >= As_cm2:
                opciones.append((area_provista - As_cm2, n, diam, area_provista))
                break
    if not opciones:
        diam = '1'
        n = max(math.ceil(As_cm2 / AREAS[diam]), min_barras)
        opciones.append((n * AREAS[diam] - As_cm2, n, diam, n * AREAS[diam]))
    opciones.sort(key=lambda x: x[0])
    _, n, diam, area_provista = opciones[0]
    return {"cantidad": n, "diametro": diam, "area_provista": area_provista}


def diseno_flexion(Mu_tm, b, d, fc, fy):
    """Mu en ton-m. Verifica si la viga es simple o doblemente reforzada
    y devuelve el detalle paso a paso del calculo (formulas con numeros)."""
    Mu_kgcm = Mu_tm * 100000.0
    phi = 0.9
    pasos = []

    a = d / 5.0
    As = 0.0
    for _ in range(30):
        As_nuevo = Mu_kgcm / (phi * fy * (d - a / 2.0))
        a_nuevo = As_nuevo * fy / (0.85 * fc * b)
        if abs(a_nuevo - a) < 1e-4 and abs(As_nuevo - As) < 1e-4:
            As, a = As_nuevo, a_nuevo
            break
        As, a = As_nuevo, a_nuevo

    As_min = max((0.7 * math.sqrt(fc) / fy) * b * d, (14.0 / fy) * b * d)
    rho_b = cuantia_balanceada(fc, fy)
    As_max = 0.75 * rho_b * b * d

    pasos.append("Se asume viga simplemente reforzada y se itera con brazo de palanca real:")
    pasos.append(f"a = As·fy/(0.85·f'c·b) ; As = Mu/(φ·fy·(d−a/2)) ; φ = 0.90")
    pasos.append(f"Convergencia: a = {a:.2f} cm  →  As = {As:.2f} cm2")
    pasos.append(
        f"As mín = máx(0.7√f'c/fy·b·d ; 14/fy·b·d) = "
        f"máx({(0.7 * math.sqrt(fc) / fy) * b * d:.2f} ; {(14.0 / fy) * b * d:.2f}) = {As_min:.2f} cm2"
    )
    pasos.append(
        f"ρ balanceada = 0.85·β1·(f'c/fy)·(6000/(6000+fy)) = {rho_b:.4f}  "
        f"→  As máx = 0.75·ρb·b·d = {As_max:.2f} cm2"
    )

    if As <= As_max:
        As_final = max(As, As_min)
        barras = seleccionar_acero(As_final)
        pasos.append("As ≤ As máx  →  VIGA SIMPLEMENTE REFORZADA (no necesita acero en compresión).")
        pasos.append(
            f"Acero en tracción seleccionado: {barras['cantidad']}Ø{barras['diametro']}\" "
            f"(As provisto = {barras['area_provista']:.2f} cm2)"
        )
        return {
            "tipo": "Simplemente reforzada",
            "As": As_final, "As_prima": 0.0,
            "As_min": As_min, "As_max": As_max,
            "barras": barras, "barras_prima": None,
            "pasos": pasos,
        }

    # --- Diseño doblemente reforzado ---
    pasos.append("As > As máx  →  VIGA DOBLEMENTE REFORZADA (requiere acero en compresión As').")
    As1 = As_max
    a1 = As1 * fy / (0.85 * fc * b)
    M1 = phi * As1 * fy * (d - a1 / 2.0)
    M2 = Mu_kgcm - M1
    b1v = beta1(fc)
    c1 = a1 / b1v
    fs_prima = 6000.0 * (c1 - D_PRIMA) / c1
    fluye = fs_prima >= fy
    fs_prima = min(fs_prima, fy)
    As2 = M2 / (phi * fy * (d - D_PRIMA))
    As_prima = M2 / (phi * fs_prima * (d - D_PRIMA))
    As_final = As1 + As2

    pasos.append(f"As1 = As máx = {As1:.2f} cm2  →  a1 = As1·fy/(0.85·f'c·b) = {a1:.2f} cm")
    pasos.append(f"M1 = φ·As1·fy·(d−a1/2) = {M1 / 100000:.2f} ton·m")
    pasos.append(f"M2 = Mu − M1 = {Mu_kgcm / 100000:.2f} − {M1 / 100000:.2f} = {M2 / 100000:.2f} ton·m")
    pasos.append(f"c1 = a1/β1 = {c1:.2f} cm  ;  fs' = 6000·(c1−d')/c1 = {fs_prima:.0f} kg/cm2"
                 f" ({'fluye' if fluye else 'no fluye, se usa fs<fy'}, d'={D_PRIMA:.0f}cm)")
    pasos.append(f"As2 = M2/(φ·fy·(d−d')) = {As2:.2f} cm2")
    pasos.append(f"As' = M2/(φ·fs'·(d−d')) = {As_prima:.2f} cm2")
    pasos.append(f"As total = As1 + As2 = {As_final:.2f} cm2")

    barras = seleccionar_acero(As_final)
    barras_prima = seleccionar_acero(As_prima) if As_prima > 0.1 else None
    pasos.append(
        f"Acero en tracción: {barras['cantidad']}Ø{barras['diametro']}\" "
        f"(As provisto = {barras['area_provista']:.2f} cm2)"
    )
    if barras_prima:
        pasos.append(
            f"Acero en compresión: {barras_prima['cantidad']}Ø{barras_prima['diametro']}\" "
            f"(As' provisto = {barras_prima['area_provista']:.2f} cm2)"
        )

    return {
        "tipo": "Doblemente reforzada",
        "As": As_final, "As_prima": As_prima,
        "As_min": As_min, "As_max": As_max,
        "barras": barras, "barras_prima": barras_prima,
        "pasos": pasos,
    }


def diseno_corte(Vu_ton, b, h, d, fc, fy_estribo):
    """Vu en toneladas. Devuelve espaciamientos y el detalle paso a paso
    de como se obtuvieron (incluye que limite gobierna en cada zona)."""
    Vu_kg = Vu_ton * 1000.0
    phi = 0.85
    Vc = 0.53 * math.sqrt(fc) * b * d
    phiVc = phi * Vc
    pasos = []
    pasos.append(f"Vc = 0.53·√f'c·b·d = {Vc / 1000:.2f} ton  ;  φVc = 0.85·Vc = {phiVc / 1000:.2f} ton")
    pasos.append(f"Vu = {Vu_ton:.2f} ton")

    if Vu_kg <= phiVc:
        Vs_req = 0.0
        pasos.append("Vu ≤ φVc  →  no se requiere Vs por cálculo; se usa espaciamiento mínimo constructivo.")
    else:
        Vs_req = Vu_kg / phi - Vc
        pasos.append(f"Vu > φVc  →  Vs = Vu/φ − Vc = {Vs_req / 1000:.2f} ton")
        Vs_max = 2.1 * math.sqrt(fc) * b * d
        pasos.append(f"Vs máx = 2.1·√f'c·b·d = {Vs_max / 1000:.2f} ton")
        if Vs_req > Vs_max:
            pasos.append("⚠ Vs requerido > Vs máx: sección insuficiente por cortante.")
            return {"error": True, "phiVc": phiVc, "Vu_kg": Vu_kg, "pasos": pasos}

    Av = AREAS[DB_ESTRIBO] * 2
    if Vs_req > 0:
        s_por_corte = Av * fy_estribo * d / Vs_req
        pasos.append(f"s (por corte) = Av·fy·d/Vs = {Av:.2f}·{fy_estribo:.0f}·{d:.1f}/{Vs_req:.0f} = {s_por_corte:.1f} cm")
    else:
        s_por_corte = d / 2.0
        pasos.append(f"s (constructivo) = d/2 = {s_por_corte:.1f} cm")

    db_estribo_cm = DIAMETROS[DB_ESTRIBO]
    db_long_cm = DIAMETROS[DB_LONG_MIN]

    limites_confinado = {
        "d/4": d / 4.0,
        "8·db long": 8 * db_long_cm,
        "24·db estribo": 24 * db_estribo_cm,
        "30 cm": 30.0,
        "por corte": s_por_corte,
    }
    s_confinado = min(limites_confinado.values())
    gobierna_confinado = min(limites_confinado, key=limites_confinado.get)
    pasos.append("Zona confinada (2h desde la cara del apoyo), límites: " +
                 ", ".join(f"{k}={v:.1f}cm" for k, v in limites_confinado.items()))
    pasos.append(f"→ gobierna \"{gobierna_confinado}\": s confinado = {s_confinado:.1f} cm")

    limites_central = {"d/2": d / 2.0, "30 cm": 30.0, "por corte": s_por_corte}
    s_central = min(limites_central.values())
    gobierna_central = min(limites_central, key=limites_central.get)
    pasos.append("Zona central, límites: " + ", ".join(f"{k}={v:.1f}cm" for k, v in limites_central.items()))
    pasos.append(f"→ gobierna \"{gobierna_central}\": s central = {s_central:.1f} cm")

    aviso_espaciamiento_minimo = s_confinado < 5.0
    s_confinado = max(s_confinado, 5.0)
    s_central = max(s_central, 5.0)

    return {
        "error": False,
        "phiVc": phiVc, "Vu_kg": Vu_kg, "Vs_req": Vs_req,
        "s_confinado": s_confinado, "s_central": s_central,
        "longitud_confinamiento": 2 * h,
        "aviso_espaciamiento_minimo": aviso_espaciamiento_minimo,
        "pasos": pasos,
    }


# ============================================================
# GRAFICO
# ============================================================
def generar_grafico_viga(b, h, flex, corte, chat_id):
    barras = flex['barras']
    barras_prima = flex['barras_prima']
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5.5))

    # --- Seccion transversal con acero real ---
    ax1.set_title(f"Sección {b:.0f}×{h:.0f} cm — {flex['tipo']}", fontsize=10, fontweight='bold')
    ax1.add_patch(patches.Rectangle((0, 0), b, h, edgecolor='black', facecolor='#eeeeee', linewidth=2))
    rec = REC
    ax1.add_patch(patches.Rectangle((rec, rec), b - 2 * rec, h - 2 * rec, edgecolor='#333333', fill=False, linewidth=1.5))

    diam_bot = DIAMETROS[barras['diametro']]
    margen_bot = rec + DIAMETROS[DB_ESTRIBO] + diam_bot / 2
    n_bot = barras['cantidad']
    xs_bot = [b / 2] if n_bot == 1 else [margen_bot + i * (b - 2 * margen_bot) / (n_bot - 1) for i in range(n_bot)]
    for x in xs_bot:
        ax1.add_patch(patches.Circle((x, margen_bot), diam_bot / 2, color='#c0392b', zorder=5))
    ax1.text(b / 2, margen_bot - 4.5, f"{n_bot}Ø{barras['diametro']}\" (As={barras['area_provista']:.2f}cm2)",
              ha='center', fontsize=7.5, color='#c0392b')

    if barras_prima:
        diam_top = DIAMETROS[barras_prima['diametro']]
        margen_top = rec + DIAMETROS[DB_ESTRIBO] + diam_top / 2
        n_top = barras_prima['cantidad']
        xs_top = [b / 2] if n_top == 1 else [margen_top + i * (b - 2 * margen_top) / (n_top - 1) for i in range(n_top)]
        for x in xs_top:
            ax1.add_patch(patches.Circle((x, h - margen_top), diam_top / 2, color='#2e7d32', zorder=5))
        ax1.text(b / 2, h - margen_top + 4.5, f"{n_top}Ø{barras_prima['diametro']}\" (As'={barras_prima['area_provista']:.2f}cm2)",
                  ha='center', fontsize=7.5, color='#2e7d32')

    ax1.annotate('', xy=(0, -4), xytext=(b, -4), arrowprops=dict(arrowstyle='<->'))
    ax1.text(b / 2, -7.5, f"{b:.0f} cm", ha='center', fontsize=8)
    ax1.annotate('', xy=(-4, 0), xytext=(-4, h), arrowprops=dict(arrowstyle='<->'))
    ax1.text(-9, h / 2, f"{h:.0f} cm", va='center', fontsize=8, rotation=90)

    ax1.set_xlim(-16, b + 10)
    ax1.set_ylim(-13, h + 12)
    ax1.set_aspect('equal')
    ax1.axis('off')

    # --- Elevacion: distribucion de estribos ---
    Ltotal = max(6 * h, 250)
    Lconf = corte['longitud_confinamiento']
    ax2.set_title("Distribución de estribos (elevación)", fontsize=10, fontweight='bold')
    ax2.plot([0, Ltotal], [0, 0], 'k', linewidth=3)
    ax2.plot([0, Ltotal], [h * 0.3, h * 0.3], 'k', linewidth=3)
    ax2.axvspan(0, Lconf, color='#fff3b0', alpha=0.6)
    ax2.axvspan(Ltotal - Lconf, Ltotal, color='#fff3b0', alpha=0.6)
    ax2.text(Lconf / 2, h * 0.15, f"Confinado\n@{corte['s_confinado']:.0f}cm", ha='center', fontsize=8, fontweight='bold')
    ax2.text(Ltotal / 2, h * 0.15, f"Central\n@{corte['s_central']:.0f}cm", ha='center', fontsize=8, fontweight='bold')
    ax2.text(Ltotal - Lconf / 2, h * 0.15, f"Confinado\n@{corte['s_confinado']:.0f}cm", ha='center', fontsize=8, fontweight='bold')
    ax2.annotate('', xy=(0, -h * 0.15), xytext=(Lconf, -h * 0.15), arrowprops=dict(arrowstyle='<->'))
    ax2.text(Lconf / 2, -h * 0.28, f"2h = {Lconf:.0f}cm", ha='center', fontsize=7.5)
    ax2.set_xlim(-10, Ltotal + 10)
    ax2.set_ylim(-h * 0.5, h * 0.6)
    ax2.axis('off')

    plt.tight_layout()
    ruta = f"viga_{chat_id}_{int(time.time() * 1000)}.png"
    plt.savefig(ruta, dpi=110)
    plt.close(fig)
    return ruta


# ============================================================
# MEMORIA DE CALCULO EN PDF
# ============================================================
def generar_pdf_memoria(b, h, d, fc, fy, Mu, Vu, flex, corte, ruta_imagen, chat_id):
    ruta_pdf = f"memoria_{chat_id}_{int(time.time() * 1000)}.pdf"
    doc = SimpleDocTemplate(
        ruta_pdf, pagesize=A4,
        topMargin=1.5 * cm, bottomMargin=1.5 * cm, leftMargin=1.8 * cm, rightMargin=1.8 * cm,
    )
    styles = getSampleStyleSheet()
    titulo = ParagraphStyle('titulo', parent=styles['Heading1'], fontSize=15, spaceAfter=2)
    subtitulo = ParagraphStyle('subtitulo', parent=styles['Heading2'], fontSize=11,
                                textColor=colors.HexColor('#1a4d8f'), spaceBefore=12, spaceAfter=4)
    normal = styles['Normal']
    paso = ParagraphStyle('paso', parent=normal, fontSize=8.5, leftIndent=8, spaceAfter=3, leading=11)
    nota = ParagraphStyle('nota', parent=styles['Normal'], fontSize=8, textColor=colors.grey, spaceBefore=10)
    aviso = ParagraphStyle('aviso', parent=normal, textColor=colors.red, spaceBefore=4)

    def tabla_resultados(filas, col1=8 * cm, col2=7 * cm):
        t = Table(filas, colWidths=[col1, col2])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a4d8f')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f2f2f2')]),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        return t

    elementos = []
    elementos.append(Paragraph("MEMORIA DE CÁLCULO ESTRUCTURAL", titulo))
    elementos.append(Paragraph("Diseño de viga de concreto armado — Método de resistencia (RNE E.060)", normal))
    if ENGINEER_NAME:
        firma = ENGINEER_NAME + (f" — CIP {ENGINEER_CIP}" if ENGINEER_CIP else "")
        elementos.append(Paragraph(firma, normal))
    elementos.append(Paragraph(datetime.now().strftime("Fecha: %d/%m/%Y %H:%M"), nota))
    elementos.append(Spacer(1, 8))

    elementos.append(Paragraph("1. Datos de entrada", subtitulo))
    elementos.append(tabla_resultados([
        ["Parámetro", "Valor"],
        ["Base (b)", f"{b:.0f} cm"],
        ["Peralte (h)", f"{h:.0f} cm"],
        ["Peralte efectivo (d)", f"{d:.1f} cm"],
        ["f'c", f"{fc:.0f} kg/cm2"],
        ["fy", f"{fy:.0f} kg/cm2"],
        ["Momento último (Mu)", f"{Mu:.2f} ton·m"],
        ["Cortante último (Vu)", f"{Vu:.2f} ton"],
    ]))

    elementos.append(Paragraph(f"2. Diseño por flexión — {flex['tipo']}", subtitulo))
    for p in flex['pasos']:
        elementos.append(Paragraph("• " + p, paso))
    filas_flex = [
        ["Resultado", "Valor"],
        ["As requerido (tracción)", f"{flex['As']:.2f} cm2"],
        ["Acero seleccionado (tracción)", f"{flex['barras']['cantidad']}Ø{flex['barras']['diametro']}\" = {flex['barras']['area_provista']:.2f} cm2"],
    ]
    if flex['barras_prima']:
        filas_flex.append(["As' requerido (compresión)", f"{flex['As_prima']:.2f} cm2"])
        filas_flex.append(["Acero seleccionado (compresión)",
                            f"{flex['barras_prima']['cantidad']}Ø{flex['barras_prima']['diametro']}\" = {flex['barras_prima']['area_provista']:.2f} cm2"])
    filas_flex.append(["As mínimo", f"{flex['As_min']:.2f} cm2"])
    filas_flex.append(["As máximo (0.75·ρb)", f"{flex['As_max']:.2f} cm2"])
    elementos.append(tabla_resultados(filas_flex))

    elementos.append(Paragraph("3. Diseño por cortante", subtitulo))
    for p in corte['pasos']:
        elementos.append(Paragraph("• " + p, paso))
    if not corte.get("error"):
        elementos.append(tabla_resultados([
            ["Resultado", "Valor"],
            ["φVc", f"{corte['phiVc'] / 1000:.2f} ton"],
            ["Vu", f"{corte['Vu_kg'] / 1000:.2f} ton"],
            ["Vs requerido", f"{corte['Vs_req'] / 1000:.2f} ton"],
            [f"Zona confinada (2h = {corte['longitud_confinamiento']:.0f} cm)", f"@ {corte['s_confinado']:.0f} cm"],
            ["Zona central", f"@ {corte['s_central']:.0f} cm"],
        ]))
    else:
        elementos.append(Paragraph(
            "⚠ La sección es insuficiente por cortante. Se recomienda aumentar b o h.", aviso
        ))

    elementos.append(Paragraph("4. Esquema de la sección y armado", subtitulo))
    elementos.append(RLImage(ruta_imagen, width=17 * cm, height=17 * cm * 5.5 / 12))

    elementos.append(Paragraph(
        "Nota: memoria generada automáticamente como estimación preliminar según RNE E.060. "
        "No reemplaza la revisión y firma de un ingeniero civil colegiado responsable del proyecto.",
        nota
    ))

    doc.build(elementos)
    return ruta_pdf


# ============================================================
# MANEJADORES DE TELEGRAM
# ============================================================
@bot.message_handler(commands=['start', 'menu'])
def enviar_bienvenida(message):
    bot.reply_to(
        message,
        "¡Hola! Sistema de diseño de vigas activo.\n\n"
        "Envía los datos así:\n"
        "b h f'c fy Mu Vu\n\n"
        "Unidades: b y h en cm, f'c y fy en kg/cm2, Mu en ton-m, Vu en ton.\n\n"
        "Ejemplo: 25 50 210 4200 12 8\n\n"
        "El bot detecta si la viga necesita ser doblemente reforzada, selecciona el acero "
        "y te manda una memoria de cálculo en PDF con las fórmulas y sustituciones.\n\n"
        "O escribe /morales para ver ejemplos del libro de Morales."
    )


@bot.message_handler(commands=['morales'])
def comando_morales(message):
    bot.reply_to(
        message,
        "Ejemplos del libro de Morales:\n"
        "/test_viga_simple\n/test_viga_doble\n/test_viga_confinada"
    )


@bot.message_handler(commands=['test_viga_simple', 'test_viga_doble', 'test_viga_confinada'])
def test_ejemplo(message):
    nombre = message.text.replace("/", "").replace("test_", "").replace("_", "-")
    datos = EJEMPLOS_MORALES.get(nombre)
    if not datos:
        bot.reply_to(message, "Ejemplo no encontrado.")
        return
    valores = [datos["b"], datos["h"], datos["fc"], datos["fy"], datos["Mu"], datos["Vu"]]
    message.text = " ".join(map(str, valores))
    procesar_mensajes(message)


@bot.message_handler(func=lambda message: True)
def procesar_mensajes(message):
    try:
        texto = message.text.strip().replace(',', '.')
        valores = [float(x) for x in texto.split()]

        if len(valores) != 6:
            bot.reply_to(
                message,
                "Formato incorrecto. Envíalo así:\n"
                "b h f'c fy Mu Vu\n"
                "(cm, cm, kg/cm2, kg/cm2, ton-m, ton)"
            )
            return

        b, h, fc, fy, Mu, Vu = valores
        d = peralte_efectivo(h)
        if d <= 5:
            bot.reply_to(message, "El peralte h es muy pequeño para el recubrimiento asumido (4cm + estribo 3/8 + long 5/8).")
            return

        flex = diseno_flexion(Mu, b, d, fc, fy)
        corte = diseno_corte(Vu, b, h, d, fc, fy)

        lineas = [
            "📐 DISEÑO DE VIGA",
            f"b={b:.0f}cm  h={h:.0f}cm  d={d:.1f}cm",
            f"f'c={fc:.0f}  fy={fy:.0f} kg/cm2",
            "",
            f"— FLEXIÓN ({flex['tipo']}) —",
            f"As: {flex['As']:.2f} cm2  →  {flex['barras']['cantidad']}Ø{flex['barras']['diametro']}\"",
        ]
        if flex['barras_prima']:
            lineas.append(f"As': {flex['As_prima']:.2f} cm2  →  {flex['barras_prima']['cantidad']}Ø{flex['barras_prima']['diametro']}\"")

        if corte.get("error"):
            lineas += [
                "",
                "— CORTANTE —",
                f"φVc: {corte['phiVc'] / 1000:.2f} ton   Vu: {corte['Vu_kg'] / 1000:.2f} ton",
                "⚠️ Sección insuficiente por cortante. Aumenta b o h.",
            ]
            bot.reply_to(message, "\n".join(lineas))
            return

        lineas += [
            "",
            "— CORTANTE —",
            f"Estribos {DB_ESTRIBO}\" (2 ramas):",
            f"  Confinado (2h={corte['longitud_confinamiento']:.0f}cm): @{corte['s_confinado']:.0f}cm",
            f"  Central: @{corte['s_central']:.0f}cm",
            "",
            "📄 Memoria de cálculo detallada en el PDF adjunto.",
        ]
        if corte["aviso_espaciamiento_minimo"]:
            lineas.append("⚠️ Espaciamiento calculado <5cm; revisar diámetro de estribo o sección.")

        bot.reply_to(message, "\n".join(lineas))

        ruta_img = generar_grafico_viga(b, h, flex, corte, message.chat.id)
        ruta_pdf = None
        try:
            ruta_pdf = generar_pdf_memoria(b, h, d, fc, fy, Mu, Vu, flex, corte, ruta_img, message.chat.id)
            with open(ruta_pdf, 'rb') as f:
                bot.send_document(
                    message.chat.id, f,
                    visible_file_name="memoria_calculo_viga.pdf",
                    caption="📄 Memoria de cálculo lista"
                )
        finally:
            for ruta in (ruta_img, ruta_pdf):
                if ruta and os.path.exists(ruta):
                    os.remove(ruta)

    except ValueError:
        bot.reply_to(message, "No pude leer los números. Usa punto o coma decimal, separados por espacios.")
    except Exception as e:
        bot.reply_to(message, f"Error en el cálculo: {e}")


if __name__ == '__main__':
    bot.polling(none_stop=True)
