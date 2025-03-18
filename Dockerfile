FROM python:3.13

WORKDIR /app

COPY . /app

RUN pip install -r requirements.txt

CMD["python", "src/bot.py"]
