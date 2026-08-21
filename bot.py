from flask import Flask, request
import requests
import json
import os
from datetime import datetime
import logging

app = Flask(__name__)

# ===== КОНФИГ =====
TELEGRAM_TOKEN = "8757780924:AAEteceqwZmFDCpWJUZBj-gwc1DGCl-dv74"
FOOTBALL_API_KEY = "de3e69cf50436633fe4d327831c71ece"
ADMIN_CHAT_ID = "228801334"

# ===== ЛОГИ =====
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ===== ФАЙЛЫ =====
BANK_FILE = "bank.json"
HISTORY_FILE = "history.json"
CACHE_FILE = "cache.json"

def load_bank():
    if os.path.exists(BANK_FILE):
        with open(BANK_FILE, "r") as f:
            return json.load(f).get("bank", 1000)
    return 1000

def save_bank(bank):
    with open(BANK_FILE, "w") as f:
        json.dump({"bank": bank}, f)

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
    with open(CACHE_FILE, "w") as f:
        json.dump(data, f, indent=2)

# ===== ОТПРАВКА =====
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
                     {"text": "❌ Не зашло", "callback_data": f"loss_{bet_id}"}]
                ]
            }
        }
        requests.post(url, json=data, timeout=10)
    except Exception as e:
        logger.error(f"Send buttons error: {e}")

# ===== ПРЯМОЙ ЗАПРОС К API =====
def test_api():
    today = datetime.now().strftime('%Y-%m-%d')
    league_id = 39  # АПЛ
    season = "2026"
    
    url = f"https://v3.football.api-sports.io/fixtures?league={league_id}&season={season}&date={today}"
    headers = {"x-rapidapi-key": FOOTBALL_API_KEY}
    
    logger.info(f"🔍 ЗАПРОС: {url}")
    logger.info(f"🔑 КЛЮЧ: {FOOTBALL_API_KEY[:10]}...")
    
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        logger.info(f"📡 ОТВЕТ: статус {resp.status_code}")
        logger.info(f"📄 ТЕЛО: {resp.text[:500]}")
        
        if resp.status_code == 200:
            data = resp.json()
            if data.get("response"):
                logger.info(f"✅ НАЙДЕНО МАТЧЕЙ: {len(data['response'])}")
                return data["response"]
            else:
                logger.warning("⚠️ МАТЧЕЙ НЕТ")
                return []
        else:
            logger.error(f"❌ ОШИБКА: {resp.status_code} - {resp.text}")
            return None
    except Exception as e:
        logger.error(f"❌ ИСКЛЮЧЕНИЕ: {e}")
        return None

# ===== ПРОСТАЯ СТАВКА =====
def make_bet(matches):
    if not matches:
        return None
    match = matches[0]
    home = match["teams"]["home"]["name"]
    away = match["teams"]["away"]["name"]
    league = "АПЛ"
    return {
        "home": home,
        "away": away,
        "league": league,
        "fixture_id": match["fixture"]["id"],
        "bet": "ОЗ - ДА",
        "odds": 1.85,
        "prob": 55.0,
        "ev": 8.7,
        "stake": 10.0,
        "home_xg": 1.5,
        "away_xg": 1.3,
    }

# ===== ВЕБХУК =====
@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.get_json()
        
        if data and 'callback_query' in data:
            callback = data['callback_query']
            bet_id = callback['data'].split('_')[1]
            result = callback['data'].split('_')[0]
            
            history = load_history()
            for bet in history:
                if str(bet.get('id')) == bet_id:
                    bet['result'] = result
                    bank = load_bank()
                    if result == 'win':
                        profit = bet.get('stake', 0) * (bet.get('odds', 1) - 1)
                        save_bank(bank + profit)
                        send_telegram(f"✅ Зашло! +${profit:.2f}")
                    elif result == 'loss':
                        stake = bet.get('stake', 0)
                        save_bank(bank - stake)
                        send_telegram(f"❌ Не зашло! -${stake:.2f}")
                    break
            save_history(history)
            return "ok"
        
        if data and 'message' in data:
            text = data['message'].get('text', '')
            chat_id = data['message']['chat']['id']
            
            if str(chat_id) != ADMIN_CHAT_ID:
                send_telegram("⛔ Нет доступа")
                return "ok"
            
            if text == '/start':
                send_telegram("""🚀 QUANTUM BETTING BOT - ТЕСТ API

📋 КОМАНДЫ:
/update - ПРЯМОЙ запрос к API
/bank - Банк
/help - Помощь""")
            
            elif text == '/update':
                send_telegram("🔄 Делаю прямой запрос к API...")
                
                matches = test_api()
                
                if matches is None:
                    send_telegram("❌ Ошибка запроса к API. Проверь логи на Render.")
                elif len(matches) == 0:
                    send_telegram("⚠️ Матчей сегодня нет.")
                else:
                    bet = make_bet(matches)
                    if bet:
                        send_telegram(f"""🔥 <b>ТЕСТОВАЯ СТАВКА (РЕАЛЬНЫЙ МАТЧ)</b>

🏟️ {bet['home']} vs {bet['away']}
🏆 {bet['league']}

🎯 {bet['bet']}
📈 КЭФ: {bet['odds']}
💰 СТАВКА: ${bet['stake']:.2f}
📊 EV: <b>{bet['ev']}%</b>""")
                        send_telegram("✅ API РАБОТАЕТ! Матчи найдены.")
                    else:
                        send_telegram("⚠️ Матчи есть, но ставка не сформирована.")
            
            elif text == '/bank':
                bank = load_bank()
                send_telegram(f"💰 БАНК\n${bank:.2f}")
            
            elif text == '/help':
                send_telegram("""📖 КОМАНДЫ:
/update - Проверить API
/bank - Банк
/help - Помощь""")
            
            else:
                send_telegram("❌ /help")
        
        return "ok"
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return "error", 500

@app.route('/', methods=['GET'])
def index():
    return f"🤖 Quantum Bot | Работает | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
