import time
import logging
import pika
import json
import os
from moviepy.editor import VideoFileClip


EXCHANGE = 'audio'
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

# Функция для извлечения аудиодорожки из видео
def extract_audio_from_video(video_file, base_path):
    video_path = os.path.join(base_path, video_file)
    audio_file = video_file.rsplit(".", 1)[0] + ".wav"# Заменяем расширение на .wav
    audio_path = os.path.join(base_path, audio_file)  

    if not os.path.exists(audio_path):  # Проверяем, извлечена ли уже аудиодорожка
        try:
            logging.info(f"Извлечение аудио из {video_file}...")
            clip = VideoFileClip(video_path)
            clip.audio.write_audiofile(audio_path, codec="pcm_s16le")
            logging.info(f"Аудио успешно сохранено: {audio_path}")
        except Exception as e:
            logging.error(f"Ошибка при извлечении аудио из {video_file}: {e}")
            return None
    else:
        logging.info(f"Аудиофайл уже существует: {audio_path}")

    return audio_file


# Создаём функцию callback для обработки данных из очереди
def callback(ch, method, properties, body):
    logging.info(f'Получено сообщение - {body}')
    message = json.loads(body)
    user_id = message['user_id']
    video_file = message['fname']
    tstamp = message['timestamp']


    # Извлечение аудиодорожки из выбранного видеофайла
    audio_file = extract_audio_from_video(video_file, DATA_DIR)
    
    message = {
        'user_id': user_id,
        'fname': audio_file,
        'timestamp':tstamp
    }

    channel.basic_publish(
        exchange = EXCHANGE,
        routing_key = '',
        body=json.dumps(message))

    logging.info(f"Видео успешно обработано")



channel.queue_declare(queue='extract_audio', durable=True)
channel.queue_bind(exchange=EXCHANGE_IN, queue='extract_audio', routing_key='')
channel.basic_consume(queue='extract_audio', on_message_callback=callback, auto_ack=True)






if __name__ == "__main__":
    # Запускаем режим ожидания прихода сообщений
    logging.info(f"Сервис извлечения аудио стартует...")
    channel.start_consuming()
