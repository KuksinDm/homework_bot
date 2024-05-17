import os
import sys
import time
import logging
import requests

from dotenv import load_dotenv
from telebot import TeleBot


load_dotenv()

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

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
        logger.debug('Сообщение успешно отправлено')
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
        if response.status_code != 200:
            error_message = (
                'Получен неправильный код состояния'
                f' от API: {response.status_code}'
            )
            logger.error(error_message)
            raise Exception(error_message)

        return response.json()
    except requests.RequestException as error:
        error_message = (
            'Произошла ошибка при обращении'
            f' к API: {response.status_code} {error}'
        )
        logger.error(error_message)
        raise Exception(error_message)


def check_response(response: dict[str, any]) -> bool:
    """Проверяет ответ API на соответствие документации."""
    if not isinstance(response, dict):
        error_message = ('Ответ должен быть словарем')
        logger.error(error_message)
        raise TypeError(error_message)

    if 'homeworks' not in response:
        error_message = ('Ответ API не содержит поле "homeworks"')
        logger.error(error_message)
        raise ValueError(error_message)

    if not isinstance(response['homeworks'], list):
        error_message = ('Поле "homeworks" должно быть списком')
        logger.error(error_message)
        raise TypeError(error_message)

    return True


def parse_status(homework: dict[str, any]) -> str:
    """Извлекает статус работы и возвращает соответствующий вердикт."""
    try:
        status = homework['status']
        homework_name = homework['homework_name']
    except KeyError as error:
        error_message = (
            f'Недостаточно информации для определения статуса работы {error}'
        )
        logger.error(error_message)
        raise ValueError(error_message)

    if status not in HOMEWORK_VERDICTS:
        error_message = ('Недокументированный статус работы')
        logger.error(error_message)
        raise ValueError(error_message)

    verdict = HOMEWORK_VERDICTS[status]
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main() -> None:
    """Основная логика работы бота."""
    check_tokens()

    # Создаем объект класса бота
    bot = TeleBot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())

    while True:
        try:
            api_response = get_api_answer(timestamp)
            check_response(api_response)
            homeworks = api_response.get('homeworks', [])
            status_message = "Новых домашних работ нет"
            if homeworks:
                status_message = parse_status(homeworks[0])
            send_message(bot, status_message)
            timestamp = api_response.get('current_date', timestamp)

        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            send_message(bot, message)
            logger.error(message)

        time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
