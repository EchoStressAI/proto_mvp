import time
import logging
import pika
import json
import os
from moviepy.editor import VideoFileClip


EXCHANGE = 'videofat'
EXCHANGE_IN = 'video'

logging.basicConfig(level=logging.INFO,    
                    format='%(asctime)s - %(levelname)s - %(module)s - %(message)s'
                    )

### https://habr.com/ru/companies/otus/articles/761444/
# Создаём подключение по адресу rabbitmq:
connection = pika.BlockingConnection(pika.ConnectionParameters('rabbitmq'))
channel = connection.channel()

channel.exchange_declare(exchange=EXCHANGE, exchange_type="fanout")

# Папка для хранения данных
DATA_DIR = "./data"

os.makedirs(DATA_DIR, exist_ok=True)



# Создаём функцию callback для обработки данных из очереди
def callback(ch, method, properties, body):
    logging.info(f'Получено сообщение - {body}')
    message = json.loads(body)
    user_id = message['user_id']
    video_file = message['fname']
    tstamp = message['timestamp']


    # Извлечение усталости из выбранного видеофайла
    fatigue  = 0.01
    
    message = {
        'user_id': user_id,
        'fatigue_video': fatigue,
        'timestamp':tstamp
    }

    channel.basic_publish(
        exchange = EXCHANGE,
        routing_key = '',
        body=json.dumps(message))

    logging.info(f"Видео успешно обработано")



channel.queue_declare(queue='extract_vid_fat', durable=True)
channel.queue_bind(exchange=EXCHANGE_IN, queue='extract_vid_fat', routing_key='')
channel.basic_consume(queue='extract_vid_fat', on_message_callback=callback, auto_ack=True)






if __name__ == "__main__":
    # Запускаем режим ожидания прихода сообщений
    logging.info(f"Сервис извлечения усталости из видео стартует...")
    channel.start_consuming()
