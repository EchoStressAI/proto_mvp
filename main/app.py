import pika
import json
import os
import logging
import numpy as np
from openai import OpenAI

client = OpenAI(
    base_url='http://llamaserver:8000/v1',
    api_key='not-needed',
)


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






# Создаём функцию callback для обработки данных из очереди
def callback(ch, method, properties, body):
    logging.info(f'Получено сообщение - {body}')
    message = json.loads(body)
    
    history = [
        {
            "role": "system",
            "content": "You are an intelligent assistant."
        }
    ]
    history.append({"role": "user", "content": f"{message['text']}"})
    logging.info(f'запрос к модели - {history}')
    completion = client.chat.completions.create(
            model="local-model",
            messages=history,
            temperature=0.7,
            max_tokens=100  # Ограничьте число токенов
        )
    content = completion.choices[0].message.content    
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
    
    
    

