cat << 'EOF' > /sdcard/Download/main.py
import telebot
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

TOKEN = "8978402989:AAEcJEXuFFHQImwQVJph58ZmZpMpn7xSfqk"
bot = telebot.TeleBot(TOKEN)

class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot activo 24/7")

def run_http_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), SimpleHTTPRequestHandler)
    server.serve_forever()

threading.Thread(target=run_http_server, daemon=True).start()

def calcular_concreto(b, l, h):
    v = b * l * h
    return f"📐 **Metrado de Concreto:**\n- Base: {b} m\n- Largo: {l} m\n- Altura: {h} m\n\n✅ **Total:** {v:.2f} m³"

@bot.message_handler(commands=['start', 'help'])
def enviar_bienvenida(message):
    mensaje = (
        "¡Hola! Soy tu calculadora de concreto.\n\n"
        "Envíame las 3 medidas separadas por un espacio:\n"
        "`Base Largo Altura`\n\n"
        "Ejemplo: `0.30 0.40 3.00`"
    )
    bot.reply_to(message, mensaje, parse_mode="Markdown")

@bot.message_handler(func=lambda message: True)
def procesar_calculo(message):
    try:
        datos = message.text.split()
        b = float(datos[0])
        l = float(datos[1])
        h = float(datos[2])
        respuesta = calcular_concreto(b, l, h)
        bot.reply_to(message, respuesta, parse_mode="Markdown")
    except Exception:
        bot.reply_to(
            message, 
            "⚠️ Por favor envía exactamente 3 números separados por espacio.\nEjemplo: `0.30 0.40 3.00`",
            parse_mode="Markdown"
        )

bot.infinity_polling()
EOF
