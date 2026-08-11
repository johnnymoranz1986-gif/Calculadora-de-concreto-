import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import io
import os
import math
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

TOKEN = "8978402989:AAEcJEXuFFHQImwQVJph58ZmZpMpn7xSfqk"
bot = telebot.TeleBot(TOKEN)

# Servidor HTTP en segundo plano para Render
class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot Estructural Activo en Render")

def run_http_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), SimpleHTTPRequestHandler)
    server.serve_forever()

threading.Thread(target=run_http_server, daemon=True).start()

# Tabla de dosificaciones por m³ (RNE Perú)
DOSIFICACIONES = {
    '140': {'cemento': 7.01, 'arena': 0.51, 'piedra': 0.64, 'agua': 0.184, 'nombre': "140 kg/cm²"},
    '175': {'cemento': 8.43, 'arena': 0.54, 'piedra': 0.55, 'agua': 0.185, 'nombre': "175 kg/cm²"},
    '210': {'cemento': 9.73, 'arena': 0.52, 'piedra': 0.53, 'agua': 0.186, 'nombre': "210 kg/cm²"},
    '280': {'cemento': 13.34, 'arena': 0.45, 'piedra': 0.51, 'agua': 0.189, 'nombre': "280 kg/cm²"},
    '350': {'cemento': 15.80, 'arena': 0.43, 'piedra': 0.50, 'agua': 0.190, 'nombre': "350 kg/cm²"},
    '450': {'cemento': 18.50, 'arena': 0.40, 'piedra': 0.48, 'agua': 0.195, 'nombre': "450 kg/cm²"}
}

user_state = {}

# ---------------------------------------------------------
# GENERACIÓN DE GRÁFICOS (CROQUIS DE SECCIÓN DE VIGA)
# ---------------------------------------------------------
def generar_croquis_viga(b, h, rec, tipo_viga, As_req, As_comp, Vu, s_estribo):
    fig, ax = plt.subplots(figsize=(5, 6))
    
    # Dibujo de la sección de concreto
    rect_viga = patches.Rectangle((0, 0), b, h, linewidth=2, edgecolor='#2D3748', facecolor='#E2E8F0')
    ax.add_patch(rect_viga)

    # Estribo (recubrimiento de 4 cm a eje/borde)
    rec_est = 4.0
    rect_estribo = patches.Rectangle((rec_est, rec_est), b - 2*rec_est, h - 2*rec_est, 
                                     linewidth=1.5, edgecolor='#C53030', facecolor='none', linestyle='--')
    ax.add_patch(rect_estribo)

    # Dibujo de Varillas Longitudinales Tracción (Abajo)
    y_trac = rec
    ax.scatter([rec_est + 2, b/2, b - rec_est - 2], [y_trac, y_trac, y_trac], color='#1A202C', s=120, zorder=5, label='Acero Tracción (As)')

    # Varillas en Compresión (Arriba)
    y_comp = h - rec
    if tipo_viga == "Doblemente Reforzada":
        ax.scatter([rec_est + 2, b - rec_est - 2], [y_comp, y_comp], color='#DD6B20', s=120, zorder=5, label="Acero Compresión (As')")
    else:
        ax.scatter([rec_est + 2, b - rec_est - 2], [y_comp, y_comp], color='#A0AEC0', s=80, zorder=5, label="Montaje (2 ø 3/8\")")

    ax.set_xlim(-10, b + 15)
    ax.set_ylim(-10, h + 15)
    ax.set_aspect('equal')
    ax.axis('off')

    # Cotas y Anotaciones
    plt.title(f"Detalle Estructural de la Viga ({b:.0f}x{h:.0f} cm)\nNorma RNE E.060", fontsize=11, fontweight='bold', pad=10)
    ax.text(b/2, -6, f"b = {b:.0f} cm", ha='center', fontweight='bold', color='#2D3748')
    ax.text(-6, h/2, f"h = {h:.0f} cm", va='center', rotation='vertical', fontweight='bold', color='#2D3748')
    
    # Leyendas
    ax.legend(loc='upper right', bbox_to_anchor=(1.1, -0.02), fontsize=8)

    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)
    plt.close(fig)
    return buf

# ---------------------------------------------------------
# COMANDOS DEL BOT
# ---------------------------------------------------------
@bot.message_handler(commands=['start', 'menu'])
def mostrar_menu(message):
    markup = InlineKeyboardMarkup()
    markup.row_width = 1
    markup.add(
        InlineKeyboardButton("📐 Diseñar Viga por Flexión y Corte (E.060)", callback_data="modo_viga"),
        InlineKeyboardButton("📦 Cubicación / Dosificación de Concreto", callback_data="modo_concreto")
    )
    bot.reply_to(message, "🏗️ **SISTEMA DE INGENIERÍA ESTRUCTURAL (RNE PERÚ)**\n\nSeleccione la herramienta:", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: True)
def callback_listener(call):
    chat_id = call.message.chat.id
    if call.data == "modo_viga":
        user_state[chat_id] = {'modo': 'viga'}
        msg = (
            "📐 **DISEÑO ESTRUCTURAL DE VIGAS (RNE E.060)**\n\n"
            "Envíe los parámetros de diseño separados por espacio en el formato:\n"
            "`[b] [h] [f'c] [fy] [Mu] [Vu]`\n\n"
            "📌 **Donde:**\n"
            "• `b`: Ancho de viga (cm)\n"
            "• `h`: Altural o peralte total (cm)\n"
            "• `f'c`: Resistencia del concreto (kg/cm²)\n"
            "• `fy`: Fluencia del acero (kg/cm²) [Usual: 4200]\n"
            "• `Mu`: Momento flector último (tn·m)\n"
            "• `Vu`: Fuerza cortante última (tn)\n\n"
            "✏️ **Ejemplo:** Viga 30×50 cm, f'c=210, fy=4200, Mu=14.5 tn·m, Vu=8.5 tn:\n"
            "`30 50 210 4200 14.5 8.5`"
        )
        bot.send_message(chat_id, msg, parse_mode="Markdown")
        
    elif call.data == "modo_concreto":
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("fc = 140 kg/cm²", callback_data="fc_140"),
            InlineKeyboardButton("fc = 175 kg/cm²", callback_data="fc_175"),
            InlineKeyboardButton("fc = 210 kg/cm²", callback_data="fc_210"),
            InlineKeyboardButton("fc = 280 kg/cm²", callback_data="fc_280"),
            InlineKeyboardButton("fc = 350 kg/cm²", callback_data="fc_350"),
            InlineKeyboardButton("fc = 450 kg/cm²", callback_data="fc_450")
        )
        bot.send_message(chat_id, "Seleccione la resistencia del concreto ($f'c$):", reply_markup=markup, parse_mode="Markdown")

    elif call.data.startswith("fc_"):
        fc = call.data.split("_")[1]
        user_state[chat_id] = {'modo': 'concreto', 'fc': fc}
        msg = (
            f"✅ **Concreto Seleccionado:** f'c = {fc} kg/cm²\n\n"
            "Envía las dimensiones y cantidad:\n"
            "`[Ancho] [Largo] [Altura] [Cantidad] [% Desperdicio]`\n"
            "Ejemplo: `0.30 0.40 3.50 4 5`"
        )
        bot.send_message(chat_id, msg, parse_mode="Markdown")

# ---------------------------------------------------------
# PROCESAMIENTO DE MENSAJES DE ENTRADA
# ---------------------------------------------------------
@bot.message_handler(func=lambda message: True)
def procesar_mensajes(message):
    chat_id = message.chat.id
    estado = user_state.get(chat_id, {})
    modo = estado.get('modo', None)

    if not modo:
        bot.reply_to(message, "⚠️ Use el comando /start para seleccionar una opción.")
        return

    # MÓDULO 1: DISEÑO DE VIGA ESTRUCTURAL (E.060)
    if modo == 'viga':
        try:
            datos = [float(x) for x in message.text.split()]
            if len(datos) < 6:
                raise ValueError

            b, h, fc, fy, Mu_tnm, Vu_tn = datos[0], datos[1], datos[2], datos[3], datos[4], datos[5]
            
            # Recubrimiento estándar RNE E.060 (viga)
            rec = 6.0 # cm a centro de masa del acero
            d = h - rec
            phi_flex = 0.90
            phi_corte = 0.85

            # Parámetro Beta1 según E.060
            beta1 = 0.85 if fc <= 280 else max(0.65, 0.85 - 0.05 * (fc - 280) / 70.0)

            # Acero mínimo y máximo
            as_min = max((0.7 * math.sqrt(fc) / fy) * b * d, (14.0 / fy) * b * d)
            cb = (6000.0 / (6000.0 + fy)) * d
            ab = beta1 * cb
            as_b = (0.85 * fc * ab * b) / fy
            as_max = 0.75 * as_b

            # Momento resistente máximo en sección simplemente reforzada
            a_max = (as_max * fy) / (0.85 * fc * b)
            Mu_max_simp = phi_flex * as_max * fy * (d - a_max / 2.0) / 100000.0 # tn*m

            # Determinación de tipo de refuerzo
            Mu_kgcm = Mu_tnm * 100000.0
            if Mu_tnm <= Mu_max_simp:
                tipo_viga = "SIMPLEMENTE REFORZADA"
                # Solución cuadrática para As
                A_q = 0.5 * phi_flex * (fy**2) / (0.85 * fc * b)
                B_q = - phi_flex * fy * d
                C_q = Mu_kgcm
                disc = B_q**2 - 4 * A_q * C_q
                As_calc = (-B_q - math.sqrt(disc)) / (2 * A_q)
                As_req = max(As_calc, as_min)
                As_comp = 0.0
            else:
                tipo_viga = "DOBLEMENTE REFORZADA"
                As1 = as_max
                Mu1_kgcm = Mu_max_simp * 100000.0
                Mu2_kgcm = Mu_kgcm - Mu1_kgcm
                dp = rec
                As2 = Mu2_kgcm / (phi_flex * fy * (d - dp))
                As_req = As1 + As2
                As_comp = As2

            # CÁLCULO POR CORTE (E.060)
            Vc = 0.53 * math.sqrt(fc) * b * d # kg
            phi_Vc = phi_corte * Vc / 1000.0 # tn
            Vu_kg = Vu_tn * 1000.0

            if Vu_tn <= 0.5 * phi_Vc:
                corte_msg = "No requiere estribos por cálculo. Colocar separación máxima por norma."
                s_estribo = 25.0
            elif Vu_tn <= phi_Vc:
                corte_msg = "Requiere estribos mínimos por norma RNE E.060."
                s_estribo = min(d / 2, 30.0)
            else:
                Vs_req = (Vu_kg - (phi_corte * Vc)) / phi_corte
                Av = 2 * 0.71 # Estribos de 3/8" (0.71 cm2 por rama)
                s_calc = (Av * fy * d) / Vs_req
                s_estribo = min(s_calc, d / 2, 30.0)
                corte_msg = f"Requiere estribos de 3/8\" por cálculo cada `{s_estribo:.1f}` cm en zona de apriete."

            # Distribución sísmica estándar peruana E.060
            distribucion_estribos = f"1 @ 0.05 m, 5 @ 0.10 m, 4 @ 0.15 m, resto @ {s_estribo/100:.2f} m c/extremos"

            informe = (
                f"📐 **INFORME DE DISEÑO ESTRUCTURAL (RNE E.060)**\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🔹 **Sección:** {b:.0f} × {h:.0f} cm | Peralte efe. (d): `{d:.1f} cm`\n"
                f"🔹 **Materiales:** f'c = {fc:.0f} kg/cm² | fy = {fy:.0f} kg/cm²\n"
                f"🔹 **Solicitaciones:** Mu = `{Mu_tnm:.2f} tn·m` | Vu = `{Vu_tn:.2f} tn`\n\n"
                f"📌 **1. FLEXIÓN:**\n"
                f"• **Tipo de Viga:** `{tipo_viga}`\n"
                f"• Mu Máx. Simplemente Ref.: `{Mu_max_simp:.2f} tn·m`\n"
                f"• Acero Mínimo ($A_{{s,min}}$): `{as_min:.2f} cm²`\n"
                f"• **Acero en Tracción ($A_s$):** `{As_req:.2f} cm²`\n"
                + (f"• **Acero en Compresión ($A_{{s'}}$):** `{As_comp:.2f} cm²`\n" if As_comp > 0 else "") +
                f"\n📌 **2. CORTE Y ESTRIBADO:**\n"
                f"• Resistencia Concreto ($\phi V_c$): `{phi_Vc:.2f} tn`\n"
                f"• Estado: {corte_msg}\n"
                f"• **Distribución recomendada:**\n`{distribucion_estribos}`"
            )

            bot.reply_to(message, informe, parse_mode="Markdown")

            # Generar y enviar gráfico
            buf = generar_croquis_viga(b, h, rec, tipo_viga, As_req, As_comp, Vu_tn, s_estribo)
            bot.send_photo(chat_id, photo=buf, caption=f"📊 Croquis de Armado - Viga {b:.0f}x{h:.0f} cm")

        except Exception as e:
            bot.reply_to(
                message,
                "⚠️ **Error en formato de entrada.** Envíe 6 valores numéricos:\n"
                "`[b] [h] [f'c] [fy] [Mu] [Vu]`\n\n"
                "Ejemplo: `30 50 210 4200 14.5 8.5`",
                parse_mode="Markdown"
            )

    # MÓDULO 2: DOSIFICACIÓN DE CONCRETO
    elif modo == 'concreto':
        try:
            datos = [float(x) for x in message.text.split()]
            b, l, h, cant = datos[0], datos[1], datos[2], int(datos[3])
            desp_pct = datos[4] if len(datos) >= 5 else 5.0
            
            fc = estado.get('fc', '210')
            dosi = DOSIFICACIONES[fc]
            factor = 1 + (desp_pct / 100.0)

            vol_neto = b * l * h * cant
            vol_tot = vol_neto * factor

            cemento = vol_tot * dosi['cemento']
            arena = vol_tot * dosi['arena']
            piedra = vol_tot * dosi['piedra']
            agua = vol_tot * dosi['agua'] * 1000

            resumen = (
                f"📄 **DOSIFICACIÓN DE CONCRETO (f'c = {fc} kg/cm²)**\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📦 Volumen Total (+{desp_pct:.1f}% desperdicio): `{vol_tot:.2f} m³`\n\n"
                f"🛠️ **Insumos Requeridos:**\n"
                f"• Cemento: `{cemento:.1f}` bolsas\n"
                f"• Arena Gruesa: `{arena:.2f}` m³\n"
                f"• Piedra Chancada: `{piedra:.2f}` m³\n"
                f"• Agua: `{agua:.0f}` Litros"
            )
            bot.reply_to(message, resumen, parse_mode="Markdown")
        except Exception:
            bot.reply_to(message, "⚠️ Formato incorrecto. Ejemplo: `0.30 0.40 3.50 4 5`", parse_mode="Markdown")

bot.infinity_polling()

