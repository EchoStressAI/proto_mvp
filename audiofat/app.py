import time
import logging
import pika
import json
import os


EXCHANGE = 'audiofat'
EXCHANGE_IN = 'audio'

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


    # Извлечение усталости из выбранного аудиофайла
    fatigue  = 0.03
    
    message = {
        'user_id': user_id,
        'fatigue_audio': fatigue,
        'timestamp':tstamp
    }

    channel.basic_publish(
        exchange = EXCHANGE,
        routing_key = '',
        body=json.dumps(message))

    logging.info(f"Аудио успешно обработано")



channel.queue_declare(queue='extract_aud_fat', durable=True)
channel.queue_bind(exchange=EXCHANGE_IN, queue='extract_aud_fat', routing_key='')
channel.basic_consume(queue='extract_aud_fat', on_message_callback=callback, auto_ack=True)






if __name__ == "__main__":
    # Запускаем режим ожидания прихода сообщений
    logging.info(f"Сервис извлечения усталости из аудио стартует...")
    channel.start_consuming()
