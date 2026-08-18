from flask import Flask, request
import requests
import math
from datetime import datetime

app = Flask(__name__)

TELEGRAM_TOKEN = "8757780924:AAEteceqwZmFDCpWJUZBj-gwc1DGCl-dv74"
FOOTBALL_API_KEY = "3e01a7f37589da560393ad459bfd61ff"
WEATHER_API_KEY = "7f0cfaed346b0fe364815ab65d627af2"

LEAGUES = [39, 140, 78, 135, 61, 94, 88, 144, 203, 218, 179, 113, 84, 90, 197, 52, 103, 111, 169, 213, 142, 123, 157, 223, 170, 73, 97]

# Храним банк в словаре, чтобы избежать проблем с global
state = {"bank": 1000}

def poisson_prob(lam, k):
    if lam == 0:
        return 1 if k == 0 else 0
    return (math.exp(-lam) * lam**k) / math.factorial(k)

def calculate_probs(home_xg, away_xg):
    max_goals = 7
    probs = []
    for i in range(max_goals):
        row = []
        for j in range(max_goals):
            row.append(poisson_prob(home_xg, i) * poisson_prob(away_xg, j))
        probs.append(row)
    
    btts = sum(probs[i][j] for i in range(1, 7) for j in range(1, 7))
    over_2_5 = sum(probs[i][j] for i in range(7) for j in range(7) if i + j > 2.5)
    home_win = sum(probs[i][j] for i in range(7) for j in range(7) if i > j)
    away_win = sum(probs[i][j] for i in range(7) for j in range(7) if i < j)
    draw = sum(probs[i][i] for i in range(7))
    home_or_draw = home_win + draw
    away_or_draw = away_win + draw
    
    return {
        "btts": btts,
        "over_2_5": over_2_5,
        "home_win": home_win,
        "away_win": away_win,
        "draw": draw,
        "home_or_draw": home_or_draw,
        "away_or_draw": away_or_draw,
    }

def get_matches():
    all_matches = []
    for league_id in LEAGUES:
        try:
            url = f"https://v3.football.api-sports.io/fixtures?league={league_id}&season=2026&date={datetime.now().strftime('%Y-%m-%d')}"
            headers = {"x-rapidapi-key": FOOTBALL_API_KEY}
            resp = requests.get(url, headers=headers, timeout=10)
            data = resp.json()
            if data.get("response"):
                for match in data["response"]:
                    if match["fixture"]["status"]["short"] == "NS":
                        all_matches.append(match)
        except:
            pass
    return all_matches

def find_value_bets(matches):
    bets = []
    for match in matches:
        try:
            home = match["teams"]["home"]["name"]
            away = match["teams"]["away"]["name"]
            league = match["league"]["name"]
            fixture_id = match["fixture"]["id"]
            
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
                    stake = state["bank"] * 0.05
                    if stake < 1:
                        stake = 1
                    bets.append({
                        "home": home,
                        "away": away,
                        "league": league,
                        "bet": label,
                        "odds": default_odds,
                        "prob": round(prob * 100, 1),
                        "ev": round(ev * 100, 1),
                        "stake": round(stake, 2),
                        "home_xg": round(home_xg, 2),
                        "away_xg": round(away_xg, 2),
                    })
        except:
            pass
    return bets

def send_telegram(text):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": "228801334", "text": text, "parse_mode": "HTML"}
        requests.post(url, json=data)
    except:
        pass

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        data = request.get_json()
        if data and 'message' in data:
            text = data['message'].get('text', '')
            
            if text == '/start':
                send_telegram("🚀 Бот запущен! Напиши /today для поиска ставок")
            elif text == '/today':
                matches = get_matches()
                bets = find_value_bets(matches)
                if bets:
                    for bet in bets:
                        msg = f"""✅ <b>ВАЛУЙНАЯ СТАВКА!</b>
🏟️ {bet['home']} vs {bet['away']}
🏆 {bet['league']}
🎯 {bet['bet']} | КЭФ: {bet['odds']}
💰 РАЗМЕР: {bet['stake']}$ (5% банка)
📊 УВЕРЕННОСТЬ: {bet['prob']}%
📈 EV: {bet['ev']}%
📊 xG: {bet['home_xg']} : {bet['away_xg']}"""
                        send_telegram(msg)
                else:
                    send_telegram("❌ Сегодня валуйных ставок не найдено")
            elif text == '/bank':
                send_telegram(f"💰 Текущий банк: ${state['bank']}")
            elif text == '/help':
                send_telegram("""📖 <b>Команды:</b>
/today - ставки на сегодня
/bank - текущий банк
/setbank 1500 - установить банк
/help - помощь""")
            elif text.startswith('/setbank'):
                try:
                    state["bank"] = float(text.split()[1])
                    send_telegram(f"✅ Банк установлен: ${state['bank']}")
                except:
                    send_telegram("❌ Введите сумму: /setbank 1500")
            else:
                send_telegram("Неизвестная команда. Напиши /help")
        return "ok"
    return "Quantum Bot is running!"

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=10000)
