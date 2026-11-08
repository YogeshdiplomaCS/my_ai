# YogeshAI

A desktop AI chat app built with Kivy and OpenRouter. It provides model selection, quick prompts, settings, and chat history for the current session.

## Requirements

- Python 3
- An OpenRouter API key for live requests

## Install and run

```bash
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

The `OPENROUTER_API_KEY` value currently in `main.py` is a fake placeholder, not a valid key. For local testing, replace it locally with your own key, but do not commit real credentials. A future improvement is to load it from an environment variable.

Chat history is stored only in memory and is lost when the app closes. Check the provider's current model availability and pricing before use.
