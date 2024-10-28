FROM python:3.8-slim

WORKDIR /app

COPY pyproject.toml .
COPY scribe_ai/ scribe_ai/

RUN pip install --no-cache-dir -e .

EXPOSE 8501

CMD ["streamlit", "run", "scribe_ai/frontend/app.py"]