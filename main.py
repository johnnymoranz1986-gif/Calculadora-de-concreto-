import os
import math
import time
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

TOKEN = os.environ.get("BOT_TOKEN", "8978402989:AAH5pIvfI_76cePT7PY6pziMkVLcoN2kxL8")
bot = telebot.TeleBot(TOKEN, parse_mode=None)

DOSIFICACIONES = {
    '140': {'cemento': 7.01, 'arena': 0.51, 'piedra': 0.64, 'agua': 0.184},
    '175': {'cemento': 8.43, 'arena': 0.54, 'piedra': 0.55, 'agua': 0.185},
    '210': {'cemento': 9.73, 'arena': 0.52, 'piedra': 0.53, 'agua': 0.186},
    '280': {'cemento': 13.34, 'arena': 0.45, 'piedra': 0.51, 'agua': 0.189},
    '350': {'cemento': 15.80, 'arena': 0.43, 'piedra': 0.50, 'agua': 0.190},
    '450': {'cemento': 18.50, 'arena': 0.40, 'piedra': 0.48, 'agua': 0.195}
}

user_state = {}

@bot.message_handler(commands=['start', 'menu'])
def mostrar_menu(message):
    markup = InlineKeyboardMarkup()
    markup.row_width = 1
    markup.add(
        InlineKeyboardButton("📐 Diseño de Viga (Flexión y Corte)", callback_data="modo_viga"),
        InlineKeyboardButton("📦 Cubicación y Dosificación de Concreto", callback_data="modo_concreto")
    )
    msg = (
        "🏗️ SISTEMA DE INGENIERÍA ESTRUCTURAL (RNE PERÚ)\n\n"
        "💡 Ingrese los datos directamente:\n\n"
        "• Para Viga (6 datos):\n"
        "[b] [h] [f'c] [fy] [Mu] [Vu]\n"
        "  Ejemplo: 30 60 210 4200 20 12\n\n"
        "• Para Concreto (4 o 5 datos):\n"
        "[Ancho] [Largo] [Altura] [Cant] [%Desp]\n"
        "  Ejemplo: 0.30 0.40 3.50 4 5"
    )
    bot.reply_to(message, msg, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def callback_listener(call):
    chat_id = call.message.chat.id
    if call.data == "modo_viga":
        user_state[chat_id] = {'modo': 'viga'}
        msg = (
            "📐 DISEÑO ESTRUCTURAL DE VIGAS (RNE E.060)\n\n"
            "Envíe los 6 valores numéricos separados por espacio:\n"
            "[b] [h] [f'c] [fy] [Mu] [Vu]\n\n"
            "📌 Ejemplo: 30 60 210 4200 20 12"
        )
        bot.send_message(chat_id, msg)
        
    elif call.data == "modo_concreto":
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("fc = 140", callback_data="fc_140"),
            InlineKeyboardButton("fc = 175", callback_data="fc_175"),
            InlineKeyboardButton("fc = 210", callback_data="fc_210"),
            InlineKeyboardButton("fc = 280", callback_data="fc_280"),
            InlineKeyboardButton("fc = 350", callback_data="fc_350"),
            InlineKeyboardButton("fc = 450", callback_data="fc_450")
        )
        bot.send_message(chat_id, "Seleccione la resistencia del concreto (f'c):", reply_markup=markup)

    elif call.data.startswith("fc_"):
        fc = call.data.split("_")[1]
        user_state[chat_id] = {'modo': 'concreto', 'fc': fc}
        msg = (
            f"✅ Concreto Seleccionado: f'c = {fc} kg/cm²\n\n"
            "Envía las dimensiones:\n"
            "[Ancho] [Largo] [Altura] [Cantidad] [% Desperdicio]\n"
            "Ejemplo: 0.30 0.40 3.50 4 5"
        )
        bot.send_message(chat_id, msg)

@bot.message_handler(func=lambda message: True)
def procesar_mensajes(message):
    try:
        chat_id = message.chat.id
        texto = message.text.strip().replace(',', '.')
        partes = texto.split()

        try:
            valores = [float(x) for x in partes]
        except ValueError:
            bot.reply_to(message, "⚠️ Entrada no válida. Envíe valores numéricos separados por espacio.")
            return

        # ----------------------------------------------------
        # CASO 1: DISEÑO ESTRUCTURAL DE VIGA (6 DATOS)
        # ----------------------------------------------------
        if len(valores) == 6:
            b, h, fc, fy, Mu_tnm, Vu_tn = valores
            
            rec = 6.0
            d = h - rec
            phi_flex = 0.90
            phi_corte = 0.85

            beta1 = 0.85 if fc <= 280 else max(0.65, 0.85 - 0.05 * (fc - 280) / 70.0)

            as_min = max((0.7 * math.sqrt(fc) / fy) * b * d, (14.0 / fy) * b * d)
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
                    bot.reply_to(message, "❌ Error: El momento actuante supera la capacidad física de la sección de concreto.")
                    return
                
                As_calc = (0.85 * fc * b * d / fy) * (1.0 - math.sqrt(term))
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

            Vc = 0.53 * math.sqrt(fc) * b * d
            phi_Vc = phi_corte * Vc / 1000.0
            Vu_kg = Vu_tn * 1000.0

            if Vu_tn <= 0.5 * phi_Vc:
                corte_msg = "No requiere estribos por cálculo (usar mínimo por norma)."
                s_estribo = 22.0
            elif Vu_tn <= phi_Vc:
                corte_msg = "Requiere estribos mínimos por norma RNE E.060."
                s_estribo = min(d / 2, 30.0)
            else:
                Vs_req = (Vu_kg - (phi_corte * Vc)) / phi_corte
                Av = 2 * 0.71
                s_calc = (Av * fy * d) / Vs_req
                s_estribo = min(s_calc, d / 2, 30.0)
                corte_msg = f"Requiere estribos ø 3/8\" c/ {s_estribo:.1f} cm."

            distribucion_estribos = f"1 @ 0.05 m, 5 @ 0.10 m, 4 @ 0.15 m, resto @ {s_estribo/100:.2f} m c/extremo"

            comp_line = f"• Acero Compresión (As'): {As_comp:.2f} cm²\n" if As_comp > 0 else ""

            informe = (
                f"📐 DISEÑO ESTRUCTURAL DE VIGA (RNE E.060)\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🔹 Sección: {b:.0f} × {h:.0f} cm | Peralte efe. (d): {d:.1f} cm\n"
                f"🔹 Materiales: f'c = {fc:.0f} kg/cm² | fy = {fy:.0f} kg/cm²\n"
                f"🔹 Solicitaciones: Mu = {Mu_tnm:.2f} tn·m | Vu = {Vu_tn:.2f} tn\n\n"
                f"📌 1. DISEÑO POR FLEXIÓN:\n"
                f"• Tipo: {tipo_viga}\n"
                f"• Mu Máx. Simplemente Ref.: {Mu_max_simp:.2f} tn·m\n"
                f"• Acero Mínimo (As_min): {as_min:.2f} cm²\n"
                f"• Acero Tracción (As): {As_req:.2f} cm²\n"
                f"{comp_line}\n"
                f"📌 2. DISEÑO POR CORTE:\n"
                f"• Resistencia Concreto (phi Vc): {phi_Vc:.2f} tn\n"
                f"• Estado: {corte_msg}\n"
                f"• Distribución Sísmica Recomendada:\n{distribucion_estribos}"
            )
            bot.reply_to(message, informe)

        # ----------------------------------------------------
        # CASO 2: DOSIFICACIÓN DE CONCRETO (4 O 5 DATOS)
        # ----------------------------------------------------
        elif len(valores) in [4, 5]:
            b, l, h, cant = valores[0], valores[1], valores[2], int(valores[3])
            desp_pct = valores[4] if len(valores) == 5 else 5.0

            fc = user_state.get(chat_id, {}).get('fc', '210')
            dosi = DOSIFICACIONES.get(fc, DOSIFICACIONES['210'])
            factor = 1 + (desp_pct / 100.0)

            vol_tot = (b * l * h * cant) * factor

            cemento = vol_tot * dosi['cemento']
            arena = vol_tot * dosi['arena']
            piedra = vol_tot * dosi['piedra']
            agua = vol_tot * dosi['agua'] * 1000

            resumen = (
                f"📄 DOSIFICACIÓN DE CONCRETO (f'c = {fc} kg/cm²)\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📦 Volumen Total (+{desp_pct:.1f}% desperdicio): {vol_tot:.2f} m³\n\n"
                f"🛠️ Insumos Requeridos:\n"
                f"• Cemento: {cemento:.1f} bolsas\n"
                f"• Arena Gruesa: {arena:.2f} m³\n"
                f"• Piedra Chancada: {piedra:.2f} m³\n"
                f"• Agua: {agua:.0f} Litros"
            )
            bot.reply_to(message, resumen)

        else:
            bot.reply_to(
                message,
                "⚠️ Formato no reconocido.\n\n"
                "• Viga (6 datos): 30 60 210 4200 20 12\n"
                "• Concreto (4-5 datos): 0.30 0.40 3.50 4 5"
            )

    except Exception as err:
        print(f"Error procesando mensaje: {err}")
        bot.reply_to(message, f"⚠️ Error interno en el cálculo: {err}")

if __name__ == '__main__':
    print("Iniciando servicio del Bot en Render...")
    try:
        bot.remove_webhook(drop_pending_updates=True)
        time.sleep(2)
    except Exception as e:
        print(f"Aviso al limpiar webhook: {e}")

    while True:
        try:
            bot.polling(none_stop=True, interval=1, timeout=20)
        except Exception as e:
            print(f"Bucle de polling reanudado tras excepción: {e}")
            time.sleep(3)
