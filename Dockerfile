FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    PYTHONIOENCODING=utf-8

WORKDIR /app

COPY --chown=user:user requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

COPY --chown=user:user . .

# Download voice models (one-time, baked into the image)
RUN python -m piper.download_voices --download-dir voices \
    en_US-lessac-medium en_US-amy-medium hi_IN-priyamvada-medium hi_IN-pratham-medium

# Download the English-to-Hindi translation model (one-time, baked into the image)
RUN python -c "\
import argostranslate.package; \
argostranslate.package.update_package_index(); \
pkg = next(p for p in argostranslate.package.get_available_packages() if p.from_code=='en' and p.to_code=='hi'); \
argostranslate.package.install_from_path(pkg.download())"

ENV PORT=7860
EXPOSE 7860

CMD ["python", "app.py"]
