import pika
import json
import os
import logging
import numpy as np

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
    # user_id = message['user_id']
    # audio_file_name = message['fname']
    # audio_file_path = os.path.join(DATA_DIR, audio_file_name)

    # logging.info(f'start transcribe: {audio_file_path}')
    # message = extract_audio_features(audio_file_path)

    # logging.info(f'features: {message}')

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
    logging.info(f"Сервис извлечения характеристик стартует...")
    channel.start_consuming()
    
    
    

