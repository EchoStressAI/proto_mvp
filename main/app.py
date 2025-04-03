import pika
import json
import os
import logging
import numpy as np
from openai import OpenAI
from gigachat import GigaChat
from gigachat.models import Chat, Messages, MessagesRole

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









# Создаём функцию callback для обработки данных из очереди
def callback(ch, method, properties, body):
    logging.info(f'Получено сообщение - {body}')
    message = json.loads(body)
    content = get_LLM_answer(message['text']) 
    logging.info(f'ответ модели - {content}')
    message['text'] = content    
    # user_id = message['user_id']
    # audio_file_name = message['fname']
    # audio_file_path = os.path.join(DATA_DIR, audio_file_name)

    # logging.info(f'start transcribe: {audio_file_path}')
    # message = extract_audio_features(audio_file_path)

    logging.info(f'сообщение к отправке: {message}')

    # message['user_id'] = user_id
    

    channel.basic_publish(
        exchange = EXCHANGE,
        routing_key='',
        body=json.dumps(message))

    logging.info(f"сообщение успешно обработано")



channel.queue_declare(queue='main_text', durable=True)
channel.queue_bind(exchange=EXCHANGE_IN, queue='main_text', routing_key='')
channel.basic_consume(queue='main_text', on_message_callback=callback, auto_ack=True)




if __name__ == "__main__":
    # Запускаем режим ожидания прихода сообщений
    logging.info(f"Сервис управления стартует...")
    channel.start_consuming()
    
    
    

