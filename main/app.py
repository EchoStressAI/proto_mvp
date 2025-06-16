import pika
import json
import time
import os
import logging
import numpy as np
from openai import OpenAI
from gigachat import GigaChat
from gigachat.models import Chat, Messages, MessagesRole
import requests

# Читаем переменные окружения
LLM_MAX_NEW_TOKEN = os.getenv("LLM_MAX_NEW_TOKEN", "100")
LLM_NAME = os.getenv("LLM_NAME", "gigachat")
LLM_TEMPERATURE = os.getenv("LLM_TEMPERATURE", "0.7")
LLM_ADRESS = os.getenv("LLM_TEMPERATURE", "http://llamaserver:8000/v1.7")

# Читаем API ключ из файла секрета
with open("/run/secrets/llm_api_key", "r") as f:
    LLM_APIKEY = f.read().strip()
if not LLM_APIKEY:
    LLM_APIKEY = 'notneeded'

EXCHANGE = 'main'
EXCHANGE_IN = 'text'
EXCHANGE_IN_AUTH = 'auth'

logging.basicConfig(level=logging.INFO,    
                    format='%(asctime)s - %(levelname)s - %(module)s - %(message)s'
                    )

# Создаём подключение по адресу rabbitmq:
connection = pika.BlockingConnection(pika.ConnectionParameters('rabbitmq'))
channel = connection.channel()

channel.exchange_declare(exchange = EXCHANGE, exchange_type = "fanout")



# Папка для хранения данных
DATA_DIR = "./data"

os.makedirs(DATA_DIR, exist_ok=True)



logging.info(f'Используем модель - {LLM_NAME}')
if LLM_NAME == "gigachat":
    client = GigaChat(credentials=LLM_APIKEY, verify_ssl_certs=False)
    
   
    def get_LLM_answer(text:str):
        logging.info(f'Запрос в gigachat')
        payload = Chat(
            messages=[
                Messages(
                    role=MessagesRole.SYSTEM,
                    content="Ты — бот-психолог, который ведёт поддерживающий разговор с диспетчером перед началом смены. \
        Основные рекомендации по стилю общения:\
            Дружелюбный и спокойный тон.\
            Используй теплый, ненавязчивый язык, создающий атмосферу доверия.")
            ],
            temperature=LLM_TEMPERATURE,
            max_tokens=LLM_MAX_NEW_TOKEN,
        )        
        payload.messages.append(Messages(role=MessagesRole.USER, content=text))
        response = client.chat(payload)        
        content = response.choices[0].message.content  
        return content
    
else:
    client = OpenAI(
        base_url = LLM_ADRESS,
        api_key = LLM_APIKEY,
    )
    def get_LLM_answer(text:str):        
        logging.info(f'Запрос в OPENAI')
        history = [
            {
                "role": "system",
                "content": "You are an intelligent assistant."
            }
        ]    

        history.append({"role": "user", "content": f"{text}"})
        logging.info(f'запрос к модели - {history}')
        completion = client.chat.completions.create(
                model="local-model",
                messages=history,
                temperature=LLM_TEMPERATURE,
                max_tokens=LLM_MAX_NEW_TOKEN  # Ограничьте число токенов
            )
        content = completion.choices[0].message.content    
        return content




# ЗАГРУЗКА СПИСКА ВОПРОСОВ ИЗ ФАЙЛА


def load_survey_questions(path):
    if not os.path.exists(path):
        logging.warning(f"Файл с вопросами не найден: {path}")
        return []
    with open(path, "r", encoding="utf-8") as f:
        questions = [line.strip() for line in f if line.strip()]
    logging.info(f"Загружено {len(questions)} вопросов из файла.")
    return questions


MORNING_PATH = os.path.join(DATA_DIR, "survey_morning_questions.txt")
EVENING_PATH = os.path.join(DATA_DIR, "survey_evening_questions.txt")
SURVEY_QUESTIONS_MORNING = load_survey_questions(MORNING_PATH)
SURVEY_QUESTIONS_EVENING = load_survey_questions(EVENING_PATH)
logging.info(f"Загружены  вопросы из файлов.")

# Хранилище состояния опроса
SURVEY_STATE = {}

#функция для запроса к локальному Rasa
def get_rasa_intent(text: str, sender_id: str = "default") -> dict:
    try:
        response = requests.post(
            "http://rasa-nlu:5005/model/parse",
            json={"text": text},
            timeout=3
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logging.error(f"Ошибка при запросе к Rasa: {e}")
        return {"intent": {"name": "unknown", "confidence": 0}}


# логика обработки опроса с учётом утреннего/вечернего интента
def handle_survey(user_id: str, text: str, workshift: str) -> str:
    # получаем текущее состояние (или None, если ещё не начинали опрос)
    state = SURVEY_STATE.get(user_id)
    logging.info(f"Статус: {state}")
    # если пользователь ещё не выбрал тип опроса — разбираем intent
    if state is None:
        if workshift == "before":
            survey_type = "перед сменой"
            questions = SURVEY_QUESTIONS_MORNING
        else:
            survey_type = "после смены"
            questions = SURVEY_QUESTIONS_EVENING

        logging.info(f"Статус: {state}")

        if not questions:
            return f"Вопросы для {survey_type} опроса пока не загружены."

        # инициализируем состояние опроса
        state = {
            "type": survey_type,
            "questions": questions,
            "step": 0,
            "answers": []
        }
        SURVEY_STATE[user_id] = state
        logging.info(f"Статус: {state}")
    logging.info(f"Статус общий : {SURVEY_STATE}")

    # сохраняем ответ на предыдущий вопрос (если это не первый шаг)
    if state["step"] > 0:
        state["answers"].append(text)

    # если ещё остались вопросы — задаём следующий
    if state["step"] < len(state["questions"]):
        question = state["questions"][state["step"]]
        state["step"] += 1
        return question

    
    # иначе завершаем опрос
    res = 'был рад пообщаться,  '
    if state['type'] == "после смены":
        # TODO добавить работу LLM c контекстом опроса
        res =  'Было ли что-то во время смены, что вызвало сильную эмоциональную реакцию? Расскажите, как это повлияло на вас. Если у вас не осталось вопросов попрощайтесь с ассистентом'
    elif state['type'] == "перед сменой":
        # TODO добавить работу LLM c контекстом опроса
        res = "Было ли что-то со времени нашей последней встречи, что вызвало сильную эмоциональную реакцию? Расскажите, как это повлияло на вас?  Если у вас не осталось вопросов попрощайтесь с ассистентом"
    
    del SURVEY_STATE[user_id]
    return res



# Создаём функцию callback для обработки данных из очереди
def callback(ch, method, properties, body):
    logging.info(f'Получено сообщение - {body}')
    message = json.loads(body)
    user_text = message.get("text", "")
    user_id = str(message.get("user_id", "default"))
    
    rasa_result = get_rasa_intent(user_text, sender_id=user_id)
    intent = rasa_result.get("intent", {}).get("name", "unknown")

    logging.info(f"Распознан интент: {intent}")

    message['exit'] = '0' # флаг завершения общения с ассистентом устанавливам в 0 мы хотим общаться
    
    if  user_id in SURVEY_STATE:
        logging.info(f"in survay")
        response_text = handle_survey(user_id, user_text, intent)
    elif intent == "goodbay":
        response_text = 'До свидания был рад пообщаться'
        message['exit'] = '1' # пользователь попрощался уходим
    elif intent == "ask_llm":
        response_text = get_LLM_answer(user_text)
    else:
        response_text = response_text = get_LLM_answer("ты скорее всего не понял пользователя сказавшего ["+user_text+"] переспроси его") 

    message['text'] = response_text
    logging.info(f'Ответ: {response_text}')
    channel.basic_publish(
        exchange = EXCHANGE,
        routing_key='',
        body=json.dumps(message))

    logging.info(f"сообщение успешно обработано")

# Создаём функцию callback для обработки данных из очереди
def callback_auth(ch, method, properties, body):
    logging.info(f'Получено сообщение - {body}')
    message = json.loads(body)
    user_id = str(message['user_id'])
    workshift = message['work']
    if workshift == 'before':
        content = f"Доброе утро, {message['publicname']}. Давайте обсудим ваше самочувствие. "
    else:
        content = f"Добрый вечер, {message['publicname']}. Давайте пообщаемся о вашем состоянии. "
    content += handle_survey(user_id, '', workshift)

    logging.info(f'ответ модели - {content}')
    message['text'] = content 
    str_time = time.strftime("%a_%d_%b_%Y_%H_%M_%S", time.gmtime())
    message['dialog'] = "диалог_"+str_time+ ("_утро" if workshift == 'before' else "_вечер")
    message['exit'] = '0' # флаг завершения общения с ассистентом устанавливам в 0 мы хотим общаться   
    logging.info(f'сообщение к отправке: {message}')
    channel.basic_publish(
        exchange = EXCHANGE,
        routing_key='',
        body=json.dumps(message))
    logging.info(f"сообщение успешно обработано")

channel.queue_declare(queue='main_text', durable=True)
channel.queue_bind(exchange=EXCHANGE_IN, queue='main_text', routing_key='')
channel.basic_consume(queue='main_text', on_message_callback=callback, auto_ack=True)

channel.queue_declare(queue='main_auth', durable=True)
channel.queue_bind(exchange=EXCHANGE_IN_AUTH, queue='main_auth', routing_key='')
channel.basic_consume(queue='main_auth', on_message_callback=callback_auth, auto_ack=True)



if __name__ == "__main__":
    # Запускаем режим ожидания прихода сообщений
    logging.info(f"Сервис управления стартует...")
    channel.start_consuming()
    
    
    

