from flask import Flask, request, jsonify, send_from_directory, render_template, session, redirect, url_for, flash
import time
import logging
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



app = Flask(__name__, static_folder="static", template_folder="templates")
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///app.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False





# Устанавливаем секретный ключ для сессий (замените на более надёжное значение)
app.secret_key = "your-secret-key1"

db = SQLAlchemy(app)

logging.basicConfig(level=logging.INFO,    
                    format='%(asctime)s - %(levelname)s - %(module)s - %(message)s'
                    )


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


# Создаем таблицы (если их еще нет)
with app.app_context():
    db.create_all()
    

# Маршрут для авторизации
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
         username = request.form.get("username").strip()
         password = request.form.get("password").strip()
         
         user = User.get_by_username(username)
         if user and user.check_password(password):
            session["user_id"] = user.id
            session['sex'] = user.sex
            session['username'] = username
            flash("Вы успешно вошли в систему", "success")
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

  
  


        

if __name__ == "__main__":
    # Запускаем RabbitMQ в фоновом потоке
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain('./certs/cert.pem', './certs/key.pem')
    logging.info("webserver start.")    
    app.run(host="0.0.0.0", 
            port=5001, 
            debug=True,        
            ssl_context= context#'adhoc'
            )
