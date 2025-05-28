import time
import logging
import pika
import json
import joblib
import os
import pandas as pd

EXCHANGE = 'audiofat'
EXCHANGE_IN = 'audioemo'
EXCHANGE_FEAT = 'feat'

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


from sklearn.base import BaseEstimator, ClassifierMixin
from sklearn.preprocessing import StandardScaler, LabelEncoder

class ThresholdedSVM(BaseEstimator, ClassifierMixin):
    def __init__(self, model, threshold=0.5):
        self.model = model
        self.threshold = threshold

    def fit(self, X, y):
        self.model.fit(X, y)
        return self

    def predict(self, X):
        
        
        merged_with_f = X.rename(columns={'sex': 'Пол', 'timestamp':'УтроВечер', 'pauses_scaled':'Паузы', 'jitter':'Джиттер', 'shimmer':'Шиммер', 'loudness':'Громкость', 
                                              'pitch_median':'ЧОТмедиан', 'pitch_mean':'ЧОТсреднее', 'voice_impulses':'ГолосовыеИмпульсы', 'Angry_audio':'Angry', 
                                          'Disgusted_audio':'Disgusted', 'Scared_audio':'Scared', 'Happy_audio':'Happy', 'Neutral_audio':'Neutral',
                                          'Sad_audio':'Sad', 'Surprised_audio':'Surprised', 'Valence_audio':'Valence', 'Arousal_audio':'Arousal'})
        feature_columns = [
            'УтроВечер', 'ЧОТсреднее', 'Громкость', 'ГолосовыеИмпульсы', 'Паузы', 'Джиттер', 'Шиммер',
            'Neutral', 'Happy', 'Sad', 'Angry', 'Surprised', 'Scared', 'Disgusted',
            'Valence', 'Arousal', 'Пол', 'VND'
        ]
        X = merged_with_f[feature_columns]
        label_encoders = {}
        for col in ["Пол", "УтроВечер", 'VND']:
            le = LabelEncoder()
            X[col] = le.fit_transform(X[col])
            label_encoders[col] = le
        X = X.fillna(X.median())

        proba = self.model.predict_proba(X)[:, 1]
        return (proba >= self.threshold).astype(int)

    def predict_proba(self, X):
        return self.model.predict_proba(X)


model = joblib.load("./model/voice_model_fatique.pkl")

# Создаём функцию callback для обработки данных из очереди
def callback(ch, method, properties, body):
    logging.info(f'Получено сообщение - {body}')
    message = json.loads(body)
    user_id = message['user_id']
    audio_file = message['audio_file']
    tstamp = message['timestamp']


    # Извлечение усталости из выбранного аудиофайла
    fatigue  = 0.03
    
    message = {
        'user_id': user_id,
        'fatigue_audio': fatigue,
        'timestamp':tstamp
    }

    channel.basic_publish(
        exchange = EXCHANGE,
        routing_key = '',
        body=json.dumps(message))

    logging.info(f"Аудио успешно обработано")

# Buffer to store partial messages until both parts arrive
message_buffer = {}




def try_process(user_id, timestamp):
    """
    If features from both audioemo and feat are present for the same user_id and timestamp,
    merge them, convert to DataFrame, predict fatigue_audio, and publish the result.
    """
    key = (user_id, timestamp)
    entry = message_buffer.get(key)
    if entry and 'audioemo' in entry and 'feat' in entry:
        # Pop combined entry from buffer
        data = message_buffer.pop(key)

        # Merge feature dictionaries
        features = {}
        features.update(data['audioemo'])
        features.update(data['feat'])

        # Prepare DataFrame row
        row = {'user_id': user_id, 'timestamp': timestamp}
        row.update(features)
        df = pd.DataFrame([row])

        # Predict fatigue_audio
        prediction = model.predict(df)
        fatigue_audio = float(prediction[0])

        # Build and publish result message
        result = {
            'user_id': user_id,
            'timestamp': timestamp,
            'fatigue_audio': fatigue_audio
        }
        channel.basic_publish(
            exchange=EXCHANGE,
            routing_key='',
            body=json.dumps(result)
        )
        logging.info(f"Prediction sent: {result}")


def audioemo_callback(ch, method, properties, body):
    logging.info(f"Audioemo features received: {body}")
    msg = json.loads(body)
    user_id = msg['user_id']
    timestamp = msg['timestamp']

    # Extract features payload
    features = {k: v for k, v in msg.items() if k not in ('user_id', 'timestamp')}

    # Store in buffer
    key = (user_id, timestamp)
    message_buffer.setdefault(key, {})['audioemo'] = features

    # Try to process if both sources are ready
    try_process(user_id, timestamp)

    # Acknowledge message
    ch.basic_ack(delivery_tag=method.delivery_tag)


def feat_callback(ch, method, properties, body):
    logging.info(f"Feat features received: {body}")
    msg = json.loads(body)
    user_id = msg['user_id']
    timestamp = msg['timestamp']

    # Extract features payload
    features = {k: v for k, v in msg.items() if k not in ('user_id', 'timestamp')}

    # Store in buffer
    key = (user_id, timestamp)
    message_buffer.setdefault(key, {})['feat'] = features

    # Try to process if both sources are ready
    try_process(user_id, timestamp)

    # Acknowledge message
    ch.basic_ack(delivery_tag=method.delivery_tag)

    
    

channel.queue_declare(queue='extract_aud_fat', durable=True)
channel.queue_bind(exchange=EXCHANGE_IN, queue='extract_aud_fat', routing_key='')
channel.basic_consume(queue='extract_aud_fat', on_message_callback=audioemo_callback, auto_ack=True)

channel.queue_declare(queue='extract_feat', durable=True)
channel.queue_bind(exchange=EXCHANGE_IN, queue='extract_feat', routing_key='')
channel.basic_consume(queue='extract_feat', on_message_callback=feat_callback, auto_ack=True)





if __name__ == "__main__":
    # Запускаем режим ожидания прихода сообщений
    logging.info(f"Сервис извлечения усталости из аудио стартует...")
    channel.start_consuming()
