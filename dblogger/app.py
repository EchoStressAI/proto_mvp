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
    if not kwargs:
        return  # Нечего обновлять
    
    # Преобразуем timestamp в datetime, если он передан как число
    timestamp = convert_timestamp(timestamp)    
    
    # Фильтруем только существующие колонки
    valid_columns = {col: val for col, val in kwargs.items() if col in existing_columns}
    if not valid_columns:
        return  # Нет подходящих колонок для обновления
    
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

# Создаём функцию callback для обработки данных из очереди
def callback(ch, method, properties, body):
    logging.info(f'Получено сообщение - {body}')
    if isinstance(body, bytes):
        body = json.loads(body.decode('utf-8'))
    #body['timestamp']='2024-02-06 12:30:00'
    upsert_chanks(conn=conn, existing_columns=existing_columns,**body)
    # username ='xxx'
    # email = 'xxx@xxx.xx'

    # if username and email:
    #     try:
    #         cur.execute(
    #             "INSERT INTO users (username, email) VALUES (%s, %s) ON CONFLICT (username) DO NOTHING;",
    #             (username, email),
    #         )
    #         conn.commit()
    #         print(f"Добавлен пользователь: {username}, {email}")
    #     except Exception as e:
    #         print(f"Ошибка при добавлении пользователя: {e}")
    #         conn.rollback()
        
    # message = json.loads(body)
    # user_id = message['user_id']
    # audio_file_name = message['fname']
    # audio_file_path = os.path.join(DATA_DIR, audio_file_name)

    # logging.info(f'start transcribe: {audio_file_path}')
    # message = extract_audio_features(audio_file_path)

    # logging.info(f'features: {message}')

    # message['user_id'] = user_id
    

    # channel.basic_publish(
    #     exchange='audfeat_in',
    #     routing_key='audfeatget',
    #     body=json.dumps(message))

    # logging.info(f"Аудио успешно обработано")



channel.queue_declare(queue='log_text', durable=True)
channel.queue_bind(exchange=EXCHANGE_IN2, queue='log_text', routing_key='')
channel.basic_consume(queue='log_text', on_message_callback=callback, auto_ack=True)

channel.queue_declare(queue='log_feat', durable=True)
channel.queue_bind(exchange=EXCHANGE_IN3, queue='log_feat', routing_key='')
channel.basic_consume(queue='log_feat', on_message_callback=callback, auto_ack=True)

channel.queue_declare(queue='log_video', durable=True)
channel.queue_bind(exchange=EXCHANGE_IN1, queue='log_video', routing_key='')
channel.basic_consume(queue='log_video', on_message_callback=callback, auto_ack=True)


if __name__ == "__main__":
    # Запускаем режим ожидания прихода сообщений
    logging.info(f"Сервис извлечения характеристик стартует...")
    channel.start_consuming()
    
    
    

