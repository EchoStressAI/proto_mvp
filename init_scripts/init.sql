-- Подключение к созданной базе
\connect echodatabase;

-- Создание таблицы пользователей
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(64) UNIQUE NOT NULL,
    publicname VARCHAR(64) NOT NULL,
    sex VARCHAR(10) NOT NULL,
    password_hash VARCHAR(256) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);





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
    fatigue_video NUMERIC(6,2),
    fatigue_audio NUMERIC(6,2),
    Angry_text    NUMERIC(6,2),
    Disgusted_text    NUMERIC(6,2),
    Scared_text    NUMERIC(6,2),  
    Happy_text    NUMERIC(6,2),
    Neutral_text    NUMERIC(6,2),
    Sad_text    NUMERIC(6,2),
    Surprised_text    NUMERIC(6,2),  
    Angry_video    NUMERIC(6,2),
    Disgusted_video    NUMERIC(6,2),
    Scared_video    NUMERIC(6,2),  
    Happy_video    NUMERIC(6,2),
    Neutral_video    NUMERIC(6,2),
    Sad_video    NUMERIC(6,2),
    Surprised_video    NUMERIC(6,2),  
    Valence_video    NUMERIC(6,2),
    Arousal_video    NUMERIC(6,2),
    dom_emo_video  TEXT,
    Angry_audio    NUMERIC(6,2),
    Disgusted_audio    NUMERIC(6,2),
    Scared_audio    NUMERIC(6,2),  
    Happy_audio    NUMERIC(6,2),
    Neutral_audio    NUMERIC(6,2),
    Sad_audio    NUMERIC(6,2),
    Surprised_audio    NUMERIC(6,2),  
    Valence_audio    NUMERIC(6,2),
    Arousal_audio    NUMERIC(6,2),
    Mean_Deviation_audio NUMERIC(6,2),  
    text TEXT,
    assistant TEXT,
    workshift VARCHAR(10),
    fname TEXT;
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    UNIQUE (user_id, timestamp)
);


CREATE TABLE IF NOT EXISTS self_reports (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    joy INTEGER,
    sadness INTEGER,
    anger INTEGER,
    surprise INTEGER,
    stress_level INTEGER,
    fatigue INTEGER,
    anxiety INTEGER,
    current_state INTEGER,
    previous_state INTEGER,
    health_issues TEXT,
    event_details TEXT,
    fatigue_reason TEXT,
    stress_reason TEXT,
    anxiety_reason TEXT,
    stress_duration TEXT,
    fatigue_duration TEXT,
    anxiety_duration TEXT
);