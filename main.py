import os
import math
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# --- SERVIDOR HTTP PARA RENDER ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(b"Bot activo y escuchando.")

def run_health_check_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    server.serve_forever()

threading.Thread(target=run_health_check_server, daemon=True).start()

# --- CONFIGURACIÓN DEL BOT ---
TOKEN = os.environ.get("BOT_TOKEN", "8978402989:AAH5pIvfI_76cePT7PY6pziMkVLcoN2kxL8")
bot = telebot.TeleBot(TOKEN, parse_mode="Markdown")

DOSIFICACIONES = {
    '140': {'cemento': 7.01, 'arena': 0.51, 'piedra': 0.64, 'agua': 0.184},
    '175': {'cemento': 8.43, 'arena': 0.54, 'piedra': 0.55, 'agua': 0.185},
    '210': {'cemento': 9.73, 'arena': 0.52, 'piedra': 0.53, 'agua': 0.186},
    '280': {'cemento': 13.34, 'arena': 0.45, 'piedra': 0.51, 'agua': 0.189},
    '350': {'cemento': 15.80, 'arena': 0.43, 'piedra': 0.50, 'agua': 0.190},
    '450': {'cemento': 18.50, 'arena': 0.40, 'piedra': 0.48, 'agua': 0.195}
}

user_state = {}

def generar_grafico_viga(b, h, As, As_comp, s_estribo):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 5))
    
    # 1. SECCIÓN TRANSVERSAL
    ax1.set_title(f"Seccion Transversal\n{b:.0f} x {h:.0f} cm", fontsize=10, fontweight='bold')
    recubrimiento = 4.0
    viga_rect = patches.Rectangle((0, 0), b, h, linewidth=2, edgecolor='black', facecolor='#e0e0e0')
    estribo_rect = patches.Rectangle((recubrimiento, recubrimiento), b - 2*recubrimiento, h - 2*recubrimiento, 
                                     linewidth=1.5, edgecolor='blue', facecolor='none', linestyle='--', label=f"Estribo c/ {s_estribo:.1f}cm")
    ax1.add_patch(viga_rect)
    ax1.add_patch(estribo_rect)

    ax1.scatter([b/4, b/2, 3*b/4], [recubrimiento, recubrimiento, recubrimiento], color='red', s=80, zorder=5, label=f"Traccion As: {As:.2f}cm²")
    
    if As_comp > 0:
        ax1.scatter([b/3, 2*b/3], [h-recubrimiento, h-recubrimiento], color='green', s=80, zorder=5, label=f"Compresion As': {As_comp:.2f}cm²")
    else:
        ax1.scatter([b/3, 2*b/3], [h-recubrimiento, h-recubrimiento], color='purple', s=50, zorder=5, label="Acero Montaje")

    ax1.set_xlim(-5, b + 5)
    ax1.set_ylim(-5, h + 5)
    ax1.set_aspect('equal')
    ax1.legend(loc='upper right', fontsize=8)
    ax1.grid(True, linestyle=':', alpha=0.5)

    # 2. PERFIL LONGITUDINAL
    ax2.set_title("Distribucion de Estribos (Norma E.060)", fontsize=10, fontweight='bold')
    longitud_viga = 300.0
    ax2.plot([0, longitud_viga], [0, 0], color='black', linewidth=4)
    ax2.plot([0, longitud_viga], [h, h], color='black', linewidth=4)

    zona_conf = 60.0
    ax2.axvspan(0, zona_conf, color='yellow', alpha=0.3, label='Confinamiento (1@5, c/10cm)')
    ax2.axvspan(longitud_viga - zona_conf, longitud_viga, color='yellow', alpha=0.3)

    ax2.text(zona_conf/2, h/2, "ZONA 1\nConfinada", ha='center', va='center', fontsize=8, fontweight='bold')
    ax2.text(longitud_viga/2, h/2, f"ZONA CENTRAL\nEstribos c/ {s_estribo:.0f}cm", ha='center', va='center', fontsize=8, fontweight='bold')
    ax2.text(longitud_viga - zona_conf/2, h/2, "ZONA 3\nConfinada", ha='center', va='center', fontsize=8, fontweight='bold')

    ax2.set_xlim(-10, longitud_viga + 10)
    ax2.set_ylim(-10, h + 20)
    ax2.legend(loc='upper center', fontsize=8)
    ax2.grid(True, linestyle=':', alpha=0.5)

    plt.tight_layout()
    ruta_imagen = "detalles_viga.png"
    plt.savefig(ruta_imagen, dpi=150)
    plt.close()
    return ruta_imagen

@bot.message_handler(commands=['start', 'menu'])
def mostrar_menu(message):
    markup = InlineKeyboardMarkup()
    markup.row_width = 1
    markup.add(
        InlineKeyboardButton("📐 Diseño de Viga Detallado (RNE E.060)", callback_data="modo_viga"),
        InlineKeyboardButton("📦 Cubicación de Concreto", callback_data="modo_concreto")
    )
    msg = (
        "🏗️ *SISTEMA DE INGENIERÍA ESTRUCTURAL (RNE PERÚ)*\n\n"
        "• Para Viga (6 datos):\n"
        "`30 60 210 4200 20 12`\n\n"
        "• Para Concreto (4 o 5 datos):\n"
        "`0.30 0.40 3.50 4 5`"
    )
    bot.reply_to(message, msg)

@bot.callback_query_handler(func=lambda call: True)
def callback_listener(call):
    chat_id = call.message.chat.id
    if call.data == "modo_viga":
        user_state[chat_id] = {'modo': 'viga'}
        bot.send_message(chat_id, "📐 Envíe los 6 valores para la viga:\n`[b] [h] [f'c] [fy] [Mu] [Vu]`")
    elif call.data == "modo_concreto":
        markup = InlineKeyboardMarkup(row_width=2)
        for r in ['140', '175', '210', '280', '350', '450']:
            markup.add(InlineKeyboardButton(f"fc = {r}", callback_data=f"fc_{r}"))
        bot.send_message(chat_id, "Seleccione f'c:", reply_markup=markup)
    elif call.data.startswith("fc_"):
        fc = call.data.split("_")[1]
        user_state[chat_id] = {'modo': 'concreto', 'fc': fc}
        bot.send_message(chat_id, f"✅ `f'c = {fc}` seleccionado. Envía dimensiones: `[Ancho] [Largo] [Altura] [Cant] [%Desp]`")

@bot.message_handler(func=lambda message: True)
def procesar_mensajes(message):
    try:
        chat_id = message.chat.id
        texto = message.text.strip().replace(',', '.')
        valores = [float(x) for x in texto.split()]

        if len(valores) == 6:
            b, h, fc, fy, Mu_tnm, Vu_tn = valores
            
            rec = 6.0
            d = h - rec
            phi_flex = 0.90
            phi_corte = 0.85

            beta1 = 0.85 if fc <= 280 else max(0.65, 0.85 - 0.05 * (fc - 280) / 70.0)

            # --- FÓRMULAS ACERO MÍNIMO ---
            as_min1 = (0.7 * math.sqrt(fc) / fy) * b * d
            as_min2 = (14.0 / fy) * b * d
            as_min = max(as_min1, as_min2)

            cb = (6000.0 / (6000.0 + fy)) * d
            ab = beta1 * cb
            as_b = (0.85 * fc * ab * b) / fy
            as_max = 0.75 * as_b

            a_max_calc = (as_max * fy) / (0.85 * fc * b)
            Mu_max_simp = phi_flex * as_max * fy * (d - a_max_calc / 2.0) / 100000.0
            Mu_kgcm = Mu_tnm * 100000.0

            if Mu_tnm <= Mu_max_simp:
                tipo_viga = "SIMPLEMENTE REFORZADA"
                term = 1.0 - (2.0 * Mu_kgcm) / (phi_flex * b * (d**2) * 0.85 * fc)
                if term < 0:
                    bot.reply_to(message, "❌ Error: Momento actuante excede la capacidad máxima.")
                    return
                As_calc = (0.85 * fc * b * d / fy) * (1.0 - math.sqrt(term))
                As_req = max(As_calc, as_min)
                As_comp = 0.0
            else:
                tipo_viga = "DOBLEMENTE REFORZADA"
                As1 = as_max
                Mu1_kgcm = Mu_max_simp * 100000.0
                Mu2_kgcm = Mu_kgcm - Mu1_kgcm
                As2 = Mu2_kgcm / (phi_flex * fy * (d - rec))
                As_req = As1 + As2
                As_comp = As2

            # --- FÓRMULAS CORTE Y ESPACIAMIENTO ---
            Vc = 0.53 * math.sqrt(fc) * b * d
            phi_Vc_tn = (phi_corte * Vc) / 1000.0
            Vu_kg = Vu_tn * 1000.0

            if Vu_tn <= 0.5 * phi_Vc_tn:
                corte_estado = "Vu <= 0.5*φ*Vc (Mínimo constructivo)"
                s_estribo = 22.0
                formula_s = "s = 22.0 cm (Fijo por norma)"
            elif Vu_tn <= phi_Vc_tn:
                corte_estado = "0.5*φ*Vc < Vu <= φ*Vc"
                s_estribo = min(d / 2.0, 30.0)
                formula_s = f"s = min(d/2, 30) = min({d/2:.1f}, 30)"
            else:
                corte_estado = "Vu > φ*Vc (Requiere cálculo por corte)"
                Vs_req = (Vu_kg - (phi_corte * Vc)) / phi_corte
                Av = 2 * 0.71
                s_calc = (Av * fy * d) / Vs_req
                s_estribo = min(s_calc, d / 2.0, 30.0)
                formula_s = f"s = (Av * fy * d) / Vs = ({Av} * {fy} * {d}) / {Vs_req:.1f} = {s_calc:.1f} cm"

            # --- INFORME CON FÓRMULAS Y PASOS DETALLADOS ---
            informe = (
                "📐 *MEMORIA DE CÁLCULO Y FÓRMULAS (E.060)*\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                
                "🔹 *1. GEOMETRÍA Y MATERIALES*\n"
                f"• Peralte efectivo ($d$): `h - rec` = `{h} - 6 = {d:.1f} cm`\n"
                f"• Factor $\\beta_1$: `{beta1:.2f}`\n\n"
                
                "🔹 *2. CÁLCULO DE FLEXIÓN*\n"
                f"• Acero Mínimo ($As_{{min}}$):\n"
                f"  `max((0.7*√f'c/fy)*b*d, (14/fy)*b*d)`\n"
                f"  = `max({as_min1:.2f}, {as_min2:.2f})` = *{as_min:.2f} cm²*\n"
                f"• Comportamiento: *{tipo_viga}*\n"
                f"• Momento Máximo Simp. ($Mu_{{max}}$): `{Mu_max_simp:.2f} tn·m`\n\n"
                
                "🎯 *RESULTADOS CRÍTICOS DE DISEÑO:*\n"
                "┌────────────────────────────────────────┐\n"
                f"│ • Acero Tracción (As)  : {As_req:6.2f} cm²   │\n" +
                (f"│ • Acero Compresión (As'): {As_comp:6.2f} cm²   │\n" if As_comp > 0 else "") +
                f"│ • Estribos (Zona Cent.): c/ {s_estribo:4.1f} cm    │\n" +
                "└────────────────────────────────────────┘\n\n"
                
                "🔹 *3. CÁLCULO Y ESPACIAMIENTO POR CORTE*\n"
                f"• Concreto ($\\phi V_c$): `0.85 * (0.53 * √f'c * b * d) / 1000`\n"
                f"  = *{phi_Vc_tn:.2f} tn* (vs $Vu$ = {Vu_tn:.2f} tn)\n"
                f"• Condición: *{corte_estado}*\n"
                f"• Aplicación de Fórmula:\n"
                f"  `{formula_s}`\n"
                f"  -> Rige final: *s = {s_estribo:.1f} cm*"
            )
            bot.reply_to(message, informe)

            # Enviar gráfico
            ruta_img = generar_grafico_viga(b, h, As_req, As_comp, s_estribo)
            with open(ruta_img, 'rb') as foto:
                bot.send_photo(chat_id, foto, caption="📊 *Plano esquemático y distribución de estribos según RNE E.060*")

        elif len(valores) in [4, 5]:
            b, l, h, cant = valores[0], valores[1], valores[2], int(valores[3])
            desp_pct = valores[4] if len(valores) == 5 else 5.0
            fc = user_state.get(chat_id, {}).get('fc', '210')
            dosi = DOSIFICACIONES.get(fc, DOSIFICACIONES['210'])
            vol_neto = b * l * h * cant
            vol_tot = vol_neto * (1 + desp_pct / 100.0)

            resumen = (
                f"📦 *CÚBICA Y FÓRMULAS DE CONCRETO (f'c = {fc})*\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"• Fórmula Volumen Neto: `Ancho * Largo * Altura * Cantidad`\n"
                f"  = `{b} * {l} * {h} * {cant}` = `{vol_neto:.2f} m³`\n"
                f"• Volumen Total (+{desp_pct:.1f}% des.): `{vol_neto} * (1 + {desp_pct}/100)` = *{vol_tot:.2f} m³*\n\n"
                f"🎯 *MATERIALES REQUERIDOS:*\n"
                "┌────────────────────────────────────────┐\n"
                f"│ • Cemento : {vol_tot * dosi['cemento']:6.1f} bolsas       │\n"
                f"│ • Arena   : {vol_tot * dosi['arena']:6.2f} m³          │\n"
                f"│ • Piedra  : {vol_tot * dosi['piedra']:6.2f} m³          │\n"
                f"│ • Agua    : {vol_tot * dosi['agua'] * 1000:6.0f} Litros       │\n"
                "└────────────────────────────────────────┘"
            )
            bot.reply_to(message, resumen)
        else:
            bot.reply_to(message, "⚠️ Formato incorrecto. Envíe 6 valores para viga o 4-5 para concreto.")
    except Exception as err:
        bot.reply_to(message, f"⚠️ Error de cálculo: {err}")

if __name__ == '__main__':
    print("Iniciando bot con fórmulas explícitas...")
    while True:
        try:
            bot.polling(none_stop=True, interval=1, timeout=20)
        except Exception as e:
            time.sleep(3)
