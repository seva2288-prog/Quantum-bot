from flask import Flask, request
import requests
import math
import json
import os
from datetime import datetime, timedelta
import threading
import time
import logging
from logging.handlers import RotatingFileHandler
from typing import Dict, List, Optional, Tuple, Any
from dotenv import load_dotenv
from functions import *

load_dotenv()

app = Flask(__name__)

# ===== КОНФИГ =====
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN', "8757780924:AAEteceqwZmFDCpWJUZBj-gwc1DGCl-dv74")
FOOTBALL_API_KEY = os.getenv('FOOTBALL_API_KEY', "b6a8c1fcee6769a0fa3b0efd9be476")
WEATHER_API_KEY = os.getenv('WEATHER_API_KEY', "7f0cfaed346b0fe364815ab65d627af2")
ADMIN_CHAT_ID = os.getenv('ADMIN_CHAT_ID', "228801334")

# ===== ЛОГИ =====
def setup_logging():
    os.makedirs('logs', exist_ok=True)
    logger = logging.getLogger('betting_bot')
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler = RotatingFileHandler('logs/bot.log', maxBytes=10*1024*1024, backupCount=5)
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return logger

logger = setup_logging()
logger.info("🚀 БОТ ЗАПУЩЕН!")

# ===== НАСТРОЙКИ =====
SETTINGS = {
    "improved_form": True,
    "referee": True,
    "odds_movement": True,
    "psy_factor": True,
    "neural_learning": True,
    "inversion_mode": False,
    "full_mode": False,
}

# ===== ФАЙЛЫ =====
CACHE_FILE = "cache.json"
HISTORY_FILE = "history.json"
WEIGHTS_FILE = "weights.json"
BANK_FILE = "bank.json"
ODDS_HISTORY_FILE = "odds_history.json"
PRIOR_FILE = "prior.json"
DIVERGENCE_FILE = "divergence.json"

def load_bank():
    if os.path.exists(BANK_FILE):
        with open(BANK_FILE, "r") as f:
            return json.load(f).get("bank", 1000)
    return 1000

def save_bank(bank):
    with open(BANK_FILE, "w") as f:
        json.dump({"bank": bank, "updated": datetime.now().isoformat()}, f)

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r") as f:
            return json.load(f)
    return []

def save_history(history):
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)

def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r") as f:
            return json.load(f)
    return None

def save_cache(data):
    data["last_update"] = datetime.now().isoformat()
    with open(CACHE_FILE, "w") as f:
        json.dump(data, f, indent=2)

def load_weights():
    if os.path.exists(WEIGHTS_FILE):
        with open(WEIGHTS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_weights(weights):
    with open(WEIGHTS_FILE, "w") as f:
        json.dump(weights, f, indent=2)

def load_odds_history():
    if os.path.exists(ODDS_HISTORY_FILE):
        with open(ODDS_HISTORY_FILE, "r") as f:
            return json.load(f)
    return {}

def save_odds_history(data):
    with open(ODDS_HISTORY_FILE, "w") as f:
        json.dump(data, f, indent=2)

def load_prior():
    if os.path.exists(PRIOR_FILE):
        with open(PRIOR_FILE, "r") as f:
            return json.load(f)
    return {"home": 1.5, "away": 1.3, "count": 0}

def save_prior(prior):
    with open(PRIOR_FILE, "w") as f:
        json.dump(prior, f, indent=2)

def load_divergence():
    if os.path.exists(DIVERGENCE_FILE):
        with open(DIVERGENCE_FILE, "r") as f:
            return json.load(f)
    return {"total": 0, "wins": 0, "losses": 0, "history": []}

def save_divergence(data):
    with open(DIVERGENCE_FILE, "w") as f:
        json.dump(data, f, indent=2)

def send_telegram(text):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": ADMIN_CHAT_ID, "text": text, "parse_mode": "HTML"}
        requests.post(url, json=data, timeout=10)
    except Exception as e:
        logger.error(f"Send error: {e}")

def send_telegram_with_buttons(text, bet_id):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {
            "chat_id": ADMIN_CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
            "reply_markup": {
                "inline_keyboard": [
                    [{"text": "✅ Зашло", "callback_data": f"win_{bet_id}"},
                     {"text": "❌ Не зашло", "callback_data": f"loss_{bet_id}"}],
                    [{"text": "↩️ Возврат", "callback_data": f"push_{bet_id}"}]
                ]
            }
        }
        requests.post(url, json=data, timeout=10)
    except Exception as e:
        logger.error(f"Send buttons error: {e}")

# ===== ВСЕ ЛИГИ =====
LEAGUES = [
    39, 140, 78, 135, 61, 40, 141, 79, 136, 62,
    2, 3, 848, 88, 89, 94, 203, 197, 345, 106,
    207, 90, 242, 272, 276, 283, 288, 253, 289,
    290, 291, 179, 218, 240, 1, 12, 45, 46, 47, 48, 50,
    71, 128, 169, 172, 176, 138, 139, 144, 148, 149,
    142, 137, 140, 250, 251, 252, 260, 261, 262,
    263, 264, 265, 266, 267
]

LEAGUE_NAMES = {
    39: "АПЛ", 140: "Ла Лига", 78: "Бундеслига", 135: "Серия А", 61: "Лига 1",
    40: "Чемпионшип", 141: "Ла Лига 2", 79: "2. Бундеслига", 136: "Серия В", 62: "Лига 2",
    2: "ЛЧ", 3: "ЛЕ", 848: "ЛК",
    88: "Эредивизи", 89: "Про Лига", 94: "Примейра", 203: "Греция", 197: "Турция",
    345: "Швейцария", 106: "Австрия", 207: "Шотландия",
    90: "РПЛ", 242: "Чехия", 272: "Польша", 276: "Украина", 283: "Хорватия",
    288: "Сербия", 253: "Румыния", 289: "Болгария", 290: "Словакия", 291: "Словения",
    179: "Дания", 218: "Норвегия", 240: "Швеция",
    1: "Кубок мира", 12: "Кубок Англии", 45: "Кубок Испании",
    46: "Кубок Германии", 47: "Кубок Италии", 48: "Кубок Франции", 50: "Кубок Лиги",
    71: "Бразилейрао", 128: "Аргентина", 169: "Уругвай", 172: "Чили", 176: "Колумбия",
    138: "J1 Лига", 139: "K Лига", 144: "Саудовская Аравия", 148: "ОАЭ", 149: "Катар",
    142: "Liga MX", 137: "Египет", 140: "ЮАР",
    250: "Кипр", 251: "Исландия", 252: "Финляндия",
    260: "Албания", 261: "Македония", 262: "Грузия",
    263: "Армения", 264: "Азербайджан", 265: "Казахстан",
    266: "Узбекистан", 267: "Беларусь"
}

# ===== ОТПРАВКА УВЕДОМЛЕНИЯ =====
last_notified_bets = {}

def send_bet_notification(bet):
    global last_notified_bets
    
    if not bet:
        return
    
    if bet['ev'] < 1:
        return
    
    key = f"{bet['fixture_id']}_{bet['bet_type']}"
    if key in last_notified_bets and last_notified_bets[key] == bet['ev']:
        return
    
    last_notified_bets[key] = bet['ev']
    
    msg = f"""🔥 <b>ВАЛУЙНАЯ СТАВКА!</b>

🏟️ {bet['home']} vs {bet['away']}
🏆 {bet['league']}

🎯 <b>{bet['bet']}</b>
📈 КЭФ: {bet['odds']}
💰 СТАВКА: ${bet['stake']:.2f}
📊 ВЕРОЯТНОСТЬ: {bet['prob']}%
📈 EV: <b>{bet['ev']}%</b>

📊 xG: {bet['home_xg']} : {bet['away_xg']}
🌤️ {bet.get('weather_reason', '☀️ Без погоды')}"""

    if bet.get('weather'):
        w = bet['weather']
        msg += f"\n🌡️ {w['weather_ru']}, {w['temp']}°C"
    
    bet_id = f"{bet['fixture_id']}_{bet['bet_type']}_{int(time.time())}"
    send_telegram_with_buttons(msg, bet_id)
    
    history = load_history()
    bet['id'] = bet_id
    bet['result'] = 'pending'
    bet['date'] = datetime.now().strftime("%Y-%m-%d %H:%M")
    history.append(bet)
    save_history(history)

# ================================================================
# !!! АВТОМАТИЧЕСКОЕ ОБНОВЛЕНИЕ ПОЛНОСТЬЮ ОТКЛЮЧЕНО !!!
# ================================================================

# ===== ВЕБХУК =====
@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.get_json()
        logger.info(f"📨 ВЕБХУК: {data}")
        
        if data and 'callback_query' in data:
            callback = data['callback_query']
            bet_id = callback['data'].split('_')[1]
            result = callback['data'].split('_')[0]
            
            history = load_history()
            for bet in history:
                if str(bet.get('id')) == bet_id:
                    bet['result'] = result
                    bet['date'] = datetime.now().strftime("%Y-%m-%d %H:%M")
                    
                    bank = load_bank()
                    if result == 'win':
                        profit = bet.get('stake', 0) * (bet.get('odds', 1) - 1)
                        save_bank(bank + profit)
                        send_telegram(f"✅ Зашло! +${profit:.2f}")
                    elif result == 'loss':
                        stake = bet.get('stake', 0)
                        save_bank(bank - stake)
                        send_telegram(f"❌ Не зашло! -${stake:.2f}")
                    elif result == 'push':
                        send_telegram(f"↩️ Возврат")
                    break
            
            save_history(history)
            
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/answerCallbackQuery"
            requests.post(url, json={"callback_query_id": callback['id'], "text": "✅ OK"})
            return "ok"
        
        if data and 'message' in data:
            text = data['message'].get('text', '')
            chat_id = data['message']['chat']['id']
            
            logger.info(f"💬 СООБЩЕНИЕ: {text} от {chat_id}")
            
            if str(chat_id) != ADMIN_CHAT_ID:
                send_telegram("⛔ Нет доступа")
                return "ok"
            
            if text == '/start':
                send_telegram("""🚀 QUANTUM BETTING BOT v10 PRO

⚠️ АВТООБНОВЛЕНИЕ ОТКЛЮЧЕНО!

📋 КОМАНДЫ:
/today - Ставка из кеша
/update - РУЧНОЙ поиск
/bank - Банк
/stats - Статистика
/leagues - Лиги
/mode - Режим
/inversion - Инверсия
/help - Помощь""")
            
            elif text == '/update':
                send_telegram("🔄 Поиск матчей с учётом погоды...")
                matches = get_matches_with_factors(FOOTBALL_API_KEY)
                if matches:
                    bet = find_best_bet(matches, FOOTBALL_API_KEY, load_bank, send_bet_notification)
                    save_cache({"best_bet": bet})
                    if bet:
                        send_bet_notification(bet)
                        send_telegram(f"✅ Найдена ставка! EV: {bet['ev']}%")
                    else:
                        send_telegram("❌ Ставок с EV > 5% нет")
                else:
                    send_telegram("⚠️ Матчей не найдено, использую тестовые")
                    test_matches = get_test_matches()
                    bet = find_best_bet(test_matches, FOOTBALL_API_KEY, load_bank, send_bet_notification)
                    save_cache({"best_bet": bet})
                    if bet:
                        send_bet_notification(bet)
            
            elif text == '/today':
                cache = load_cache()
                if cache and cache.get("best_bet"):
                    send_bet_notification(cache["best_bet"])
                else:
                    send_telegram("❌ Нет ставок. /update")
            
            elif text == '/bank':
                bank = load_bank()
                send_telegram(f"💰 БАНК\n${bank:.2f}")
            
            elif text == '/stats':
                history = load_history()
                if not history:
                    send_telegram("📭 Нет данных")
                else:
                    total = len(history)
                    wins = sum(1 for b in history if b.get('result') == 'win')
                    losses = sum(1 for b in history if b.get('result') == 'loss')
                    winrate = wins / (wins + losses) * 100 if (wins + losses) > 0 else 0
                    send_telegram(f"""📊 СТАТИСТИКА
Всего: {total}
✅ Выигрышей: {wins}
❌ Проигрышей: {losses}
🎯 Проходимость: {round(winrate, 1)}%""")
            
            elif text == '/leagues':
                msg = "📊 ЛИГИ\n\n"
                count = 0
                for league_id, name in LEAGUE_NAMES.items():
                    msg += f"• {name} (ID: {league_id})\n"
                    count += 1
                    if count >= 30:
                        break
                msg += f"\n...и ещё {len(LEAGUE_NAMES) - 30} лиг"
                send_telegram(msg)
            
            elif text == '/mode':
                SETTINGS['full_mode'] = not SETTINGS['full_mode']
                mode = "ПОЛНЫЙ" if SETTINGS['full_mode'] else "КРАТКИЙ"
                send_telegram(f"📋 Режим: {mode}")
            
            elif text == '/inversion':
                SETTINGS['inversion_mode'] = not SETTINGS['inversion_mode']
                status = "ВКЛЮЧЕНА" if SETTINGS['inversion_mode'] else "ВЫКЛЮЧЕНА"
                send_telegram(f"🔄 Инверсия {status}!")
            
            elif text == '/help':
                send_telegram("""📖 КОМАНДЫ:
/today - Ставка
/update - Поиск
/bank - Банк
/stats - Статистика
/leagues - Лиги
/mode - Режим
/inversion - Инверсия
/help - Помощь""")
            
            else:
                send_telegram("❌ Неизвестная команда. /help")
        
        return "ok"
    except Exception as e:
        logger.error(f"❌ Webhook error: {e}")
        return "error", 500

@app.route('/', methods=['GET'])
def index():
    cache = load_cache()
    bet = cache.get("best_bet") if cache else None
    status = f"Ставка: {bet['bet']} EV:{bet['ev']}%" if bet else "Нет ставки"
    return f"🤖 Quantum Bot v10 PRO | АВТО-ОБНОВЛЕНИЕ ОТКЛЮЧЕНО | {status} | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

@app.route('/health', methods=['GET'])
def health():
    return {"status": "ok", "time": datetime.now().isoformat()}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    logger.info(f"🚀 Запуск на порту {port}")
    logger.info(f"📊 Загружено лиг: {len(LEAGUES)}")
    logger.info("=" * 50)
    logger.info("⚠️ АВТОМАТИЧЕСКОЕ ОБНОВЛЕНИЕ ОТКЛЮЧЕНО!")
    logger.info("📌 Бот НЕ делает запросы к API автоматически")
    logger.info("📌 Только по команде /update")
    logger.info("=" * 50)
    app.run(host='0.0.0.0', port=port)
