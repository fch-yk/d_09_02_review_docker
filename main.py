import contextlib
import logging
import textwrap
import time

import requests
import telegram
from environs import Env

logger = logging.getLogger(__file__)


class TelegramLogsHandler(logging.Handler):

    def __init__(self, logs_bot_token, chat_id):
        super().__init__()
        self.chat_id = chat_id
        self.tg_bot = telegram.Bot(token=logs_bot_token)
        self.setFormatter(
            logging.Formatter(
                fmt=(
                    '%(process)d %(levelname)s %(message)s %(asctime)s'
                    '  %(filename)s'
                )
            )
        )

    def emit(self, record):
        log_entry = self.format(record)
        max_tg_message_size = 4096
        msg_texts = textwrap.wrap(log_entry, max_tg_message_size)
        for msg_text in msg_texts:
            self.tg_bot.send_message(chat_id=self.chat_id, text=msg_text)


def send_review_message(review_bot, chat_id, new_attempt):
    lesson_title = new_attempt["lesson_title"]
    lesson_url = new_attempt["lesson_url"]
    work = ("The teacher reviewed your work "
            f"[\"{lesson_title}\"\\.]({lesson_url})"
            )
    result = (
        "The teacher liked everything, "
        "you can proceed to the next lesson\\!"
    )
    if new_attempt["is_negative"]:
        result = "Unfortunately, there were errors in your work\\."

    review_bot.send_message(
        text=f"{work}\n{result}",
        chat_id=chat_id,
        parse_mode=telegram.ParseMode.MARKDOWN_V2
    )


def main():
    env = Env()
    env.read_env()
    devman_token = env("DEVMAN_TOKEN")
    review_bot_token = env("REVIEW_BOT_TOKEN")
    chat_id = env("TELEGRAM_USER_ID")
    timeout = env.int("REVIEW_REQUEST_TIMEOUT", 100)

    logging.basicConfig()
    logs_handler = TelegramLogsHandler(
        logs_bot_token=env('REVIEW_LOGS_BOT_TOKEN'),
        chat_id=chat_id,
    )

    logger.addHandler(logs_handler)
    logger.setLevel(
        logging.DEBUG if env.bool("DEBUG_MODE", False) else logging.INFO
    )

    url = "https://dvmn.org/api/long_polling/"
    headers = {"Authorization": f"Token {devman_token}"}
    timestamp = None
    review_bot = None
    review_bot = telegram.Bot(token=review_bot_token)
    logger.info('Review bot started')
    last_error_type = None
    while True:
        try:
            payload = {"timestamp": timestamp}
            response = requests.get(
                url,
                headers=headers,
                params=payload,
                timeout=timeout
            )
            response.raise_for_status()
            reviews = response.json()
            logger.debug("The response: %s", reviews)
            if reviews["status"] == "found":
                for new_attempt in reviews["new_attempts"]:
                    send_review_message(review_bot, chat_id, new_attempt)

                timestamp = reviews["last_attempt_timestamp"]
            else:
                timestamp = reviews["timestamp_to_request"]

            logger.debug("timestamp for the next request: %s", timestamp)
            last_error_type = None
        except (
            requests.exceptions.ConnectionError,
            telegram.error.NetworkError
        ) as error:
            error_type = type(error)
            if last_error_type != error_type:
                logging.error('Connection error %s', error_type)
            last_error_type = error_type
            time.sleep(10)
        except Exception as error:
            error_type = type(error)
            if last_error_type != error_type:
                logger.exception(
                    'Review bot failed: %s %s',
                    error_type,
                    error
                )
            last_error_type = error_type
            time.sleep(10)


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        main()
