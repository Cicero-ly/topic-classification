FROM python:3

ENV CRYPTOGRAPHY_DONT_BUILD_RUST=1

WORKDIR /usr/src/app

COPY requirements.txt ./

RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chmod +x start.sh

CMD [ "./start.sh"] 