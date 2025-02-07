import pika
import json
import os
import librosa
import parselmouth
from parselmouth.praat import call
import logging
import numpy as np

EXCHANGE = 'feat'
EXCHANGE_IN = 'audio'

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



def extract_audio_features(audio_file_path):
    try:
        logging.info(f"Загрузка файла: {audio_file_path}")
        snd = parselmouth.Sound(audio_file_path)

        # ЧОТ среднее и медиана
        logging.info("Вычисление ЧОТ среднее и медиана")
        pitch = call(snd, "To Pitch", 0.0, 75, 600)
        pitch_values = pitch.selected_array["frequency"]
        pitch_values = pitch_values[pitch_values > 0]
        pitch_mean = np.mean(pitch_values) if len(pitch_values) > 0 else 0
        pitch_median = np.median(pitch_values) if len(pitch_values) > 0 else 0

        # Громкость
        logging.info("Вычисление громкости")
        loudness = call(snd, "Get intensity (dB)")

        # Голосовые импульсы
        print("Вычисление голосовых импульсов")
        point_process = call(snd, "To PointProcess (periodic, cc)", 75, 600)
        voice_impulses = call(point_process, "Get number of periods", 0, snd.get_total_duration(), 0.0001, 0.02, 1.3)
        logging.info(f"Голосовые импульсы: {voice_impulses}")

        # Паузы
        logging.info("Вычисление пауз через librosa (в долях)")
        y, sr = librosa.load(audio_file_path, sr=16000)
        intervals = librosa.effects.split(y, top_db=30)
        total_duration = len(y) / sr
        silent_duration = total_duration - sum((end - start) / sr for start, end in intervals)
        pauses = silent_duration / total_duration
        pauses_scaled = pauses * 0.5  # Подгонка под шкалу метаданных
        logging.info(f"Паузы: {pauses_scaled:.5f}")

        # Джиттер и шиммер
        logging.info("Вычисление джиттера и шиммера")
        try:
            jitter = call(point_process, "Get jitter (local)", 0, 0, 0.0001, 0.02, 1.3)
            shimmer = call([snd, point_process], "Get shimmer (local)", 0, 0, 0.0001, 0.02, 1.3, 1.6)
            logging.info(f"Джиттер: {jitter:.5f}, Шиммер: {shimmer:.5f}")
        except Exception as e:
            logging.error(f"Ошибка при вычислении джиттера и шиммера: {e}")
            jitter, shimmer = 0, 0

        # Тревожность
        logging.info("Вычисление тревожности")
        anxiety_raw = (jitter * 100 + shimmer * 100 + pauses_scaled * 100) / 3
        anxiety = min(max(anxiety_raw, 0), 60)

        logging.info("Характеристики извлечены успешно")
        return {
            "pitch_mean": round(pitch_mean, 2),
            "pitch_median": round(pitch_median, 2),
            "loudness": round(loudness, 2),
            "voice_impulses": round(voice_impulses, 2),
            "pauses_scaled": round(pauses_scaled, 5),
            "jitter": round(jitter, 5),
            "shimmer": round(shimmer, 5),
            "anxiety": round(anxiety, 2)
        }
    except Exception as e:
        logging.error(f"Ошибка при извлечении характеристик: {e}")
        return None


# Создаём функцию callback для обработки данных из очереди
def callback(ch, method, properties, body):
    logging.info(f'Получено сообщение - {body}')
    message = json.loads(body)
    user_id = message['user_id']
    audio_file_name = message['fname']
    audio_file_path = os.path.join(DATA_DIR, audio_file_name)

    logging.info(f'start extract: {audio_file_path}')
    message = extract_audio_features(audio_file_path)

    logging.info(f'features: {message}')

    message['user_id'] = user_id
    

    channel.basic_publish(
        exchange= EXCHANGE,
        routing_key='',
        body=json.dumps(message))

    logging.info(f"Аудио успешно обработано")



channel.queue_declare(queue='extract_feat', durable=True)
channel.queue_bind(exchange=EXCHANGE_IN, queue='extract_feat', routing_key='')
channel.basic_consume(queue='extract_feat', on_message_callback=callback, auto_ack=True)


if __name__ == "__main__":
    # Запускаем режим ожидания прихода сообщений
    logging.info(f"Сервис извлечения характеристик стартует...")
    channel.start_consuming()
    
    
    

