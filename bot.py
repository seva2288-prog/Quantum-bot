from flask import Flask, request
import requests
import math
import json
import os
from datetime import datetime, timedelta
import threading
import time
import re

app = Flask(__name__)

# ===== КЛЮЧИ =====
TELEGRAM_TOKEN = "8757780924:AAEteceqwZmFDCpWJUZBj-gwc1DGCl-dv74"
FOOTBALL_API_KEY = "3e01a7f37589da560393ad459bfd61ff"
WEATHER_API_KEY = "7f0cfaed346b0fe364815ab65d627af2"

# ===== ВСЕ ЛИГИ (РАСШИРЕННЫЙ СПИСОК) =====
LEAGUES = [
    # ⭐ ТОП-5
    39, 140, 78, 135, 61,
    # 📊 ВТОРЫЕ ДИВИЗИОНЫ
    40, 141, 79, 136, 62,
    # 🏆 ЕВРОКУБКИ
    2, 3, 848,
    # 🇪🇺 ЗАПАДНАЯ ЕВРОПА
    88, 89, 94, 203, 197, 345, 106, 207,
    # 🇷🇺 ВОСТОЧНАЯ ЕВРОПА
    90, 242, 272, 276, 283, 288, 253, 289, 290, 291,
    # ❄️ СЕВЕРНАЯ ЕВРОПА
    179, 218, 240,
    # 🏆 КУБКИ
    1, 12, 45, 46, 47, 48, 50
]

# ===== НАЗВАНИЯ ЛИГ =====
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
    46: "Кубок Германии", 47: "Кубок Италии", 48: "Кубок Франции", 50: "Кубок Лиги"
}

# ===== НАСТРОЙКИ СЛОЁВ =====
SETTINGS = {
    "improved_form": True,
    "referee": True,
    "odds_movement": True,
    "psy_factor": True,
    "neural_learning": True,
}

# ===== ФАЙЛЫ =====
CACHE_FILE = "cache.json"
HISTORY_FILE = "history.json"
WEIGHTS_FILE = "weights.json"
BANK_FILE = "bank.json"
ODDS_HISTORY_FILE = "odds_history.json"
PRIOR_FILE = "prior.json"
LEAGUES_FILE = "leagues.json"

# ===== ЗАГРУЗКА/СОХРАНЕНИЕ =====
def load_leagues():
    if os.path.exists(LEAGUES_FILE):
        with open(LEAGUES_FILE, "r") as f:
            return json.load(f)
    return LEAGUES

def save_leagues(leagues):
    with open(LEAGUES_FILE, "w") as f:
        json.dump(leagues, f, indent=2)

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

def is_cache_fresh():
    cache = load_cache()
    if not cache:
        return False
    last_update = datetime.fromisoformat(cache.get("last_update", "2000-01-01T00:00:00"))
    return (datetime.now() - last_update).total_seconds() < 21600

# ===== РАСЧЁТ ВЕРОЯТНОСТЕЙ (Пуассон) =====
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
        "under_2_5": sum(probs[i][j] for i in range(7) for j in range(7) if i + j < 2.5),
        "home_win": sum(probs[i][j] for i in range(7) for j in range(7) if i > j),
        "away_win": sum(probs[i][j] for i in range(7) for j in range(7) if i < j),
        "draw": sum(probs[i][i] for i in range(7)),
        "home_or_draw": sum(probs[i][j] for i in range(7) for j in range(7) if i >= j),
        "away_or_draw": sum(probs[i][j] for i in range(7) for j in range(7) if i <= j),
    }

# ===== ДОПОЛНИТЕЛЬНЫЕ СЛОИ =====
def apply_improved_form(home_xg, away_xg, match):
    if not SETTINGS.get("improved_form", True):
        return home_xg, away_xg, []
    reasons = []
    home_rank = match.get("factors", {}).get("home_rank", 10)
    away_rank = match.get("factors", {}).get("away_rank", 10)
    if home_rank < 5 and away_rank > 15:
        home_xg *= 1.05
        reasons.append("📈 Улучшенная форма: победа над сильным соперником (+5%)")
    elif home_rank > 15 and away_rank < 5:
        away_xg *= 1.05
        reasons.append("📈 Улучшенная форма: победа над сильным соперником (+5%)")
    return home_xg, away_xg, reasons

def apply_referee(home_xg, away_xg, match):
    if not SETTINGS.get("referee", True):
        return home_xg, away_xg, []
    reasons = []
    referee = match.get("factors", {}).get("referee")
    if referee:
        strict_referees = ["маттеу", "клос", "лаос", "олсен"]
        for strict in strict_referees:
            if strict in referee.lower():
                home_xg *= 0.95
                away_xg *= 0.95
                reasons.append(f"👨‍⚖️ Строгий судья: {referee} (-5% к тоталу)")
                break
    return home_xg, away_xg, reasons

def apply_odds_movement(home_xg, away_xg, fixture_id):
    if not SETTINGS.get("odds_movement", True):
        return home_xg, away_xg, []
    reasons = []
    history = load_odds_history()
    key = str(fixture_id)
    if key in history and len(history[key]) >= 2:
        first_odds = history[key][0].get("odds", 1.9)
        last_odds = history[key][-1].get("odds", 1.9)
        if first_odds - last_odds > 0.15:
            home_xg *= 0.95
            away_xg *= 0.95
            reasons.append(f"📉 Кэф упал с {first_odds:.2f} до {last_odds:.2f} → снижение xG на 5%")
        elif last_odds - first_odds > 0.15:
            home_xg *= 1.02
            away_xg *= 1.02
            reasons.append(f"📈 Кэф вырос с {first_odds:.2f} до {last_odds:.2f} → повышение xG на 2%")
    return home_xg, away_xg, reasons

def apply_psy_factor(home_xg, away_xg, match):
    if not SETTINGS.get("psy_factor", True):
        return home_xg, away_xg, []
    reasons = []
    fixture_name = match.get("fixture", {}).get("name", "").lower()
    league_name = match.get("league", {}).get("name", "").lower()
    home_form = match.get("factors", {}).get("home_form", {})
    away_form = match.get("factors", {}).get("away_form", {})
    if "derby" in fixture_name or "derby" in league_name:
        home_xg *= 0.92
        away_xg *= 0.92
        reasons.append("🧠 Дерби: высокое давление (-8% к xG)")
    if home_form.get("losses", 0) >= 3 and away_form.get("wins", 0) >= 3:
        home_xg *= 0.93
        away_xg *= 1.05
        reasons.append("🧠 Кризис vs подъём: хозяева в кризисе (-7%), гости на подъёме (+5%)")
    return home_xg, away_xg, reasons

def apply_neural_learning(home_xg, away_xg, league):
    if not SETTINGS.get("neural_learning", True):
        return home_xg, away_xg, []
    reasons = []
    weights = load_weights()
    league_weight = weights.get(league, {}).get("xg", 1.0)
    if league_weight != 1.0:
        home_xg *= league_weight
        away_xg *= league_weight
        reasons.append(f"🧠 Нейросеть: вес лиги {league_weight:.2f}")
    return home_xg, away_xg, reasons

def update_odds_history(fixture_id, current_odds):
    history = load_odds_history()
    key = str(fixture_id)
    if key not in history:
        history[key] = []
    history[key].append({"time": datetime.now().isoformat(), "odds": current_odds})
    if len(history[key]) > 10:
        history[key] = history[key][-10:]
    save_odds_history(history)

# ===== СУПЕР-СЛОЙ =====
def calculate_super_ik(match, raw_home_xg, raw_away_xg):
    reasons = []
    prior = load_prior()
    home_prior = prior.get("home", 1.5)
    away_prior = prior.get("away", 1.3)
    alpha = 10
    home_xg = (raw_home_xg * 5 + home_prior * alpha) / (5 + alpha)
    away_xg = (raw_away_xg * 5 + away_prior * alpha) / (5 + alpha)
    if raw_home_xg > home_prior * 1.5:
        reasons.append(f"📊 Байес: xG хозяев скорректирован с {raw_home_xg:.2f} до {home_xg:.2f}")
    if raw_away_xg > away_prior * 1.5:
        reasons.append(f"📊 Байес: xG гостей скорректирован с {raw_away_xg:.2f} до {away_xg:.2f}")
    
    factors = match.get("factors", {})
    home_form = factors.get("home_form", {})
    away_form = factors.get("away_form", {})
    h2h = factors.get("h2h")
    
    home_ratio = home_form.get("ratio", 0.5)
    away_ratio = away_form.get("ratio", 0.5)
    if home_ratio < 0.4:
        home_xg *= 0.95
        reasons.append("📉 Плохая форма хозяев (-5%)")
    if away_ratio < 0.4:
        away_xg *= 0.95
        reasons.append("📉 Плохая форма гостей (-5%)")
    if home_ratio > 0.8:
        home_xg *= 1.05
        reasons.append("📈 Отличная форма хозяев (+5%)")
    if away_ratio > 0.8:
        away_xg *= 1.05
        reasons.append("📈 Отличная форма гостей (+5%)")
    
    home_inj = factors.get("home_injuries", 1.0)
    away_inj = factors.get("away_injuries", 1.0)
    if home_inj < 0.9:
        home_xg *= 0.93
        reasons.append("🏥 Травмы хозяев (-7%)")
    if away_inj < 0.9:
        away_xg *= 0.93
        reasons.append("🏥 Травмы гостей (-7%)")
    
    home_mot = factors.get("home_motivation", 1.0)
    away_mot = factors.get("away_motivation", 1.0)
    if home_mot > 1.05:
        home_xg *= 1.05
        reasons.append("🎯 Мотивация хозяев (+5%)")
    if away_mot > 1.05:
        away_xg *= 1.05
        reasons.append("🎯 Мотивация гостей (+5%)")
    
    home_xg *= 1.05
    reasons.append("🏠 Домашний стадион (+5%)")
    
    if h2h and h2h.get("matches", 0) >= 3:
        home_wins = h2h.get("home_wins", 0)
        away_wins = h2h.get("away_wins", 0)
        total = h2h.get("matches", 1)
        if home_wins / total > 0.6:
            home_xg *= 1.05
            reasons.append("📊 Хозяева доминируют в личных встречах (+5%)")
        elif away_wins / total > 0.6:
            away_xg *= 1.05
            reasons.append("📊 Гости доминируют в личных встречах (+5%)")
    
    if h2h and h2h.get("matches", 0) >= 3:
        home_wins = h2h.get("home_wins", 0)
        away_wins = h2h.get("away_wins", 0)
        total = h2h.get("matches", 1)
        if home_wins / total < 0.2:
            home_xg *= 0.92
            reasons.append("⚠️ Хозяева неудобный соперник (-8%)")
        if away_wins / total < 0.2:
            away_xg *= 0.92
            reasons.append("⚠️ Гости неудобный соперник (-8%)")
    
    fixture_name = match.get("fixture", {}).get("name", "").lower()
    league_name = match.get("league", {}).get("name", "").lower()
    if "derby" in fixture_name or "derby" in league_name:
        home_xg *= 0.92
        away_xg *= 0.92
        reasons.append("⚔️ Дерби: -8% к xG")
    
    if home_form.get("losses", 0) >= 3:
        home_xg *= 0.95
        reasons.append("📉 Хозяева проиграли 3 матча подряд (-5%)")
    if away_form.get("losses", 0) >= 3:
        away_xg *= 0.95
        reasons.append("📉 Гости проиграли 3 матча подряд (-5%)")
    
    home_scorers = factors.get("home_scorers", [])
    away_scorers = factors.get("away_scorers", [])
    if home_scorers:
        reasons.append(f"⚽ Лучший бомбардир хозяев: {home_scorers[0]['name']} ({home_scorers[0]['goals']} голов)")
    if away_scorers:
        reasons.append(f"⚽ Лучший бомбардир гостей: {away_scorers[0]['name']} ({away_scorers[0]['goals']} голов)")
    
    home_xg, away_xg, add_reasons = apply_improved_form(home_xg, away_xg, match)
    reasons.extend(add_reasons)
    home_xg, away_xg, add_reasons = apply_referee(home_xg, away_xg, match)
    reasons.extend(add_reasons)
    fixture_id = match.get("fixture", {}).get("id")
    home_xg, away_xg, add_reasons = apply_odds_movement(home_xg, away_xg, fixture_id)
    reasons.extend(add_reasons)
    home_xg, away_xg, add_reasons = apply_psy_factor(home_xg, away_xg, match)
    reasons.extend(add_reasons)
    home_xg, away_xg, add_reasons = apply_neural_learning(home_xg, away_xg, league_name)
    reasons.extend(add_reasons)
    
    if fixture_id:
        update_odds_history(fixture_id, 1.9)
    
    return home_xg, away_xg, reasons

# ===== ПОЛУЧЕНИЕ ДАННЫХ =====
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

def get_injuries(team_id):
    try:
        url = f"https://v3.football.api-sports.io/injuries?team={team_id}"
        headers = {"x-rapidapi-key": FOOTBALL_API_KEY}
        resp = requests.get(url, headers=headers, timeout=10)
        data = resp.json()
        if data.get("response"):
            injured_players = len(data["response"])
            if injured_players >= 3:
                return 0.85, [p["player"]["name"] for p in data["response"][:3]]
            elif injured_players >= 1:
                return 0.93, [p["player"]["name"] for p in data["response"]]
    except:
        pass
    return 1.0, []

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
                            if pos <= 4:
                                return 1.10, f"{pos}-е место (борьба за еврокубки)"
                            elif pos >= total - 3:
                                return 1.10, f"{pos}-е место (борьба за выживание)"
                            else:
                                return 1.0, f"{pos}-е место"
    except:
        pass
    return 1.0, "неизвестно"

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

def get_referee_style(fixture_id):
    try:
        url = f"https://v3.football.api-sports.io/fixtures?id={fixture_id}"
        headers = {"x-rapidapi-key": FOOTBALL_API_KEY}
        resp = requests.get(url, headers=headers, timeout=10)
        data = resp.json()
        if data.get("response"):
            referee = data["response"][0]["fixture"]["referee"]
            if referee:
                return referee
    except:
        pass
    return None

def get_top_scorers(team_id):
    try:
        url = f"https://v3.football.api-sports.io/players?team={team_id}&season=2026"
        headers = {"x-rapidapi-key": FOOTBALL_API_KEY}
        resp = requests.get(url, headers=headers, timeout=10)
        data = resp.json()
        if data.get("response"):
            scorers = []
            for player in data["response"][:5]:
                if "statistics" in player and player["statistics"]:
                    for stat in player["statistics"]:
                        if "goals" in stat and "total" in stat["goals"]:
                            goals = stat["goals"]["total"] or 0
                            if goals > 0:
                                scorers.append({
                                    "name": player["player"]["name"],
                                    "goals": goals,
                                    "position": stat["games"]["position"] if "games" in stat else "F"
                                })
            return scorers
    except:
        pass
    return []

def get_real_odds(fixture_id):
    """Получает реальные коэффициенты на матч из API"""
    try:
        url = f"https://v3.football.api-sports.io/odds?fixture={fixture_id}"
        headers = {"x-rapidapi-key": FOOTBALL_API_KEY}
        resp = requests.get(url, headers=headers, timeout=10)
        data = resp.json()
        
        if data.get("response") and len(data["response"]) > 0:
            result = {}
            # Берём первую букмекерскую контору
            bookmaker = data["response"][0].get("bookmakers", [])[0] if data["response"][0].get("bookmakers") else None
            if not bookmaker:
                return None
            
            for bet in bookmaker.get("bets", []):
                if bet.get("name") == "Both Teams To Score":
                    for value in bet.get("values", []):
                        if value.get("value") == "Yes":
                            result["btts_yes"] = float(value.get("odd", 1.9))
                        elif value.get("value") == "No":
                            result["btts_no"] = float(value.get("odd", 2.1))
                elif bet.get("name") == "Total Goals Over/Under":
                    for value in bet.get("values", []):
                        if value.get("value") == "Over 2.5":
                            result["over_2_5"] = float(value.get("odd", 1.85))
                        elif value.get("value") == "Under 2.5":
                            result["under_2_5"] = float(value.get("odd", 2.0))
                elif bet.get("name") == "Match Winner":
                    for value in bet.get("values", []):
                        if value.get("value") == "Home":
                            result["home_win"] = float(value.get("odd", 2.1))
                        elif value.get("value") == "Away":
                            result["away_win"] = float(value.get("odd", 3.5))
                        elif value.get("value") == "Draw":
                            result["draw"] = float(value.get("odd", 3.2))
            return result if result else None
    except Exception as e:
        pass
    return None

def get_matches_with_factors(date=None):
    if date is None:
        date = datetime.now().strftime('%Y-%m-%d')
    all_matches = []
    leagues = load_leagues()
    for league_id in leagues:
        try:
            url = f"https://v3.football.api-sports.io/fixtures?league={league_id}&season=2026&date={date}"
            headers = {"x-rapidapi-key": FOOTBALL_API_KEY}
            resp = requests.get(url, headers=headers, timeout=15)
            data = resp.json()
            if data.get("response"):
                for match in data["response"]:
                    if match["fixture"]["status"]["short"] == "NS":
                        home_id = match["teams"]["home"]["id"]
                        away_id = match["teams"]["away"]["id"]
                        fixture_id = match["fixture"]["id"]
                        
                        home_motivation, home_motivation_text = get_motivation(home_id, league_id)
                        away_motivation, away_motivation_text = get_motivation(away_id, league_id)
                        
                        match["factors"] = {
                            "home_form": get_form(home_id),
                            "away_form": get_form(away_id),
                            "home_injuries": get_injuries(home_id)[0],
                            "away_injuries": get_injuries(away_id)[0],
                            "home_injuries_list": get_injuries(home_id)[1],
                            "away_injuries_list": get_injuries(away_id)[1],
                            "home_motivation": home_motivation,
                            "away_motivation": away_motivation,
                            "home_motivation_text": home_motivation_text,
                            "away_motivation_text": away_motivation_text,
                            "home_rank": int(home_motivation_text.split()[0]) if home_motivation_text and home_motivation_text[0].isdigit() else 10,
                            "away_rank": int(away_motivation_text.split()[0]) if away_motivation_text and away_motivation_text[0].isdigit() else 10,
                            "h2h": get_h2h(home_id, away_id),
                            "referee": get_referee_style(fixture_id),
                            "home_scorers": get_top_scorers(home_id),
                            "away_scorers": get_top_scorers(away_id),
                        }
                        all_matches.append(match)
        except Exception as e:
            pass
    return all_matches

# ===== ПОИСК ЛУЧШЕЙ СТАВКИ (С РЕАЛЬНЫМИ КЭФАМИ) =====
def find_best_bet(matches):
    bank = load_bank()
    best_bet = None
    best_ev = -100
    
    for match in matches:
        try:
            home = match["teams"]["home"]["name"]
            away = match["teams"]["away"]["name"]
            league = match["league"]["name"]
            league_id = match["league"]["id"]
            fixture_id = match["fixture"]["id"]
            factors = match.get("factors", {})
            
            # ===== ПОЛУЧАЕМ РЕАЛЬНЫЕ КЭФЫ =====
            real_odds = get_real_odds(fixture_id)
            if not real_odds:
                continue
            
            stats_url = f"https://v3.football.api-sports.io/fixtures/statistics?fixture={fixture_id}"
            headers = {"x-rapidapi-key": FOOTBALL_API_KEY}
            resp = requests.get(stats_url, headers=headers, timeout=10)
            stats = resp.json()
            
            raw_home_xg, raw_away_xg = 1.5, 1.3
            for stat in stats.get("response", []):
                if stat["team"]["name"] == home:
                    for item in stat.get("statistics", []):
                        if item["type"] == "expected_goals":
                            raw_home_xg = float(item["value"] or 1.5)
                elif stat["team"]["name"] == away:
                    for item in stat.get("statistics", []):
                        if item["type"] == "expected_goals":
                            raw_away_xg = float(item["value"] or 1.3)
            
            home_xg, away_xg, ik_reasons = calculate_super_ik(match, raw_home_xg, raw_away_xg)
            probs = calculate_probs(home_xg, away_xg)
            
            # ===== БЕТ-ТИПЫ С РЕАЛЬНЫМИ КЭФАМИ =====
            bet_types = []
            
            # ОЗ - ДА
            btts_yes_odds = real_odds.get("btts_yes", 1.9)
            bet_types.append(("btts", btts_yes_odds, "ОЗ - ДА"))
            
            # Тотал > 2.5
            over_odds = real_odds.get("over_2_5", 1.85)
            bet_types.append(("over_2_5", over_odds, "Тотал > 2.5"))
            
            # Тотал < 2.5
            under_odds = real_odds.get("under_2_5", 2.0)
            bet_types.append(("under_2_5", under_odds, "Тотал < 2.5"))
            
            # Победа хозяев
            home_win_odds = real_odds.get("home_win", 2.1)
            bet_types.append(("home_win", home_win_odds, "Победа хозяев"))
            
            # Победа гостей
            away_win_odds = real_odds.get("away_win", 3.5)
            bet_types.append(("away_win", away_win_odds, "Победа гостей"))
            
            # Ничья
            draw_odds = real_odds.get("draw", 3.2)
            bet_types.append(("draw", draw_odds, "Ничья"))
            
            # 1Х (хозяева не проиграют)
            if draw_odds and home_win_odds:
                home_or_draw_odds = 1 / ((1 / home_win_odds) + (1 / draw_odds))
                bet_types.append(("home_or_draw", home_or_draw_odds, "1Х"))
            
            # 2Х (гости не проиграют)
            if draw_odds and away_win_odds:
                away_or_draw_odds = 1 / ((1 / away_win_odds) + (1 / draw_odds))
                bet_types.append(("away_or_draw", away_or_draw_odds, "2Х"))
            
            for bet_type, odds, label in bet_types:
                prob = probs.get(bet_type, 0)
                if prob < 0.1 or prob > 0.99:
                    continue
                ev = (prob * odds) - 1
                if ev > best_ev:
                    best_ev = ev
                    stake = bank * 0.05
                    if stake < 1:
                        stake = 1
                    best_bet = {
                        "home": home,
                        "away": away,
                        "league": league,
                        "league_id": league_id,
                        "fixture_id": fixture_id,
                        "bet": label,
                        "bet_type": bet_type,
                        "odds": round(odds, 2),
                        "real_odds": real_odds,
                        "prob": round(prob * 100, 1),
                        "ev": round(ev * 100, 1),
                        "stake": round(stake, 2),
                        "home_xg": round(home_xg, 2),
                        "away_xg": round(away_xg, 2),
                        "raw_home_xg": round(raw_home_xg, 2),
                        "raw_away_xg": round(raw_away_xg, 2),
                        "ik_reasons": ik_reasons,
                        "referee": factors.get("referee"),
                        "factors": {
                            "home_form": round(factors.get("home_form", {}).get("ratio", 0.5), 2),
                            "away_form": round(factors.get("away_form", {}).get("ratio", 0.5), 2),
                            "home_injuries": factors.get("home_injuries", 1.0),
                            "away_injuries": factors.get("away_injuries", 1.0),
                            "home_injuries_list": factors.get("home_injuries_list", []),
                            "away_injuries_list": factors.get("away_injuries_list", []),
                            "home_motivation": factors.get("home_motivation", 1.0),
                            "away_motivation": factors.get("away_motivation", 1.0),
                            "home_motivation_text": factors.get("home_motivation_text", ""),
                            "away_motivation_text": factors.get("away_motivation_text", ""),
                            "home_scorers": factors.get("home_scorers", []),
                            "away_scorers": factors.get("away_scorers", []),
                        }
                    }
        except Exception as e:
            pass
    
    if best_bet and best_ev > 0.05:
        return best_bet
    return None

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
    
    all_xg = []
    for b in history:
        if 'home_xg' in b and 'away_xg' in b:
            all_xg.append(b['home_xg'])
            all_xg.append(b['away_xg'])
    if all_xg:
        prior = {
            "home": sum(all_xg) / len(all_xg),
            "away": sum(all_xg) / len(all_xg),
            "count": len(all_xg)
        }
        save_prior(prior)

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
            best = find_best_bet(matches)
            save_cache({"best_bet": best})
            train_model()
            send_telegram(f"✅ Кеш обновлён! Лучшая ставка найдена." if best else "❌ Ставок не найдено")
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
        chat_id = data['message']['chat']['id']
        
        if text == '/start':
            send_telegram("🚀 Бот запущен! Напиши /today для поиска ставок")
        
        elif text == '/today':
            cache = load_cache()
            if cache and cache.get("best_bet"):
                bet = cache["best_bet"]
            else:
                send_telegram("🔄 Обновляю кеш...")
                matches = get_matches_with_factors()
                bet = find_best_bet(matches)
                save_cache({"best_bet": bet})
                train_model()
            
            if bet:
                factors = bet.get("factors", {})
                ik_reasons = "\n".join([f"• {r}" for r in bet.get("ik_reasons", [])]) if bet.get("ik_reasons") else "Нет"
                real_odds = bet.get("real_odds", {})
                
                injuries_info = ""
                if factors.get("home_injuries_list"):
                    injuries_info += f"\n🏥 Травмы хозяев: {', '.join(factors['home_injuries_list'][:3])}"
                if factors.get("away_injuries_list"):
                    injuries_info += f"\n🏥 Травмы гостей: {', '.join(factors['away_injuries_list'][:3])}"
                
                scorers_info = ""
                if factors.get("home_scorers"):
                    scorers_info += f"\n⚽ Лучший бомбардир хозяев: {factors['home_scorers'][0]['name']} ({factors['home_scorers'][0]['goals']} голов)"
                if factors.get("away_scorers"):
                    scorers_info += f"\n⚽ Лучший бомбардир гостей: {factors['away_scorers'][0]['name']} ({factors['away_scorers'][0]['goals']} голов)"
                
                real_odds_info = ""
                if real_odds:
                    real_odds_info = f"""📊 <b>РЕАЛЬНЫЕ КЭФЫ:</b>
ОЗ - ДА: {real_odds.get('btts_yes', '—')}  |  ОЗ - НЕТ: {real_odds.get('btts_no', '—')}
Тотал > 2.5: {real_odds.get('over_2_5', '—')}  |  Тотал < 2.5: {real_odds.get('under_2_5', '—')}
П1: {real_odds.get('home_win', '—')}  |  X: {real_odds.get('draw', '—')}  |  П2: {real_odds.get('away_win', '—')}"""
                
                settings_status = f"""
⚙️ <b>Активные слои:</b>
• Улучшенная форма: {'✅' if SETTINGS['improved_form'] else '❌'}
• Судья: {'✅' if SETTINGS['referee'] else '❌'}
• Движение кэфов: {'✅' if SETTINGS['odds_movement'] else '❌'}
• PSY-фактор: {'✅' if SETTINGS['psy_factor'] else '❌'}
• Нейросетевое обучение: {'✅' if SETTINGS['neural_learning'] else '❌'}"""
                
                bet_id = f"{bet['fixture_id']}_{bet['bet_type']}"
                msg = f"""🔥 <b>РЕКОМЕНДАЦИЯ (ЛУЧШАЯ СТАВКА)</b>

🏟️ {bet['home']} vs {bet['away']}
🏆 {bet['league']}

🎯 <b>{bet['bet']}</b>
📈 КЭФ: {bet['odds']}
💰 РАЗМЕР: {bet['stake']}$ (5% банка)
📊 УВЕРЕННОСТЬ: {bet['prob']}%
📈 EV: <b>{bet['ev']}%</b> ← САМЫЙ ВЫСОКИЙ!

📊 xG: {bet['home_xg']} : {bet['away_xg']} (сырые: {bet['raw_home_xg']} : {bet['raw_away_xg']})
👨‍⚖️ Судья: {bet.get('referee', 'неизвестен')}

{real_odds_info}

📋 <b>КЛЮЧЕВЫЕ ФАКТОРЫ:</b>
📈 Форма хозяев: {factors.get('home_form', 0.5)*100:.0f}%
📈 Форма гостей: {factors.get('away_form', 0.5)*100:.0f}%
🎯 Мотивация хозяев: {factors.get('home_motivation', 1.0)*100:.0f}% ({factors.get('home_motivation_text', '')})
🎯 Мотивация гостей: {factors.get('away_motivation', 1.0)*100:.0f}% ({factors.get('away_motivation_text', '')})
{injuries_info}
{scorers_info}

🧠 <b>СУПЕР-СЛОЙ (Байес + IK):</b>
{ik_reasons}
{settings_status}"""
                send_telegram_with_buttons(msg, bet_id)
            else:
                send_telegram("❌ Сегодня валуйных ставок не найдено")
        
        elif text == '/tomorrow':
            tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
            send_telegram(f"🔄 Поиск матчей на {tomorrow}...")
            matches = get_matches_with_factors(tomorrow)
            bet = find_best_bet(matches)
            save_cache({"best_bet": bet})
            train_model()
            if bet:
                factors = bet.get("factors", {})
                ik_reasons = "\n".join([f"• {r}" for r in bet.get("ik_reasons", [])]) if bet.get("ik_reasons") else "Нет"
                real_odds = bet.get("real_odds", {})
                
                real_odds_info = ""
                if real_odds:
                    real_odds_info = f"\n📊 Реальные кэфы: ОЗ {real_odds.get('btts_yes', '—')} | Тотал > 2.5 {real_odds.get('over_2_5', '—')}"
                
                msg = f"""🔥 <b>РЕКОМЕНДАЦИЯ НА ЗАВТРА</b>

🏟️ {bet['home']} vs {bet['away']}
🏆 {bet['league']}

🎯 <b>{bet['bet']}</b>
📈 КЭФ: {bet['odds']}
💰 РАЗМЕР: {bet['stake']}$ (5% банка)
📊 УВЕРЕННОСТЬ: {bet['prob']}%
📈 EV: <b>{bet['ev']}%</b>{real_odds_info}

📊 xG: {bet['home_xg']} : {bet['away_xg']}

🧠 <b>СУПЕР-СЛОЙ:</b>
{ik_reasons}"""
                send_telegram_with_buttons(msg, f"{bet['fixture_id']}_{bet['bet_type']}")
            else:
                send_telegram(f"❌ На {tomorrow} валуйных ставок не найдено")
        
        elif text == '/matches':
            matches = get_matches_with_factors()
            if matches:
                leagues_found = set()
                for m in matches:
                    leagues_found.add(m.get("league", {}).get("name", "Неизвестно"))
                msg = f"✅ Найдено {len(matches)} матчей на сегодня\n\n"
                for league in sorted(leagues_found):
                    count = sum(1 for m in matches if m.get("league", {}).get("name") == league)
                    msg += f"• {league}: {count} матчей\n"
                send_telegram(msg)
            else:
                send_telegram("❌ Матчей на сегодня не найдено")
        
        elif text == '/leagues':
            leagues = load_leagues()
            msg = "📋 <b>СПИСОК ЛИГ:</b>\n\n"
            for lid in leagues:
                name = LEAGUE_NAMES.get(lid, f"Лига {lid}")
                msg += f"• {name} (ID: {lid})\n"
            send_telegram(msg)
        
        elif text.startswith('/add_league'):
            try:
                lid = int(text.split()[1])
                leagues = load_leagues()
                if lid not in leagues:
                    leagues.append(lid)
                    save_leagues(leagues)
                    send_telegram(f"✅ Лига {lid} добавлена!")
                else:
                    send_telegram(f"ℹ️ Лига {lid} уже есть в списке")
            except:
                send_telegram("❌ Используйте: /add_league ID")
        
        elif text.startswith('/remove_league'):
            try:
                lid = int(text.split()[1])
                leagues = load_leagues()
                if lid in leagues:
                    leagues.remove(lid)
                    save_leagues(leagues)
                    send_telegram(f"✅ Лига {lid} удалена!")
                else:
                    send_telegram(f"ℹ️ Лига {lid} не найдена в списке")
            except:
                send_telegram("❌ Используйте: /remove_league ID")
        
        elif text.startswith('/today_league'):
            try:
                lid = int(text.split()[1])
                matches = get_matches_with_factors()
                matches = [m for m in matches if m.get("league", {}).get("id") == lid]
                if matches:
                    bet = find_best_bet(matches)
                    if bet:
                        msg = f"""🔥 <b>ЛУЧШАЯ СТАВКА В ЛИГЕ</b>

🏟️ {bet['home']} vs {bet['away']}
🏆 {bet['league']}

🎯 <b>{bet['bet']}</b>
📈 КЭФ: {bet['odds']}
💰 РАЗМЕР: {bet['stake']}$ (5% банка)
📊 УВЕРЕННОСТЬ: {bet['prob']}%
📈 EV: <b>{bet['ev']}%</b>"""
                        send_telegram_with_buttons(msg, f"{bet['fixture_id']}_{bet['bet_type']}")
                    else:
                        send_telegram(f"❌ В лиге {lid} нет валуйных ставок")
                else:
                    send_telegram(f"❌ В лиге {lid} нет матчей сегодня")
            except:
                send_telegram("❌ Используйте: /today_league ID")
        
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
            bet = find_best_bet(matches)
            save_cache({"best_bet": bet})
            train_model()
            send_telegram("✅ Кеш обновлён!" if bet else "❌ Ставок не найдено")
        
        elif text.startswith('/setbank'):
            try:
                new_bank = float(text.split()[1])
                save_bank(new_bank)
                send_telegram(f"✅ Банк установлен: ${new_bank}")
            except:
                send_telegram("❌ Введите сумму: /setbank 1500")
        
        elif text == '/settings':
            status = f"""⚙️ <b>ТЕКУЩИЕ НАСТРОЙКИ</b>
Улучшенная форма: {'✅ Вкл' if SETTINGS['improved_form'] else '❌ Выкл'}
Судья: {'✅ Вкл' if SETTINGS['referee'] else '❌ Выкл'}
Движение кэфов: {'✅ Вкл' if SETTINGS['odds_movement'] else '❌ Выкл'}
PSY-фактор: {'✅ Вкл' if SETTINGS['psy_factor'] else '❌ Выкл'}
Нейросетевое обучение: {'✅ Вкл' if SETTINGS['neural_learning'] else '❌ Выкл'}

Используйте /toggle [номер] чтобы включить/выключить слой:
1 - Улучшенная форма
2 - Судья
3 - Движение кэфов
4 - PSY-фактор
5 - Нейросетевое обучение"""
            send_telegram(status)
        
        elif text.startswith('/toggle'):
            try:
                num = int(text.split()[1])
                layers = ["improved_form", "referee", "odds_movement", "psy_factor", "neural_learning"]
                if 1 <= num <= 5:
                    key = layers[num-1]
                    SETTINGS[key] = not SETTINGS[key]
                    send_telegram(f"✅ Слой '{key}' {'включен' if SETTINGS[key] else 'выключен'}")
                else:
                    send_telegram("❌ Введите номер слоя от 1 до 5")
            except:
                send_telegram("❌ Используйте: /toggle 1")
        
        elif text == '/help':
            send_telegram("""📖 <b>КОМАНДЫ:</b>
/today - ЛУЧШАЯ ставка на сегодня
/tomorrow - ЛУЧШАЯ ставка на завтра
/matches - Показать матчи на сегодня
/leagues - Список всех лиг
/add_league ID - Добавить лигу
/remove_league ID - Удалить лигу
/today_league ID - Лучшая ставка в лиге
/bank - Текущий банк
/stats - Статистика
/update - Обновить кеш
/setbank 1500 - Установить банк
/settings - Настройки слоёв
/toggle 1 - Включить/выключить слой
/help - Помощь""")
        
        else:
            send_telegram("Неизвестная команда. Напиши /help")
    
    return "ok"

@app.route('/', methods=['GET'])
def index():
    return "Quantum Bot v9.0 Ultimate with Real Odds is running!"

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=10000)
