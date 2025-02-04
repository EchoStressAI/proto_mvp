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
