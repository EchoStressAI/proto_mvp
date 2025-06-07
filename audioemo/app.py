import time
import logging
import pika
import json
import os
import mlflow.transformers


EXCHANGE = 'audioemo'
EXCHANGE_IN = 'audio'

INT_EMO_MODEL_PATH = 'model_int'
EXT_EMO_MODEL_PATH = 'model_ext'
DOM_MODEL_PATH = 'model_dom'

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




# Весовые коэффициенты для валентности
valence_map = {
    "Angry": -0.7,
    "Disgusted": -0.6,
    "Happy": 0.8,
    "Neutral": 0.0,
    "Sad": -0.8,
    "Scared": -0.7,
    "Surprised": 0.3
}

# Весовые коэффициенты для активации
arousal_map = {
    "Angry": 0.8,
    "Disgusted": 0.4,
    "Happy": 0.7,
    "Neutral": 0.0,
    "Sad": -0.5,
    "Scared": 0.9,
    "Surprised": 0.9
}
# Создаем pipeline для инференса
emo_int =  mlflow.transformers.load_model(INT_EMO_MODEL_PATH) 
emo_ext =  mlflow.transformers.load_model(EXT_EMO_MODEL_PATH) 
emo_dom =  mlflow.transformers.load_model(DOM_MODEL_PATH) 

# Создаём функцию callback для обработки данных из очереди
def callback(ch, method, properties, body):
    logging.info(f'Получено сообщение - {body}')
    message = json.loads(body)
    user_id = message['user_id']
    audio_file = message['audio_file']
    tstamp = message['timestamp']
    res = emo_int(DATA_DIR+"/"+audio_file)
    logging.info(f'Внутренние эмоции - {res}')
    message["Emotion_internal"] = res[0]['label']
    message["Confidence_internal"] =  res[0]['score']
    for i in res:
        message[f"{i['label']}_internal"] = i['score']
     
    message["Valence_classic_internal"]= sum(emo['score'] * valence_map[emo['label']] for emo in res)
    message["Arousal_classic_internal"] = sum(emo['score'] * arousal_map[emo['label']] for emo in res)
    

    res = emo_ext(DATA_DIR+"/"+audio_file)
    logging.info(f'Внешние эмоции - {res}')
    message["Emotion_external"] = res[0]['label']
    message["Confidence_external"] =  res[0]['score']
    for i in res:
        message[f"{i['label']}_external"] = i['score']
     
    message["Valence_classic_external"]= sum(emo['score'] * valence_map[emo['label']] for emo in res)
    message["Arousal_classic_external"] = sum(emo['score'] * arousal_map[emo['label']] for emo in res)

    res = emo_dom(DATA_DIR+"/"+audio_file)
    logging.info(f'доминированиа - {res}')
    for i in res:
        message[f"{i['label']}_audeering".capitalize()] = i['score']
        
        
    message['user_id'] = user_id
    message['timestamp']  = tstamp
   


    channel.basic_publish(
        exchange = EXCHANGE,
        routing_key = '',
        body=json.dumps(message))

    logging.info(f"Аудио успешно обработано")



channel.queue_declare(queue='extract_aud_emo', durable=True)
channel.queue_bind(exchange=EXCHANGE_IN, queue='extract_aud_emo', routing_key='')
channel.basic_consume(queue='extract_aud_emo', on_message_callback=callback, auto_ack=True)






if __name__ == "__main__":
    # Запускаем режим ожидания прихода сообщений
    logging.info(f"Сервис извлечения эмоций из аудио стартует...")
    channel.start_consuming()
