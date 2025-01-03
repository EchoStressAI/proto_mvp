from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import os
from tempfile import NamedTemporaryFile
from scipy.io import wavfile
from pywhispercpp.model import Model
import numpy as np
import re

model = Model('model.bin', n_threads=6,)

app = FastAPI()




@app.post("/process-audio/")
async def process_audio(file: UploadFile = File(...), phrases: str = Form(...)):
    """
    Обработка аудиофайла.
    """
    if file.content_type != "audio/wav":
        raise HTTPException(status_code=400, detail="Файл должен быть в формате WAV.")

    try:
        #Сохранение временного файла для обработки
        with NamedTemporaryFile(delete=False, suffix=".wav") as temp_file:
            temp_file.write(await file.read())
            temp_file_path = temp_file.name

        response = model.transcribe(temp_file_path, language="ru")
        print("response=",response)        

        # Регулярное выражение для извлечения значения text
        match = re.search(r"text=([^,]+)]", str(response))
        if match:
            recognized_text = match.group(1)
            print("Extracted text:", recognized_text)
        else:
            print("Text not found")
        
        return JSONResponse(content={
            "recognized_text": recognized_text,
        })
    finally:
        # Удаляем временный файл
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
