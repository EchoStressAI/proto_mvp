import pika
import json
import os
import logging
import numpy as np
import psycopg2
from datetime import datetime

# Читаем переменные окружения
DB_HOST = os.getenv("DB_HOST", "postgres")
DB_NAME = os.getenv("DB_NAME", "echodatabase")
DB_USER = os.getenv("DB_USER", "dbuser")

# Читаем пароль из файла секрета
with open("/run/secrets/postgres_password", "r") as f:
    DB_PASSWORD = f.read().strip()

# Подключение к PostgreSQL
conn = psycopg2.connect(dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD, host=DB_HOST)
cur = conn.cursor()



EXCHANGE = 'logger'
EXCHANGE_IN1 = 'video'
EXCHANGE_IN2 = 'text'
EXCHANGE_IN3 = 'feat'
EXCHANGE_IN4 = 'textemo'
EXCHANGE_IN5 = 'audioemo'
EXCHANGE_IN6 = 'videoemo'
EXCHANGE_IN7 = 'videofat'
EXCHANGE_IN8 = 'audiofat'

EXCHANGE_IN_SELF_REPORT = 'self_report'

logging.basicConfig(level=logging.INFO,    
                    format='%(asctime)s - %(levelname)s - %(module)s - %(message)s'
                    )

# Создаём подключение по адресу rabbitmq:
connection = pika.BlockingConnection(pika.ConnectionParameters('rabbitmq'))
channel = connection.channel()

channel.exchange_declare(exchange = EXCHANGE, exchange_type = "fanout")


# Папка для хранения данных
DATA_DIR = "./data"

os.makedirs(DATA_DIR, exist_ok=True)



def convert_timestamp(timestamp):
    if isinstance(timestamp, (int, float)):  # Если передан UNIX timestamp
        return datetime.utcfromtimestamp(timestamp)
    return timestamp  # Если уже datetime или строка

def get_table_columns(conn, table_name):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = %s;
        """, (table_name,))
        return {row[0] for row in cur.fetchall()}


        
        
def upsert_chanks(conn, existing_columns, user_id, timestamp, **kwargs):
    logging.info(f"existing_columns - {existing_columns}")    
    if not kwargs:
        return  # Нечего обновлять
    
    # Преобразуем timestamp в datetime, если он передан как число
    timestamp = convert_timestamp(timestamp)    
    
    # Фильтруем только существующие колонки
    valid_columns = {col: val for col, val in kwargs.items() if col in existing_columns}
    if not valid_columns:
        return  # Нет подходящих колонок для обновления
    logging.info(f"valid_columns - {valid_columns}")    
    
    columns = list(valid_columns.keys())
    values = list(valid_columns.values())
    
    insert_columns = ', '.join(['user_id', 'timestamp'] + columns)
    insert_placeholders = ', '.join(['%s', '%s'] + ['%s'] * len(columns))
    update_assignments = ', '.join([f"{col} = EXCLUDED.{col}" for col in columns])
    
    query = f"""
        INSERT INTO chanks ({insert_columns})
        VALUES ({insert_placeholders})
        ON CONFLICT (user_id, timestamp) DO UPDATE SET {update_assignments};
    """
    
    with conn.cursor() as cur:
        cur.execute(query, [user_id, timestamp] + values)
        conn.commit()        

existing_columns = get_table_columns(conn, 'chanks')  # Получаем список колонок один раз за сессию





def insert_self_report(conn, report_data):
    # Преобразуем timestamp
    report_data["timestamp"] = convert_timestamp(report_data.get("timestamp"))

    # Очистим значения: "" → None, строковые числа → int
    for key, value in report_data.items():
        if isinstance(value, str):
            if value.strip() == "":
                report_data[key] = None
            elif value.isdigit():
                report_data[key] = int(value)

    query = """
        INSERT INTO self_reports (
            user_id, timestamp,
            joy, sadness, anger, surprise,
            stress_level, fatigue, anxiety,
            current_state, previous_state,
            health_issues, event_details,
            fatigue_reason, stress_reason, anxiety_reason,
            stress_duration, fatigue_duration, anxiety_duration
        ) VALUES (
            %(user_id)s, %(timestamp)s,
            %(joy)s, %(sadness)s, %(anger)s, %(surprise)s,
            %(stress_level)s, %(fatigue)s, %(anxiety)s,
            %(current_state)s, %(previous_state)s,
            %(health_issues)s, %(event_details)s,
            %(fatigue_reason)s, %(stress_reason)s, %(anxiety_reason)s,
            %(stress_duration)s, %(fatigue_duration)s, %(anxiety_duration)s
        );
    """

    with conn.cursor() as cur:
        cur.execute(query, report_data)
        conn.commit()


   
    
    
def callback(ch, method, properties, body):
    logging.info(f'Получено сообщение - {body}')
    if isinstance(body, bytes):
        body = json.loads(body.decode('utf-8'))
    
    if 'stress_duration' in body or 'current_state' in body:  # Признак формы самоотчета
        insert_self_report(conn, body)
    else:
        upsert_chanks(conn=conn, existing_columns=existing_columns, **body)
            


channel.queue_declare(queue='log_text_emo', durable=True)
channel.queue_bind(exchange=EXCHANGE_IN4, queue='log_text_emo', routing_key='')
channel.basic_consume(queue='log_text_emo', on_message_callback=callback, auto_ack=True)

channel.queue_declare(queue='log_vid_emo', durable=True)
channel.queue_bind(exchange=EXCHANGE_IN6, queue='log_vid_emo', routing_key='')
channel.basic_consume(queue='log_vid_emo', on_message_callback=callback, auto_ack=True)

channel.queue_declare(queue='log_aud_emo', durable=True)
channel.queue_bind(exchange=EXCHANGE_IN5, queue='log_aud_emo', routing_key='')
channel.basic_consume(queue='log_aud_emo', on_message_callback=callback, auto_ack=True)


channel.queue_declare(queue='log_text', durable=True)
channel.queue_bind(exchange=EXCHANGE_IN2, queue='log_text', routing_key='')
channel.basic_consume(queue='log_text', on_message_callback=callback, auto_ack=True)

channel.queue_declare(queue='log_feat', durable=True)
channel.queue_bind(exchange=EXCHANGE_IN3, queue='log_feat', routing_key='')
channel.basic_consume(queue='log_feat', on_message_callback=callback, auto_ack=True)

channel.queue_declare(queue='log_video', durable=True)
channel.queue_bind(exchange=EXCHANGE_IN1, queue='log_video', routing_key='')
channel.basic_consume(queue='log_video', on_message_callback=callback, auto_ack=True)

channel.queue_declare(queue='log_self_report', durable=True)
channel.queue_bind(exchange=EXCHANGE_IN_SELF_REPORT, queue='log_self_report', routing_key='')
channel.basic_consume(queue='log_self_report', on_message_callback=callback, auto_ack=True)

channel.queue_declare(queue='log_vid_fat', durable=True)
channel.queue_bind(exchange=EXCHANGE_IN7, queue='log_vid_fat', routing_key='')
channel.basic_consume(queue='log_vid_fat', on_message_callback=callback, auto_ack=True)

channel.queue_declare(queue='log_aud_fat', durable=True)
channel.queue_bind(exchange=EXCHANGE_IN8, queue='log_aud_fat', routing_key='')
channel.basic_consume(queue='log_aud_fat', on_message_callback=callback, auto_ack=True)


if __name__ == "__main__":
    # Запускаем режим ожидания прихода сообщений
    logging.info(f"Сервис логгирования стартует...")
    channel.start_consuming()
    
    
    

