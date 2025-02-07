-- Подключение к созданной базе
\connect echodatabase;

-- Создание таблицы пользователей
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Вставка тестовых данных
INSERT INTO users (username, email) 
VALUES 
    ('admin', 'admin@example.com'),
    ('user1', 'user1@example.com')
ON CONFLICT (username) DO NOTHING;





CREATE TABLE IF NOT EXISTS chanks (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    pitch_mean NUMERIC(6,2),
    pitch_median NUMERIC(6,2),
    loudness NUMERIC(6,2),
    voice_impulses NUMERIC(6,2),
    pauses_scaled NUMERIC(10,5),
    jitter NUMERIC(10,5),
    shimmer NUMERIC(10,5),
    anxiety NUMERIC(6,2),
    text TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    UNIQUE (user_id, timestamp)
);