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
        pass  # silenciar logs del health check


def run_health_check_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    server.serve_forever()


threading.Thread(target=run_health_check_server, daemon=True).start()

# ============================================================
# CONFIGURACION DEL BOT
# ============================================================
# El token NUNCA debe ir escrito en el código. Configúralo como
# variable de entorno BOT_TOKEN en tu servidor/plataforma (Render, etc).
# Si tu token anterior estuvo escrito en el código en algún momento,
# revócalo en @BotFather y genera uno nuevo antes de usar este bot.
TOKEN = os.environ.get("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError(
        "Falta la variable de entorno BOT_TOKEN. Configúrala antes de ejecutar el bot."
    )
bot = telebot.TeleBot(TOKEN, parse_mode=None)

# Datos opcionales para la firma de la memoria de cálculo (personaliza en Render > Environment)
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

# Diametros comerciales (cm) y sus areas (cm2)
DIAMETROS = {'3/8': 0.95, '1/2': 1.27, '5/8': 1.59, '3/4': 1.91, '1': 2.54}
AREAS = {'3/8': 0.71, '1/2': 1.29, '5/8': 1.99, '3/4': 2.85, '1': 5.10}

REC = 4.0            # recubrimiento libre asumido (cm)
DB_ESTRIBO = '3/8'    # diametro de estribo asumido
DB_LONG_MIN = '5/8'   # diametro longitudinal asumido, solo para chequeo de zona confinada

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


def diseno_flexion(Mu_tm, b, d, fc, fy):
    """Mu en ton-m. Iteracion con brazo de palanca real jd = d - a/2."""
    Mu_kgcm = Mu_tm * 100000.0
    phi = 0.9
    a = d / 5.0  # semilla inicial
    As = 0.0
    for _ in range(30):
        As = Mu_kgcm / (phi * fy * (d - a / 2.0))
        a_nuevo = As * fy / (0.85 * fc * b)
        if abs(a_nuevo - a) < 1e-4:
            a = a_nuevo
            break
        a = a_nuevo

    As_min = max((0.7 * math.sqrt(fc) / fy) * b * d, (14.0 / fy) * b * d)
    As_final = max(As, As_min)

    rho_b = cuantia_balanceada(fc, fy)
    As_max = 0.75 * rho_b * b * d

    return {
        "As": As_final,
        "As_min": As_min,
        "As_max": As_max,
        "excede_cuantia_max": As_final > As_max,
    }


def diseno_corte(Vu_ton, b, h, d, fc, fy_estribo):
    """Vu en toneladas. Diseño por cortante + espaciamiento de estribos
    en zona confinada (2h desde la cara de apoyo) y zona central."""
    Vu_kg = Vu_ton * 1000.0
    phi = 0.85
    Vc = 0.53 * math.sqrt(fc) * b * d
    phiVc = phi * Vc

    if Vu_kg <= phiVc:
        Vs_req = 0.0
    else:
        Vs_req = Vu_kg / phi - Vc
        Vs_max = 2.1 * math.sqrt(fc) * b * d
        if Vs_req > Vs_max:
            return {"error": True, "phiVc": phiVc, "Vu_kg": Vu_kg}

    Av = AREAS[DB_ESTRIBO] * 2  # 2 ramas
    s_por_corte = (Av * fy_estribo * d / Vs_req) if Vs_req > 0 else d / 2.0

    db_estribo_cm = DIAMETROS[DB_ESTRIBO]
    db_long_cm = DIAMETROS[DB_LONG_MIN]

    s_confinado = min(d / 4.0, 8 * db_long_cm, 24 * db_estribo_cm, 30.0, s_por_corte)
    s_central = min(d / 2.0, 30.0, s_por_corte)

    aviso_espaciamiento_minimo = s_confinado < 5.0
    s_confinado = max(s_confinado, 5.0)
    s_central = max(s_central, 5.0)

    return {
        "error": False,
        "phiVc": phiVc,
        "Vu_kg": Vu_kg,
        "Vs_req": Vs_req,
        "s_confinado": s_confinado,
        "s_central": s_central,
        "longitud_confinamiento": 2 * h,
        "aviso_espaciamiento_minimo": aviso_espaciamiento_minimo,
    }


# ============================================================
# GRAFICO
# ============================================================
def generar_grafico_viga(b, h, As, s_confinado, s_central, chat_id):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 5))

    ax1.set_title(f"Sección {b:.0f}x{h:.0f} cm", fontsize=10, fontweight='bold')
    rec = REC
    ax1.add_patch(patches.Rectangle((0, 0), b, h, edgecolor='black', facecolor='#e0e0e0', linewidth=2))
    ax1.add_patch(patches.Rectangle((rec, rec), b - 2 * rec, h - 2 * rec, edgecolor='blue', fill=False, linestyle='--'))
    ax1.scatter([b / 4, b / 2, 3 * b / 4], [rec, rec, rec], color='red', s=60, label=f"As: {As:.2f} cm2")
    ax1.set_xlim(-5, b + 5)
    ax1.set_ylim(-5, h + 5)
    ax1.set_aspect('equal')
    ax1.legend(loc='upper right', fontsize=8)

    ax2.set_title("Distribución de estribos", fontsize=10, fontweight='bold')
    ax2.plot([0, 300], [0, 0], 'k', linewidth=4)
    ax2.plot([0, 300], [h, h], 'k', linewidth=4)
    ax2.axvspan(0, 60, color='yellow', alpha=0.3)
    ax2.axvspan(240, 300, color='yellow', alpha=0.3)
    ax2.text(30, h / 2, f"Confinado\n@{s_confinado:.0f}cm", ha='center', fontsize=8, fontweight='bold')
    ax2.text(150, h / 2, f"Central\n@{s_central:.0f}cm", ha='center', fontsize=8, fontweight='bold')
    ax2.text(270, h / 2, f"Confinado\n@{s_confinado:.0f}cm", ha='center', fontsize=8, fontweight='bold')
    ax2.set_xlim(-5, 305)

    plt.tight_layout()
    ruta = f"viga_{chat_id}_{int(time.time() * 1000)}.png"
    plt.savefig(ruta, dpi=100)
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
        ["f'c", f"{fc:.0f} kg/cm²"],
        ["fy", f"{fy:.0f} kg/cm²"],
        ["Momento último (Mu)", f"{Mu:.2f} ton·m"],
        ["Cortante último (Vu)", f"{Vu:.2f} ton"],
    ]))

    elementos.append(Paragraph("2. Diseño por flexión", subtitulo))
    elementos.append(Paragraph(
        "As = Mu / (φ·fy·(d − a/2)), con a = As·fy/(0.85·f'c·b), resuelto de forma iterativa. φ = 0.90.",
        normal
    ))
    elementos.append(tabla_resultados([
        ["Resultado", "Valor"],
        ["As requerido", f"{flex['As']:.2f} cm²"],
        ["As mínimo", f"{flex['As_min']:.2f} cm²"],
        ["As máximo (0.75·ρb)", f"{flex['As_max']:.2f} cm²"],
    ]))
    if flex["excede_cuantia_max"]:
        elementos.append(Paragraph(
            "⚠ El acero requerido supera la cuantía máxima permitida. Se recomienda acero en "
            "compresión (As') o aumentar la sección.", aviso
        ))

    elementos.append(Paragraph("3. Diseño por cortante", subtitulo))
    if corte.get("error"):
        elementos.append(Paragraph(
            "⚠ La sección es insuficiente por cortante: el Vs requerido excede el máximo permitido "
            "(2.1·√f'c·b·d). Se recomienda aumentar b o h.", aviso
        ))
    else:
        elementos.append(Paragraph(
            "Vc = 0.53·√f'c·b·d ; φ = 0.85. Estribos diseñados con ϕ 3/8\", 2 ramas.", normal
        ))
        elementos.append(tabla_resultados([
            ["Resultado", "Valor"],
            ["φVc", f"{corte['phiVc'] / 1000:.2f} ton"],
            ["Vu", f"{corte['Vu_kg'] / 1000:.2f} ton"],
            ["Vs requerido", f"{corte['Vs_req'] / 1000:.2f} ton"],
            ["Zona confinada (2h = {:.0f} cm)".format(corte['longitud_confinamiento']), f"@ {corte['s_confinado']:.0f} cm"],
            ["Zona central", f"@ {corte['s_central']:.0f} cm"],
        ]))

    elementos.append(Paragraph("4. Esquema de la sección y armado", subtitulo))
    elementos.append(RLImage(ruta_imagen, width=16 * cm, height=16 * cm * 5 / 11))

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
        "Recibirás el resultado y una memoria de cálculo en PDF lista para tu expediente.\n\n"
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
            "— FLEXIÓN —",
            f"As requerido: {flex['As']:.2f} cm2",
            f"As mínimo: {flex['As_min']:.2f} cm2",
        ]
        if flex["excede_cuantia_max"]:
            lineas.append(
                f"⚠️ As supera la cuantía máxima permitida ({flex['As_max']:.2f} cm2). "
                "Se requiere acero en compresión (As') o aumentar la sección."
            )

        if corte.get("error"):
            lineas += [
                "",
                "— CORTANTE —",
                f"φVc: {corte['phiVc'] / 1000:.2f} ton   Vu: {corte['Vu_kg'] / 1000:.2f} ton",
                "⚠️ Sección insuficiente por cortante (Vs requerido excede el máximo permitido). "
                "Aumenta b o h.",
            ]
            bot.reply_to(message, "\n".join(lineas))
            return

        lineas += [
            "",
            "— CORTANTE —",
            f"φVc: {corte['phiVc'] / 1000:.2f} ton   Vu: {corte['Vu_kg'] / 1000:.2f} ton",
            f"Estribos {DB_ESTRIBO}\" (2 ramas):",
            f"  Zona confinada (2h={corte['longitud_confinamiento']:.0f}cm desde apoyo): 1@5cm, resto @{corte['s_confinado']:.0f}cm",
            f"  Zona central: @{corte['s_central']:.0f}cm",
        ]
        if corte["aviso_espaciamiento_minimo"]:
            lineas.append("⚠️ El espaciamiento calculado es menor a 5cm; revisar diámetro de estribo o sección.")

        bot.reply_to(message, "\n".join(lineas))

        ruta_img = generar_grafico_viga(b, h, flex['As'], corte['s_confinado'], corte['s_central'], message.chat.id)
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
