# Author: Prashant Srivastava
import json
import logging
import os
import sys

from telegram import __version__ as TG_VER

# Get the current directory
current_directory = os.path.dirname(os.path.abspath(__file__))
# Get the parent directory
parent_directory = os.path.dirname(current_directory)
# Add the parent directory to sys.path temporarily
sys.path.append(parent_directory)

from clients.client_5paisa import Client

try:
    from telegram import __version_info__
except ImportError:
    __version_info__ = (0, 0, 0, 0, 0)  # type: ignore[assignment]

if __version_info__ < (20, 0, 0, "alpha", 5):
    raise RuntimeError(
        f"This is not compatible with current PTB version {TG_VER}. To view the "
        f"{TG_VER} version of this example, "
        f"visit https://docs.python-telegram-bot.org/en/v{TG_VER}/examples.html"
    )

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    InvalidCallbackData,
    filters,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
# set higher logging level for httpx to avoid all GET and POST requests being logged
logging.getLogger("httpx").setLevel(logging.WARNING)

## read API_TOKEN from file creds.json
with open("../creds.json") as cred_fh:
    cred = json.load(cred_fh)
API_TOKEN = cred["telegram_token"]
client = Client(cred_file="../creds.json")
client.login()


def get_update_from_client():
    tags = client.get_todays_tags()
    order_book = client.order_book()
    info = ""
    for item in order_book:
        if item["RemoteOrderID"] in tags:
            ## Format like this: BUY 1 lot of NIFTY 12000 PE @ 100 x 75
            buysell = "Sold" if  item["BuySell"] == "S" else "Brought"
            name = item["ScripName"]
            avg_price = round(item["AveragePrice"], 2)
            quantity = item["Qty"]
            info += f"{buysell}\n\t| {name} |x{quantity} @ {avg_price} INR\n"
    return info


async def send_updates(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Replace these with actual updates from client - sample only
    info = get_update_from_client()
    overall_pnl_button = InlineKeyboardButton(
        "Overall PnL", callback_data="overall_pnl"
    )
    individual_pnl_button = InlineKeyboardButton(
        "Individual PnL", callback_data="individual_pnl"
    )
    keyboard = [[overall_pnl_button, individual_pnl_button]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "Recent Updates:\n\n" + info,
        reply_markup=reply_markup,
    )


async def button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query.data == "overall_pnl":
        total_pnl, _ = get_pnl_text()
        await query.answer(text="Fetching overall PnL...")
        # Replace with actual overall PnL calculation and send the result
        await context.bot.send_message(
            chat_id=query.message.chat_id, text="Overall PnL: %.2f INR " % total_pnl
        )
    elif query.data == "individual_pnl":
        _, individual_pnl = get_pnl_text()
        await query.answer(text="Fetching individual PnL...")
        # Replace with actual individual PnL calculation and send the result
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="Individual Legs\n%s" % individual_pnl,
        )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Welcome to Option Strategies Algo Bot!",
    )
    """Add a job to the queue."""
    chat_id = update.effective_message.chat_id
    try:
        interval_duration = float(context.args[0])
        if interval_duration < 5:
            await update.effective_message.reply_text(
                "Interval should be atleast 5 seconds."
            )
            return
        job_removed = remove_job_if_exists(str(chat_id), context)
        context.job_queue.run_repeating(
            send_pnl_update,
            interval=interval_duration,
            chat_id=chat_id,
            name=str(chat_id),
        )
        text = "Pnl Updates subscribed for {} seconds.".format(interval_duration)
        if job_removed:
            text += " Old one was removed."
        await update.effective_message.reply_text(text)

    except (IndexError, ValueError):
        await update.effective_message.reply_text(
            "Usage: /start <interval in seconds> <tag>"
        )


async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Sorry, I didn't understand that command.",
    )


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Remove the job if the user changed their mind."""
    chat_id = update.message.chat_id
    job_removed = remove_job_if_exists(str(chat_id), context)
    text = (
        "PnL updates successfully cancelled!"
        if job_removed
        else "You have no pnl updates subscription."
    )
    await update.message.reply_text(text)


async def handle_invalid_button(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    await update.callback_query.answer()
    await update.effective_message.edit_text(
        "Sorry, I could not process this button click 😕 Please send /start to get a new keyboard."
    )


def get_pnl_text():
    positions = client.get_pnl_summary()
    total = 0.0
    individual_pnl = ""
    if positions:
        for item in positions:
            individual_pnl += "%s : %.2f INR\n" % (item["ScripName"], item["Pnl"])
            total += item["Pnl"]
    total_pnl = round(total, 2)
    return total_pnl, individual_pnl


async def send_pnl_update(context: ContextTypes.DEFAULT_TYPE) -> None:
    # Replace with actual PnL calculations from client
    job = context.job
    total_pnl, individual_pnl = get_pnl_text()
    pnl_message = (
        f"Overall MTM: {total_pnl} INR\nIndividual Legs MTM:\n{individual_pnl}"
    )
    await context.bot.send_message(job.chat_id, text=pnl_message)


def remove_job_if_exists(name: str, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Remove job with given name. Returns whether job was removed."""
    current_jobs = context.job_queue.get_jobs_by_name(name)
    if not current_jobs:
        return False
    for job in current_jobs:
        job.schedule_removal()
    return True


if __name__ == "__main__":
    application = ApplicationBuilder().token(API_TOKEN).build()

    application.add_handler(CommandHandler(["start", "help"], start))
    application.add_handler(CommandHandler("updates", send_updates))
    application.add_handler(CommandHandler("stop_updates", stop))
    application.add_handler(MessageHandler(filters.COMMAND, unknown))
    application.add_handler(CallbackQueryHandler(button))
    application.add_handler(
        CallbackQueryHandler(handle_invalid_button, pattern=InvalidCallbackData)
    )

    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)
