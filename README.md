
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium


uvicorn main:app --reload
Приложение запустится на `http://localhost:8000`

Документация API: `http://localhost:8000/docs`

