import pika
import json
import os
import logging
import numpy as np
import torch
from transformers import BertTokenizer, BertForSequenceClassification

EXCHANGE = 'textemo'
EXCHANGE_IN = 'text'

logging.basicConfig(level=logging.INFO,    
                    format='%(asctime)s - %(levelname)s - %(module)s - %(message)s'
                    )

# Создаём подключение по адресу rabbitmq:
connection = pika.BlockingConnection(pika.ConnectionParameters('rabbitmq'))
channel = connection.channel()

channel.exchange_declare(exchange=EXCHANGE, exchange_type="fanout")




# Классы эмоций (замени на свои, если у модели другой набор классов)
LABELS = ["admiration","amusement","anger","annoyance", "approval", "caring", "confusion", 
          "curiosity", "desire", "disappointment", "disapproval", "disgust", "embarrassment", 
          "excitement", "fear", "gratitude", "grief", "joy", "love", "nervousness", "optimism", 
          "pride", "realization", "relief", "remorse", "sadness", "surprise", "neutral"]

# Инициализация модели и токенайзера
MODEL_PATH = 'model'
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

print("Загрузка модели и токенайзера...")
tokenizer = BertTokenizer.from_pretrained(MODEL_PATH)
model = BertForSequenceClassification.from_pretrained(MODEL_PATH)
model.to(device)
model.eval()
print("Модель загружена!")

# Функция для предсказания эмоций с вероятностями
def predict_emotions(text: str) -> dict:
    inputs = tokenizer(text, return_tensors="pt", padding=True, truncation=True)
    inputs = {k: v.to(device) for k, v in inputs.items()}

    with torch.no_grad():
        outputs = model(**inputs)

    logits = outputs.logits
    probabilities = torch.softmax(logits, dim=1).squeeze().tolist()

    # Возвращаем словарь с вероятностями эмоций
    return {LABELS[i]: round(probabilities[i], 4) for i in range(len(LABELS))}


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
    
    
    

