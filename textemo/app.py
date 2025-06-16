import pika
import json
import os
import logging
import numpy as np
import mlflow

EXCHANGE = 'textemo'
EXCHANGE_IN = 'text'

trashhold  = 0.5 # граница чувствиетльности модели

logging.basicConfig(level=logging.INFO,    
                    format='%(asctime)s - %(levelname)s - %(module)s - %(message)s'
                    )

# Создаём подключение по адресу rabbitmq:
connection = pika.BlockingConnection(pika.ConnectionParameters('rabbitmq'))
channel = connection.channel()

channel.exchange_declare(exchange=EXCHANGE, exchange_type="fanout")

# Весовые коэффициенты для валентности
valence_map = {
    "angry_text": -0.7,
    "disgusted_text": -0.6,
    "happy_text": 0.8,
    "neutral_text": 0.0,
    "sad_text": -0.8,
    "scared_text": -0.7,
    "surprised_text": 0.3
}

# Весовые коэффициенты для активации
arousal_map = {
    "angry_text": 0.8,
    "disgusted_text": 0.4,
    "happy_text": 0.7,
    "neutral_text": 0.0,
    "sad_text": -0.5,
    "scared_text": 0.9,
    "surprised_text": 0.9
}


# Классы эмоций 
EMOTIONS = ['angry_text', 'disgusted_text', 'happy_text', 'neutral_text', 'sad_text', 'scared_text', 'surprised_text']

# Инициализация модели и токенайзера
MODEL_PATH = 'model'


logging.info("Загрузка модели и токенайзера...")

# Создаем pipeline для инференса
classifier =  mlflow.sklearn.load_model(MODEL_PATH) 


logging.info("Модель загружена!")

# Функция для предсказания эмоций с вероятностями
def predict_emotions(text: str) -> dict:
    # Преобразуем текст в DataFrame 
    df = [text]
    # Получаем вероятности для каждого бинара
    proba_list = classifier.predict_proba(df)
    # MultiOutputClassifier возвращает список массивов (для каждого класса)
    # Берем proba[:, 1] для каждого
    scores = [p[0][1] for p in proba_list]
    return {EMOTIONS[i]: round(scores[i], 4) for i in range(len(EMOTIONS))}



# Создаём функцию callback для обработки данных из очереди
def callback(ch, method, properties, body):
    logging.info(f'Получено сообщение - {body}')
    message = json.loads(body)
    user_id = message['user_id']
    text = message['text']    
    tstamp = message['timestamp']
    logging.info(f'start predict: {text}')
    # Получаем вероятности всех эмоций
    message = predict_emotions(text)
    emo_rec =  ''
    argmax_emo = ''
    argmax_val = 0.0
    for emo in EMOTIONS:
        if message[emo] > argmax_val:
            argmax_emo = emo
            argmax_val = message[emo]
        if message[emo]>=trashhold:
            if len(emo_rec)>0:
                emo_rec+=','
            emo_rec+= emo[:-5].capitalize()
    message["emotions_text"] = emo_rec
    val = sum(message[emo] * valence_map[emo] for emo in EMOTIONS)        
    message["valence_classic_text"] = val
    message["arousal_classic_text"] = sum(message[emo] * arousal_map[emo] for emo in EMOTIONS)
    
        # Позитивные и негативные эмоции
    pos = ["happy_text"]
    neg = ["angry_text", "scared_text", "disgusted_text", "sad_text"]

    if val > 0.1:
        pos.append("surprised_text")
    elif val < -0.1:
        neg.append("surprised_text")

    pos_vals = [ message[emo] for emo in pos]
    neg_vals = [ message[emo] for emo in neg]

    message["mean_positive_text"] = np.mean(pos_vals)
    message["min_positive_text"] = np.min(pos_vals)
    message["max_positive_text"] = np.max(pos_vals)
    message["mean_negative_text"] = np.mean(neg_vals)
    message["min_negative_text"] = np.min(neg_vals)
    message["max_negative_text"] = np.max(neg_vals)
    message["emotion_text_argmax"] = argmax_emo[:-5].capitalize()

    logging.info(f"predictions: {message}")
    message['user_id'] = user_id
    message['timestamp']  = tstamp

    channel.basic_publish(
        exchange= EXCHANGE,
        routing_key='',
        body=json.dumps(message))

    logging.info(f"текст успешно обработан")



channel.queue_declare(queue='extract_text_emo', durable=True)
channel.queue_bind(exchange=EXCHANGE_IN, queue='extract_text_emo', routing_key='')
channel.basic_consume(queue='extract_text_emo', on_message_callback=callback, auto_ack=True)


if __name__ == "__main__":
    # Запускаем режим ожидания прихода сообщений
    logging.info(f"Сервис извлечения эмоций из текста стартует...")
    channel.start_consuming()
    
    
    

