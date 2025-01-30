from flask import Flask, request, jsonify, send_from_directory, render_template
import time
import logging
import pika
import json
import os

EXCHANGE = 'video'


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

@app.route("/")
def index():
    """Возвращает HTML-страницу"""
    return render_template("index.html")

# @app.route("/get_question", methods=["GET"])
# def get_question():
#     """Возвращает видео с вопросом"""
#     videos = os.listdir(QUESTIONS_DIR)
#     if not videos:
#         return jsonify({"error": "Нет видео с вопросами"}), 404
#     return send_from_directory(QUESTIONS_DIR, videos[0])

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
        logging.info(f"webserver -  start write video - {video_path}.")    

        video.save(video_path)
        logging.info(f"webserver -  end write video - {video_path}.")    

        message = {
	        'user_id': user_id,
    	    'fname': fname
	    }

        channel.basic_publish(
            exchange=EXCHANGE,
            routing_key='',
            body=json.dumps(message))

        return jsonify({"message": "Видео успешно загружено"}), 200
    except Exception as e:
        logging.error('error in upload_answer:',e)

if __name__ == "__main__":
    logging.info("webserver start.")    
    app.run(host="0.0.0.0", port=5000, debug=True)
