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

load_dotenv()

app = Flask(__name__)

# ===== КОНФИГ =====
TELEGRAM_TOKEN = "8757780924:AAEteceqwZmFDCpWJUZBj-gwc1DGCl-dv74"
FOOTBALL_API_KEY = "fa6a81c18feae6769a0fa3baefd9e476"
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

def odds_to_probability(odds):
    if odds <= 1:
        return 0
    return round((1 / odds) * 100, 1)

# ===== УПРАВЛЕНИЕ РИСКАМИ =====
class RiskManager:
    def __init__(self):
        self.daily_loss = 0
        self.daily_loss_limit = float(os.getenv('MAX_DAILY_LOSS', 100))
        self.consecutive_losses = 0
        self.max_consecutive_losses = int(os.getenv('MAX_CONSECUTIVE_LOSSES', 3))
        self.bets_today = 0
        self.max_bets_per_day = 10
        self.current_day = datetime.now().date()
        self.lock = threading.Lock()
    
    def reset_if_new_day(self):
        today = datetime.now().date()
        if today != self.current_day:
            with self.lock:
                self.daily_loss = 0
                self.bets_today = 0
                self.current_day = today
    
    def can_bet(self, stake: float, bank: float) -> Tuple[bool, str]:
        self.reset_if_new_day()
        with self.lock:
            if self.daily_loss + stake > self.daily_loss_limit:
                return False, f"❌ Дневной лимит (${self.daily_loss_limit}) превышен!"
            if self.bets_today >= self.max_bets_per_day:
                return False, f"❌ Лимит ставок в день ({self.max_bets_per_day})!"
            if self.consecutive_losses >= self.max_consecutive_losses:
                return False, f"❌ Серия проигрышей ({self.consecutive_losses})!"
            if stake > bank * 0.1:
                return False, f"❌ Ставка превышает 10% банка!"
            if stake < 0.5:
                return False, f"❌ Ставка меньше $0.50!"
            return True, "✅ OK"
    
    def update_after_bet(self, result: str, stake: float, profit: float = 0):
        self.reset_if_new_day()
        with self.lock:
            if result == 'loss':
                self.daily_loss += stake
                self.consecutive_losses += 1
            elif result == 'win':
                self.consecutive_losses = 0
                self.daily_loss = max(0, self.daily_loss - profit * 0.3)
            self.bets_today += 1
    
    def get_status(self) -> str:
        self.reset_if_new_day()
        return f"""📊 Риск-менеджер:
• Проигрыш: ${self.daily_loss:.2f} / ${self.daily_loss_limit}
• Ставок: {self.bets_today} / {self.max_bets_per_day}
• Серия: {self.consecutive_losses} / {self.max_consecutive_losses}"""

risk_manager = RiskManager()

# ===== КРИТЕРИЙ КЕЛЛИ =====
def calculate_kelly_stake(prob: float, odds: float, bank: float, max_fraction: float = 0.25) -> float:
    if odds <= 1 or prob <= 0 or prob >= 1 or prob < 0.45:
        return 0
    b = odds - 1
    q = 1 - prob
    f = (b * prob - q) / b
    f = max(0, min(f, max_fraction))
    stake = round(bank * f, 2)
    return max(stake, 0.5)

# ===== УЛУЧШЕННЫЙ АНАЛИЗ xG =====
def calculate_xg_with_context(match, raw_home_xg, raw_away_xg):
    factors = match.get('factors', {})
    reasons = []
    
    home_xg = raw_home_xg * 1.1
    away_xg = raw_away_xg
    reasons.append("🏠 Домашнее поле (+10%)")
    
    home_form = factors.get('home_form', {}).get('ratio', 0.5)
    away_form = factors.get('away_form', {}).get('ratio', 0.5)
    
    if home_form > 0.7:
        home_xg *= 1.08
        reasons.append(f"📈 Хозяева в форме ({home_form*100:.0f}%) +8%")
    elif home_form < 0.3:
        home_xg *= 0.92
        reasons.append(f"📉 Хозяева в кризисе ({home_form*100:.0f}%) -8%")
    
    if away_form > 0.7:
        away_xg *= 1.08
        reasons.append(f"📈 Гости в форме ({away_form*100:.0f}%) +8%")
    elif away_form < 0.3:
        away_xg *= 0.92
        reasons.append(f"📉 Гости в кризисе ({away_form*100:.0f}%) -8%")
    
    home_inj = factors.get('home_injuries', 1.0)
    away_inj = factors.get('away_injuries', 1.0)
    if home_inj < 0.9:
        home_xg *= 0.92
        reasons.append("🏥 Травмы хозяев (-8%)")
    if away_inj < 0.9:
        away_xg *= 0.92
        reasons.append("🏥 Травмы гостей (-8%)")
    
    h2h = factors.get('h2h')
    if h2h and h2h.get('matches', 0) >= 3:
        h2h_home = h2h.get('home_avg', 1.0)
        h2h_away = h2h.get('away_avg', 1.0)
        home_xg = home_xg * 0.6 + h2h_home * 0.4
        away_xg = away_xg * 0.6 + h2h_away * 0.4
        reasons.append("📊 Коррекция по H2H")
    
    home_xg = max(0.3, min(home_xg, 4.0))
    away_xg = max(0.3, min(away_xg, 4.0))
    
    return home_xg, away_xg, reasons

# ===== СЛОИ АНАЛИЗА =====
def apply_improved_form(home_xg, away_xg, match):
    if not SETTINGS.get("improved_form", True):
        return home_xg, away_xg, []
    reasons = []
    home_rank = match.get("factors", {}).get("home_rank", 10)
    away_rank = match.get("factors", {}).get("away_rank", 10)
    if home_rank < 5 and away_rank > 15:
        home_xg *= 1.05
        reasons.append("📈 Улучшенная форма (+5%)")
    elif home_rank > 15 and away_rank < 5:
        away_xg *= 1.05
        reasons.append("📈 Улучшенная форма (+5%)")
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
                reasons.append(f"👨‍⚖️ Строгий судья: {referee} (-5%)")
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
            reasons.append(f"📉 Кэф упал {first_odds:.2f}→{last_odds:.2f} (-5%)")
        elif last_odds - first_odds > 0.15:
            home_xg *= 1.02
            away_xg *= 1.02
            reasons.append(f"📈 Кэф вырос {first_odds:.2f}→{last_odds:.2f} (+2%)")
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
        reasons.append("🧠 Дерби (-8%)")
    if home_form.get("losses", 0) >= 3 and away_form.get("wins", 0) >= 3:
        home_xg *= 0.93
        away_xg *= 1.05
        reasons.append("🧠 Кризис vs подъём (-7%/+5%)")
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
        reasons.append(f"🧠 Нейросеть: вес {league_weight:.2f}")
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
    
    home_xg, away_xg, context_reasons = calculate_xg_with_context(match, raw_home_xg, raw_away_xg)
    reasons.extend(context_reasons)
    
    home_xg = (home_xg * 5 + home_prior * alpha) / (5 + alpha)
    away_xg = (away_xg * 5 + away_prior * alpha) / (5 + alpha)
    
    if abs(home_xg - raw_home_xg) > 0.15:
        reasons.append(f"📊 Байес: {raw_home_xg:.2f}→{home_xg:.2f}")
    if abs(away_xg - raw_away_xg) > 0.15:
        reasons.append(f"📊 Байес: {raw_away_xg:.2f}→{away_xg:.2f}")
    
    home_xg, away_xg, add_reasons = apply_improved_form(home_xg, away_xg, match)
    reasons.extend(add_reasons)
    home_xg, away_xg, add_reasons = apply_referee(home_xg, away_xg, match)
    reasons.extend(add_reasons)
    
    fixture_id = match.get("fixture", {}).get("id")
    home_xg, away_xg, add_reasons = apply_odds_movement(home_xg, away_xg, fixture_id)
    reasons.extend(add_reasons)
    home_xg, away_xg, add_reasons = apply_psy_factor(home_xg, away_xg, match)
    reasons.extend(add_reasons)
    
    league_name = match.get("league", {}).get("name", "")
    home_xg, away_xg, add_reasons = apply_neural_learning(home_xg, away_xg, league_name)
    reasons.extend(add_reasons)
    
    if fixture_id:
        update_odds_history(fixture_id, 1.9)
    
    home_xg = max(0.3, min(home_xg, 4.5))
    away_xg = max(0.3, min(away_xg, 4.5))
    
    return home_xg, away_xg, reasons

# ===== ПОЛУЧЕНИЕ ДАННЫХ =====
def get_form(team_id):
    try:
        url = f"https://v3.football.api-sports.io/fixtures?team={team_id}&last=5"
        headers = {"x-rapidapi-key": FOOTBALL_API_KEY}
        resp = requests.get(url, headers=headers, timeout=15)
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
        resp = requests.get(url, headers=headers, timeout=15)
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
        resp = requests.get(url, headers=headers, timeout=15)
        data = resp.json()
        if data.get("response"):
            for league in data["response"]:
                for standing in league["league"]["standings"]:
                    for team in standing:
                        if team["team"]["id"] == team_id:
                            pos = team["rank"]
                            total = len(standing)
                            if pos <= 4:
                                return 1.10, f"{pos}-е место (еврокубки)"
                            elif pos >= total - 3:
                                return 1.10, f"{pos}-е место (выживание)"
                            else:
                                return 1.0, f"{pos}-е место"
    except:
        pass
    return 1.0, "неизвестно"

def get_h2h(home_id, away_id):
    try:
        url = f"https://v3.football.api-sports.io/fixtures/headtohead?h2h={home_id}-{away_id}&last=5"
        headers = {"x-rapidapi-key": FOOTBALL_API_KEY}
        resp = requests.get(url, headers=headers, timeout=15)
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
        resp = requests.get(url, headers=headers, timeout=15)
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
        resp = requests.get(url, headers=headers, timeout=15)
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

# ===== ПОЛУЧЕНИЕ МАТЧЕЙ С ФАКТОРАМИ =====
def get_matches_with_factors():
    all_matches = []
    today = datetime.now().strftime('%Y-%m-%d')
    
    logger.info("=" * 60)
    logger.info(f"🔍 ИЩУ МАТЧИ ЗА {today}...")
    logger.info("=" * 60)
    
    for league_id in LEAGUES:
        for season in ["2026", "2025"]:
            try:
                url = f"https://v3.football.api-sports.io/fixtures?league={league_id}&season={season}&date={today}"
                headers = {"x-rapidapi-key": FOOTBALL_API_KEY}
                
                league_name = LEAGUE_NAMES.get(league_id, str(league_id))
                logger.info(f"📡 ЗАПРОС: {league_name} (ID:{league_id}, сезон {season})")
                
                resp = requests.get(url, headers=headers, timeout=20)
                logger.info(f"📡 ОТВЕТ: статус {resp.status_code}")
                
                if resp.status_code == 200:
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
                                match["league"]["name"] = league_name
                                all_matches.append(match)
                                logger.info(f"✅ {match['teams']['home']['name']} vs {match['teams']['away']['name']} ({league_name})")
                        break
                    else:
                        logger.info(f"⚠️ Нет матчей в {league_name} (сезон {season})")
                else:
                    logger.error(f"❌ ОШИБКА {resp.status_code}: {resp.text[:200]}")
                    
            except Exception as e:
                logger.error(f"❌ ИСКЛЮЧЕНИЕ: {e}")
            
            time.sleep(0.1)
    
    logger.info("=" * 60)
    logger.info(f"📊 ВСЕГО НАЙДЕНО МАТЧЕЙ: {len(all_matches)}")
    logger.info("=" * 60)
    return all_matches

# ===== ТЕСТОВЫЕ ДАННЫЕ =====
def get_test_matches():
    logger.info("📊 ТЕСТОВЫЙ РЕЖИМ")
    return [
        {"fixture": {"id": 1, "status": {"short": "NS"}}, "teams": {"home": {"name": "Arsenal"}, "away": {"name": "Chelsea"}}, "league": {"name": "АПЛ"}},
        {"fixture": {"id": 2, "status": {"short": "NS"}}, "teams": {"home": {"name": "Barcelona"}, "away": {"name": "Real Madrid"}}, "league": {"name": "Ла Лига"}},
        {"fixture": {"id": 3, "status": {"short": "NS"}}, "teams": {"home": {"name": "Bayern Munich"}, "away": {"name": "Dortmund"}}, "league": {"name": "Бундеслига"}},
        {"fixture": {"id": 4, "status": {"short": "NS"}}, "teams": {"home": {"name": "AC Milan"}, "away": {"name": "Inter"}}, "league": {"name": "Серия А"}},
        {"fixture": {"id": 5, "status": {"short": "NS"}}, "teams": {"home": {"name": "PSG"}, "away": {"name": "Marseille"}}, "league": {"name": "Лига 1"}},
        {"fixture": {"id": 6, "status": {"short": "NS"}}, "teams": {"home": {"name": "Flamengo"}, "away": {"name": "Palmeiras"}}, "league": {"name": "Бразилейрао"}},
        {"fixture": {"id": 7, "status": {"short": "NS"}}, "teams": {"home": {"name": "River Plate"}, "away": {"name": "Boca Juniors"}}, "league": {"name": "Аргентина"}},
    ]

# ===== ПОИСК ЛУЧШЕЙ СТАВКИ =====
def find_best_bet(matches):
    bank = load_bank()
    best_bet = None
    best_ev = -100
    
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
                if ev > best_ev and ev > 0.05:
                    stake = calculate_kelly_stake(prob, default_odds, bank)
                    
                    can_bet, _ = risk_manager.can_bet(stake, bank)
                    if not can_bet:
                        continue
                    
                    best_ev = ev
                    best_bet = {
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
                        "over_2_5": round(probs.get("over_2_5", 0) * 100, 1),
                        "prob_both_score": round(probs.get("btts", 0) * 100, 1),
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
            logger.error(f"find_best_bet error: {e}")
            continue
    
    if best_bet:
        return best_bet
    return None

# ===== ОБУЧЕНИЕ =====
def train_model():
    history = load_history()
    if len(history) < 20:
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
            xg_weight = 0.5 + (xg_weight - 0.5) * 0.5
            weights[league] = {"xg": round(xg_weight + 0.5, 2)}
    
    save_weights(weights)
    
    all_xg = []
    for b in history:
        if 'home_xg' in b and 'away_xg' in b:
            all_xg.append(b['home_xg'])
            all_xg.append(b['away_xg'])
    if all_xg:
        prior = {"home": sum(all_xg) / len(all_xg), "away": sum(all_xg) / len(all_xg), "count": len(all_xg)}
        save_prior(prior)

# ===== ОТПРАВКА УВЕДОМЛЕНИЯ О НОВОЙ СТАВКЕ =====
last_notified_bets = {}

def send_bet_notification(bet):
    global last_notified_bets
    
    if not bet:
        return
    
    if bet['ev'] < 5:
        return
    
    key = f"{bet['fixture_id']}_{bet['bet_type']}"
    if key in last_notified_bets and last_notified_bets[key] == bet['ev']:
        return
    
    last_notified_bets[key] = bet['ev']
    
    factors = bet.get("factors", {})
    ik_reasons = "\n".join([f"• {r}" for r in bet.get("ik_reasons", [])]) if bet.get("ik_reasons") else "Нет"
    
    if not SETTINGS.get("full_mode", False):
        msg = f"""🔥 <b>РЕКОМЕНДАЦИЯ</b>

🏟️ {bet['home']} vs {bet['away']}
🏆 {bet['league']}

🎯 <b>{bet['bet']}</b>
📈 КЭФ: {bet['odds']}
💰 РАЗМЕР: ${bet['stake']:.2f}
📊 УВЕРЕННОСТЬ: {bet['prob']}%
📈 EV: <b>{bet['ev']}%</b>

📊 xG: {bet['home_xg']} : {bet['away_xg']}

📋 {ik_reasons[:100]}...

💡 /mode - включить полный режим"""
        
        bet_id = f"{bet['fixture_id']}_{bet['bet_type']}_{int(time.time())}"
        send_telegram_with_buttons(msg, bet_id)
        return
    
    # ===== ПОЛНЫЙ РЕЖИМ =====
    injuries_info = ""
    if factors.get("home_injuries_list"):
        injuries_info += f"\n🏥 Травмы хозяев: {', '.join(factors['home_injuries_list'][:3])}"
    if factors.get("away_injuries_list"):
        injuries_info += f"\n🏥 Травмы гостей: {', '.join(factors['away_injuries_list'][:3])}"
    
    scorers_info = ""
    if factors.get("home_scorers"):
        scorers_info += f"\n⚽ Бомбардир хозяев: {factors['home_scorers'][0]['name']} ({factors['home_scorers'][0]['goals']} голов)"
    if factors.get("away_scorers"):
        scorers_info += f"\n⚽ Бомбардир гостей: {factors['away_scorers'][0]['name']} ({factors['away_scorers'][0]['goals']} голов)"
    
    bet_id = f"{bet['fixture_id']}_{bet['bet_type']}_{int(time.time())}"
    msg = f"""🔥 <b>РЕКОМЕНДАЦИЯ (ПОЛНЫЙ РЕЖИМ)</b>

🏟️ {bet['home']} vs {bet['away']}
🏆 {bet['league']}

🎯 <b>{bet['bet']}</b>
📈 КЭФ: {bet['odds']}
💰 РАЗМЕР: ${bet['stake']:.2f}
📊 УВЕРЕННОСТЬ: {bet['prob']}%
📈 EV: <b>{bet['ev']}%</b>

📊 xG: {bet['home_xg']} : {bet['away_xg']}
👨‍⚖️ Судья: {bet.get('referee', 'неизвестен')}

📋 <b>ФАКТОРЫ:</b>
📈 Форма хозяев: {factors.get('home_form', 0.5)*100:.0f}%
📈 Форма гостей: {factors.get('away_form', 0.5)*100:.0f}%
{injuries_info}
{scorers_info}

🧠 <b>СУПЕР-СЛОЙ:</b>
{ik_reasons}

💡 /mode - выключить полный режим"""
    
    send_telegram_with_buttons(msg, bet_id)

# ===== ФУНКЦИИ ДЛЯ СТАТИСТИКИ =====
def get_detailed_statistics():
    history = load_history()
    if not history:
        return "📭 Нет данных"
    
    total = len(history)
    wins = sum(1 for b in history if b.get('result') == 'win')
    losses = sum(1 for b in history if b.get('result') == 'loss')
    winrate = wins / total * 100 if total > 0 else 0
    
    profit = 0
    for b in history:
        if b.get('result') == 'win':
            profit += b.get('stake', 0) * (b.get('odds', 1) - 1)
        elif b.get('result') == 'loss':
            profit -= b.get('stake', 0)
    
    league_stats = {}
    for b in history:
        league = b.get('league', 'Unknown')
        if league not in league_stats:
            league_stats[league] = {'wins': 0, 'losses': 0}
        if b.get('result') == 'win':
            league_stats[league]['wins'] += 1
        elif b.get('result') == 'loss':
            league_stats[league]['losses'] += 1
    
    sorted_leagues = sorted(
        [(k, v) for k, v in league_stats.items() if v['wins'] + v['losses'] >= 3],
        key=lambda x: x[1]['wins'] / (x[1]['wins'] + x[1]['losses']) if x[1]['wins'] + x[1]['losses'] > 0 else 0,
        reverse=True
    )[:5]
    
    msg = f"""📊 ДЕТАЛЬНАЯ СТАТИСТИКА

Всего: {total}
✅ Выигрышей: {wins}
❌ Проигрышей: {losses}
🎯 Проходимость: {round(winrate, 1)}%
💰 Прибыль: ${round(profit, 2)}

🏆 Топ-5 лиг:"""
    for league, data in sorted_leagues:
        total_league = data['wins'] + data['losses']
        rate = data['wins'] / total_league * 100
        msg += f"\n• {league}: {data['wins']}/{total_league} ({round(rate, 1)}%)"
    
    return msg

def export_statistics():
    history = load_history()
    if not history:
        return "📭 Нет данных"
    
    import csv
    from io import StringIO
    output = StringIO()
    fieldnames = ['id', 'date', 'home', 'away', 'league', 'bet', 'odds', 'stake', 'result']
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for bet in history:
        row = {f: bet.get(f, '') for f in fieldnames}
        writer.writerow(row)
    
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument"
        files = {'document': (f'history_{datetime.now().strftime("%Y%m%d")}.csv', output.getvalue())}
        data = {'chat_id': ADMIN_CHAT_ID}
        requests.post(url, files=files, data=data, timeout=30)
        return "✅ Статистика экспортирована в CSV"
    except:
        return "❌ Ошибка экспорта"

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
                        risk_manager.update_after_bet('win', bet.get('stake', 0), profit)
                        save_bank(bank + profit)
                        send_telegram(f"✅ Ставка #{bet_id} зашла! +${profit:.2f}")
                    elif result == 'loss':
                        stake = bet.get('stake', 0)
                        risk_manager.update_after_bet('loss', stake)
                        save_bank(bank - stake)
                        send_telegram(f"❌ Ставка #{bet_id} не зашла! -${stake:.2f}")
                    elif result == 'push':
                        risk_manager.update_after_bet('push', bet.get('stake', 0))
                        send_telegram(f"↩️ Ставка #{bet_id} возврат")
                    break
            
            save_history(history)
            train_model()
            
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/answerCallbackQuery"
            requests.post(url, json={"callback_query_id": callback['id'], "text": f"✅ Результат: {result}"})
            return "ok"
        
        if data and 'message' in data:
            text = data['message'].get('text', '')
            chat_id = data['message']['chat']['id']
            
            logger.info(f"💬 СООБЩЕНИЕ: {text} от {chat_id}")
            
            if str(chat_id) != ADMIN_CHAT_ID:
                send_telegram("⛔ Нет доступа")
                return "ok"
            
            if text == '/start':
                send_telegram("""🚀 QUANTUM BETTING BOT v10

⚠️ АВТООБНОВЛЕНИЕ ОТКЛЮЧЕНО!
Бот НЕ делает запросы к API автоматически.

📋 КОМАНДЫ:
/today - Лучшая ставка из кеша
/update - РУЧНОЙ поиск ставок
/bank - Банк
/stats - Статистика
/leagues - Активные лиги
/mode - Краткий/Полный режим
/inversion - Вкл/Выкл инверсию
/settings - Настройки
/export - Экспорт CSV
/divergence - Расхождения с букмекером
/help - Помощь""")
            
            elif text == '/today':
                cache = load_cache()
                if cache and cache.get("best_bet"):
                    send_bet_notification(cache["best_bet"])
                else:
                    send_telegram("❌ Нет сохранённых ставок. Используйте /update")
            
            elif text == '/update':
                send_telegram("🔄 РУЧНОЙ поиск матчей во всех лигах...")
                logger.info("🔍 НАЧАЛО ПОИСКА")
                
                matches = get_matches_with_factors()
                
                if matches:
                    bet = find_best_bet(matches)
                    save_cache({"best_bet": bet})
                    train_model()
                    
                    if bet:
                        send_bet_notification(bet)
                        send_telegram(f"✅ Найдена ставка! EV: {bet['ev']}%")
                        logger.info(f"✅ СТАВКА НАЙДЕНА: {bet['home']} vs {bet['away']}")
                    else:
                        send_telegram(f"❌ Ставок с EV > 5% не найдено")
                        logger.info("❌ СТАВОК НЕТ")
                else:
                    send_telegram("⚠️ Матчей не найдено, использую тестовые данные")
                    logger.info("⚠️ МАТЧЕЙ НЕТ, ТЕСТОВЫЙ РЕЖИМ")
                    test_matches = get_test_matches()
                    bet = find_best_bet(test_matches)
                    save_cache({"best_bet": bet})
                    if bet:
                        send_bet_notification(bet)
            
            elif text == '/mode':
                SETTINGS['full_mode'] = not SETTINGS['full_mode']
                mode = "ПОЛНЫЙ" if SETTINGS['full_mode'] else "КРАТКИЙ"
                send_telegram(f"📋 Режим: {mode}")
            
            elif text == '/inversion':
                SETTINGS['inversion_mode'] = not SETTINGS['inversion_mode']
                status = "ВКЛЮЧЕНА" if SETTINGS['inversion_mode'] else "ВЫКЛЮЧЕНА"
                send_telegram(f"🔄 Инверсия {status}!")
            
            elif text == '/bank':
                bank = load_bank()
                status = risk_manager.get_status()
                send_telegram(f"""💰 <b>БАНК</b>
${bank:.2f}

{status}""")
            
            elif text == '/stats':
                stats = get_detailed_statistics()
                send_telegram(stats)
            
            elif text == '/export':
                result = export_statistics()
                send_telegram(result)
            
            elif text == '/risk':
                send_telegram(risk_manager.get_status())
            
            elif text == '/settings':
                status = f"""⚙️ НАСТРОЙКИ
Форма: {'✅' if SETTINGS['improved_form'] else '❌'}
Судья: {'✅' if SETTINGS['referee'] else '❌'}
Кэфы: {'✅' if SETTINGS['odds_movement'] else '❌'}
PSY: {'✅' if SETTINGS['psy_factor'] else '❌'}
Нейросеть: {'✅' if SETTINGS['neural_learning'] else '❌'}
ПОРОГ EV: <b>5%</b>
ИНВЕРСИЯ: {'🔀 Вкл' if SETTINGS['inversion_mode'] else '📊 Выкл'}
РЕЖИМ: {'📋 Полный' if SETTINGS['full_mode'] else '📄 Краткий'}"""
                send_telegram(status)
            
            elif text == '/leagues':
                msg = "📊 <b>АКТИВНЫЕ ЛИГИ</b>\n\n"
                count = 0
                for league_id, name in LEAGUE_NAMES.items():
                    msg += f"• {name} (ID: {league_id})\n"
                    count += 1
                    if count >= 30:
                        break
                msg += f"\n...и ещё {len(LEAGUE_NAMES) - 30} лиг"
                send_telegram(msg)
            
            elif text == '/divergence':
                stats = load_divergence()
                total = stats.get("total", 0)
                wins = stats.get("wins", 0)
                losses = stats.get("losses", 0)
                if total == 0:
                    send_telegram("📭 Нет данных о расхождениях")
                else:
                    winrate = round(wins / total * 100, 1)
                    send_telegram(f"""📊 СТАТИСТИКА РАСХОЖДЕНИЙ

Всего ставок с расхождением: {total}
✅ Выигрышей: {wins}
❌ Проигрышей: {losses}
🎯 Проходимость: {winrate}%""")
            
            elif text == '/help':
                send_telegram("""📖 КОМАНДЫ:

/today - Лучшая ставка из кеша
/update - РУЧНОЙ поиск (все лиги)
/bank - Банк + риск
/stats - Статистика
/export - Экспорт CSV
/risk - Риск-менеджер
/settings - Настройки
/mode - Краткий/Полный режим
/inversion - Вкл/Выкл инверсию
/divergence - Расхождения с букмекером
/leagues - Список лиг
/help - Помощь

⚠️ АВТООБНОВЛЕНИЕ ОТКЛЮЧЕНО!""")
            
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
    return f"🤖 Quantum Bot v10 | АВТО-ОБНОВЛЕНИЕ ОТКЛЮЧЕНО | {status} | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

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
