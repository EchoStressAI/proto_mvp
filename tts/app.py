import pika
import json
import os
import logging
import numpy as np
from NeuralSpeaker import NeuralSpeaker
import io
import wave
import time



EXCHANGE = 'tts'
EXCHANGE_IN = 'text'

speaker=os.environ.get("SPEAKER",'xenia')
sample_rate = int(os.environ.get("SAMPLE_RATE",'8000'))

logging.basicConfig(level=logging.INFO,    
                    format='%(asctime)s - %(levelname)s - %(module)s - %(message)s'
                    )

# Создаём подключение по адресу rabbitmq:
connection = pika.BlockingConnection(pika.ConnectionParameters('rabbitmq'))
channel = connection.channel()

channel.exchange_declare(exchange = EXCHANGE, exchange_type = "fanout")



neural_speaker = NeuralSpeaker()



# Папка для хранения данных
DATA_DIR = "./data"

os.makedirs(DATA_DIR, exist_ok=True)






# Создаём функцию callback для обработки данных из очереди
def callback(ch, method, properties, body):
    logging.info(f'Получено сообщение - {body}')
    message = json.loads(body)
    user_id = message['user_id']
    text = message['text']
    audio_data = neural_speaker.speak(words=text, speaker=speaker, save_file=True, sample_rate=sample_rate)
    str_time = time.strftime("%a_%d_%b_%Y_%H_%M_%S", time.gmtime())
    fname = f"{user_id}_{str_time}_speak.wav"
    audio_path = os.path.join(DATA_DIR, fname)
    logging.info(f"tts -  start write audio - {audio_path}.")    
    with wave.open(audio_path, 'wb') as wav_file:
        wav_file.setnchannels(1)  # mono
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(audio_data)
        wav_file.close()
    logging.info(f"tts -  end write audio - {audio_path}.")    

    message['fname'] = fname        
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



channel.queue_declare(queue='tts_text', durable=True)
channel.queue_bind(exchange=EXCHANGE_IN, queue='tts_text', routing_key='')
channel.basic_consume(queue='tts_text', on_message_callback=callback, auto_ack=True)




if __name__ == "__main__":
    # Запускаем режим ожидания прихода сообщений
    logging.info(f"Сервис перевода текста в речь стартует...")
    channel.start_consuming()
    
    
    

