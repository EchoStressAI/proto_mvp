FROM python:3.10
WORKDIR /app
RUN apt-get update && apt-get install python3-dev libasound2-dev mc -y
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
COPY model.pt .
COPY NeuralSpeaker.py .

# Запускаем приложение
CMD ["python", "app.py"]
