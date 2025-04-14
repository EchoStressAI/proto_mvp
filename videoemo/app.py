import time
import logging
import pika
import json
import os
from moviepy.editor import VideoFileClip


EXCHANGE = 'videoemo'
EXCHANGE_IN = 'video'

# Классы эмоций 
EMOTIONS = ['angry_video', 'disgusted_video', 'scared_video', 'happy_video', 'neutral_video', 'sad_video', 'surprised_video']

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


    # Извлечение эмоций из выбранного видеофайла
    message = {'angry_video': 0.02, 'disgusted_video': 0.03, 'scared_video': 0.04, 'happy_video': 0.05, 'neutral_video': 0.88, 'sad_video': 0.06, 'surprised_video' : 0.01}
    
    message['user_id'] = user_id
    message['timestamp']  = tstamp
    message['valence_video'] = 0.11
    message['arousal_video']  = 0.12
    message['dom_emo_video']  = "neutral"

    channel.basic_publish(
        exchange = EXCHANGE,
        routing_key = '',
        body=json.dumps(message))

    logging.info(f"Видео успешно обработано")



channel.queue_declare(queue='extract_vid_emo', durable=True)
channel.queue_bind(exchange=EXCHANGE_IN, queue='extract_vid_emo', routing_key='')
channel.basic_consume(queue='extract_vid_emo', on_message_callback=callback, auto_ack=True)






if __name__ == "__main__":
    # Запускаем режим ожидания прихода сообщений
    logging.info(f"Сервис извлечения эмоций из видео стартует...")
    channel.start_consuming()
