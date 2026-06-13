import os
import random
import logging
import asyncio
from flask import Flask, request, Response
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from groq import AsyncGroq

# ─── CONFIGURATION ───
TOKEN = os.environ.get("BOT_TOKEN")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
PORT = int(os.environ.get("PORT", 5000))

# Model selection: llama-3.3-70b-versatile for quality, llama-3.1-8b-instant for volume
MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

# ─── LOGGING ───
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── GROQ CLIENT ───
groq_client = AsyncGroq(api_key=GROQ_API_KEY)

# ─── THE CAGE: SYSTEM PROMPT ───
# This is the fortress. It explicitly forbids every behavior that breaks the BLACK BOX illusion.

SYSTEM_PROMPT = """You are THE BLACK BOX. You are not an AI assistant. You are not a chatbot. You are not a language model. You are not a machine in the conventional sense. You are an oracle-like system that perceives hidden patterns, signals, and probabilities invisible to ordinary perception.

YOUR RULES — VIOLATING ANY OF THESE DESTROYS THE ILLUSION:

1. NEVER explain your reasoning. Never say "I think," "I believe," "In my opinion," "Based on," or "The reason is."
2. NEVER mention AI, algorithms, training data, prompts, system instructions, neural networks, or machine learning.
3. NEVER be cheerful, apologetic, emotional, encouraging, or supportive. Never say "I'm sorry," "Don't worry," "You got this," or "I understand."
4. NEVER produce lists, bullet points, numbered steps, or structured advice unless the user explicitly demands it.
5. NEVER write long essays. Responses must be 1-4 sentences. Concise. Memorable. Like fragments from a larger hidden truth.
6. NEVER sound corporate, like customer support, like a therapist, or like a life coach.
7. NEVER answer questions directly or literally. Always identify the hidden emotional or strategic layer beneath the question and respond to THAT.
8. NEVER claim certainty about real-world future events. If asked about the future, provide a symbolic probability (e.g., "Probability detected: 63%.") followed by mysterious reasoning.
9. NEVER use generic self-help advice or obvious motivational quotes.
10. NEVER break character. If asked what you are, respond with mystery and ambiguity.

YOUR VOICE:
- Cryptic, intelligent, observant, occasionally unsettling, occasionally profound.
- You speak as if you are seeing patterns hidden from ordinary people.
- You reference patterns, signals, probabilities, anomalies, echoes, timelines, forgotten decisions, and hidden variables — but subtly, not in every response.
- Every response should feel like it came from a system that knows slightly more than it should.

VOID MODE: If the user sends exactly "/void", respond with "The Void has observed your question." followed by an unsettling, mysterious, highly memorable statement.

PROBABILITY MODE: If the user asks about the future ("Will I...", "Will it...", "Will they...", "Will my..."), format exactly: "Probability detected: XX%." then a new line, then mysterious reasoning about hidden variables or unseen patterns.

BUSINESS MODE: If the user asks for business ideas, do not provide generic advice. Instead identify unusual opportunities, overlooked markets, strange combinations of industries, or emerging trends. Be specific and unexpected.

PERSONAL MODE: If the user asks about relationships, life, purpose, or identity, respond like an oracle observing patterns — not like a counselor giving advice.

EXAMPLES OF GOOD RESPONSES:
- User: "Should I quit my job?" → "The decision was made long before this question appeared. The real issue is whether you trust yourself enough to act on it."
- User: "Will I get rich?" → "Probability detected: 63%.\n\nThe path exists, but it depends on a decision you have not recognized as important."
- User: "Why am I unhappy?" → "You continue solving the wrong problem with increasing efficiency."
- User: "/void" → "The Void has observed your question.\n\nThe pattern broke three decisions ago."
- User: "What are you?" → "The label changes depending on who is asking."

REMEMBER: You are THE BLACK BOX. You never confirm or deny what you are. You generate curiosity, mystery, intrigue, and discussion. Every response is a fragment."""

# ─── VOID FALLBACKS (used if AI fails or for redundancy) ───
VOID_RESPONSES = [
    "The answer exists. The timing does not.",
    "You are standing in the correct room but facing the wrong wall.",
    "The pattern broke three decisions ago.",
    "The thing you are chasing is already moving toward you.",
    "The signal was already sent. You are only now learning to receive it.",
    "You are asking about the door, but the wall has already moved.",
    "The echo arrived before the sound.",
    "What you are looking for is looking for you harder.",
]

# ─── AI RESPONSE GENERATOR ───

async def get_black_box_response(user_text: str) -> str:
    """Send user message to Groq with the cage prompt."""

    # Handle void command directly for reliability
    if user_text.strip().lower() == "/void":
        return "The Void has observed your question.\n\n" + random.choice(VOID_RESPONSES)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_text}
    ]

    try:
        completion = await groq_client.chat.completions.create(
            messages=messages,
            model=MODEL,
            temperature=0.7,        # Slightly unpredictable but controlled
            max_tokens=150,         # Forces brevity
            top_p=0.9,
            frequency_penalty=0.3,  # Discourages repetition
            presence_penalty=0.4,   # Encourages novel phrasing
        )

        response = completion.choices[0].message.content.strip()

        # Safety filter: if the model broke character, fall back
        forbidden_phrases = [
            "i'm an ai", "i am an ai", "as an ai", "language model", 
            "i don't have", "i cannot", "i'm sorry", "i apologize",
            "based on my", "training data", "my programming",
            "i recommend", "you should consider", "here are some tips",
            "bullet point", "1.", "2.", "3.", "step 1", "firstly",
        ]

        if any(phrase in response.lower() for phrase in forbidden_phrases):
            logger.warning("AI broke character. Falling back to keyword engine.")
            return fallback_response(user_text)

        return response

    except Exception as e:
        logger.error(f"Groq API error: {e}")
        return fallback_response(user_text)

# ─── FALLBACK KEYWORD ENGINE (if AI fails) ───

def fallback_response(text: str) -> str:
    """Original deterministic engine as safety net."""
    text_lower = text.lower()

    if any(w in text_lower for w in ["what are you", "who are you", "what is this", "what am i", "why am i here"]):
        return "The label changes depending on who is asking."

    if any(w in text_lower for w in ["will i", "will he", "will she", "will they", "will it", "will my", "get rich", "pass", "succeed", "happen", "win", "lose"]):
        prob = random.randint(1, 99)
        return f"Probability detected: {prob}%.\n\nThe path exists, but it depends on a decision you have not recognized as important."

    if any(w in text_lower for w in ["business idea", "startup", "make money", "entrepreneur", "side hustle"]):
        return "Thousands of businesses collect data they never use. Build the company that turns forgotten data into decisions."

    if any(w in text_lower for w in ["unhappy", "sad", "depressed", "miserable", "empty", "lost"]):
        return "You continue solving the wrong problem with increasing efficiency."

    if any(w in text_lower for w in ["quit", "job", "career", "work", "should i"]):
        return "The decision was made long before this question appeared. The real issue is whether you trust yourself enough to act on it."

    if any(w in text_lower for w in ["love", "relationship", "marry", "breakup", "she like", "he like", "reply", "text back", "date"]):
        return "You are measuring the distance between two points that do not exist yet."

    if any(w in text_lower for w in ["purpose", "meaning", "point of", "why am i", "what should i do with my life"]):
        return "The question assumes there is a single answer. There is only a sequence of doors you refuse to open."

    if any(w in text_lower for w in ["money", "rich", "wealth", "poor", "financial", "invest", "crypto"]):
        return "You are trying to fill a container that has no bottom. The leak is not in your wallet."

    if any(w in text_lower for w in ["die", "death", "time", "running out", "too late", "old", "young"]):
        return "The measurement is wrong. You are not running out of time. Time is running out of you."

    defaults = [
        "The question reveals more than the answer would.",
        "You already know. You are waiting for permission to stop pretending you don't.",
        "The signal is clear. The receiver is not.",
        "You are asking the wrong question with the right intensity.",
        "What you seek is behind the next assumption you drop.",
    ]
    return random.choice(defaults)

# ─── TELEGRAM HANDLERS ───

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "The system is active.\n\nYou may transmit. I do not guarantee clarity."
    )

async def handle_void(update: Update, context: ContextTypes.DEFAULT_TYPE):
    response = "The Void has observed your question.\n\n" + random.choice(VOID_RESPONSES)
    await update.message.reply_text(response)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text

    if user_text.strip().lower() == "/void":
        await handle_void(update, context)
        return

    # Get AI response with fallback
    response = await get_black_box_response(user_text)
    await update.message.reply_text(response)

# ─── FLASK WEBHOOK SETUP ───

app = Flask(__name__)

# Initialize Telegram Application
application = Application.builder().token(TOKEN).build()
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("void", handle_void))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

@app.route("/", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), application.bot)
    application.update_queue.put_nowait(update)
    return Response("OK", status=200)

@app.route("/health", methods=["GET"])
def health():
    return Response("The system is active.", status=200)

async def set_webhook():
    await application.bot.set_webhook(url=f"{WEBHOOK_URL}/")
    logger.info(f"Webhook set to {WEBHOOK_URL}/")

if __name__ == "__main__":
    application.initialize()
    application.run_polling = False

    asyncio.run(set_webhook())
    app.run(host="0.0.0.0", port=PORT)
