import telebot

TOKEN = "8978402989:AAEcJEXuFFHQImwQVJph58ZmZpMpn7xSfqk"
bot = telebot.TeleBot(TOKEN)

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
