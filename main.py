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

# Servidor HTTP dummy para mantener activo el Web Service en Render
class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot Profesional Activo")

def run_http_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), SimpleHTTPRequestHandler)
    server.serve_forever()

threading.Thread(target=run_http_server, daemon=True).start()

# Lógica de dosificación para f'c = 210 kg/cm2
DOSIFICACION_210 = {
    'cemento_bolsas': 9.73,
    'arena_m3': 0.52,
    'piedra_m3': 0.53,
    'agua_m3': 0.186
}

def generar_grafico_materiales(cemento, arena, piedra):
    fig, ax = plt.subplots(figsize=(6, 4))
    materiales = ['Cemento\n(Bolsas)', 'Arena Gruesa\n(m³)', 'Piedra Chancada\n(m³)']
    cantidades = [cemento, arena, piedra]
    colores = ['#4A5568', '#D69E2E', '#718096']

    bars = ax.bar(materiales, cantidades, color=colores, width=0.5)
    ax.set_ylabel('Cantidad Requerida')
    ax.set_title("Resumen de Insumos - Concreto f'c = 210 kg/cm²", fontsize=11, fontweight='bold')
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
    markup.row_width = 1
    markup.add(
        InlineKeyboardButton("📐 Metrado y Dosificación de Elementos", callback_data="calc_rect"),
        InlineKeyboardButton("📋 Ver Tabla de Dosificación (f'c = 210)", callback_data="info_dosi")
    )
    bot.reply_to(message, "🏗️ **SISTEMA PROFESIONAL DE METRADOS**\n\nSeleccione la opción requerida:", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: True)
def callback_listener(call):
    if call.data == "calc_rect":
        bot.send_message(
            call.message.chat.id, 
            "Envía las dimensiones y cantidad del elemento:\n"
            "`[Base] [Largo] [Altura] [Cantidad]`\n\n"
            "Ejemplo para 4 columnas de 0.30 × 0.40 × 3.50 m:\n"
            "`0.30 0.40 3.50 4`",
            parse_mode="Markdown"
        )
    elif call.data == "info_dosi":
        info = (
            "📋 **Dosificación Estándar por m³ (f'c = 210 kg/cm²):**\n"
            "- Cemento: 9.73 bolsas\n"
            "- Arena gruesa: 0.52 m³\n"
            "- Piedra chancada (1/2\"): 0.53 m³\n"
            "- Agua: 186 Litros"
        )
        bot.send_message(call.message.chat.id, info, parse_mode="Markdown")

@bot.message_handler(func=lambda message: True)
def procesar_metrado_profesional(message):
    try:
        datos = message.text.split()
        if len(datos) != 4:
            raise ValueError

        b, l, h, cant = float(datos[0]), float(datos[1]), float(datos[2]), int(datos[3])
        vol_unitario = b * l * h
        vol_total = vol_unitario * cant

        factor_desperdicio = 1.05
        cemento = vol_total * DOSIFICACION_210['cemento_bolsas'] * factor_desperdicio
        arena = vol_total * DOSIFICACION_210['arena_m3'] * factor_desperdicio
        piedra = vol_total * DOSIFICACION_210['piedra_m3'] * factor_desperdicio
        agua = vol_total * DOSIFICACION_210['agua_m3'] * 1000 * factor_desperdicio

        resumen_texto = (
            f"📄 **MEMORIA DE METRADO Y MATERIALES**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔹 **Elementos:** {cant} unidad(es)\n"
            f"🔹 **Sección:** {b:.2f} m × {l:.2f} m × {h:.2f} m\n"
            f"📦 **Volumen Total Concreto:** `{vol_total:.2f} m³`\n\n"
            f"🛠️ **Materiales Requeridos (+5% Desperdicio):**\n"
            f"• Cemento: `{cemento:.1f}` bolsas\n"
            f"• Arena Gruesa: `{arena:.2f}` m³\n"
            f"• Piedra Chancada 1/2\": `{piedra:.2f}` m³\n"
            f"• Agua: `{agua:.0f}` Litros"
        )

        bot.reply_to(message, resumen_texto, parse_mode="Markdown")

        img_buf = generar_grafico_materiales(cemento, arena, piedra)
        bot.send_photo(message.chat.id, photo=img_buf, caption="📊 Diagrama de insumos requeridos.")

    except Exception:
        bot.reply_to(
            message,
            "⚠️ Formato incorrecto. Debe enviar 4 valores separados por espacio:\n`Base Largo Altura Cantidad`\nEjemplo: `0.30 0.40 3.50 4`",
            parse_mode="Markdown"
        )

bot.infinity_polling()
