from flask import Flask, request
import requests
import json
import math
from datetime import datetime, timedelta

app = Flask(__name__)

# ===== ВСЕ КЛЮЧИ =====
TELEGRAM_TOKEN = "8757780924:AAEteceqwZmFDCpWJUZBj-gwc1DGCl-dv74"
FOOTBALL_API_KEY = "3e01a7f37589da560393ad459bfd61ff"
WEATHER_API_KEY = "7f0cfaed346b0fe364815ab65d627af2"

# ===== СПИСОК ЛИГ (ЕВРОПА) =====
LEAGUES = [
    39,  # АПЛ
    140, # Ла Лига
    78,  # Бундеслига
    135, # Серия А
    61,  # Лига 1
    94,  # Примейра-Лига
    88,  # Эредивизи
    144, # Жюпилер Про-Лига
    203, # Суперлига (Турция)
    218, # РПЛ
    179, # Шотландия
    113, # Австрия
    84,  # Украина (если есть)
    90,  # Греция
    197, # Дания
    52,  # Швеция
    103, # Норвегия
    111, # Швейцария
    169, # Польша
    213, # Сербия
    142, # Хорватия
    123, # Чехия
    157, # Румыния
    223, # Словакия
    170, # Венгрия
    73,  # Болгария
    97,  # Кипр
]

# ===== БАНК (по умолчанию) =====
bank = 1000

# ===== РАСЧЁТ ПУАССОНА =====
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
    
    # ОЗ (Обе забьют)
    btts = sum(probs[i][j] for i in range(1, 7) for j in range(1, 7))
    
    # Тотал > 2.5
    over_2_5 = sum(probs[i][j] for i in range(7) for j in range(7) if i + j > 2.5)
    
    # Победа хозяев
    home_win = sum(probs[i][j] for i in range(7) for j in range(7) if i > j)
    
    # Победа гостей
    away_win = sum(probs[i][j] for i in range(7) for j in range(7) if i < j)
    
    # Ничья
    draw = sum(probs[i][i] for i in range(7))
    
    # 1Х
    home_or_draw = home_win + draw
    
    # 2Х
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

# ===== ПОГОДА =====
def get_weather(lat, lon):
    try:
        url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={WEATHER_API_KEY}&units=metric"
        resp = requests.get(url, timeout=5)
        data = resp.json()
        if "main" in data:
            temp = data["main"]["temp"]
            desc = data["weather"][0]["description"].lower()
            return temp, desc
    except:
        pass
    return None, None

# ===== ПОЛУЧЕНИЕ МАТЧЕЙ =====
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

# ===== ПОИСК СТАВОК =====
def find_value_bets(matches):
    bets = []
    for match in matches:
        try:
            home = match["teams"]["home"]["name"]
            away = match["teams"]["away"]["name"]
            league = match["league"]["name"]
            fixture_id = match["fixture"]["id"]
            
            # Получаем статистику xG
            stats_url = f"https://v3.football.api-sports.io/fixtures/statistics?fixture={fixture_id}"
            headers = {"x-rapidapi-key": FOOTBALL_API_KEY}
            resp = requests.get(stats_url, headers=headers, timeout=10)
            stats = resp.json()
            
            home_xg = 1.5
            away_xg = 1.3
            home_form = 0.5
            away_form = 0.5
            
            for stat in stats.get("response", []):
                if stat["team"]["name"] == home:
                    for item in stat["statistics"]:
                        if item["type"] == "expected_goals":
                            home_xg = float(item["value"] or 1.5)
                        elif item["type"] == "form":
                            try:
                                home_form = float(item["value"]) / 100
                            except:
                                pass
                elif stat["team"]["name"] == away:
                    for item in stat["statistics"]:
                        if item["type"] == "expected_goals":
                            away_xg = float(item["value"] or 1.3)
                        elif item["type"] == "form":
                            try:
                                away_form = float(item["value"]) / 100
                            except:
                                pass
            
            # Корректировка на форму
            home_xg *= (0.8 + 0.4 * home_form)
            away_xg *= (0.8 + 0.4 * away_form)
            
            # Погода
            if match["fixture"].get("venue", {}).get("city"):
                city = match["fixture"]["venue"]["city"]
                temp, desc = get_weather(50, 10)  # Для простоты
                if temp and desc:
                    if temp > 28 or "rain" in desc:
                        home_xg *= 0.93
                        away_xg *= 0.93
            
            # Вероятности
            probs = calculate_probs(home_xg, away_xg)
            
            # Проверяем каждый тип ставки
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
                
                # Ищем коэффициент у букмекера (упрощённо, можно добавить позже)
                odds = default_odds
                ev = (prob * odds) - 1
                
                if ev > 0.05:
                    stake = bank * 0.05  # 5% от банка
                    if stake < 1:
                        stake = 1
                    bets.append({
                        "home": home,
                        "away": away,
                        "league": league,
                        "bet": label,
                        "odds": odds,
                        "prob": round(prob * 100, 1),
                        "ev": round(ev * 100, 1),
                        "stake": round(stake, 2),
                        "home_xg": round(home_xg, 2),
                        "away_xg": round(away_xg, 2),
                    })
        except Exception as e:
            print(f"Ошибка: {e}")
    
    return bets

# ===== ОТПРАВКА СООБЩЕНИЯ В ТЕЛЕГРАМ =====
def send_telegram(text):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {
            "chat_id": "YOUR_CHAT_ID",  # Замени на свой ID
            "text": text,
            "parse_mode": "HTML"
        }
        requests.post(url, json=data)
    except:
        pass

# ===== ВЕБХУК =====
@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        data = request.get_json()
        if data and 'message' in data:
            chat_id = data['message']['chat']['id']
            text = data['message'].get('text', '')
            
            if text == '/start':
                reply = "🚀 Бот запущен! Ищу валуйные ставки..."
                send_telegram(reply)
            elif text == '/today':
                matches = get_matches()
                bets = find_value_bets(matches)
                if bets:
                    for bet in bets:
                        msg = f"""✅ <b>ВАЛУЙНАЯ СТАВКА!</b>
🏟️ {bet['home']} vs {bet['away']}
🏆 {bet['league']}
🎯 {bet['bet']}
📈 КЭФ: {bet['odds']}
💰 РАЗМЕР: {bet['stake']}$ (5% банка)
📊 УВЕРЕННОСТЬ: {bet['prob']}%
📈 EV: {bet['ev']}%
📊 xG: {bet['home_xg']} : {bet['away_xg']}"""
                        send_telegram(msg)
                else:
                    send_telegram("❌ Сегодня валуйных ставок не найдено")
            elif text == '/help':
                reply = """📖 <b>Команды:</b>
/today - ставки на сегодня
/bank - текущий банк
/setbank 1500 - установить банк
/help - помощь"""
                send_telegram(reply)
            elif text.startswith('/setbank'):
                try:
                    new_bank = float(text.split()[1])
                    bank = new_bank
                    send_telegram(f"✅ Банк установлен: ${bank}")
                except:
                    send_telegram("❌ Введите сумму: /setbank 1500")
            else:
                send_telegram("Неизвестная команда. Напиши /help")
        
        return "ok"
    return "Quantum Bot is running!"

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=10000)
