from flask import Flask, request
import requests
import math
import json
import os
from datetime import datetime
import threading
import time

app = Flask(__name__)

# ===== КЛЮЧИ =====
TELEGRAM_TOKEN = "8757780924:AAEteceqwZmFDCpWJUZBj-gwc1DGCl-dv74"
FOOTBALL_API_KEY = "3e01a7f37589da560393ad459bfd61ff"
WEATHER_API_KEY = "7f0cfaed346b0fe364815ab65d627af2"

# ===== ЛИГИ =====
LEAGUES = [39, 140, 78, 135, 61, 94, 88, 144, 203, 218, 179, 113, 84, 90, 197, 52, 103, 111, 169, 213, 142, 123, 157, 223, 170, 73, 97]

# ===== ФАЙЛЫ =====
CACHE_FILE = "cache.json"
HISTORY_FILE = "history.json"
WEIGHTS_FILE = "weights.json"
BANK_FILE = "bank.json"

# ===== ЗАГРУЗКА/СОХРАНЕНИЕ =====
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

def load_bank():
    if os.path.exists(BANK_FILE):
        with open(BANK_FILE, "r") as f:
            return json.load(f).get("bank", 1000)
    return 1000

def save_bank(bank):
    with open(BANK_FILE, "w") as f:
        json.dump({"bank": bank}, f)

def is_cache_fresh():
    cache = load_cache()
    if not cache:
        return False
    last_update = datetime.fromisoformat(cache.get("last_update", "2000-01-01T00:00:00"))
    return (datetime.now() - last_update).total_seconds() < 21600

# ===== РАСЧЁТ ВЕРОЯТНОСТЕЙ =====
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
        "draw": sum(probs[i][i] for i in range(7)),
        "home_or_draw": sum(probs[i][j] for i in range(7) for j in range(7) if i >= j),
        "away_or_draw": sum(probs[i][j] for i in range(7) for j in range(7) if i <= j),
    }

# ===== ПОЛУЧЕНИЕ ФОРМЫ =====
def get_form(team_id):
    try:
        url = f"https://v3.football.api-sports.io/fixtures?team={team_id}&last=5"
        headers = {"x-rapidapi-key": FOOTBALL_API_KEY}
        resp = requests.get(url, headers=headers, timeout=10)
        data = resp.json()
        if data.get("response"):
            wins, losses = 0, 0
            for match in data["response"]:
                if match["teams"]["home"]["id"] == team_id:
                    if match["goals"]["home"] > match["goals"]["away"]:
                        wins += 1
                    elif match["goals"]["home"] < match["goals"]["away"]:
                        losses += 1
                else:
                    if match["goals"]["away"] > match["goals"]["home"]:
                        wins += 1
                    elif match["goals"]["away"] < match["goals"]["home"]:
                        losses += 1
            return {"wins": wins, "losses": losses, "ratio": wins / 5}
    except:
        pass
    return {"wins": 0, "losses": 0, "ratio": 0.5}

# ===== ПОЛУЧЕНИЕ ТРАВМ =====
def get_injuries(team_id):
    try:
        url = f"https://v3.football.api-sports.io/injuries?team={team_id}"
        headers = {"x-rapidapi-key": FOOTBALL_API_KEY}
        resp = requests.get(url, headers=headers, timeout=10)
        data = resp.json()
        if data.get("response"):
            injured_players = len(data["response"])
            if injured_players >= 3:
                return 0.85
            elif injured_players >= 1:
                return 0.93
    except:
        pass
    return 1.0

# ===== ПОЛУЧЕНИЕ МОТИВАЦИИ =====
def get_motivation(team_id, league_id):
    try:
        url = f"https://v3.football.api-sports.io/standings?league={league_id}&season=2026"
        headers = {"x-rapidapi-key": FOOTBALL_API_KEY}
        resp = requests.get(url, headers=headers, timeout=10)
        data = resp.json()
        if data.get("response"):
            for league in data["response"]:
                for standing in league["league"]["standings"]:
                    for team in standing:
                        if team["team"]["id"] == team_id:
                            pos = team["rank"]
                            total = len(standing)
                            if pos <= 4 or pos >= total - 3:
                                return 1.10
                            else:
                                return 1.0
    except:
        pass
    return 1.0

# ===== H2H (ЛИЧНЫЕ ВСТРЕЧИ) =====
def get_h2h(home_id, away_id):
    try:
        url = f"https://v3.football.api-sports.io/fixtures/headtohead?h2h={home_id}-{away_id}&last=5"
        headers = {"x-rapidapi-key": FOOTBALL_API_KEY}
        resp = requests.get(url, headers=headers, timeout=10)
        data = resp.json()
        if data.get("response"):
            home_wins, away_wins = 0, 0
            home_goals, away_goals = [], []
            for match in data["response"]:
                if match["teams"]["home"]["id"] == home_id:
                    home_goals.append(match["goals"]["home"])
                    away_goals.append(match["goals"]["away"])
                    if match["goals"]["home"] > match["goals"]["away"]:
                        home_wins += 1
                    elif match["goals"]["home"] < match["goals"]["away"]:
                        away_wins += 1
                else:
                    home_goals.append(match["goals"]["away"])
                    away_goals.append(match["goals"]["home"])
                    if match["goals"]["away"] > match["goals"]["home"]:
                        home_wins += 1
                    elif match["goals"]["away"] < match["goals"]["home"]:
                        away_wins += 1
            if home_goals:
                return {
                    "home_avg": sum(home_goals) / len(home_goals),
                    "away_avg": sum(away_goals) / len(away_goals),
                    "home_wins": home_wins,
                    "away_wins": away_wins,
                    "matches": len(home_goals),
                }
    except:
        pass
    return None

# ===== ЭКСПЕРТНЫЕ ПРАВИЛА =====
def apply_expert_rules(home_xg, away_xg, match):
    rules_applied = []
    
    if "derby" in match.get("fixture", {}).get("name", "").lower():
        home_xg *= 0.9
        away_xg *= 0.9
        rules_applied.append("Дерби: -10% к xG")
    
    if match.get("factors", {}).get("home_form", {}).get("losses", 0) >= 3:
        home_xg *= 0.95
        rules_applied.append("Хозяева проиграли 3 матча подряд: -5% к xG")
    if match.get("factors", {}).get("away_form", {}).get("losses", 0) >= 3:
        away_xg *= 0.95
        rules_applied.append("Гости проиграли 3 матча подряд: -5% к xG")
    
    return home_xg, away_xg, rules_applied

# ===== НЕУДОБНЫЙ СОПЕРНИК =====
def apply_uncomfortable_opponent(home_xg, away_xg, h2h):
    if h2h and h2h.get("matches", 0) >= 3:
        home_wins = h2h.get("home_wins", 0)
        away_wins = h2h.get("away_wins", 0)
        total = h2h.get("matches", 1)
        
        if home_wins / total < 0.2:
            home_xg *= 0.9
            away_xg *= 1.05
        if away_wins / total < 0.2:
            away_xg *= 0.9
            home_xg *= 1.05
    return home_xg, away_xg

# ===== ПОЛУЧЕНИЕ МАТЧЕЙ =====
def get_matches_with_factors():
    all_matches = []
    for league_id in LEAGUES:
        try:
            url = f"https://v3.football.api-sports.io/fixtures?league={league_id}&season=2026&date={datetime.now().strftime('%Y-%m-%d')}"
            headers = {"x-rapidapi-key": FOOTBALL_API_KEY}
            resp = requests.get(url, headers=headers, timeout=15)
            data = resp.json()
            if data.get("response"):
                for match in data["response"]:
                    if match["fixture"]["status"]["short"] == "NS":
                        home_id = match["teams"]["home"]["id"]
                        away_id = match["teams"]["away"]["id"]
                        
                        match["factors"] = {
                            "home_form": get_form(home_id),
                            "away_form": get_form(away_id),
                            "home_injuries": get_injuries(home_id),
                            "away_injuries": get_injuries(away_id),
                            "home_motivation": get_motivation(home_id, league_id),
                            "away_motivation": get_motivation(away_id, league_id),
                            "h2h": get_h2h(home_id, away_id),
                        }
                        all_matches.append(match)
        except:
            pass
    return all_matches

# ===== ПОИСК СТАВОК =====
def find_value_bets(matches):
    bank = load_bank()
    bets = []
    weights = load_weights()
    
    for match in matches:
        try:
            home = match["teams"]["home"]["name"]
            away = match["teams"]["away"]["name"]
            league = match["league"]["name"]
            fixture_id = match["fixture"]["id"]
            factors = match.get("factors", {})
            h2h = factors.get("h2h")
            
            stats_url = f"https://v3.football.api-sports.io/fixtures/statistics?fixture={fixture_id}"
            headers = {"x-rapidapi-key": FOOTBALL_API_KEY}
            resp = requests.get(stats_url, headers=headers, timeout=10)
            stats = resp.json()
            
            home_xg, away_xg = 1.5, 1.3
            for stat in stats.get("response", []):
                if stat["team"]["name"] == home:
                    for item in stat.get("statistics", []):
                        if item["type"] == "expected_goals":
                            home_xg = float(item["value"] or 1.5)
                elif stat["team"]["name"] == away:
                    for item in stat.get("statistics", []):
                        if item["type"] == "expected_goals":
                            away_xg = float(item["value"] or 1.3)
            
            league_weight = weights.get(league, {}).get("xg", 1.0)
            home_xg *= league_weight
            away_xg *= league_weight
            
            home_xg *= factors.get("home_form", {}).get("ratio", 0.5) + 0.5
            away_xg *= factors.get("away_form", {}).get("ratio", 0.5) + 0.5
            home_xg *= factors.get("home_injuries", 1.0)
            away_xg *= factors.get("away_injuries", 1.0)
            home_xg *= factors.get("home_motivation", 1.0)
            away_xg *= factors.get("away_motivation", 1.0)
            
            if h2h and h2h.get("matches", 0) >= 3:
                h2h_home = h2h["home_avg"]
                h2h_away = h2h["away_avg"]
                if h2h_home > 0 and h2h_away > 0:
                    home_xg = (home_xg + h2h_home) / 2
                    away_xg = (away_xg + h2h_away) / 2
            
            home_xg, away_xg = apply_uncomfortable_opponent(home_xg, away_xg, h2h)
            
            home_xg *= 1.1
            away_xg *= 0.95
            
            home_xg, away_xg, rules = apply_expert_rules(home_xg, away_xg, match)
            
            probs = calculate_probs(home_xg, away_xg)
            
            bet_types = [
                ("btts", 1.9, "ОЗ - ДА"),
                ("over_2_5", 1.85, "Тотал > 2.5"),
                ("home_win", 2.1, "Победа хозяев"),
                ("away_win", 2.1, "Победа гостей"),
                ("home_or_draw", 1.6, "1Х"),
                ("away_or_draw", 1.6, "2Х"),
            ]
            
            for bet_type, default_odds, label in bet_types:
                prob = probs.get(bet_type, 0)
                if prob < 0.1 or prob > 0.99:
                    continue
                ev = (prob * default_odds) - 1
                if ev > 0.05:
                    stake = bank * 0.05
                    if stake < 1:
                        stake = 1
                    bets.append({
                        "home": home,
                        "away": away,
                        "league": league,
                        "fixture_id": fixture_id,
                        "bet": label,
                        "bet_type": bet_type,
                        "odds": default_odds,
                        "prob": round(prob * 100, 1),
                        "ev": round(ev * 100, 1),
                        "stake": round(stake, 2),
                        "home_xg": round(home_xg, 2),
                        "away_xg": round(away_xg, 2),
                        "rules": rules,
                        "factors": {
                            "home_form": round(factors.get("home_form", {}).get("ratio", 0.5), 2),
                            "away_form": round(factors.get("away_form", {}).get("ratio", 0.5), 2),
                            "home_injuries": factors.get("home_injuries", 1.0),
                            "away_injuries": factors.get("away_injuries", 1.0),
                            "home_motivation": factors.get("home_motivation", 1.0),
                            "away_motivation": factors.get("away_motivation", 1.0),
                            "h2h_home": round(h2h["home_avg"], 2) if h2h else None,
                            "h2h_away": round(h2h["away_avg"], 2) if h2h else None,
                            "h2h_matches": h2h["matches"] if h2h else 0,
                            "h2h_home_wins": h2h["home_wins"] if h2h else 0,
                            "h2h_away_wins": h2h["away_wins"] if h2h else 0,
                        }
                    })
        except Exception as e:
            pass
    return bets

# ===== ОБУЧЕНИЕ =====
def train_model():
    history = load_history()
    if len(history) < 30:
        return
    
    wins = [b for b in history if b.get('result') == 'win']
    losses = [b for b in history if b.get('result') == 'loss']
    
    weights = {}
    for league in set(b.get('league', '') for b in history):
        league_wins = [b for b in wins if b.get('league') == league]
        league_losses = [b for b in losses if b.get('league') == league]
        total = len(league_wins) + len(league_losses)
        if total > 5:
            xg_weight = len(league_wins) / total if total > 0 else 0.5
            weights[league] = {"xg": round(0.5 + xg_weight * 0.5, 2)}
    
    save_weights(weights)

# ===== ОТПРАВКА В ТЕЛЕГРАМ =====
def send_telegram_with_buttons(text, bet_id):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {
            "chat_id": "228801334",
            "text": text,
            "parse_mode": "HTML",
            "reply_markup": {
                "inline_keyboard": [
                    [
                        {"text": "✅ Зашло", "callback_data": f"win_{bet_id}"},
                        {"text": "❌ Не зашло", "callback_data": f"loss_{bet_id}"}
                    ]
                ]
            }
        }
        requests.post(url, json=data)
    except:
        pass

def send_telegram(text):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": "228801334", "text": text, "parse_mode": "HTML"}
        requests.post(url, json=data)
    except:
        pass

# ===== ФОНОВОЕ ОБНОВЛЕНИЕ =====
def scheduled_update():
    while True:
        now = datetime.now()
        if now.hour in [10, 18] and now.minute == 0:
            send_telegram("🔄 Плановое обновление кеша...")
            matches = get_matches_with_factors()
            bets = find_value_bets(matches)
            save_cache({"bets": bets})
            train_model()
            send_telegram(f"✅ Кеш обновлён! Найдено ставок: {len(bets)}")
        time.sleep(60)

threading.Thread(target=scheduled_update, daemon=True).start()

# ===== ВЕБХУК =====
@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    
    if data and 'callback_query' in data:
        callback = data['callback_query']
        bet_id = callback['data'].split('_')[1]
        result = callback['data'].split('_')[0]
        
        history = load_history()
        for bet in history:
            if str(bet['id']) == bet_id:
                bet['result'] = result
                bet['date'] = datetime.now().strftime("%Y-%m-%d %H:%M")
                break
        save_history(history)
        train_model()
        
        send_telegram(f"✅ Результат ставки #{bet_id} сохранён: {result}")
        return "ok"
    
    if data and 'message' in data:
        text = data['message'].get('text', '')
        
        if text == '/start':
            send_telegram("🚀 Бот запущен! Напиши /today для поиска ставок")
        
        elif text == '/today':
            if not is_cache_fresh():
                send_telegram("🔄 Обновляю кеш...")
                matches = get_matches_with_factors()
                bets = find_value_bets(matches)
                save_cache({"bets": bets})
                train_model()
            else:
                cache = load_cache()
                bets = cache.get("bets", [])
            
            if bets:
                for bet in bets:
                    bet_id = f"{bet['fixture_id']}_{bet['bet_type']}"
                    factors = bet.get("factors", {})
                    rules_text = "\n".join([f"• {r}" for r in bet.get("rules", [])]) if bet.get("rules") else "Нет"
                    h2h_info = ""
                    if factors.get("h2h_matches", 0) >= 3:
                        h2h_info = f"\n📋 H2H (посл. {factors['h2h_matches']}): {factors['h2h_home']} : {factors['h2h_away']} (в ср.)"
                        if factors.get("h2h_home_wins", 0) > factors.get("h2h_away_wins", 0):
                            h2h_info += "\n⚠️ Хозяева доминируют в личных встречах"
                        else:
                            h2h_info += "\n⚠️ Гости доминируют в личных встречах"
                    
                    msg = f"""✅ <b>ВАЛУЙНАЯ СТАВКА!</b>
🏟️ {bet['home']} vs {bet['away']}
🏆 {bet['league']}
🎯 {bet['bet']} | КЭФ: {bet['odds']}
💰 РАЗМЕР: {bet['stake']}$ (5% банка)
📊 УВЕРЕННОСТЬ: {bet['prob']}%
📈 EV: {bet['ev']}%
📊 xG: {bet['home_xg']} : {bet['away_xg']}

📋 <b>ФАКТОРЫ:</b>
🏠 Дома: +10% к xG
📈 Форма хозяев: {factors.get('home_form', 0.5)*100:.0f}%
📈 Форма гостей: {factors.get('away_form', 0.5)*100:.0f}%
🏥 Травмы хозяев: {factors.get('home_injuries', 1.0)*100:.0f}%
🏥 Травмы гостей: {factors.get('away_injuries', 1.0)*100:.0f}%
🎯 Мотивация хозяев: {factors.get('home_motivation', 1.0)*100:.0f}%
🎯 Мотивация гостей: {factors.get('away_motivation', 1.0)*100:.0f}%
{h2h_info}

📌 <b>Экспертные правила:</b>
{rules_text}"""
                    send_telegram_with_buttons(msg, bet_id)
            else:
                send_telegram("❌ Сегодня валуйных ставок не найдено")
        
        elif text == '/bank':
            bank = load_bank()
            send_telegram(f"💰 Текущий банк: ${bank}")
        
        elif text == '/stats':
            history = load_history()
            total = len(history)
            wins = sum(1 for b in history if b.get('result') == 'win')
            losses = sum(1 for b in history if b.get('result') == 'loss')
            winrate = wins / total * 100 if total > 0 else 0
            send_telegram(f"""📊 <b>СТАТИСТИКА СТАВОК</b>
Всего: {total}
✅ Выигрышей: {wins}
❌ Проигрышей: {losses}
🎯 Проходимость: {round(winrate, 1)}%""")
        
        elif text == '/update':
            send_telegram("🔄 Принудительное обновление кеша...")
            matches = get_matches_with_factors()
            bets = find_value_bets(matches)
            save_cache({"bets": bets})
            train_model()
            send_telegram(f"✅ Кеш обновлён! Найдено ставок: {len(bets)}")
        
        elif text.startswith('/setbank'):
            try:
                new_bank = float(text.split()[1])
                save_bank(new_bank)
                send_telegram(f"✅ Банк установлен: ${new_bank}")
            except:
                send_telegram("❌ Введите сумму: /setbank 1500")
        
        elif text == '/help':
            send_telegram("""📖 <b>Команды:</b>
/today - ставки на сегодня
/bank - текущий банк
/stats - статистика
/update - обновить кеш
/setbank 1500 - установить банк
/help - помощь""")
        
        else:
            send_telegram("Неизвестная команда. Напиши /help")
    
    return "ok"

@app.route('/', methods=['GET'])
def index():
    return "Quantum Bot v9.0 is running!"

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=10000)
