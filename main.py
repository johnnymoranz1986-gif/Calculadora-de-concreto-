import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import io
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

TOKEN = "8978402989:AAEcJEXuFFHQImwQVJph58ZmZpMpn7xSfqk"
bot = telebot.TeleBot(TOKEN)

# Servidor HTTP para mantener activo el Web Service en Render
class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot activo en Render")

def run_http_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), SimpleHTTPRequestHandler)
    server.serve_forever()

threading.Thread(target=run_http_server, daemon=True).start()

# Tabla de dosificaciones por m³ (Estándar RNE / CAPECO / ACI)
DOSIFICACIONES = {
    '140': {'cemento': 7.01, 'arena': 0.51, 'piedra': 0.64, 'agua': 0.184, 'nombre': "140 kg/cm² (Solados / Falso Piso)"},
    '175': {'cemento': 8.43, 'arena': 0.54, 'piedra': 0.55, 'agua': 0.185, 'nombre': "175 kg/cm² (Cimientos / Sobrecimientos)"},
    '210': {'cemento': 9.73, 'arena': 0.52, 'piedra': 0.53, 'agua': 0.186, 'nombre': "210 kg/cm² (Columnas / Vigas / Losas)"},
    '280': {'cemento': 13.34, 'arena': 0.45, 'piedra': 0.51, 'agua': 0.189, 'nombre': "280 kg/cm² (Vigas de gran luz / Puentes)"},
    '350': {'cemento': 15.80, 'arena': 0.43, 'piedra': 0.50, 'agua': 0.190, 'nombre': "350 kg/cm² (Pretensado / Alta Resistencia)"},
    '450': {'cemento': 18.50, 'arena': 0.40, 'piedra': 0.48, 'agua': 0.195, 'nombre': "450 kg/cm² (Alta Resistencia Especial)"}
}

# Almacenamiento temporal de estado de usuario
user_state = {}

def generar_grafico_materiales(cemento, arena, piedra, fc):
    fig, ax = plt.subplots(figsize=(6, 4))
    materiales = ['Cemento\n(Bolsas)', 'Arena Gruesa\n(m³)', 'Piedra Chancada\n(m³)']
    cantidades = [cemento, arena, piedra]
    colores = ['#4A5568', '#D69E2E', '#718096']

    bars = ax.bar(materiales, cantidades, color=colores, width=0.5)
    ax.set_ylabel('Cantidad Requerida')
    ax.set_title(f"Insumos de Concreto f'c = {fc} kg/cm²", fontsize=11, fontweight='bold')
    ax.grid(axis='y', linestyle='--', alpha=0.7)

    for bar in bars:
        yval = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2, yval + (yval * 0.02), f'{yval:.2f}', ha='center', va='bottom', fontweight='bold')

    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=150)
    buf.seek(0)
    plt.close(fig)
    return buf

@bot.message_handler(commands=['start', 'menu'])
def mostrar_menu(message):
    markup = InlineKeyboardMarkup()
    markup.row_width = 2
    markup.add(
        InlineKeyboardButton("fc = 140 kg/cm²", callback_data="fc_140"),
        InlineKeyboardButton("fc = 175 kg/cm²", callback_data="fc_175"),
        InlineKeyboardButton("fc = 210 kg/cm²", callback_data="fc_210"),
        InlineKeyboardButton("fc = 280 kg/cm²", callback_data="fc_280"),
        InlineKeyboardButton("fc = 350 kg/cm²", callback_data="fc_350"),
        InlineKeyboardButton("fc = 450 kg/cm²", callback_data="fc_450")
    )
    markup.add(
        InlineKeyboardButton("📋 Ver Tabla de Dosificaciones", callback_data="info_tabla")
    )
    bot.reply_to(
        message,
        "🏗️ **CÁLCULO Y METRADO DE CONCRETO**\n\n"
        "Seleccione la resistencia del concreto ($f'c$):",
        reply_markup=markup,
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: True)
def callback_listener(call):
    if call.data.startswith("fc_"):
        fc = call.data.split("_")[1]
        user_state[call.message.chat.id] = {'fc': fc}
        
        info = DOSIFICACIONES[fc]
        msg = (
            f"✅ **Resistencia seleccionada:** f'c = {info['nombre']}\n\n"
            "Envía las dimensiones, cantidad y % de desperdicio en el siguiente formato:\n"
            "`[Ancho] [Largo] [Altura] [Cantidad] [% Desperdicio]`\n\n"
            "📌 **Ejemplo:** Para 4 columnas de 0.30×0.40×3.50 m con 5% de desperdicio:\n"
            "`0.30 0.40 3.50 4 5`"
        )
        bot.send_message(call.message.chat.id, msg, parse_mode="Markdown")

    elif call.data == "info_tabla":
        tabla_msg = (
            "📋 **DOSIFICACIONES ESTÁNDAR POR m³:**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "🔹 **f'c = 140:** 7.01 bols. | 0.51 m³ arena | 0.64 m³ piedra\n"
            "🔹 **f'c = 175:** 8.43 bols. | 0.54 m³ arena | 0.55 m³ piedra\n"
            "🔹 **f'c = 210:** 9.73 bols. | 0.52 m³ arena | 0.53 m³ piedra\n"
            "🔹 **f'c = 280:** 13.34 bols. | 0.45 m³ arena | 0.51 m³ piedra\n"
            "🔹 **f'c = 350:** 15.80 bols. | 0.43 m³ arena | 0.50 m³ piedra\n"
            "🔹 **f'c = 450:** 18.50 bols. | 0.40 m³ arena | 0.48 m³ piedra"
        )
        bot.send_message(call.message.chat.id, tabla_msg, parse_mode="Markdown")

@bot.message_handler(func=lambda message: True)
def procesar_metrado(message):
    chat_id = message.chat.id
    if chat_id not in user_state or 'fc' not in user_state[chat_id]:
        bot.reply_to(message, "⚠️ Primero seleccione la resistencia enviando /start o /menu")
        return

    try:
        datos = message.text.split()
        if len(datos) < 4:
            raise ValueError

        b = float(datos[0])
        l = float(datos[1])
        h = float(datos[2])
        cant = int(datos[3])
        
        # Porcentaje de desperdicio opcional (si se omite, toma 5.0%)
        desperdicio_pct = float(datos[4]) if len(datos) >= 5 else 5.0
        factor_desperdicio = 1 + (desperdicio_pct / 100)

        fc = user_state[chat_id]['fc']
        dosi = DOSIFICACIONES[fc]

        vol_unitario = b * l * h
        vol_neto = vol_unitario * cant
        vol_total = vol_neto * factor_desperdicio

        cemento = vol_total * dosi['cemento']
        arena = vol_total * dosi['arena']
        piedra = vol_total * dosi['piedra']
        agua = vol_total * dosi['agua'] * 1000

        resumen = (
            f"📄 **MEMORIA DE CÁLCULO DE MATERIALES**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎯 **Resistencia:** f'c = {fc} kg/cm²\n"
            f"🔹 **Elementos:** {cant} unidad(es) ({b:.2f} m × {l:.2f} m × {h:.2f} m)\n"
            f"📦 **Volumen Neto:** `{vol_neto:.2f} m³`\n"
            f"📈 **Volumen Total (+{desperdicio_pct:.1f}% Desp.):** `{vol_total:.2f} m³`\n\n"
            f"🛠️ **Materiales Requeridos:**\n"
            f"• Cemento (42.5 kg): `{cemento:.1f}` bolsas\n"
            f"• Arena Gruesa: `{arena:.2f}` m³\n"
            f"• Piedra Chancada: `{piedra:.2f}` m³\n"
            f"• Agua: `{agua:.0f}` Litros"
        )

        bot.reply_to(message, resumen, parse_mode="Markdown")

        img_buf = generar_grafico_materiales(cemento, arena, piedra, fc)
        bot.send_photo(chat_id, photo=img_buf, caption=f"📊 Cuadro de Insumos para f'c = {fc} kg/cm²")

    except Exception:
        bot.reply_to(
            message,
            "⚠️ **Formato incorrecto.** Envíe los datos en el formato:\n"
            "`[Ancho] [Largo] [Altura] [Cantidad] [% Desperdicio]`\n\n"
            "Ejemplo: `0.30 0.40 3.50 4 5`",
            parse_mode="Markdown"
        )

bot.infinity_polling()
