import time
import logging
import pika
import json
import os
import numpy as np
import mlflow.transformers
from transformers import AutoProcessor, AutoModelForAudioClassification
import torch
import torchaudio


EXCHANGE = 'audioemo'
EXCHANGE_IN = 'audio'

INT_EMO_MODEL_PATH = 'model_int'
EXT_EMO_MODEL_PATH = 'model_ext'
DOM_MODEL_PATH = 'model_dom'


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
#emo_dom =  mlflow.transformers.load_model(DOM_MODEL_PATH) 

processor = AutoProcessor.from_pretrained(DOM_MODEL_PATH)
model = AutoModelForAudioClassification.from_pretrained(DOM_MODEL_PATH)
model.eval().to("cuda" if torch.cuda.is_available() else "cpu")


# Создаём функцию callback для обработки данных из очереди
def callback(ch, method, properties, body):
    logging.info(f'Получено сообщение - {body}')
    message = json.loads(body)
    user_id = message['user_id']
    audio_file = message['audio_file']
    tstamp = message['timestamp']
    res = emo_int(DATA_DIR+"/"+audio_file)
    logging.info(f'Внутренние эмоции - {res}')
    message["emotion_internal_audio"] = res[0]['label']
    message["confidence_internal_audio"] =  res[0]['score']
    for i in res:
        message[f"{i['label']}_internal_audio".lower()] = i['score']
     
    message["valence_classic_internal_audio"]= sum(emo['score'] * valence_map[emo['label']] for emo in res)
    message["arousal_classic_internal_audio"] = sum(emo['score'] * arousal_map[emo['label']] for emo in res)
    

    res = emo_ext(DATA_DIR+"/"+audio_file)
    logging.info(f'Внешние эмоции - {res}')
    message["emotion_external_audio"] = res[0]['label']
    message["confidence_external_audio"] =  res[0]['score']
    for i in res:
        message[f"{i['label']}_external_audio".lower()] = i['score']
     
    message["valence_classic_external_audio"]= sum(emo['score'] * valence_map[emo['label']] for emo in res)
    message["arousal_classic_external_audio"] = sum(emo['score'] * arousal_map[emo['label']] for emo in res)

   # res = emo_dom(DATA_DIR+"/"+audio_file)
    logging.info(f'доминированиа - {res}')
    # for i in res:
    #     message[f"{i['label']}_audio"] = i['score']
        
    waveform, sr = torchaudio.load(DATA_DIR+"/"+audio_file)

    # Усреднение каналов при необходимости
    if waveform.shape[0] > 1:
        waveform = waveform.mean(dim=0, keepdim=True)

    # Приведение к 16 кГц
    if sr != 16000:
        waveform = torchaudio.transforms.Resample(orig_freq=sr, new_freq=16000)(waveform)

    # Подготовка входов
    inputs = processor(
        waveform.squeeze().numpy(),
        sampling_rate=16000,
        return_tensors="pt",
        padding=True,
        truncation=True,
        max_length=16000 * 10
    )
    inputs = {k: v.to(model.device) for k, v in inputs.items()}

    # Предсказание
    with torch.no_grad():
        logits = model(**inputs).logits

    # Извлечение значений
    valence, arousal, dominance = logits[0].cpu().numpy().tolist()

    message["valence_audio"] = valence
    message["arousal_audio"] = arousal
    message["dominance_audio"] = dominance    
    
    logging.info(f"Модели отработали")
    
    
    # Позитивные и негативные эмоции
    pos = ["happy_external_audio"]
    neg = ["angry_external_audio", "scared_external_audio", "disgusted_external_audio", "sad_external_audio"]

    if message["valence_classic_external_audio"] > 0.1:
        pos.append("surprised_external_audio")
    elif message["valence_classic_external_audio"] < -0.1:
        neg.append("surprised_external_audio")

    pos_vals = [ message[emo] for emo in pos]
    neg_vals = [ message[emo] for emo in neg]

    message["mean_positive_external_audio"] = np.mean(pos_vals)
    message["min_positive_external_audio"] = np.min(pos_vals)
    message["max_positive_external_audiot"] = np.max(pos_vals)
    message["mean_negative_external_audio"] = np.mean(neg_vals)
    message["min_negative_external_audio"] = np.min(neg_vals)
    message["max_negative_external_audio"] = np.max(neg_vals)
    
    
    # Позитивные и негативные эмоции
    pos = ["happy_internal_audio"]
    neg = ["angry_internal_audio", "scared_internal_audio", "disgusted_internal_audio", "sad_internal_audio"]

    if message["valence_classic_internal_audio"] > 0.1:
        pos.append("surprised_internal_audio")
    elif message["valence_classic_internal_audio"] < -0.1:
        neg.append("surprised_internal_audio")

    pos_vals = [ message[emo] for emo in pos]
    neg_vals = [ message[emo] for emo in neg]

    message["mean_positive_internal_audio"] = np.mean(pos_vals)
    message["min_positive_internal_audio"] = np.min(pos_vals)
    message["max_positive_internal_audio"] = np.max(pos_vals)
    message["mean_negative_internal_audio"] = np.mean(neg_vals)
    message["min_negative_internal_audio"] = np.min(neg_vals)
    message["max_negative_internal_audio"] = np.max(neg_vals)        
        
    
    int_emo  = message.get("emotion_internal_audio")
    ext_emo  = message.get("emotion_external_audio")
    conf_int = (message.get("confidence_internal_audio") or 0)
    conf_ext = (message.get("confidence_external_audio") or 0)

    both_exist = int_emo is not None and ext_emo is not None

    # -------- расчёт emotion_conf_audio ------------------------------------
    if both_exist:
        # обе уверенности низкие → «neutral»
        if conf_int < 0.6 and conf_ext < 0.6:
            emotion_conf = "neutral"
        # иначе выбираем эмоцию с большей (или равной) уверенностью
        else:
            emotion_conf = ext_emo if conf_ext >= conf_int else int_emo
    else:
        # есть только одна эмоция → берём её
        emotion_conf = ext_emo if ext_emo is not None else int_emo

    message["emotion_conf_audio"] = emotion_conf

    # -------- расчёт hidden_emotion_audio ----------------------------------
    hidden = None
    if (
        both_exist and                 # обе эмоции получены
        int_emo != emotion_conf and    # внутренняя ≠ итоговой
        conf_int >= 0.4                # её уверенность ≥ 0.4
    ):
        hidden = int_emo

    message["hidden_emotion_audio"] = hidden
        
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
