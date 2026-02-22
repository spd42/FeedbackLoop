# MentorLoop

A local, no-UI app that:
- Reads content from `content/` (PDF, DOCX, TXT/MD, images, and `links.txt`)
- Uses OpenAI to generate a daily fun lesson from boring language textbooks and also generate anki cards and then uses Anki performance to reinforce next lessons
- Pulls recent failed cards from Anki (via AnkiConnect, optional)
- Exports a daily `.apkg` deck with `genanki`
- Emails the lesson + deck daily at whatever time you have scheduled it, can also be run ad hoc whenever you need so you don't have to rely on scheduler

## To-do/upcoming updates
- MCP to let the user chat with the service to see how autonomy would work in this system and to compare the results with this version 

## Quick Start

1. Create and activate a Python 3.11+ virtualenv.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
3. Copy env file and fill secrets:
   ```bash
   copy .env.example .env   
4. Get a free smtp server and Anki and ankiconnect and add the config in config.yaml (it is simple to setup, ask chatgpt)
5. Edit `config.yaml` for lesson/card size preferences.
6. Put content into `content/`:
   - PDFs, DOCX, TXT/MD, images
   - optional `links.txt` (one URL per line)
7. Run once:
   ```bash
   python run.py run-once
   ```
8. Run scheduler (6 AM daily):
   ```bash
   python run.py serve
   ```

## Content Tracking

The app stores progress in `state/state.json`:
- file fingerprint + number of units (pages/chunks)
- next unread unit per source
- next unread link index
- run history

If you add new files, they are automatically indexed. If a file changes, that source is re-indexed.

## Anki Wrong Cards

Install AnkiConnect add-on in desktop Anki and keep Anki open while running.
The app will try `http://127.0.0.1:8765` and fetch failed cards from recent days.
If unavailable, generation still works without this signal.

## Email

The app uses SMTP settings from `.env` and sends at scheduled time.
Attachment: generated `.apkg`
Body: lesson markdown/plaintext

## Notes

- OCR for images uses `pytesseract`; install Tesseract binary if you want OCR quality.
- Link extraction is best-effort and strips noisy HTML.
- PDF pages can also be analyzed with vision (`openai.enable_pdf_vision` in `config.yaml`) to capture diagrams/tables in addition to extracted text.
- Image files can also be analyzed with vision (`openai.enable_image_vision`) to capture diagrams/charts beyond OCR text.
