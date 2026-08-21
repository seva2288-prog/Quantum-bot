from flask import Flask, request
import requests
import math
import json
import os
from datetime import datetime
import time
import logging
from logging.handlers import RotatingFileHandler

app = Flask(__name__)

# ===== КОНФИГ =====
TELEGRAM_TOKEN = "8757780924:AAEteceqwZmFDCpWJUZBj-gwc1DGCl-dv74"
FOOTBALL_API_KEY = "de3e69cf50436633fe4d327831c71ece"
ADMIN_CHAT_ID = "228801334"

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

# ===== ФАЙЛЫ =====
CACHE_FILE = "cache.json"
HISTORY_FILE = "history.json"
BANK_FILE = "bank.json"

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

# ===== ЛИГИ (ТОЛЬКО ТЕ, ГДЕ ТОЧНО ЕСТЬ МАТЧИ) =====
LEAGUES = {
    39: "АПЛ",
    140: "Ла Лига",
    135: "Серия А",
    61: "Лига 1",
    71: "Бразилейрао",
    128: "Аргентина",
}

# ===== ПОЛУЧЕНИЕ МАТЧЕЙ =====
def get_matches():
    all_matches = []
    today = datetime.now().strftime('%Y-%m-%d')
    
    logger.info(f"🔍 ИЩУ МАТЧИ ЗА {today}...")
    
    for league_id, league_name in LEAGUES.items():
        for season in ["2026", "2025"]:
            try:
                url = f"https://v3.football.api-sports.io/fixtures?league={league_id}&season={season}&date={today}"
                headers = {"x-rapidapi-key": FOOTBALL_API_KEY}
                
                logger.info(f"📡 {league_name} ({season})...")
                resp = requests.get(url, headers=headers, timeout=10)
                
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("response"):
                        for match in data["response"]:
                            if match["fixture"]["status"]["short"] in ["NS", "1H", "2H"]:
                                match["league"]["name"] = league_name
                                all_matches.append(match)
                                logger.info(f"✅ {match['teams']['home']['name']} vs {match['teams']['away']['name']} ({league_name})")
                        break
                    else:
                        logger.info(f"⚠️ Нет матчей в {league_name} ({season})")
                else:
                    logger.warning(f"❌ {league_name}: {resp.status_code}")
                    
            except Exception as e:
                logger.error(f"❌ {league_name}: {e}")
            
            time.sleep(0.2)
    
    logger.info(f"📊 ВСЕГО МАТЧЕЙ: {len(all_matches)}")
    return all_matches

# ===== ТЕСТОВЫЕ ДАННЫЕ =====
def get_test_matches():
    logger.info("📊 ТЕСТОВЫЙ РЕЖИМ")
    return [
        {"fixture": {"id": 1, "status": {"short": "NS"}}, "teams": {"home": {"name": "Arsenal"}, "away": {"name": "Chelsea"}}, "league": {"name": "АПЛ"}},
        {"fixture": {"id": 2, "status": {"short": "NS"}}, "teams": {"home": {"name": "Barcelona"}, "away": {"name": "Real Madrid"}}, "league": {"name": "Ла Лига"}},
    ]

# ===== РАСЧЁТ =====
def poisson_prob(lam, k):
    if lam == 0:
        return 1 if k == 0 else 0
    return (math.exp(-lam) * lam**k) / math.factorial(k)

def calculate_probs(home_xg, away_xg):
    max_goals = 7
    probs = [[poisson_prob(home_xg, i) * poisson_prob(away_xg, j) for j in range(max_goals)] for i in range(max_goals)]
    return {
        "btts": sum(probs[i][j] for i in range(1, 7) for j in range(1, 7)),
        "over_2_5": sum(probs[i][j] for i in range(7) for j in range(7) if i + j > 2.5),
        "home_win": sum(probs[i][j] for i in range(7) for j in range(7) if i > j),
        "away_win": sum(probs[i][j] for i in range(7) for j in range(7) if i < j),
    }

def find_best_bet(matches):
    if not matches:
        return None
    
    bank = load_bank()
    best_bet = None
    best_ev = -100
    
    for match in matches:
        try:
            home = match["teams"]["home"]["name"]
            away = match["teams"]["away"]["name"]
            league = match["league"]["name"]
            fixture_id = match["fixture"]["id"]
            
            home_xg = 1.5
            away_xg = 1.3
            
            try:
                stats_url = f"https://v3.football.api-sports.io/fixtures/statistics?fixture={fixture_id}"
                headers = {"x-rapidapi-key": FOOTBALL_API_KEY}
                resp = requests.get(stats_url, headers=headers, timeout=10)
                stats = resp.json()
                if stats.get("response"):
                    for stat in stats["response"]:
                        if stat["team"]["name"] == home:
                            for item in stat.get("statistics", []):
                                if item["type"] == "expected_goals" and item.get("value"):
                                    home_xg = float(item["value"])
                        elif stat["team"]["name"] == away:
                            for item in stat.get("statistics", []):
                                if item["type"] == "expected_goals" and item.get("value"):
                                    away_xg = float(item["value"])
            except:
                pass
            
            home_xg = max(0.3, min(home_xg, 4.0))
            away_xg = max(0.3, min(away_xg, 4.0))
            probs = calculate_probs(home_xg, away_xg)
            
            bet_types = [
                ("btts", 1.85, "ОЗ - ДА"),
                ("over_2_5", 1.80, "Тотал > 2.5"),
                ("home_win", 2.0, "Победа хозяев"),
                ("away_win", 2.0, "Победа гостей"),
            ]
            
            for bet_type, odds, label in bet_types:
                prob = probs.get(bet_type, 0)
                if prob < 0.05 or prob > 0.99:
                    continue
                ev = (prob * odds) - 1
                if ev > best_ev and ev > 0.02:
                    stake = round(bank * ev * 0.3, 2)
                    stake = max(0.5, min(stake, bank * 0.05))
                    best_ev = ev
                    best_bet = {
                        "home": home,
                        "away": away,
                        "league": league,
                        "fixture_id": fixture_id,
                        "bet": label,
                        "bet_type": bet_type,
                        "odds": odds,
                        "prob": round(prob * 100, 1),
                        "ev": round(ev * 100, 1),
                        "stake": stake,
                        "home_xg": round(home_xg, 2),
                        "away_xg": round(away_xg, 2),
                    }
        except Exception as e:
            logger.error(f"Ошибка: {e}")
            continue
    
    return best_bet

# ===== УВЕДОМЛЕНИЕ =====
last_notified = {}

def send_bet_notification(bet):
    if not bet:
        return
    if bet['ev'] < 2.0:
        return
    key = f"{bet['fixture_id']}_{bet['bet_type']}"
    if key in last_notified and last_notified[key] == bet['ev']:
        return
    last_notified[key] = bet['ev']
    
    msg = f"""🔥 <b>ВАЛУЙНАЯ СТАВКА!</b>

🏟️ {bet['home']} vs {bet['away']}
🏆 {bet['league']}

🎯 <b>{bet['bet']}</b>
📈 КЭФ: {bet['odds']}
💰 СТАВКА: ${bet['stake']:.2f}
📊 ВЕРОЯТНОСТЬ: {bet['prob']}%
📈 EV: <b>{bet['ev']}%</b>

📊 xG: {bet['home_xg']} : {bet['away_xg']}"""
    
    bet_id = f"{bet['fixture_id']}_{bet['bet_type']}_{int(time.time())}"
    send_telegram_with_buttons(msg, bet_id)
    
    history = load_history()
    bet['id'] = bet_id
    bet['result'] = 'pending'
    bet['date'] = datetime.now().strftime("%Y-%m-%d %H:%M")
    history.append(bet)
    save_history(history)

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
                send_telegram("""🚀 QUANTUM BETTING BOT

📋 КОМАНДЫ:
/today - Ставка из кеша
/update - ПОИСК ставок
/bank - Банк
/stats - Статистика
/help - Помощь""")
            
            elif text == '/update':
                send_telegram("🔄 Поиск матчей...")
                matches = get_matches()
                if matches:
                    bet = find_best_bet(matches)
                    save_cache({"best_bet": bet})
                    if bet:
                        send_bet_notification(bet)
                        send_telegram(f"✅ Найдена ставка! EV: {bet['ev']}%")
                    else:
                        send_telegram("❌ Ставок с EV > 2% нет")
                else:
                    send_telegram("⚠️ Матчей не найдено")
                    test = get_test_matches()
                    bet = find_best_bet(test)
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
            
            elif text == '/help':
                send_telegram("""📖 КОМАНДЫ:
/today - Ставка
/update - Поиск
/bank - Банк
/stats - Статистика
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
