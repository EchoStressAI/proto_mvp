from flask import Flask, request, jsonify, send_from_directory, render_template, session, redirect, url_for, flash
import time
import logging
import pika
import json
import os
import threading
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
import psycopg2
import base64
import ssl

# Настройки подключения к PostgreSQL
DB_HOST = os.getenv("DB_HOST", "postgres")
DB_NAME = os.getenv("DB_NAME", "echodatabase")
DB_USER = os.getenv("DB_USER", "dbuser")
DB_PASSWORD = os.getenv("DB_PASSWORD", "dbpassword")

# Читаем пароль из файла секрета
with open("/run/secrets/postgres_password", "r") as f:
    DB_PASSWORD = f.read().strip()
    
conn = psycopg2.connect(
    dbname=DB_NAME,
    user=DB_USER,
    password=DB_PASSWORD,
    host=DB_HOST
)
cur = conn.cursor()

#очереди RabbitMQ
EXCHANGE = 'video'
EXCHANGE_AUTH = 'auth'
EXCHANGE_SELF_REPORT = 'self_report'

EXCHANGE_IN = 'tts'


app = Flask(__name__, static_folder="static", template_folder="templates")
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///app.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False





# Устанавливаем секретный ключ для сессий (замените на более надёжное значение)
app.secret_key = "your-secret-key"

db = SQLAlchemy(app)

logging.basicConfig(level=logging.INFO,    
                    format='%(asctime)s - %(levelname)s - %(module)s - %(message)s'
                    )

# ### https://habr.com/ru/companies/otus/articles/761444/
# # Создаём подключение по адресу rabbitmq:
connection = pika.BlockingConnection(pika.ConnectionParameters('rabbitmq'))
channel = connection.channel()

channel.exchange_declare(exchange=EXCHANGE, exchange_type="fanout")
channel.exchange_declare(exchange=EXCHANGE_AUTH, exchange_type="fanout")
channel.exchange_declare(exchange=EXCHANGE_SELF_REPORT, exchange_type="fanout")

# Папка для хранения данных
DATA_DIR = "./data"

os.makedirs(DATA_DIR, exist_ok=True)

# Декоратор для защиты маршрутов, требующих авторизации


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
         if "user_id" not in session:
              flash("Пожалуйста, выполните вход для доступа к этой странице", "warning")
              return redirect(url_for("login"))
         return f(*args, **kwargs)
    return decorated_function



def get_current_user_id():
    """
    Извлекает идентификатор пользователя из HTTP-заголовка.
    Если заголовок отсутствует или содержит некорректное значение, прерывает выполнение запроса.
    """
    return session.get("user_id")    


# Модель пользователя 
class User:
    def __init__(self, id=None, username=None, publicname=None,sex = None,password_hash=None):
        self.id = id
        self.username = username
        self.publicname = publicname
        self.sex = sex
        self.password_hash = password_hash

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def save(self):
        try:
            with conn.cursor() as cur:
                if self.id is None:
                    cur.execute(
                        "INSERT INTO users (username, publicname, sex, password_hash) VALUES (%s,%s,%s,%s) RETURNING id",
                        (self.username, self.publicname, self.sex, self.password_hash)
                    )
                    self.id = cur.fetchone()[0]
                else:
                    cur.execute(
                        "UPDATE users SET username=%s, sex=%s, publicname=%s, password_hash=%s WHERE id=%s",
                        (self.username, self.publicname, self.sex, self.password_hash, self.id)
                    )
        finally:
            conn.commit()

    @classmethod
    def get_by_username(cls, username):
        logging.info(f"User {username} requested auth")
        with conn.cursor() as cur:
            cur.execute("SELECT id, username, publicname, sex, password_hash FROM users WHERE username= %s;", (str(username),))
            row = cur.fetchone()
            if row:
                return cls(*row)
        return None

# Модель вопроса, привязанного к пользователю
class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)  # Можно добавить ForeignKey для таблицы User
    file_name = db.Column(db.String(256), nullable=False)
    text = db.Column(db.String(1024), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    exit_q = db.Column(db.Integer, nullable=False)

# Создаем таблицы (если их еще нет)
with app.app_context():
    db.create_all()
    

# Маршрут для авторизации
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
         username = request.form.get("username").strip()
         password = request.form.get("password").strip()
         
         work = request.form.get("work")
         if work is None:
           flash("Не задано до или после смены!", "danger")
           return render_template("login.html")
         user = User.get_by_username(username)
         if user and user.check_password(password):
            session["user_id"] = user.id
            session['work'] = work
            flash("Вы успешно вошли в систему", "success")
            # сообщим всем заинтеренованным сервисам о входе пользователя
            tstamp = time.mktime(time.gmtime())
            message = {
                'user_id': user.id,
                'username': username,
                'publicname': user.publicname,
                'work': work,
                'timestamp':tstamp
            }           
            connection_pub = pika.BlockingConnection(pika.ConnectionParameters('rabbitmq'))
            channel_pub = connection_pub.channel()
            channel_pub.exchange_declare(exchange=EXCHANGE_AUTH, exchange_type="fanout")
            channel_pub.basic_publish(
                exchange=EXCHANGE_AUTH,
                routing_key='',
                body=json.dumps(message)
            )
            connection_pub.close()              
            return redirect(url_for("index"))
         else:
              flash("Неверное имя пользователя или пароль", "danger")
    return render_template("login.html")

# Маршрут для регистрации
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
         publicname = request.form.get("publicname")
         sex = request.form.get("sex")
         username = request.form.get("username")
         password = request.form.get("password")
         if  User.get_by_username(username):
              flash("Имя пользователя уже существует", "warning")
         else:
              new_user = User(username=username,publicname=publicname, sex=sex)
              new_user.set_password(password)
              new_user.save()
              flash("Регистрация успешна. Теперь выполните вход.", "success")
              return redirect(url_for("login"))
    return render_template("register.html")

# Маршрут для выхода из системы
@app.route("/logout")
def logout():
    session.pop("user_id", None)
    flash("Вы вышли из системы", "info")
    return redirect(url_for("login"))
    

@app.route("/")
@login_required
def index():
    """Возвращает HTML-страницу"""
    return render_template("index.html")

@app.route("/get_question", methods=["GET"])
def get_question():
    """
    Возвращает аудиофайл с текущим вопросом для пользователя.
    Вопрос не удаляется из очереди, чтобы избежать повторного исчезновения.
    Клиент должен вызвать /ack_question после обработки.
    """
    user_id = get_current_user_id()
    logging.info(f"User {user_id} requested a question")
    # Ищем самый ранний вопрос для данного пользователя
    question = Question.query.filter_by(user_id=user_id).order_by(Question.created_at).first()
    if not question:
        logging.info(f"No questions found for user {user_id}")
        return jsonify({"info": "No questions found for user"}), 404
    fname = question.file_name
    text = question.text
    logging.info(f"Found question file: {fname}")
    question_path = os.path.join(DATA_DIR, fname)
    if not os.path.exists(question_path):
        logging.error("Audio file for question not found")
        return jsonify({"error": "Audio file for question not found"}), 404
    b64_text = base64.b64encode(text.encode('utf-8')).decode('ascii')
    # Отдаем аудио
    response = send_from_directory(DATA_DIR, fname)
    # И заголовок с базой
    response.headers['X-Question-Text'] = b64_text
    response.headers['X-Exit'] = question.exit_q
    return response


@app.route("/ack_question", methods=["POST"])
@login_required
def ack_question():
    """
    Подтверждает (удаляет) текущий вопрос для пользователя.
    Клиент вызывает этот эндпоинт после обработки вопроса.
    """
    user_id = get_current_user_id()
    logging.info(f"User {user_id} acknowledged a question")
    # Находим и удаляем самый ранний вопрос для пользователя
    question = Question.query.filter_by(user_id=user_id).order_by(Question.created_at).first()
    if question:
        fname = question.file_name
        db.session.delete(question)
        db.session.commit()
        logging.info(f"Question {fname} acknowledged and removed for user {user_id}")
        return jsonify({"message": "Question acknowledged"}), 200
    else:
        return jsonify({"error": "No question to acknowledge"}), 404

@app.route("/check_question", methods=["GET"])
@login_required
def check_question():
    """
    Проверяет наличие вопросов для пользователя и возвращает JSON-ответ.
    Если вопрос есть, возвращает сообщение "Question found" и имя файла вопроса.
    Если вопросов нет, возвращает сообщение "No questions found".
    """
    user_id = get_current_user_id()
    logging.info(f"User {user_id} checking for questions")
    question = Question.query.filter_by(user_id=user_id).order_by(Question.created_at).first()
    if question:
        logging.info("Question found")
        return jsonify({"message": "Question found"}), 200
    else:
        logging.info("No questions found")
        return jsonify({"message": "No questions found"}), 404
        

@app.route("/upload_answer", methods=["POST"])
@login_required
def upload_answer():
    try:
        """Принимает видео-ответ от пользователя"""
        logging.info("webserver -  start getting video.")    
        logging.info(f"request {request.form.get('text')}")    

        user_id = get_current_user_id()
        ass_text = request.form.get('text')
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
        logging.info(f"смена - {session['work']}.")    

        message = {
	        'user_id': user_id,
    	    'video_file': fname,
            'timestamp':tstamp,
            'assistant': ass_text,
            'workshift': session['work']
	    }
        # Открываем новое подключение и канал для публикации
        connection_pub = pika.BlockingConnection(pika.ConnectionParameters('rabbitmq'))
        channel_pub = connection_pub.channel()
        channel_pub.exchange_declare(exchange=EXCHANGE, exchange_type="fanout")
        channel_pub.basic_publish(
            exchange=EXCHANGE,
            routing_key='',
            body=json.dumps(message)
        )
        connection_pub.close()

        return jsonify({"message": "Видео успешно загружено"}), 200
    except Exception as e:
        logging.error(f"error in upload_answer: {e}")
        return jsonify({"error": "Ошибка при обработке запроса"}), 500
  
  
  
def consume_questions(): 
    """Фоновый поток для ожидания сообщений из RabbitMQ"""
    #Создаём функцию callback для обработки данных из очереди
    def callback(ch, method, properties, body):
        with app.app_context():
            try:
                logging.info(f'Получено сообщение - {body}')
                message = json.loads(body)
                user_id = message['user_id']
                fname = message['fname']
                text = message['text']
                exit_q = message['exit']
                if user_id is None or fname is None:
                    logging.error("Invalid message received")
                    return
                # Создаем новую запись вопроса для пользователя
                question = Question(user_id=user_id, file_name=fname, text=text,exit_q=exit_q)
                db.session.add(question)
                db.session.commit()
                logging.info(f"Question for user {user_id} added to database")
            except Exception as e:
                logging.error(f"Error in callback: {e}")
        
    try:    
        logging.info("Ожидание 30 секунд перед  попыткой подключения дадим всем запуститься...")
        time.sleep(30)
        connection1 = pika.BlockingConnection(pika.ConnectionParameters('rabbitmq'))
        channel1 = connection1.channel()
        channel1.queue_declare(queue='websrv_text', durable=True)
        channel1.queue_bind(exchange=EXCHANGE_IN, queue='websrv_text', routing_key='')
        channel1.basic_consume(queue='websrv_text', on_message_callback=callback, auto_ack=True)
        logging.info(f"стартуем получение вопросов пользователю")
        channel1.start_consuming()
    except Exception as e:
        logging.error(f"Ошибка в consume_questions: {e}")
    finally:
        if connection1 and connection1.is_open:
            connection1.close()
           
@app.route("/self_report", methods=["GET", "POST"])
@login_required
def self_report():
    if request.method == "POST":
        form_data = request.form.to_dict()
        form_data["user_id"] = get_current_user_id()
        form_data["timestamp"] = time.mktime(time.gmtime())
        logging.info(f"получен самоотчет: {form_data}")
        try:
            connection_pub = pika.BlockingConnection(pika.ConnectionParameters('rabbitmq'))
            channel_pub = connection_pub.channel()
            channel_pub.exchange_declare(exchange=EXCHANGE_SELF_REPORT, exchange_type="fanout")
            channel_pub.basic_publish(
                exchange=EXCHANGE_SELF_REPORT,
                routing_key='',
                body=json.dumps(form_data)
            )
            connection_pub.close()
            logging.info("Ваш самоотчет отправлен успешно!")
            flash("Ваш самоотчет отправлен успешно!", "success")
        except Exception as e:
            app.logger.error(f"Ошибка при отправке самоотчета: {e}")
            flash("Ошибка при отправке самоотчета", "danger")
        return redirect(url_for("index"))
    return render_template("self_report.html")


        

if __name__ == "__main__":
    # Запускаем RabbitMQ в фоновом потоке
    threading.Thread(target=consume_questions, daemon=True).start()    
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain('./certs/cert.pem', './certs/key.pem')
    logging.info("webserver start.")    
    app.run(host="0.0.0.0", 
            port=5000, 
            debug=True,        
            ssl_context= context#'adhoc'
            )
