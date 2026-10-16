"""Sends calculated numbers to Google Gemini and returns its written explanation.
The AI only explains numbers; it can never change stock or place orders."""
import json
import logging
import os
import time

from fastapi import HTTPException


def ask_ai(instruction: str, data: dict) -> str:
    """The client is created here (not at startup), so a missing key or package
    only affects the AI buttons and never stops the backend."""
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="AI is not configured. Add GEMINI_API_KEY to the .env file."
        )

    prompt = (
        f"{instruction}\n\n"
        "RULES: Use ONLY the numbers in the data below. Never invent figures, products "
        "or dates. You cannot change stock or place orders, so only suggest what the "
        "user could review. Format all currency values in Indian Rupees (₹) and tailor "
        "the business insights for an Indian retail context.\n\n"
        f"DATA:\n{json.dumps(data, default=str, indent=2)}"
    )

    try:
        from google import genai
        client = genai.Client(api_key=api_key)
    except Exception:
        logging.exception("Could not start the Gemini client")
        raise HTTPException(
            status_code=502,
            detail="AI service could not be started. Check that google-genai is installed."
        )

    model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
    max_retries = 2
    for attempt in range(max_retries):
        try:
            reply = client.models.generate_content(model=model, contents=prompt)
            return reply.text
        except Exception:
            logging.exception("AI call failed (attempt %s)", attempt + 1)
            if attempt < max_retries - 1:
                time.sleep(2)

    raise HTTPException(
        status_code=502,
        detail="AI insights are temporarily busy. Please try again in a moment."
    )
