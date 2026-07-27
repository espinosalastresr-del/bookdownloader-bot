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

PORT = int(
    os.environ.get(
        "PORT",
        "10000"
    )
)


# ============================================================
# TELEGRAM BOT
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
# MEMORIA TEMPORAL
# ============================================================

# user_id -> {
#     md5 -> book
# }

user_searches = {}


# ============================================================
# START
# ============================================================

def start(message):

    bot.send_message(

        message["chat"]["id"],

        "📚 <b>Biblioteca Digital</b>\n\n"

        "Envíame el nombre del documento que deseas buscar.\n\n"

        "Ejemplo:\n"

        "<code>Python Programming</code>"

    )


# ============================================================
# HELP
# ============================================================

def help_command(message):

    bot.send_message(

        message["chat"]["id"],

        "📚 <b>Ayuda</b>\n\n"

        "Escribe el título o autor que quieres buscar.\n\n"

        "El bot mostrará los resultados disponibles."

    )


# ============================================================
# BÚSQUEDA
# ============================================================

def search(message):

    chat_id = message["chat"]["id"]

    user_id = message["from"]["id"]

    query = message.get(
        "text",
        ""
    ).strip()


    if not query:

        return


    msg = bot.send_message(

        chat_id,

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

                chat_id,

                msg.message_id

            )

            return


        # ====================================================
        # GUARDAR RESULTADOS
        # ====================================================

        user_searches[

            user_id

        ] = {

            book["md5"]: book

            for book in books

            if book.get("md5")

        }


        # ====================================================
        # ELIMINAR MENSAJE "BUSCANDO"
        # ====================================================

        try:

            bot.delete_message(

                chat_id,

                msg.message_id

            )

        except Exception:

            pass


        # ====================================================
        # MOSTRAR RESULTADOS
        # ====================================================

        for book in books[:10]:

            send_book(

                chat_id,

                book

            )


    except requests.RequestException as e:

        print(

            "SEARCH API ERROR:",

            repr(e),

            flush=True

        )


        try:

            bot.edit_message_text(

                "⚠️ No se pudo conectar con el servidor.",

                chat_id,

                msg.message_id

            )

        except Exception:

            pass


    except Exception as e:

        print(

            "SEARCH ERROR:",

            repr(e),

            flush=True

        )


        try:

            bot.edit_message_text(

                "⚠️ Error al realizar la búsqueda.",

                chat_id,

                msg.message_id

            )

        except Exception:

            pass


# ============================================================
# MOSTRAR RESULTADO
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


    # ========================================================
    # TEXTO
    # ========================================================

    text = (

        f"📚 <b>{title}</b>\n\n"

        f"👤 Autor: {author}\n"

        f"🏢 Editorial: {publisher}\n"

        f"📅 Año: {year}\n"

        f"🌐 Idioma: {language}\n"

        f"📄 Formato: {file_type}\n"

        f"💾 Tamaño: {size}"

    )


    # ========================================================
    # BOTÓN
    # ========================================================

    keyboard = (

        telebot.types.InlineKeyboardMarkup()

    )


    keyboard.add(

        telebot.types.InlineKeyboardButton(

            "⬇️ Descargar",

            callback_data=(

                f"download:{md5}"

            )

        )

    )


    # ========================================================
    # PORTADA
    # ========================================================

    cover = book.get(

        "cover"

    )


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

                "COVER ERROR:",

                repr(e),

                flush=True

            )


    # ========================================================
    # SIN PORTADA
    # ========================================================

    bot.send_message(

        chat_id,

        text,

        reply_markup=keyboard

    )


# ============================================================
# DESCARGA
# ============================================================

def download(
    callback
):

    user_id = (

        callback["from"]["id"]

    )


    chat_id = (

        callback["message"]["chat"]["id"]

    )


    message_id = (

        callback["message"]["message_id"]

    )


    data = callback.get(

        "data",

        ""

    )


    md5 = data.split(

        ":",

        1

    )[1]


    # ========================================================
    # RESPONDER AL CALLBACK
    # ========================================================

    bot.answer_callback_query(

        callback["id"],

        "⏳ Preparando descarga..."

    )


    # ========================================================
    # BUSCAR LIBRO
    # ========================================================

    book = (

        user_searches

        .get(

            user_id,

            {}

        )

        .get(

            md5

        )

    )


    if not book:

        bot.send_message(

            chat_id,

            "❌ El resultado ya no está disponible."

        )

        return


    title = book.get(

        "title",

        "Documento"

    )


    # ========================================================
    # ESTADO
    # ========================================================

    status = bot.send_message(

        chat_id,

        f"⬇️ Descargando:\n"

        f"<b>{title}</b>"

    )


    temp_path = None


    try:

        # ====================================================
        # SOLICITAR ARCHIVO
        # ====================================================

        response = requests.get(

            f"{API_URL}/download/{md5}",

            stream=True,

            timeout=300

        )


        response.raise_for_status()


        # ====================================================
        # NOMBRE DEL ARCHIVO
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

                filename = (

                    match.group(1)

                )


        # ====================================================
        # LIMPIAR NOMBRE
        # ====================================================

        filename = re.sub(

            r'[\\/*?:"<>|]',

            "_",

            filename

        )


        # ====================================================
        # ARCHIVO TEMPORAL
        # ====================================================

        temp = (

            tempfile.NamedTemporaryFile(

                delete=False,

                suffix="_download"

            )

        )


        temp_path = temp.name


        temp.close()


        # ====================================================
        # GUARDAR DESCARGA
        # ====================================================

        with open(

            temp_path,

            "wb"

        ) as file:

            for chunk in response.iter_content(

                chunk_size=8192

            ):

                if chunk:

                    file.write(

                        chunk

                    )


        # ====================================================
        # ENVIAR A TELEGRAM
        # ====================================================

        with open(

            temp_path,

            "rb"

        ) as file:

            bot.send_document(

                chat_id,

                file,

                visible_file_name=filename,

                caption=(

                    f"📚 {title}\n\n"

                    "✅ Descarga completada."

                )

            )


        # ====================================================
        # BORRAR TEMPORAL
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
        # BORRAR ESTADO
        # ====================================================

        try:

            bot.delete_message(

                chat_id,

                status.message_id

            )

        except Exception:

            pass


    except Exception as e:

        print(

            "DOWNLOAD ERROR:",

            repr(e),

            flush=True

        )


        # ====================================================
        # LIMPIAR TEMPORAL
        # ====================================================

        if (

            temp_path

            and

            os.path.exists(

                temp_path

            )

        ):

            try:

                os.remove(

                    temp_path

                )

            except Exception:

                pass


        # ====================================================
        # ERROR
        # ====================================================

        try:

            bot.edit_message_text(

                "❌ No se pudo completar la descarga.",

                chat_id,

                status.message_id

            )

        except Exception:

            pass


# ============================================================
# WEBHOOK
# ============================================================

@app.route(

    "/webhook",

    methods=["POST"]

)
def webhook():

    try:

        data = request.get_json(

            force=True

        )


        if not data:

            return (

                "Bad Request",

                400

            )


        print(

            "🔥 WEBHOOK RECIBIDO",

            flush=True

        )


        # ====================================================
        # MESSAGE
        # ====================================================

        if "message" in data:

            message = data["message"]


            text = message.get(

                "text",

                ""

            )


            print(

                f"💬 MESSAGE: {text}",

                flush=True

            )


            if text == "/start":

                start(

                    message

                )


            elif text == "/help":

                help_command(

                    message

                )


            elif text.startswith("/"):

                bot.send_message(

                    message["chat"]["id"],

                    "❓ Comando desconocido."

                )


            else:

                search(

                    message

                )


        # ====================================================
        # CALLBACK QUERY
        # ====================================================

        elif "callback_query" in data:

            callback = data[

                "callback_query"

            ]


            callback_data = callback.get(

                "data",

                ""

            )


            print(

                f"🔘 CALLBACK: {callback_data}",

                flush=True

            )


            if callback_data.startswith(

                "download:"

            ):

                download(

                    callback

                )


        return (

            "OK",

            200

        )


    except Exception as e:

        print(

            "❌ WEBHOOK ERROR:",

            repr(e),

            flush=True

        )


        return (

            "ERROR",

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

        "service": "telegram-bot",

        "webhook": "active"

    }


# ============================================================
# EJECUCIÓN LOCAL
# ============================================================

if __name__ == "__main__":

    print(

        "🚀 Bot iniciado con Flask Webhook",

        flush=True

    )


    app.run(

        host="0.0.0.0",

        port=PORT

    )