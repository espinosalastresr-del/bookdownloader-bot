import os
import requests
import telebot


BOT_TOKEN = os.environ["BOT_TOKEN"]

API_URL = os.environ["API_URL"].rstrip("/")


bot = telebot.TeleBot(
    BOT_TOKEN,
    parse_mode="HTML"
)


user_searches = {}


@bot.message_handler(commands=["start"])
def start(message):

    bot.send_message(

        message.chat.id,

        "📚 <b>Biblioteca Digital</b>\n\n"

        "Envíame el nombre del documento que deseas buscar.\n\n"

        "Ejemplo:\n"

        "<code>Python Programming</code>"

    )



@bot.message_handler(commands=["help"])
def help_command(message):

    bot.send_message(

        message.chat.id,

        "📚 <b>Ayuda</b>\n\n"

        "Escribe el título o autor que quieres buscar.\n\n"

        "El bot mostrará los resultados disponibles."

    )



@bot.message_handler(
    func=lambda message: True
)
def search(message):

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


        user_searches[
            message.from_user.id
        ] = {

            book["md5"]: book

            for book in books

        }


        bot.delete_message(

            message.chat.id,

            msg.message_id

        )


        for book in books[:10]:

            send_book(

                message.chat.id,

                book

            )


    except Exception as e:

        print(e)


        bot.edit_message_text(

            "⚠️ Error al realizar la búsqueda.",

            message.chat.id,

            msg.message_id

        )



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


    md5 = book["md5"]


    text = (

        f"📚 <b>{title}</b>\n\n"

        f"👤 Autor: {author}\n"

        f"🏢 Editorial: {publisher}\n"

        f"📅 Año: {year}\n"

        f"🌐 Idioma: {language}\n"

        f"📄 Formato: {file_type}\n"

        f"💾 Tamaño: {size}"

    )


    keyboard = telebot.types.InlineKeyboardMarkup()


    keyboard.add(

        telebot.types.InlineKeyboardButton(

            "⬇️ Descargar",

            callback_data=f"download:{md5}"

        )

    )


    cover = book.get(
        "cover"
    )


    if cover:

        if cover.startswith("/"):

            cover = API_URL + cover


        try:

            bot.send_photo(

                chat_id,

                cover,

                caption=text,

                reply_markup=keyboard

            )

            return

        except Exception as e:

            print(e)


    bot.send_message(

        chat_id,

        text,

        reply_markup=keyboard

    )



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


    book = user_searches.get(

        call.from_user.id,

        {}

    ).get(md5)


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


    status = bot.send_message(

        call.message.chat.id,

        f"⬇️ Descargando:\n<b>{title}</b>"

    )


    try:

        response = requests.get(

            f"{API_URL}/download/{md5}",

            stream=True,

            timeout=300

        )


        response.raise_for_status()


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

            import re


            match = re.search(

                r'filename="?([^"]+)"?',

                content_disposition

            )


            if match:

                filename = match.group(1)


        temp_path = (

            f"/tmp/{call.from_user.id}_"

            f"{filename}"

        )


        with open(

            temp_path,

            "wb"

        ) as file:

            for chunk in response.iter_content(

                chunk_size=8192

            ):

                if chunk:

                    file.write(chunk)


        with open(

            temp_path,

            "rb"

        ) as file:

            bot.send_document(

                call.message.chat.id,

                file,

                caption=(

                    f"📚 {title}\n\n"

                    "✅ Descarga completada."

                )

            )


        os.remove(

            temp_path

        )


        bot.delete_message(

            call.message.chat.id,

            status.message_id

        )


    except Exception as e:

        print(e)


        bot.edit_message_text(

            "❌ No se pudo descargar el documento.",

            call.message.chat.id,

            status.message_id

        )



if __name__ == "__main__":

    print(

        "Bot iniciado..."

    )


    bot.infinity_polling(
        skip_pending=True
    )
