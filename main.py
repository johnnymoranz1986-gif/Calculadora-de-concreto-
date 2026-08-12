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

# --- SERVIDOR HTTP (PARA RENDER/KEEP-ALIVE) ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()

def run_health_check_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    server.serve_forever()

threading.Thread(target=run_health_check_server, daemon=True).start()

# --- CONFIGURACION BOT ---
TOKEN = os.environ.get("BOT_TOKEN", "8978402989:AAH5pIvfI_76cePT7PY6pziMkVLcoN2kxL8")
bot = telebot.TeleBot(TOKEN, parse_mode=None)

# --- DATOS LIBRERIA MORALES ---
def obtener_ejemplo_morales(nombre):
    ejemplos = {
        "viga-simple": [25, 50, 210, 4200, 12, 8],
        "viga-doble": [30, 60, 210, 4200, 35, 15],
        "viga-confinada": [30, 70, 280, 4200, 25, 25]
    }
    return ejemplos.get(nombre, [])

DOSIFICACIONES = {
    '140': {'cemento': 7.01, 'arena': 0.51, 'piedra': 0.64, 'agua': 0.184},
    '175': {'cemento': 8.43, 'arena': 0.54, 'piedra': 0.55, 'agua': 0.185},
    '210': {'cemento': 9.73, 'arena': 0.52, 'piedra': 0.53, 'agua': 0.186},
    '280': {'cemento': 13.34, 'arena': 0.45, 'piedra': 0.51, 'agua': 0.189},
    '350': {'cemento': 15.80, 'arena': 0.43, 'piedra': 0.50, 'agua': 0.190},
    '450': {'cemento': 18.50, 'arena': 0.40, 'piedra': 0.48, 'agua': 0.195}
}

user_state = {}

# --- FUNCIONES GRAFICAS ---
def generar_grafico_viga(b, h, As, As_comp, s_estribo):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 5))
    ax1.set_title(f"Seccion {b:.0f}x{h:.0f} cm", fontsize=10, fontweight='bold')
    rec = 4.0
    ax1.add_patch(patches.Rectangle((0,0), b, h, edgecolor='black', facecolor='#e0e0e0', linewidth=2))
    ax1.add_patch(patches.Rectangle((rec,rec), b-2*rec, h-2*rec, edgecolor='blue', fill=False, linestyle='--'))
    ax1.scatter([b/4, b/2, 3*b/4], [rec, rec, rec], color='red', s=60, label=f"As: {As:.2f}cm2")
    if As_comp > 0: ax1.scatter([b/3, 2*b/3], [h-rec, h-rec], color='green', s=60, label=f"As': {As_comp:.2f}cm2")
    ax1.set_xlim(-5, b+5); ax1.set_ylim(-5, h+5); ax1.set_aspect('equal'); ax1.legend(loc='upper right', fontsize=8)
    
    ax2.set_title("Distribucion Estribos", fontsize=10, fontweight='bold')
    ax2.plot([0, 300], [0, 0], 'k', linewidth=4); ax2.plot([0, 300], [h, h], 'k', linewidth=4)
    ax2.axvspan(0, 60, color='yellow', alpha=0.3); ax2.axvspan(240, 300, color='yellow', alpha=0.3)
    ax2.text(150, h/2, f"Centro: c/ {s_estribo:.0f} cm", ha='center', fontsize=9, fontweight='bold')
    plt.tight_layout()
    plt.savefig("viga.png", dpi=100); plt.close()
    return "viga.png"

# --- MANEJADORES ---
@bot.message_handler(commands=['start', 'menu'])
def enviar_bienvenida(message):
    bot.reply_to(message, "¡Hola! Sistema estructural activo.\nEnvía los datos así: [b] [h] [f'c] [fy] [Mu] [Vu]\nO escribe /morales para ver los ejemplos.")

@bot.message_handler(commands=['morales'])
def comando_morales(message):
    bot.reply_to(message, "Ejemplos del libro de Morales:\n/test_viga_simple\n/test_viga_doble\n/test_viga_confinada")

@bot.message_handler(commands=['test_viga_simple', 'test_viga_doble', 'test_viga_confinada'])
def test_ejemplo(message):
    nombre = message.text.replace("/", "").replace("test_", "")
    valores = obtener_ejemplo_morales(nombre.replace("_", "-"))
    if valores:
        message.text = " ".join(map(str, valores))
        procesar_mensajes(message)

@bot.message_handler(func=lambda message: True)
def procesar_mensajes(message):
    try:
        valores = [float(x) for x in message.text.strip().replace(',', '.').split()]
        if len(valores) == 6:
            b, h, fc, fy, Mu, Vu = valores
            d = h - 6.0
            as_min = max((0.7*math.sqrt(fc)/fy)*b*d, (14/fy)*b*d)
            As_req = max((Mu*100000)/(0.9*fy*(d-5)), as_min)
            s = min(d/2, 30.0)
            
            resumen = f"CALCULO ESTRUCTURAL\nAs: {As_req:.2f} cm2\nEstribos zona central: c/ {s:.1f} cm"
            bot.reply_to(message, resumen)
            
            ruta = generar_grafico_viga(b, h, As_req, 0, s)
            with open(ruta, 'rb') as f:
                bot.send_photo(message.chat.id, f)
        else:
            bot.reply_to(message, "Formato incorrecto. Envíalo así: [b] [h] [f'c] [fy] [Mu] [Vu]")
    except Exception as e:
        bot.reply_to(message, f"Error en el cálculo: {e}")

if __name__ == '__main__':
    bot.polling(none_stop=True)
