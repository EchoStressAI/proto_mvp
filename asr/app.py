import pika
import json
import os
from tempfile import NamedTemporaryFile
from gigaam.onnx_utils import load_onnx_sessions, transcribe_sample
import logging


EXCHANGE = 'text'
EXCHANGE_IN = 'audio'

onnx_dir  = os.environ.get("ONNX_DIR")
model_type = os.environ.get("MODEL_TYPE")

sessions = load_onnx_sessions(onnx_dir, model_type)

logging.basicConfig(level=logging.INFO,    
                    format='%(asctime)s - %(levelname)s - %(module)s - %(message)s'
                    )

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
    audio_file_name = message['audio_file']
    audio_file_path = os.path.join(DATA_DIR, audio_file_name)
    tstamp = message['timestamp']
    logging.info(f'start transcribe: {audio_file_path}')
    recognized_text = transcribe_sample(audio_file_path, model_type, sessions)

    logging.info(f'recognized_text: {recognized_text}')

    
    
    message['text'] = recognized_text

    channel.basic_publish(
        exchange=EXCHANGE,
        routing_key='',
        body=json.dumps(message))

    logging.info(f"Аудио успешно обработано")



channel.queue_declare(queue='extract_text', durable=True)
channel.queue_bind(exchange=EXCHANGE_IN, queue='extract_text', routing_key='')
channel.basic_consume(queue='extract_text', on_message_callback=callback, auto_ack=True)


if __name__ == "__main__":
    # Запускаем режим ожидания прихода сообщений
    logging.info(f"Сервис ASR стартует...")
    channel.start_consuming()
    
    
    

