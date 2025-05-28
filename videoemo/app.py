import time
import logging
import pika
import json
import os
from moviepy.editor import VideoFileClip
import numpy as np
import pandas as pd
from fer import FER
import torch
import torch.nn as nn
from scipy.stats import trim_mean
from collections import Counter
import cv2

EXCHANGE = 'videoemo'
EXCHANGE_IN = 'video'

# Emotion labels and column definitions
EMOTION_MAPPING = {
    "angry": "Angry", "disgust": "Disgusted", "fear": "Scared",
    "happy": "Happy", "neutral": "Neutral", "sad": "Sad", "surprise": "Surprised"
}
emotion_labels = [v for v in EMOTION_MAPPING.values()]
# SUMMARY_COLS = [
#     "FPS_fer", "Emotion_BiLSTM_fer", "Emotion_Mode_fer", "Emotion_Sum_fer", "Emotion_Smoothed_fer", "Emotion_Confident_fer",
#     "Valence_mean_fer", "Valence_median_fer", "Valence_trimmed_mean_fer",
# ] + [f"{emo}_mean_fer" for emo in emotion_labels] + [f"{emo}_max_fer" for emo in emotion_labels]

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



# Initialize FER model
fer_model = FER(mtcnn=False)

# Load Valence MLP regressor
# Load local Valence MLP regressor files
models_dir = os.environ.get('MODELS_DIR', './models')
valence_dir = os.path.join(models_dir, 'valence-regressor-mlp')
config_path = os.path.join(valence_dir, 'config.json')
weights_path = os.path.join(valence_dir, 'pytorch_model.bin')
with open(config_path, 'r') as f:
    cfg = json.load(f)

class MLPRegressor(nn.Module):
    def __init__(self, input_size, hidden_sizes, output_size):
        super().__init__()
        layers = []
        in_dim = input_size
        for h in hidden_sizes:
            layers += [nn.Linear(in_dim, h), nn.ReLU()]
            in_dim = h
        layers.append(nn.Linear(in_dim, output_size))
        self.model = nn.Sequential(*layers)
    def forward(self, x):
        return self.model(x)

mlp = MLPRegressor(cfg['input_size'], cfg['hidden_sizes'], cfg['output_size'])
mlp.load_state_dict(torch.load(weights_path, map_location='cpu'))
mlp.eval()

# Load BiLSTM Domain Classifier
class BiLSTMClassifier(nn.Module):
    def __init__(self, input_size, hidden_size, num_classes, num_layers=1, dropout=0.3):
        super().__init__()
        self.bilstm = nn.LSTM(input_size, hidden_size, num_layers=num_layers,
                              dropout=dropout if num_layers>1 else 0,
                              batch_first=True, bidirectional=True)
        self.fc = nn.Linear(hidden_size*2, num_classes)
    def forward(self, x):
        out, _ = self.bilstm(x)
        return self.fc(out)

bilstm_dir = os.path.join(models_dir, 'bilstm_dom_emotion_model')
bilstm_path = os.path.join(bilstm_dir, 'pytorch_model.bin')

bi_model = BiLSTMClassifier(len(emotion_labels), 128, len(emotion_labels))
bi_model.load_state_dict(torch.load(bilstm_path, map_location='cpu'))
bi_model.eval()

# Callback for processing video

def callback(ch, method, properties, body):
    msg = json.loads(body)
    logging.info(f'Получено сообщение - {msg}')    
    user_id = msg['user_id']
    video_file = msg['video_file']
    timestamp = msg['timestamp']

    video_path = os.path.join(DATA_DIR, video_file)
    if not os.path.exists(video_path):
        logging.error(f"Video not found: {video_path}")
        return

    # Frame-level FER predictions
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    logging.info(f'FPS - {fps}') 
    fer_records = []
    idx = 0
    while True:
        ret, frame = cap.read()
        if not ret: break
        det = fer_model.detect_emotions(frame)
        if det:
            em = det[0]['emotions']
            mapped = {f"{EMOTION_MAPPING[k]}_fer": v for k,v in em.items()}
            dom = max(mapped, key=mapped.get)
            fer_records.append({
                'Frame_Number_fer': idx,
                'Video_Time_fer': idx/fps,
                **mapped,
                'Dominant_Emotion_fer': dom
            })
        idx += 1
    cap.release()
    df = pd.DataFrame(fer_records)
    logging.info(f'FER отработал   - {len(fer_records)}')    
    # Compute summary metrics
    summary = {}
    summary['FPS_fer'] = fps
    # Valence via MLP
    feats = [f"{emo}_fer" for emo in emotion_labels]
    if all(c in df.columns for c in feats):
        X = torch.tensor(df[feats].values, dtype=torch.float32)
        with torch.no_grad():
            v_pred = mlp(X).squeeze().numpy()
        df['Valence_mlp_fer'] = v_pred
        summary['Valence_mean_fer']   = float(np.mean(v_pred))
        summary['Valence_median_fer'] = float(np.median(v_pred))
        summary['Valence_trimmed_mean_fer'] = float(trim_mean(v_pred, 0.1))
    # Emotion argmax
    df['Emotion_argmax_fer'] = df[[f"{emo}_fer" for emo in emotion_labels]].idxmax(axis=1)
    # Mode, sum, smoothed, confident
    summary['Emotion_Mode_fer'] = df['Emotion_argmax_fer'].mode().iloc[0]
    sums = df[[f"{emo}_fer" for emo in emotion_labels]].sum()
    summary['Emotion_Sum_fer'] = sums.idxmax()
    # Smoothed
    modes = [Counter(df['Emotion_argmax_fer'][max(0,i-9):i+1]).most_common(1)[0][0] for i in range(len(df))]
    summary['Emotion_Smoothed_fer'] = Counter(modes).most_common(1)[0][0]
    # Confident
    confid = df[[f"{emo}_fer" for emo in emotion_labels]].max(axis=1) >= 0.6
    if confid.any(): summary['Emotion_Confident_fer'] = df.loc[confid,'Emotion_argmax_fer'].mode().iloc[0]
    # Mean/max per emotion
    for emo in emotion_labels:
        summary[f"{emo}_mean_fer"] = float(df[f"{emo}_fer"].mean())
        summary[f"{emo}_max_fer"]  = float(df[f"{emo}_fer"].max())
    # BiLSTM summary
    seq = torch.tensor(df[[f"{emo}_fer" for emo in emotion_labels]].values, dtype=torch.float32).unsqueeze(0)
    with torch.no_grad():
        out = bi_model(seq)
    preds = out.squeeze(0).argmax(dim=1).numpy()
    uniq = sorted(set(preds))
    summary['Emotion_BiLSTM_fer'] = ",".join([emotion_labels[i] for i in uniq])

    # Build message
    result = {**summary}
    # add raw emotion probabilities at video level: mean from df
    for emo in emotion_labels:
        result[f"{emo.lower()}_video"] = float(df[f"{emo}_fer"].mean())
    # dominant, valence_video, arousal_video placeholders (if needed)
    result['Emotion_Mode_fer'] = summary['Emotion_Mode_fer']
    result['Valence_mean_fer'] = summary['Valence_mean_fer']


    result['user_id'] = user_id
    result['timestamp'] = timestamp

    channel.basic_publish(exchange=EXCHANGE, routing_key='', body=json.dumps(result))
    logging.info(f"Processed video {video_file}")


channel.queue_declare(queue='extract_vid_emo', durable=True)
channel.queue_bind(exchange=EXCHANGE_IN, queue='extract_vid_emo', routing_key='')
channel.basic_consume(queue='extract_vid_emo', on_message_callback=callback, auto_ack=True)






if __name__ == "__main__":
    # Запускаем режим ожидания прихода сообщений
    logging.info(f"Сервис извлечения эмоций из видео стартует...")
    channel.start_consuming()
