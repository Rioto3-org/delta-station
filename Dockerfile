FROM python:3.12-slim

# タイムゾーン設定
ENV TZ=Asia/Tokyo
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 作業ディレクトリ
WORKDIR /app

# システム依存関係のインストール
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# uvのインストール
RUN pip install --no-cache-dir uv

# プロジェクトファイルのコピー（依存関係定義）
COPY pyproject.toml uv.lock* ./

# 依存関係のインストール
RUN uv sync --frozen || uv sync

# アプリケーションコードのコピー
COPY src/ ./src/
COPY database/ ./database/

# outputs ディレクトリの作成（ボリュームマウントされる）
RUN mkdir -p /app/outputs/database /app/outputs/images

# デフォルトコマンド（1回実行して終了）
CMD ["uv", "run", "python", "src/scraper.py"]
