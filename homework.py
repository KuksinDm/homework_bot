import os
import sys
import time
import logging
import requests
from http import HTTPStatus
from urllib.parse import unquote
from json.decoder import JSONDecodeError

from requests import RequestException
from dotenv import load_dotenv
from telebot import TeleBot

from exceptions import ResponseStatusError


load_dotenv()

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
START_OFFSET = 300
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}
# хотел вынести в отдельный фаил, но тесты не дали
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s, %(levelname)s, %(message)s',
    handlers=[
        logging.FileHandler('my_logger.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def check_tokens() -> bool:
    """Функция проверяет наличие токенов."""
    required_tokens = {
        'PRACTICUM_TOKEN': PRACTICUM_TOKEN,
        'TELEGRAM_TOKEN': TELEGRAM_TOKEN,
        'TELEGRAM_CHAT_ID': TELEGRAM_CHAT_ID
    }
    missing_tokens = [
        name for name, token in required_tokens.items() if not token
    ]
    if missing_tokens:
        for token in missing_tokens:
            logger.critical(
                f'Отсутствует необходимая переменная окружения: {token}'
            )
            sys.exit()


def send_message(bot: TeleBot, message: str) -> None:
    """Отправка сообщений ботом."""
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        logger.debug(f'Сообщение успешно отправлено: {unquote(message)}')
    except Exception as error:
        logger.error(f'Ошибка при отправке сообщения: {error}')


def get_api_answer(timestamp: int) -> dict[str, any]:
    """Получение ответа от API."""
    payload = {'from_date': timestamp}
    try:
        response = requests.get(
            ENDPOINT,
            headers=HEADERS,
            params=payload
        )
        response.raise_for_status()

    except RequestException as error:
        error_message = (
            'Произошла ошибка при обращении'
            f' к API: {response.status_code} {error}'
        )
        raise RequestException(error_message)

    if response.status_code != HTTPStatus.OK:
        error_message = (
            'Получен неправильный код состояния'
            f' от API: {response.status_code}'
        )
        # сделал кастомный класс исключения, не знаю когда лучше использовать
        # кастомные, а когда базовые
        raise ResponseStatusError(error_message)

    try:
        return response.json()
    except JSONDecodeError as json_error:
        error_message = (
            'Ошибка декодирования JSON ответа от API:'
            f' {json_error}'
        )
        raise JSONDecodeError(error_message)


def check_response(response: dict[str, any]) -> bool:
    """Проверяет ответ API на соответствие документации."""
    if not isinstance(response, dict):
        error_message = ('Ответ должен быть словарем')
        raise TypeError(error_message)

    if 'homeworks' not in response:
        error_message = ('Ответ API не содержит поле "homeworks"')
        raise ValueError(error_message)

    if not isinstance(response['homeworks'], list):
        error_message = ('Поле "homeworks" должно быть списком')
        raise TypeError(error_message)

    return response['homeworks']


def parse_status(homework: dict[str, any]) -> str:
    """Извлекает статус работы и возвращает соответствующий вердикт."""
    status = homework.get('status')
    homework_name = homework.get('homework_name')

    if status is None or homework_name is None:
        error_message = (
            "Недостаточно информации для определения статуса работы"
        )
        raise ValueError(error_message)

    if status not in HOMEWORK_VERDICTS:
        error_message = ('Недокументированный статус работы')
        raise ValueError(error_message)

    return (
        f'Изменился статус проверки работы "{homework_name}"'
        f'. {HOMEWORK_VERDICTS[status]}')


class ErrorHandler:
    """Класс для отслеживания последней ошибки."""

    def __init__(self, bot):
        """Конструктор класса."""
        self.last_error_message = None
        self.bot = bot

    def handle_error(self, error_message):
        """Обработка ошибки."""
        if self.last_error_message != error_message:
            send_message(self.bot, error_message)
            self.last_error_message = error_message
    
    def reset_last_error(self):
        """Сброс последней ошибки."""
        self.last_error_message = None


def main() -> None:
    """Основная логика работы бота."""
    check_tokens()

    # Создаем объект класса бота
    bot = TeleBot(token=TELEGRAM_TOKEN)
    error_handler = ErrorHandler(bot)
    timestamp = int(time.time()) - START_OFFSET

    while True:
        try:
            api_response = get_api_answer(timestamp)
            homeworks = check_response(api_response)

            if homeworks:
                status_message = parse_status(homeworks[0])
                send_message(bot, status_message)
                error_handler.reset_last_error()
                timestamp = api_response.get('current_date', timestamp)
            else:
                logger.debug("Новых проверок домашних работ - нет.")

        except Exception as error:
            error_message = f'Сбой в работе программы: {error}'
            logger.error(error_message)
            error_handler.handle_error(error_message)

        time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
