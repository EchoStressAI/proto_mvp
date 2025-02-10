from flask import Flask, request, jsonify, send_from_directory, render_template
import time
import logging
import pika
import json
import os
import threading

EXCHANGE = 'video'
EXCHANGE_IN = 'tts'

app = Flask(__name__, static_folder="static", template_folder="templates")

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

#TODO сделать авторизацию и передавать id 
user_id = 1



questions = {}

@app.route("/")
def index():
    """Возвращает HTML-страницу"""
    return render_template("index.html")

@app.route("/get_question", methods=["GET"])
def get_question():
    """Возвращает аудиофайл с жестко заданным именем"""
    
    logging.info(f'Запрос вопроса')    
    logging.info(f'Вопросы {questions}')    
    if user_id not in questions: 
        logging.info(f'Вопросы для пользователя  отсутствуют')            
        return jsonify({"info": "Вопросы для пользователя  отсутствуют"}), 404  
    if len(questions[user_id])<1:
        logging.info(f'Очередь вопросов для пользователя  пуста')            
        return jsonify({"info": "Очередь вопросов для пользователя  пуста"}), 404    

    fname = questions[user_id].pop(0)
    logging.info(f'файл вопроса {fname}')    
         
    question_path = os.path.join(DATA_DIR, fname)
    if not os.path.exists(question_path):
        logging.info(f'Аудиофайл вопроса отсутствует')                    
        return jsonify({"error": "Аудиофайл вопроса отсутствует"}), 404
    return send_from_directory(DATA_DIR, fname)

@app.route("/upload_answer", methods=["POST"])
def upload_answer():
    try:
        """Принимает видео-ответ от пользователя"""
        logging.info("webserver -  start getting video.")    

        video = request.files.get("video")
        if not video:
            return jsonify({"error": "Видео не найдено"}), 400
        str_time = time.strftime("%a_%d_%b_%Y_%H_%M_%S", time.gmtime())
        fname = f"{user_id}_{str_time}_full.mp4"
        video_path = os.path.join(DATA_DIR, fname)
        tstamp = time.mktime(time.gmtime())
        logging.info(f"webserver -  start write video - {video_path}.")    

        video.save(video_path)
        logging.info(f"webserver -  end write video - {video_path}.")    

        message = {
	        'user_id': user_id,
    	    'fname': fname,
            'timestamp':tstamp
	    }
        # connection = pika.BlockingConnection(pika.ConnectionParameters('rabbitmq'))
        # channel = connection.channel()
        # channel.exchange_declare(exchange=EXCHANGE, exchange_type="fanout")        
        channel.basic_publish(
            exchange=EXCHANGE,
            routing_key='',
            body=json.dumps(message))

        return jsonify({"message": "Видео успешно загружено"}), 200
    except Exception as e:
        logging.error('error in upload_answer:',e)
  
  
  
  
def consume_questions():
    """Фоновый поток для ожидания сообщений из RabbitMQ"""
    #Создаём функцию callback для обработки данных из очереди
    def callback(ch, method, properties, body):
        logging.info(f'Получено сообщение - {body}')
        message = json.loads(body)
        user_id = message['user_id']
        fname = message['fname']
        if user_id not in questions:
            questions[user_id] = []
        questions[user_id].append(fname)
        logging.info(f'Вопросы обновлены - {questions}')    
        logging.info(f"сообщение успешно обработано")
        
    connection1 = pika.BlockingConnection(pika.ConnectionParameters('rabbitmq'))
    channel1 = connection1.channel()
    channel1.queue_declare(queue='websrv_text', durable=True)
    channel1.queue_bind(exchange=EXCHANGE_IN, queue='websrv_text', routing_key='')
    channel1.basic_consume(queue='websrv_text', on_message_callback=callback, auto_ack=True)
    channel1.start_consuming()
    

        

if __name__ == "__main__":
    # Запускаем RabbitMQ в фоновом потоке
    threading.Thread(target=consume_questions, daemon=True).start()    

    logging.info("webserver start.")    
    app.run(host="0.0.0.0", port=5000, debug=True)
