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

# ===== ЛИГИ =====
LEAGUES = [39, 140, 78, 135, 61, 94, 88, 144, 203, 218, 179, 113, 84, 90, 197, 52, 103, 111, 169, 213, 142, 123, 157, 223, 170, 73, 97]

# ===== НАСТРОЙКИ СЛОЁВ (можно менять) =====
SETTINGS = {
    "improved_form": True,      # Улучшенная форма (учёт силы соперника)
    "referee": True,            # Судья
    "odds_movement": True,      # Движение коэффициентов
    "psy_factor": True,         # PSY-фактор (психология)
    "neural_learning": True,    # Нейросетевое обучение
}

# ===== ФАЙЛЫ =====
CACHE_FILE = "cache.json"
HISTORY_FILE = "history.json"
WEIGHTS_FILE = "weights.json"
BANK_FILE = "bank.json"
ODDS_HISTORY_FILE = "odds_history.json"
PRIOR_FILE = "prior.json"

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
        "home_win": sum(probs[i][j] for i in range(7) for j in range(7) if i > j),
        "away_win": sum(probs[i][j] for i in range(7) for j in range(7) if i < j),
        "draw": sum(probs[i][i] for i in range(7)),
        "home_or_draw": sum(probs[i][j] for i in range(7) for j in range(7) if i >= j),
        "away_or_draw": sum(probs[i][j] for i in range(7) for j in range(7) if i <= j),
    }

# ===== ДОПОЛНИТЕЛЬНЫЕ СЛОИ (с возможностью выключения) =====

# ---- 1. УЛУЧШЕННАЯ ФОРМА (учёт силы соперника) ----
def apply_improved_form(home_xg, away_xg, match):
    if not SETTINGS.get("improved_form", True):
        return home_xg, away_xg, []
    
    reasons = []
    # Получаем рейтинг соперников из таблицы
    home_rank = match.get("factors", {}).get("home_rank", 10)
    away_rank = match.get("factors", {}).get("away_rank", 10)
    
    if home_rank < 5 and away_rank > 15:
        home_xg *= 1.05
        reasons.append("📈 Улучшенная форма: победа над сильным соперником (+5%)")
    elif home_rank > 15 and away_rank < 5:
        away_xg *= 1.05
        reasons.append("📈 Улучшенная форма: победа над сильным соперником (+5%)")
    
    return home_xg, away_xg, reasons

# ---- 2. СУДЬЯ ----
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

# ---- 3. ДВИЖЕНИЕ КОЭФФИЦИЕНТОВ ----
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
            reasons.append(f"📉 Кэф упал с {first_odds:.2f} до {last_odds:.2f} (-{first_odds-last_odds:.2f}) → снижение xG на 5%")
        elif last_odds - first_odds > 0.15:
            home_xg *= 1.02
            away_xg *= 1.02
            reasons.append(f"📈 Кэф вырос с {first_odds:.2f} до {last_odds:.2f} (+{last_odds-first_odds:.2f}) → повышение xG на 2%")
    
    return home_xg, away_xg, reasons

# ---- 4. PSY-ФАКТОР (психология) ----
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

# ---- 5. НЕЙРОСЕТЕВОЕ ОБУЧЕНИЕ (веса на основе истории) ----
def apply_neural_learning(home_xg, away_xg, league):
    if not SETTINGS.get("neural_learning", True):
        return home_xg, away_xg, []
    
    reasons = []
    weights = load_weights()
    league_weight = weights.get(league, {}).get("xg", 1.0)
    
    if league_weight != 1.0:
        home_xg *= league_weight
        away_xg *= league_weight
        reasons.append(f"🧠 Нейросеть: вес лиги {league_weight:.2f} (на основе истории)")
    
    return home_xg, away_xg, reasons

# ===== ОБНОВЛЕНИЕ КЭФОВ (для движения) =====
def update_odds_history(fixture_id, current_odds):
    history = load_odds_history()
    key = str(fixture_id)
    
    if key not in history:
        history[key] = []
    
    history[key].append({
        "time": datetime.now().isoformat(),
        "odds": current_odds
    })
    
    if len(history[key]) > 10:
        history[key] = history[key][-10:]
    
    save_odds_history(history)

# ===== СУПЕР-СЛОЙ: БАЙЕС + ВСЕ СЛОИ (с настройками) =====
def calculate_super_ik(match, raw_home_xg, raw_away_xg):
    reasons = []
    
    # ===== 1. БАЙЕСОВСКАЯ КОРРЕКЦИЯ (всегда) =====
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
    
    # ===== 2. БАЗОВЫЕ ФАКТОРЫ (всегда) =====
    factors = match.get("factors", {})
    home_form = factors.get("home_form", {})
    away_form = factors.get("away_form", {})
    h2h = factors.get("h2h")
    
    # Форма
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
    
    # Травмы
    home_inj = factors.get("home_injuries", 1.0)
    away_inj = factors.get("away_injuries", 1.0)
    if home_inj < 0.9:
        home_xg *= 0.93
        reasons.append("🏥 Травмы хозяев (-7%)")
    if away_inj < 0.9:
        away_xg *= 0.93
        reasons.append("🏥 Травмы гостей (-7%)")
    
    # Мотивация
    home_mot = factors.get("home_motivation", 1.0)
    away_mot = factors.get("away_motivation", 1.0)
    if home_mot > 1.05:
        home_xg *= 1.05
        reasons.append("🎯 Мотивация хозяев (+5%)")
    if away_mot > 1.05:
        away_xg *= 1.05
        reasons.append("🎯 Мотивация гостей (+5%)")
    
    # Домашний стадион
    home_xg *= 1.05
    reasons.append("🏠 Домашний стадион (+5%)")
    
    # H2H
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
    
    # Неудобный соперник
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
    
    # Экспертные правила
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
    
    # Индивидуальный профиль игроков
    home_scorers = factors.get("home_scorers", [])
    away_scorers = factors.get("away_scorers", [])
    if home_scorers:
        reasons.append(f"⚽ Лучший бомбардир хозяев: {home_scorers[0]['name']} ({home_scorers[0]['goals']} голов)")
    if away_scorers:
        reasons.append(f"⚽ Лучший бомбардир гостей: {away_scorers[0]['name']} ({away_scorers[0]['goals']} голов)")
    
    # ===== 3. ДОПОЛНИТЕЛЬНЫЕ СЛОИ (опционально) =====
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
    
    # Обновляем историю кэфов
    if fixture_id:
        update_odds_history(fixture_id, 1.9)
    
    return home_xg, away_xg, reasons

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
                return 0.85, [p["player"]["name"] for p in data["response"][:3]]
            elif injured_players >= 1:
                return 0.93, [p["player"]["name"] for p in data["response"]]
    except:
        pass
    return 1.0, []

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
                            if pos <= 4:
                                return 1.10, f"{pos}-е место (борьба за еврокубки)"
                            elif pos >= total - 3:
                                return 1.10, f"{pos}-е место (борьба за выживание)"
                            else:
                                return 1.0, f"{pos}-е место"
    except:
        pass
    return 1.0, "неизвестно"

# ===== H2H =====
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

# ===== ПОЛУЧЕНИЕ СУДЬИ =====
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

# ===== ПОЛУЧЕНИЕ БОМБАРДИРОВ =====
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

# ===== ПОИСК СТАВОК =====
def find_value_bets(matches):
    bank = load_bank()
    bets = []
    
    for match in matches:
        try:
            home = match["teams"]["home"]["name"]
            away = match["teams"]["away"]["name"]
            league = match["league"]["name"]
            fixture_id = match["fixture"]["id"]
            factors = match.get("factors", {})
            
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
                    ik_reasons = "\n".join([f"• {r}" for r in bet.get("ik_reasons", [])]) if bet.get("ik_reasons") else "Нет"
                    
                    injuries_info = ""
                    if factors.get("home_injuries_list"):
                        injuries_info += f"\n🏥 Травмы хозяев: {', '.join(factors['home_injuries_list'][:3])}"
                    if factors.get("away_injuries_list"):
                        injuries_info += f"\n🏥 Травмы гостей: {', '.join(factors['away_injuries_list'][:3])}"
                    
                    scorers_info = ""
                    if factors.get("home_scorers"):
                        scorers_info += f"\n⚽ Лучшие бомбардиры хозяев: {', '.join([s['name'] for s in factors['home_scorers'][:3]])}"
                    if factors.get("away_scorers"):
                        scorers_info += f"\n⚽ Лучшие бомбардиры гостей: {', '.join([s['name'] for s in factors['away_scorers'][:3]])}"
                    
                    settings_status = f"""
⚙️ <b>Активные слои:</b>
• Улучшенная форма: {'✅' if SETTINGS['improved_form'] else '❌'}
• Судья: {'✅' if SETTINGS['referee'] else '❌'}
• Движение кэфов: {'✅' if SETTINGS['odds_movement'] else '❌'}
• PSY-фактор: {'✅' if SETTINGS['psy_factor'] else '❌'}
• Нейросетевое обучение: {'✅' if SETTINGS['neural_learning'] else '❌'}"""
                    
                    msg = f"""✅ <b>ВАЛУЙНАЯ СТАВКА!</b>
🏟️ {bet['home']} vs {bet['away']}
🏆 {bet['league']}
🎯 {bet['bet']} | КЭФ: {bet['odds']}
💰 РАЗМЕР: {bet['stake']}$ (5% банка)
📊 УВЕРЕННОСТЬ: {bet['prob']}%
📈 EV: {bet['ev']}%
📊 xG: {bet['home_xg']} : {bet['away_xg']} (сырые: {bet['raw_home_xg']} : {bet['raw_away_xg']})
👨‍⚖️ Судья: {bet.get('referee', 'неизвестен')}

📋 <b>ФАКТОРЫ:</b>
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
            send_telegram("""📖 <b>Команды:</b>
/today - ставки на сегодня
/bank - текущий банк
/stats - статистика
/update - обновить кеш
/setbank 1500 - установить банк
/settings - настройки слоёв
/toggle 1 - включить/выключить слой
/help - помощь""")
        
        else:
            send_telegram("Неизвестная команда. Напиши /help")
    
    return "ok"

@app.route('/', methods=['GET'])
def index():
    return "Quantum Bot v9.0 Ultimate is running!"

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=10000)
