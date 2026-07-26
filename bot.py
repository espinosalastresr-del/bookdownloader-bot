import os
import re
import tempfile

import requests
import telebot

from flask import Flask, request


# ============================================================
# CONFIGURACIÓN
# ============================================================

BOT_TOKEN = os.environ.get(
    "BOT_TOKEN",
    "8867573523:AAE0SOGYlOqlSq5odJD2Cnyp7cLiTwm6Rmw"
)

API_URL = os.environ.get(
    "API_URL",
    "https://bookdownloader-api.onrender.com/"
).rstrip("/")

# Render asigna automáticamente la variable PORT
PORT = int(
    os.environ.get(
        "PORT",
        "10000"
    )
)

# URL pública del Web Service de Render.
#
# Ejemplo:
# https://bookdownloader-bot.onrender.com
#
WEBHOOK_URL = os.environ.get(
    "WEBHOOK_URL",
    "https://bookdownloader-bot.onrender.com"
).rstrip("/")


# Ruta privada del webhook.
# Telegram enviará los updates aquí.
WEBHOOK_PATH = f"/webhook"


# ============================================================
# BOT
# ============================================================

bot = telebot.TeleBot(
    BOT_TOKEN,
    parse_mode="HTML"
)


# ============================================================
# FLASK
# ============================================================

app = Flask(__name__)


# ============================================================
# MEMORIA DE BÚSQUEDAS
# ============================================================

user_searches = {}


# ============================================================
# /START
# ============================================================

@bot.message_handler(
    commands=["start"]
)
def start(message):

    bot.send_message(

        message.chat.id,

        "📚 <b>Biblioteca Digital</b>\n\n"

        "Envíame el nombre del documento que deseas buscar.\n\n"

        "Ejemplo:\n"

        "<code>Python Programming</code>"

    )


# ============================================================
# /HELP
# ============================================================

@bot.message_handler(
    commands=["help"]
)
def help_command(message):

    bot.send_message(

        message.chat.id,

        "📚 <b>Ayuda</b>\n\n"

        "Escribe el título o autor que quieres buscar.\n\n"

        "El bot mostrará los resultados disponibles."

    )


# ============================================================
# BÚSQUEDA
# ============================================================

@bot.message_handler(
    func=lambda message: True
)
def search(message):

    # Evitar errores cuando el mensaje no tiene texto
    if not message.text:

        return


    query = message.text.strip()


    if not query:

        return


    msg = bot.send_message(

        message.chat.id,

        "🔎 Buscando..."

    )


    try:

        response = requests.get(

            f"{API_URL}/search",

            params={
                "q": query
            },

            timeout=60

        )


        response.raise_for_status()


        data = response.json()


        books = data.get(
            "books",
            []
        )


        if not books:

            bot.edit_message_text(

                "❌ No se encontraron resultados.",

                message.chat.id,

                msg.message_id

            )

            return


        # Guardar resultados de la búsqueda
        user_searches[
            message.from_user.id
        ] = {

            book["md5"]: book

            for book in books

            if book.get("md5")

        }


        bot.delete_message(

            message.chat.id,

            msg.message_id

        )


        # Mostrar máximo 10 resultados
        for book in books[:10]:

            send_book(

                message.chat.id,

                book

            )


    except requests.RequestException as e:

        print(

            f"API ERROR: {e}"

        )


        bot.edit_message_text(

            "⚠️ No se pudo conectar con el servidor.",

            message.chat.id,

            msg.message_id

        )


    except Exception as e:

        print(

            f"SEARCH ERROR: {e}"

        )


        bot.edit_message_text(

            "⚠️ Error al realizar la búsqueda.",

            message.chat.id,

            msg.message_id

        )


# ============================================================
# MOSTRAR LIBRO
# ============================================================

def send_book(
    chat_id,
    book
):

    title = book.get(
        "title",
        "Sin título"
    )


    author = book.get(
        "author",
        "Desconocido"
    )


    publisher = book.get(
        "publisher",
        "Desconocido"
    )


    year = book.get(
        "year",
        "N/A"
    )


    language = book.get(
        "language",
        "N/A"
    )


    file_type = book.get(
        "file_type",
        "N/A"
    )


    size = book.get(
        "size",
        "N/A"
    )


    md5 = book.get(
        "md5"
    )


    if not md5:

        return


    text = (

        f"📚 <b>{title}</b>\n\n"

        f"👤 Autor: {author}\n"

        f"🏢 Editorial: {publisher}\n"

        f"📅 Año: {year}\n"

        f"🌐 Idioma: {language}\n"

        f"📄 Formato: {file_type}\n"

        f"💾 Tamaño: {size}"

    )


    keyboard = (
        telebot.types.InlineKeyboardMarkup()
    )


    keyboard.add(

        telebot.types.InlineKeyboardButton(

            "⬇️ Descargar",

            callback_data=f"download:{md5}"

        )

    )


    cover = book.get(
        "cover"
    )


    # ========================================================
    # PORTADA
    # ========================================================

    if cover:

        if cover.startswith("/"):

            cover = (

                API_URL

                + cover

            )


        try:

            bot.send_photo(

                chat_id,

                cover,

                caption=text,

                reply_markup=keyboard

            )

            return


        except Exception as e:

            print(

                f"COVER ERROR: {e}"

            )


    # ========================================================
    # SI NO HAY PORTADA
    # ========================================================

    bot.send_message(

        chat_id,

        text,

        reply_markup=keyboard

    )


# ============================================================
# CALLBACK DE DESCARGA
# ============================================================

@bot.callback_query_handler(

    func=lambda call:

        call.data.startswith(

            "download:"

        )

)
def download(call):

    md5 = call.data.split(

        ":",

        1

    )[1]


    bot.answer_callback_query(

        call.id,

        "⏳ Preparando descarga..."

    )


    # ========================================================
    # RECUPERAR LIBRO
    # ========================================================

    book = user_searches.get(

        call.from_user.id,

        {}

    ).get(

        md5

    )


    if not book:

        bot.send_message(

            call.message.chat.id,

            "❌ El resultado ya no está disponible."

        )

        return


    title = book.get(

        "title",

        "Documento"

    )


    # ========================================================
    # MENSAJE DE ESTADO
    # ========================================================

    status = bot.send_message(

        call.message.chat.id,

        f"⬇️ Descargando:\n<b>{title}</b>"

    )


    temp_path = None


    try:

        # ====================================================
        # SOLICITAR ARCHIVO A LA API
        # ====================================================

        response = requests.get(

            f"{API_URL}/download/{md5}",

            stream=True,

            timeout=300

        )


        response.raise_for_status()


        # ====================================================
        # DETERMINAR NOMBRE DEL ARCHIVO
        # ====================================================

        filename = (

            title

            + "."

            + book.get(

                "file_type",

                "bin"

            )

        )


        content_disposition = (

            response.headers.get(

                "Content-Disposition"

            )

        )


        if content_disposition:

            match = re.search(

                r'filename="?([^"]+)"?',

                content_disposition

            )


            if match:

                filename = match.group(1)


        # Evitar caracteres inválidos
        filename = re.sub(

            r'[\\/*?:"<>|]',

            "_",

            filename

        )


        # ====================================================
        # CREAR ARCHIVO TEMPORAL
        # ====================================================

        temp = tempfile.NamedTemporaryFile(

            delete=False,

            prefix=(

                f"{call.from_user.id}_"

            ),

            suffix="_download"

        )


        temp_path = temp.name


        temp.close()


        # ====================================================
        # GUARDAR STREAM
        # ====================================================

        with open(

            temp_path,

            "wb"

        ) as file:

            for chunk in response.iter_content(

                chunk_size=8192

            ):

                if chunk:

                    file.write(chunk)


        # ====================================================
        # ENVIAR A TELEGRAM
        # ====================================================

        with open(

            temp_path,

            "rb"

        ) as file:

            bot.send_document(

                call.message.chat.id,

                file,

                visible_file_name=filename,

                caption=(

                    f"📚 {title}\n\n"

                    "✅ Descarga completada."

                )

            )


        # ====================================================
        # ELIMINAR ARCHIVO TEMPORAL
        # ====================================================

        if (

            temp_path

            and

            os.path.exists(

                temp_path

            )

        ):

            os.remove(

                temp_path

            )


        # ====================================================
        # ELIMINAR MENSAJE DE ESTADO
        # ====================================================

        bot.delete_message(

            call.message.chat.id,

            status.message_id

        )


    except requests.RequestException as e:

        print(

            f"DOWNLOAD API ERROR: {e}"

        )


        if (

            temp_path

            and

            os.path.exists(

                temp_path

            )

        ):

            os.remove(

                temp_path

            )


        bot.edit_message_text(

            "❌ No se pudo obtener el archivo desde la API.",

            call.message.chat.id,

            status.message_id

        )


    except Exception as e:

        print(

            f"DOWNLOAD ERROR: {e}"

        )


        if (

            temp_path

            and

            os.path.exists(

                temp_path

            )

        ):

            os.remove(

                temp_path

            )


        try:

            bot.edit_message_text(

                "❌ No se pudo completar la descarga.",

                call.message.chat.id,

                status.message_id

            )

        except Exception:

            pass


# ============================================================
# WEBHOOK
# ============================================================

@app.route("/webhook", methods=["POST"])
def webhook():

    print("🔥 WEBHOOK RECIBIDO", flush=True)

    try:

        json_string = request.get_data().decode("utf-8")

        print(
            "📩 UPDATE RECIBIDO:",
            json_string,
            flush=True
        )

        update = telebot.types.Update.de_json(
            json_string
        )

        print(
            "🔄 PROCESANDO UPDATE...",
            flush=True
        )

        bot.process_new_updates(
            [update]
        )

        print(
            "✅ UPDATE PROCESADO",
            flush=True
        )

        return "", 200

    except Exception as e:

        print(
            "❌ WEBHOOK ERROR:",
            repr(e),
            flush=True
        )

        return (
            "Webhook error",
            500
        )

# ============================================================
# HEALTH CHECK
# ============================================================

@app.route(

    "/",

    methods=["GET"]

)
def health():

    return {

        "status": "ok",

        "service": "telegram-bot"

    }


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    print(
        "Bot iniciado mediante webhook."
    )

    app.run(
        host="0.0.0.0",
        port=PORT
    )