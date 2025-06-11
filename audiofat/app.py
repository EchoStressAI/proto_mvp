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


def add_best_audio_columns(
    df,
    emotions=['angry', 'happy', 'sad', 'scared', 'surprised', 'neutral', 'disgusted'],
    metrics=[('Valence', 'valence_classic_external_audio', 'valence_classic_internal_audio'),
             ('Arousal', 'arousal_classic_external_audio', 'arousal_classic_internal_audio')],
    conf_thresh=0.6
):
    def get_prob(row, ext_col, int_col):
        ext_conf = row['confidence_external_audio']
        int_conf = row['confidence_internal_audio']
        ext_val = row.get(ext_col, None)
        int_val = row.get(int_col, None)
        if ext_conf >= conf_thresh and int_conf >= conf_thresh:
            if ext_val is not None and int_val is not None:
                return (ext_val + int_val) / 2
            elif ext_val is not None:
                return ext_val
            elif int_val is not None:
                return int_val
            else:
                return None
        elif ext_conf >= conf_thresh:
            return ext_val
        elif int_conf >= conf_thresh:
            return int_val
        else:
            if ext_conf >= int_conf:
                return ext_val
            else:
                return int_val
    for emo in emotions:
        ext_col = f'{emo}_external_audio'
        int_col = f'{emo}_internal_audio'
        df[f'{emo}'.capitalize()] = df.apply(lambda row: get_prob(row, ext_col, int_col), axis=1)

    for metric, ext_col, int_col in metrics:
        df[f'{metric}'] = df.apply(lambda row: get_prob(row, ext_col, int_col), axis=1)

    return df


        # Пол мужской 0 женский 1
        # утро 0  вечер 1


class ThresholdedSVM(BaseEstimator, ClassifierMixin):
    def __init__(self, model, threshold=0.41):
        self.model = model
        self.threshold = threshold

    def fit(self, X, y):
        self.model.fit(X, y)
        return self

    def predict(self, X):
        proba = self.model.predict_proba(X)[:, 1]
        return (proba >= self.threshold).astype(int)

    def predict_proba(self, X):
        return self.model.predict_proba(X)




model = joblib.load("./model/voice_model_fatique.pkl")


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
        logging.info(f"Колонки для предсказаний: {row}")
        df = pd.DataFrame([row])

        df = add_best_audio_columns(df)
        rename_dict = {
            'sex': 'Пол',
            'workshift': 'УтроВечер',
            'pauses_scaled': 'Паузы',
            'jitter': 'Джиттер',
            'shimmer': 'Шиммер',
            'loudness': 'Громкость',
            'pitch_median': 'ЧОТмедиан',
            'pitch_mean': 'ЧОТсреднее',
            'voice_impulses': 'ГолосовыеИмпульсы'
        }
        df = df.rename(columns=rename_dict)
        df['Пол'] = df['Пол'].map({'женский': 1, 'мужской': 0})
        df['УтроВечер'] = df['УтроВечер'].map({'after': 1, 'before': 0})
        
        
        
        feature_columns = [
            'УтроВечер', 'ЧОТсреднее', 'Громкость', 'ГолосовыеИмпульсы', 'Паузы', 'Джиттер', 'Шиммер',
            'Neutral', 'Happy', 'Sad', 'Angry', 'Surprised', 'Scared', 'Disgusted',
            'Valence', 'Arousal', 'Пол'
        ]
        X = df[feature_columns].copy()
        logging.info(f"Features for model: {X}")        
        prediction = model.predict(X)

        # Predict fatigue_audio
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

    # # Acknowledge message
    # ch.basic_ack(delivery_tag=method.delivery_tag)


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

    # # Acknowledge message
    # ch.basic_ack(delivery_tag=method.delivery_tag)

    
    

channel.queue_declare(queue='extract_aud_fat', durable=True)
channel.queue_bind(exchange=EXCHANGE_IN, queue='extract_aud_fat', routing_key='')
channel.basic_consume(queue='extract_aud_fat', on_message_callback=audioemo_callback, auto_ack=True)

channel.queue_declare(queue='extract_feat', durable=True)
channel.queue_bind(exchange=EXCHANGE_FEAT, queue='extract_feat', routing_key='')
channel.basic_consume(queue='extract_feat', on_message_callback=feat_callback, auto_ack=True)





if __name__ == "__main__":
    # Запускаем режим ожидания прихода сообщений
    logging.info(f"Сервис извлечения усталости из аудио стартует...")
    channel.start_consuming()
