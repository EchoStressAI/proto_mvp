import pika
import json
import os
import logging
import numpy as np
import mlflow

EXCHANGE = 'textemo'
EXCHANGE_IN = 'text'

logging.basicConfig(level=logging.INFO,    
                    format='%(asctime)s - %(levelname)s - %(module)s - %(message)s'
                    )

# Создаём подключение по адресу rabbitmq:
connection = pika.BlockingConnection(pika.ConnectionParameters('rabbitmq'))
channel = connection.channel()

channel.exchange_declare(exchange=EXCHANGE, exchange_type="fanout")




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
    
    
    

