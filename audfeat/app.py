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
        pitch = snd.to_pitch()
        pitch_values = pitch.selected_array['frequency']
        voiced = pitch_values[pitch_values > 0]
        voiced = np.ravel(voiced)
        pitch_mean = float(voiced.mean()) if voiced.size > 0 else np.nan
        pitch_median = float(np.median(voiced)) if voiced.size > 0 else np.nan

        intensity = snd.to_intensity()
        loudness = np.nan
        intensity_values = np.ravel(intensity.values) if hasattr(intensity, 'values') else np.array([])
        if intensity_values.size > 0:
            loudness = float(intensity_values.mean())

        point_process = parselmouth.praat.call(snd, "To PointProcess (periodic, cc)", 75, 500)
        voice_impulses = parselmouth.praat.call(point_process, "Get number of points")

        total_duration = snd.get_total_duration()
        speech_rate = voice_impulses / total_duration if total_duration > 0 else np.nan

        pauses = 0.0
        min_silence_length = 0.15
        silence_thresh = loudness * 0.2 if not np.isnan(loudness) else 0
        cur_pause = 0.0
        timestep = 0.01
        if intensity_values.size > 0:
            for val in intensity_values:
                if val < silence_thresh:
                    cur_pause += timestep
                else:
                    if cur_pause > min_silence_length:
                        pauses += cur_pause
                    cur_pause = 0.0
        pauses_scaled = pauses / total_duration if total_duration > 0 else np.nan

        jitter = parselmouth.praat.call(point_process, "Get jitter (local)", 0, 0, 0.0001, 0.02, 1.3)
        shimmer = parselmouth.praat.call([snd, point_process], "Get shimmer (local)", 0, 0, 0.0001, 0.02, 1.3, 1.6)
        jitter_perc = float(jitter) if jitter is not None else np.nan
        shimmer_perc = float(shimmer) if shimmer is not None else np.nan
        anxiety = np.nanmean([jitter_perc, shimmer_perc])

        return {
            'pitch_mean': round(pitch_mean, 2),
            'pitch_median': round(pitch_median, 2),
            'loudness': round(loudness, 2) if not np.isnan(loudness) else np.nan,
            'voice_impulses': int(voice_impulses) if not np.isnan(voice_impulses) else np.nan,
            'pauses_scaled': round(pauses_scaled, 5) if not np.isnan(pauses_scaled) else np.nan,
            'jitter': round(jitter_perc, 5) if not np.isnan(jitter_perc) else np.nan,
            'shimmer': round(shimmer_perc, 5) if not np.isnan(shimmer_perc) else np.nan,
            'anxiety': round(anxiety, 3) if not np.isnan(anxiety) else np.nan,
            'speech_rate': round(speech_rate, 3) if not np.isnan(speech_rate) else np.nan
            }
    except Exception as e:
        logging.error(f"Ошибка при извлечении характеристик: {e}")
        return None


# Создаём функцию callback для обработки данных из очереди
def callback(ch, method, properties, body):
    logging.info(f'Получено сообщение - {body}')
    message = json.loads(body)
    user_id = message['user_id']
    audio_file_name = message['audio_file']
    audio_file_path = os.path.join(DATA_DIR, audio_file_name)
    tstamp = message['timestamp']
    logging.info(f'start extract: {audio_file_path}')
    message = extract_audio_features(audio_file_path)

    logging.info(f'features: {message}')

    message['user_id'] = user_id
    message['timestamp']  = tstamp

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
    
    
    

