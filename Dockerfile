FROM python:3

WORKDIR /usr/src/app

COPY requirements.txt ./

RUN python3 -m venv .venv \
    && . .venv/bin/activate

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chmod +x start.sh

CMD [ "./start.sh"]