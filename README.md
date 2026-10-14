# HRITU (ঋতু)

**A bilingual chatbot that supports young women in Bangladesh living with PCOS.**

HRITU talks in Bangla, English and Banglish, like a caring older sister. It is built for an HCI user-testing study at BRAC University. Its design is informed by our earlier study of Bangladeshi PCOS/PMOS Facebook support groups, where women asked for reliable information, emotional support and practical everyday help.

HRITU is an AI, not a doctor. It never diagnoses and never suggests medicines.

**Live demo:** _add the Render link here_

## What a user can do

| Module | What it does |
|---|---|
| **PCOS check** | 18 short questions. A small machine-learning model shows how many PCOS signs her answers match, and explains why. It always says: please see a doctor. |
| **Talk** | A safe space to share feelings. Replies are warm and supportive. |
| **Lifestyle** | Small, safe tips on sleep, activity, stress and food (with Bangladeshi food examples). |
| **Learn cycle** | Short lessons on the 4 phases of the menstrual cycle, a mini quiz, then free questions. |

## How it answers

1. It searches its own health facts first (`knowledge_base/pcos_knowledge.json`, 68 topics in Bangla and English).
2. If those facts don't cover the question, it searches trusted health websites (WHO, NHS, CDC, MedlinePlus...) through Google Search and shows the source links.
3. The AI model writes the reply. It can use **Gemini** (Google, online) or **Llama / Gemma** (running locally with Ollama). If one fails, the other is used as backup.

## Safety and privacy

- **Crisis words** (self-harm, suicide) get an immediate reply with Bangladeshi helpline numbers.
- **Medicine questions** get a "please ask a doctor" note.
- **Off-topic** requests are politely redirected.
- **Personal details** (names, phone numbers, emails, ID numbers, addresses) are hidden before any text goes to an AI model or into the logs.
- Logs are de-identified. Online, they wait briefly in a private Google Sheet, then `sync_logs.py` moves them to the researcher's laptop and deletes them from the sheet.
- Each chat is remembered for 30 days, so a user can come back to the same conversation.

## Files

| File | Job |
|---|---|
| `main.py` | The web server (FastAPI). Start here. |
| `webpage_interface.html` | The chat page (works on phones). |
| `bot.py` | Decides which module answers each message. |
| `pcos_check.py`, `talk_sister.py`, `lifestyle.py`, `learn.py` | The 4 modules. |
| `knowledge_search.py` | Finds facts, and searches the web when needed. |
| `AI_models.py` | Connects to Gemini and Ollama. |
| `safety_rules.py` | Crisis, medicine and off-topic rules. |
| `privacy_rule.py` | Hides personal details and saves logs. |
| `sync_logs.py`, `google_sheet_script.js` | Move logs from the Google Sheet to the laptop. |
| `screening_model/` | The trained screening model and the script that trained it. |
| `ONLINE_SETUP.md` | How to put HRITU online (Render + Google Sheet). |

## Run it on your computer

You need Python 3.12 and a free Gemini API key from Google AI Studio.

```
python -m venv venv
venv\Scripts\activate          (Mac/Linux: source venv/bin/activate)
pip install -r requirements.txt
```

Copy `.env.example` to a new file called `.env` and put your own Gemini key in it. To use only Gemini, set `MAIN_MODEL=gemini`.

```
uvicorn main:app --reload
```

Then open http://localhost:8000

## Before real users

- A doctor must review the health facts in the knowledge base.
- The study needs ethics approval and informed consent. Participants are told that messages are processed by Google Gemini and an online server.

## Author

Umme Jannat Taposhi, BRAC University
