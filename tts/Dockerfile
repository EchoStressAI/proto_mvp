FROM python:3.10
WORKDIR /app
RUN apt-get update && apt-get install python3-dev libasound2-dev mc -y
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py .
COPY model.pt .
COPY NeuralSpeaker.py .
CMD [ "python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8300", "--workers", "1", "--proxy-headers"]
