# Python 3.10 slim 이미지 사용
FROM python:3.10-slim

# 작업 디렉터리 설정
WORKDIR /app

# 시스템 의존성 설치
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python 의존성 먼저 복사 (캐싱 최적화)
COPY requirements.txt .

# 의존성 설치
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 애플리케이션 코드 복사
COPY . .

# RQ Worker 실행
CMD ["python", "start_worker.py", "--mode", "basic", "--scaling", "false"]