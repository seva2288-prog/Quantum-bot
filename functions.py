import requests
import math
import json
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any

logger = logging.getLogger('betting_bot')

# ===== ПОГОДА (ONE CALL 4.0) =====
WEATHER_API_KEY = "7f0cfaed346b0fe364815ab65d627af2"

def get_city_coords(city_name):
    try:
        url = f"http://api.openweathermap.org/geo/1.0/direct?q={city_name}&limit=1&appid={WEATHER_API_KEY}"
        resp = requests.get(url, timeout=5)
        data = resp.json()
        if data:
            return data[0]['lat'], data[0]['lon']
    except:
        pass
    return None, None

def get_weather_by_city(city_name):
    try:
        lat, lon = get_city_coords(city_name)
        if lat and lon:
            url = f"https://api.openweathermap.org/data/4.0/onecall?lat={lat}&lon={lon}&units=metric&appid={WEATHER_API_KEY}"
            resp = requests.get(url, timeout=5)
            data = resp.json()
            
            if data.get("data") and len(data["data"]) > 0:
                current = data["data"][0]
                
                weather = current.get("weather", [{}])[0].get("main", "Clear")
                description = current.get("weather", [{}])[0].get("description", "")
                temp = current.get("temp", {}).get("day", 20)
                
                weather_ru = {
                    "Clear": "☀️ Ясно",
                    "Clouds": "☁️ Облачно",
                    "Rain": "🌧️ Дождь",
                    "Snow": "❄️ Снег",
                    "Thunderstorm": "⛈️ Гроза",
                    "Drizzle": "🌦️ Морось",
                    "Mist": "🌫️ Туман",
                    "Fog": "🌫️ Туман",
                    "Haze": "🌫️ Дымка"
                }.get(weather, f"🌤️ {weather}")
                
                return {
                    "temp": round(temp),
                    "weather": weather,
                    "description": description,
                    "weather_ru": weather_ru,
                    "humidity": current.get("humidity", 0),
                    "wind_speed": current.get("wind_speed", 0),
                    "pressure": current.get("pressure", 0),
                    "emoji": weather_ru[:2] if " " in weather_ru else "🌤️"
                }
    except Exception as e:
        logger.warning(f"⚠️ Погода не получена: {e}")
    return None

def get_weather_impact(weather_data):
    if not weather_data:
        return 1.0, "☀️ Погода неизвестна"
    
    weather = weather_data.get("weather", "")
    temp = weather_data.get("temp", 20)
    wind = weather_data.get("wind_speed", 0)
    impact = 1.0
    reason = "☀️ Хорошая погода"
    
    if weather in ["Rain", "Drizzle", "Thunderstorm"]:
        impact = 0.92
        reason = "🌧️ Дождь (-8%)"
    elif weather == "Snow":
        impact = 0.85
        reason = "❄️ Снег (-15%)"
    elif weather in ["Mist", "Fog", "Haze"]:
        impact = 0.90
        reason = "🌫️ Туман (-10%)"
    elif wind > 10:
        impact = 0.93
        reason = f"💨 Сильный ветер ({wind:.0f} м/с) (-7%)"
    elif temp > 30:
        impact = 1.05
        reason = f"🔥 Жара ({temp:.0f}°C) (+5%)"
    elif temp < 0:
        impact = 0.95
        reason = f"🥶 Холод ({temp:.0f}°C) (-5%)"
    elif weather in ["Rain", "Drizzle"] and wind > 8:
        impact = 0.88
        reason = "🌧️💨 Дождь + ветер (-12%)"
    
    return impact, reason

# ===== ЛИГИ =====
def get_league_names():
    return {
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

def get_all_leagues():
    return list(get_league_names().keys())

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
        "home_or_draw": sum(probs[i][j] for i in range(7) for j in range(7) if i >= j),
        "away_or_draw": sum(probs[i][j] for i in range(7) for j in range(7) if i <= j),
    }

# ================================================================
# ФУНКЦИИ ДЛЯ ФУТБОЛА
# ================================================================

def get_form(team_id, football_api_key):
    try:
        url = f"https://v3.football.api-sports.io/fixtures?team={team_id}&last=5"
        headers = {"x-rapidapi-key": football_api_key}
        resp = requests.get(url, headers=headers, timeout=15)
        data = resp.json()
        if data.get("response"):
            wins, losses, draws = 0, 0, 0
            for match in data["response"]:
                if match["teams"]["home"]["id"] == team_id:
                    if match["goals"]["home"] > match["goals"]["away"]:
                        wins += 1
                    elif match["goals"]["home"] < match["goals"]["away"]:
                        losses += 1
                    else:
                        draws += 1
                else:
                    if match["goals"]["away"] > match["goals"]["home"]:
                        wins += 1
                    elif match["goals"]["away"] < match["goals"]["home"]:
                        losses += 1
                    else:
                        draws += 1
            return {"wins": wins, "losses": losses, "draws": draws, "ratio": wins / 5}
    except:
        pass
    return {"wins": 0, "losses": 0, "draws": 0, "ratio": 0.5}

def get_injuries(team_id, football_api_key):
    try:
        url = f"https://v3.football.api-sports.io/injuries?team={team_id}"
        headers = {"x-rapidapi-key": football_api_key}
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

def get_motivation(team_id, league_id, football_api_key):
    try:
        url = f"https://v3.football.api-sports.io/standings?league={league_id}&season=2026"
        headers = {"x-rapidapi-key": football_api_key}
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

def get_h2h(home_id, away_id, football_api_key):
    try:
        url = f"https://v3.football.api-sports.io/fixtures/headtohead?h2h={home_id}-{away_id}&last=5"
        headers = {"x-rapidapi-key": football_api_key}
        resp = requests.get(url, headers=headers, timeout=15)
        data = resp.json()
        if data.get("response"):
            home_wins, away_wins, draws = 0, 0, 0
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
                        draws += 1
                else:
                    home_goals.append(match["goals"]["away"])
                    away_goals.append(match["goals"]["home"])
                    if match["goals"]["away"] > match["goals"]["home"]:
                        home_wins += 1
                    elif match["goals"]["away"] < match["goals"]["home"]:
                        away_wins += 1
                    else:
                        draws += 1
            if home_goals:
                return {
                    "home_avg": sum(home_goals) / len(home_goals),
                    "away_avg": sum(away_goals) / len(away_goals),
                    "home_wins": home_wins,
                    "away_wins": away_wins,
                    "draws": draws,
                    "matches": len(home_goals),
                }
    except:
        pass
    return None

def get_referee_style(fixture_id, football_api_key):
    try:
        url = f"https://v3.football.api-sports.io/fixtures?id={fixture_id}"
        headers = {"x-rapidapi-key": football_api_key}
        resp = requests.get(url, headers=headers, timeout=15)
        data = resp.json()
        if data.get("response"):
            referee = data["response"][0]["fixture"]["referee"]
            if referee:
                return referee
    except:
        pass
    return None

def get_top_scorers(team_id, football_api_key):
    try:
        url = f"https://v3.football.api-sports.io/players?team={team_id}&season=2026"
        headers = {"x-rapidapi-key": football_api_key}
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

# ================================================================
# НОВАЯ ФУНКЦИЯ: ПОЛУЧЕНИЕ СОСТАВОВ
# ================================================================

def get_team_lineup(fixture_id, team_id, football_api_key):
    """
    Получает стартовый состав команды на матч
    Возвращает список игроков и оценку силы состава
    """
    try:
        url = f"https://v3.football.api-sports.io/fixtures/lineups?fixture={fixture_id}"
        headers = {"x-rapidapi-key": football_api_key}
        resp = requests.get(url, headers=headers, timeout=10)
        data = resp.json()
        
        if data.get("response"):
            for lineup in data["response"]:
                if lineup["team"]["id"] == team_id:
                    players = []
                    for player in lineup.get("startXI", []):
                        players.append(player["player"]["name"])
                    
                    # Оценка силы состава (по количеству игроков и их позициям)
                    strength = len(players) / 11
                    
                    return {
                        "players": players,
                        "count": len(players),
                        "strength": round(strength, 2),
                        "has_starters": len(players) >= 9
                    }
    except Exception as e:
        logger.warning(f"⚠️ Не удалось получить состав для команды {team_id}: {e}")
    
    return None

# ================================================================
# ПОЛУЧЕНИЕ МАТЧЕЙ С ФАКТОРАМИ (ВКЛЮЧАЯ СОСТАВЫ)
# ================================================================

def get_matches_with_factors(football_api_key):
    from bot import LEAGUES, LEAGUE_NAMES, logger
    
    all_matches = []
    today = datetime.now().strftime('%Y-%m-%d')
    
    logger.info("=" * 60)
    logger.info(f"🔍 ИЩУ МАТЧИ ЗА {today}...")
    logger.info("=" * 60)
    
    for league_id in LEAGUES:
        for season in ["2026", "2025"]:
            try:
                url = f"https://v3.football.api-sports.io/fixtures?league={league_id}&season={season}&date={today}"
                headers = {"x-rapidapi-key": football_api_key}
                
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
                                
                                match["factors"] = {
                                    "home_form": get_form(home_id, football_api_key),
                                    "away_form": get_form(away_id, football_api_key),
                                    "home_injuries": get_injuries(home_id, football_api_key)[0],
                                    "away_injuries": get_injuries(away_id, football_api_key)[0],
                                    "home_injuries_list": get_injuries(home_id, football_api_key)[1],
                                    "away_injuries_list": get_injuries(away_id, football_api_key)[1],
                                    "home_motivation": get_motivation(home_id, league_id, football_api_key)[0],
                                    "away_motivation": get_motivation(away_id, league_id, football_api_key)[0],
                                    "home_motivation_text": get_motivation(home_id, league_id, football_api_key)[1],
                                    "away_motivation_text": get_motivation(away_id, league_id, football_api_key)[1],
                                    "h2h": get_h2h(home_id, away_id, football_api_key),
                                    "referee": get_referee_style(fixture_id, football_api_key),
                                    "home_scorers": get_top_scorers(home_id, football_api_key),
                                    "away_scorers": get_top_scorers(away_id, football_api_key),
                                }
                                
                                # ===== ПОЛУЧАЕМ СОСТАВЫ =====
                                home_lineup = get_team_lineup(fixture_id, home_id, football_api_key)
                                away_lineup = get_team_lineup(fixture_id, away_id, football_api_key)
                                
                                if home_lineup:
                                    match["factors"]["home_lineup"] = home_lineup
                                    logger.info(f"👥 Состав хозяев: {home_lineup['count']} игроков")
                                
                                if away_lineup:
                                    match["factors"]["away_lineup"] = away_lineup
                                    logger.info(f"👥 Состав гостей: {away_lineup['count']} игроков")
                                
                                # ===== ПОГОДА =====
                                city = match.get("fixture", {}).get("venue", {}).get("city", "")
                                if city:
                                    try:
                                        weather = get_weather_by_city(city)
                                        if weather:
                                            impact, reason = get_weather_impact(weather)
                                            match["weather"] = weather
                                            match["weather_impact"] = impact
                                            match["weather_reason"] = reason
                                            logger.info(f"🌤️ Погода в {city}: {weather['weather_ru']} ({weather['temp']:.0f}°C)")
                                        else:
                                            match["weather"] = None
                                            match["weather_impact"] = 1.0
                                            match["weather_reason"] = "☀️ Погода неизвестна"
                                            logger.info(f"⚠️ Погода для {city} не получена, использую нейтральное значение")
                                    except Exception as e:
                                        logger.warning(f"⚠️ Ошибка погоды для {city}: {e}")
                                        match["weather"] = None
                                        match["weather_impact"] = 1.0
                                        match["weather_reason"] = "☀️ Погода неизвестна"
                                else:
                                    match["weather"] = None
                                    match["weather_impact"] = 1.0
                                    match["weather_reason"] = "☀️ Город неизвестен"
                                
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

# ================================================================
# ТЕСТОВЫЕ ДАННЫЕ (НЕ ИСПОЛЬЗУЮТСЯ)
# ================================================================

def get_test_matches():
    return [
        {"fixture": {"id": 1, "status": {"short": "NS"}}, "teams": {"home": {"name": "Arsenal"}, "away": {"name": "Chelsea"}}, "league": {"name": "АПЛ"}},
        {"fixture": {"id": 2, "status": {"short": "NS"}}, "teams": {"home": {"name": "Barcelona"}, "away": {"name": "Real Madrid"}}, "league": {"name": "Ла Лига"}},
        {"fixture": {"id": 3, "status": {"short": "NS"}}, "teams": {"home": {"name": "Bayern Munich"}, "away": {"name": "Dortmund"}}, "league": {"name": "Бундеслига"}},
        {"fixture": {"id": 4, "status": {"short": "NS"}}, "teams": {"home": {"name": "AC Milan"}, "away": {"name": "Inter"}}, "league": {"name": "Серия А"}},
        {"fixture": {"id": 5, "status": {"short": "NS"}}, "teams": {"home": {"name": "PSG"}, "away": {"name": "Marseille"}}, "league": {"name": "Лига 1"}},
        {"fixture": {"id": 6, "status": {"short": "NS"}}, "teams": {"home": {"name": "Flamengo"}, "away": {"name": "Palmeiras"}}, "league": {"name": "Бразилейрао"}},
        {"fixture": {"id": 7, "status": {"short": "NS"}}, "teams": {"home": {"name": "River Plate"}, "away": {"name": "Boca Juniors"}}, "league": {"name": "Аргентина"}},
    ]

# ================================================================
# ПОИСК ЛУЧШЕЙ СТАВКИ (С УЧЁТОМ СОСТАВОВ)
# ================================================================

def find_best_bet(matches, football_api_key, load_bank_func, send_bet_notification_func):
    bank = load_bank_func()
    best_bet = None
    best_ev = -100
    
    for match in matches:
        try:
            home = match["teams"]["home"]["name"]
            away = match["teams"]["away"]["name"]
            league = match["league"]["name"]
            fixture_id = match["fixture"]["id"]
            factors = match.get("factors", {})
            
            home_xg = 1.5
            away_xg = 1.3
            
            # ===== УЧЁТ СОСТАВОВ =====
            home_lineup = factors.get("home_lineup")
            away_lineup = factors.get("away_lineup")
            
            if home_lineup:
                # Если в составе меньше 9 игроков — штраф
                if home_lineup["count"] < 9:
                    home_xg *= 0.90
                    logger.info(f"⚠️ У хозяев неполный состав ({home_lineup['count']} игроков) -10%")
                elif home_lineup["strength"] < 0.8:
                    home_xg *= 0.95
                    logger.info(f"⚠️ Слабый состав хозяев ({home_lineup['strength']*100:.0f}%) -5%")
            
            if away_lineup:
                if away_lineup["count"] < 9:
                    away_xg *= 0.90
                    logger.info(f"⚠️ У гостей неполный состав ({away_lineup['count']} игроков) -10%")
                elif away_lineup["strength"] < 0.8:
                    away_xg *= 0.95
                    logger.info(f"⚠️ Слабый состав гостей ({away_lineup['strength']*100:.0f}%) -5%")
            
            # ===== УЧЁТ ПОГОДЫ =====
            if match.get("weather_impact"):
                home_xg *= match["weather_impact"]
                away_xg *= match["weather_impact"]
            
            # ===== ПОЛУЧАЕМ xG ИЗ API =====
            try:
                stats_url = f"https://v3.football.api-sports.io/fixtures/statistics?fixture={fixture_id}"
                headers = {"x-rapidapi-key": football_api_key}
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
                ("home_or_draw", 1.5, "1Х"),
                ("away_or_draw", 1.5, "2Х"),
            ]
            
            for bet_type, odds, label in bet_types:
                prob = probs.get(bet_type, 0)
                if prob < 0.05 or prob > 0.99:
                    continue
                ev = (prob * odds) - 1
                if ev > best_ev and ev > 0.001:
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
                        "weather": match.get("weather"),
                        "weather_impact": match.get("weather_impact", 1.0),
                        "weather_reason": match.get("weather_reason", "☀️ Без погоды"),
                        "home_lineup": home_lineup,
                        "away_lineup": away_lineup,
                        "factors": factors,
                    }
        except Exception as e:
            logger.error(f"Ошибка: {e}")
            continue
    
    if best_bet:
        send_bet_notification_func(best_bet)
    
    return best_bet
