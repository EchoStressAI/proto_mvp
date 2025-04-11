import time
import logging
import pika
import json
import os


EXCHANGE = 'audioemo'
EXCHANGE_IN = 'audio'

# Классы эмоций 
EMOTIONS = ['angry_audio', 'disgusted_audio', 'scared_audio', 'happy_audio', 'neutral_audio', 'sad_audio', 'surprised_audio']

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
    audio_file = message['fname']
    tstamp = message['timestamp']


    # Извлечение эмоций из выбранного видеофайла
    message = {'angry_audio': 0.02, 'disgusted_audio': 0.03, 'scared_audio': 0.04, 'happy_audio': 0.05, 'neutral_audio': 0.88, 'sad_audio': 0.06, 'surprised_audio' : 0.01}
    message['user_id'] = user_id
    message['timestamp']  = tstamp
   
    message['valence_audio'] = 0.21
    message['arousal_audio']  = 0.22
    message['mean_deviation_audio']  = 0.33


    channel.basic_publish(
        exchange = EXCHANGE,
        routing_key = '',
        body=json.dumps(message))

    logging.info(f"Видео успешно обработано")



channel.queue_declare(queue='extract_aud_emo', durable=True)
channel.queue_bind(exchange=EXCHANGE_IN, queue='extract_aud_emo', routing_key='')
channel.basic_consume(queue='extract_aud_emo', on_message_callback=callback, auto_ack=True)






if __name__ == "__main__":
    # Запускаем режим ожидания прихода сообщений
    logging.info(f"Сервис извлечения эмоций из аудио стартует...")
    channel.start_consuming()
