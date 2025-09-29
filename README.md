### Chemistry OCR → Word (FastAPI)

Приложение распознаёт химические реакции с изображений (OCR/ViT), нормализует текст и формирует Word-документы (DOCX). Веб‑интерфейс позволяет вставлять изображения из буфера обмена или загружать файлы, выбирать режим (OCR или ViT) и скачивать результат.

Основано на моделях Mistral AI:
- ViT: `pixtral-12b`, `pixtral-large-latest`
- Текстовая дообработка: `mistral-small-latest`
- OCR: `mistral-ocr-latest`


### Требования
- Python 3.10+
- Ключ API Mistral (`MISTRAL_API_KEY`), см. `https://console.mistral.ai`.

См. зависимости в `requirements.txt`:

```bash
pip install -r requirements.txt
```


### Быстрый старт
1) Установите зависимости в виртуальном окружении:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2) Запустите сервер (любой из вариантов):
```bash
# классический способ
uvicorn main:app --host 127.0.0.1 --port 8000 --reload

# или через вспомогательный скрипт
python start_server.py
```

3) Откройте браузер: `http://127.0.0.1:8000/`

4) Введите **Mistral API ключ** в UI (хранится только локально в файле `.api_key` рядом с кодом; можно удалить кнопкой в интерфейсе или вручную).

5) Загрузите изображения или вставьте из буфера, выберите режим и дождитесь генерации. Готовые DOCX появятся в списке результатов со ссылками на скачивание.


### Структура проекта (основное)
- `main.py` — FastAPI приложение: маршруты, отдача статики/шаблонов, загрузка/обработка изображений, скачивание DOCX.
- `start_server.py` — удобный запуск Uvicorn.
- `pipeline.py` — конвейер «изображение → текст → DOCX» с ViT/рефайном и базовым рендером.
- `ocr.py` — OCR через `mistral-ocr-latest` (Markdown/Text/JSON).
- `markdown_converter.py` — разбор Markdown/LaTeX‑подобных формул в DOCX с Open Sans.
- `chemistry_web_pipeline.py` — фасад/реэкспорт компонентов для веб‑приложения.
- `vision_extractor.py` — извлечение Markdown из изображений (Pixtral), опциональный рефайн.
- `templates/`, `static/` — веб‑UI (Jinja2, CSS/JS/иконки).




### REST API
- `POST /api/set-key`
  - Тело: `{ "api_key": "sk-..." }`
  - Сохраняет ключ локально.

- `POST /api/clear-key`
  - Очищает сохранённый ключ.

- `POST /api/process`
  - Форма `multipart/form-data`
    - `files`: одно или несколько изображений (`image/*`)
    - `pasted`: ноль или более data‑URL изображений (опционально)
    - `mode`: `OCR` или `ViT` (по умолчанию `ViT`)
    - `vit_model`: `pixtral-12b` или `pixtral-large-latest` (для `ViT`)
  - Ответ: `{ "documents": [{ "filename": string, "download_url": "/download/{token}" }] }`
