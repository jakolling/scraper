#!/usr/bin/env python3
# encoding: utf-8

"""
Análise de performance de um time a partir de jogos do Sofascore.
- Entrada: arquivos jogos.txt (uma URL por linha)
- Escolha do time alvo
- Saída: team_database.xlsx com abas por jogo, resumo, stats por jogador e por local
"""

import sys, re, json, math, warnings, time
import requests
from bs4 import BeautifulSoup
import pandas as pd
import numpy as np

# Selenium
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

# ------------------------------
# FUNÇÕES DE EXTRAÇÃO
# ------------------------------

def fetch_with_requests(url, timeout=15):
    headers = {"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0 Safari/537.36"}
    r = requests.get(url, headers=headers, timeout=timeout)
    r.raise_for_status()
    return r.text

def fetch_with_selenium(url):
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-gpu")
    driver = webdriver.Chrome(ChromeDriverManager().install(), options=opts)
    try:
        driver.get(url)
        time.sleep(3)
        return driver.page_source
    finally:
        try: driver.quit()
        except: pass

def extract_json_from_html(html):
    patterns = [
        r"window\.__INITIAL_STATE__\s*=\s*({.+?});\s*(?:window|\n)",
        r"window\.__PRELOADED_STATE__\s*=\s*({.+?});",
    ]
    for p in patterns:
        m = re.search(p, html, flags=re.S)
        if m:
            txt = m.group(1)
            try: return json.loads(txt)
            except Exception:
                try:
                    cleaned = re.sub(r",\s*}", "}", txt)
                    cleaned = re.sub(r",\s*]", "]", cleaned)
                    return json.loads(cleaned)
                except Exception: pass
    soup = BeautifulSoup(html, "lxml")
    for script in soup.find_all("script", {"type":"application/ld+json"}):
        try: return json.loads(script.string)
        except Exception: continue
    return None

def recursive_find_shots(obj):
    shots = []
    if isinstance(obj, dict):
        for k,v in obj.items():
            if isinstance(k,str) and ("shot" in k.lower() or "shots"==k.lower() or "events" in k.lower()):
                if isinstance(v,list):
                    for e in v:
                        if isinstance(e, dict):
                            s = json.dumps(e).lower()
                            if any(x in s for x in ["x","y","isgoal","shot","xpercent","ypercent"]):
                                shots.append(e)
                else:
                    shots += recursive_find_shots(v)
            else:
                shots += recursive_find_shots(v)
    elif isinstance(obj,list):
        for item in obj: shots += recursive_find_shots(item)
    return shots

def normalize_event(e):
    out = {}
    for key in ('minute','time','min','matchMinute','minuteInMatch'):
        if key in e: out['minute'] = e.get(key); break
    for key in ('player','playerName','player_name','playerId','player_id'):
        if key in e: out['player'] = e.get(key); break
    for key in ('team','side','teamId','teamName'):
        if key in e: out['team'] = e.get(key); break
    x = None; y = None
    for k in ('x','xCoord','xPosition','xPercent','percentX','posX'):
        if k in e: x = e.get(k); break
    for k in ('y','yCoord','yPosition','yPercent','percentY','posY'):
        if k in e: y = e.get(k); break
    out['x_raw'] = x; out['y_raw'] = y
    out['is_goal'] = bool(e.get('isGoal') or e.get('goal') or e.get('is_goal'))
    out['raw'] = e
    return out

def percent_to_meters(x_pct, y_pct, pitch_length=105.0, pitch_width=68.0):
    try: xm = (float(x_pct)*pitch_length)/100.0
    except: xm = np.nan
    try: ym = (float(y_pct)*pitch_width)/100.0
    except: ym = np.nan
    return xm, ym

def simple_xg_from_distance(dist_m):
    if dist_m is None or np.isnan(dist_m): return np.nan
    return 1.0 / (1.0 + math.exp((dist_m - 16.0)/5.0))

# ------------------------------
# EXTRAÇÃO DE UM JOGO
# ------------------------------

def extract_game(url, team_name):
    html = None
    data = None
    tried_selenium = False
    try:
        html = fetch_with_requests(url)
        data = extract_json_from_html(html)
    except Exception as e: warnings.warn(f"Requests fetch failed: {e}")

    if data is None:
        try:
            tried_selenium = True
            html = fetch_with_selenium(url)
            data = extract_json_from_html(html)
        except Exception as e: warnings.warn(f"Selenium fetch failed: {e}")

    if data is None:
        print(f"Falha ao extrair dados: {url}")
        return None

    # Identificação de times
    try:
        match_data = data.get('events', data)
        home_team = match_data.get('homeTeam', {}).get('name') or match_data.get('home', {}).get('name')
        away_team = match_data.get('awayTeam', {}).get('name') or match_data.get('away', {}).get('name')
    except:
        home_team = None; away_team = None

    location = "HOME" if team_name == home_team else "AWAY"

    # Eventos de chutes
    shots_blobs = recursive_find_shots(data)
    events = []
    for blob in shots_blobs:
        if isinstance(blob,list):
            for e in blob:
                if isinstance(e,dict) and e.get('teamName') == team_name:
                    events.append(normalize_event(e))
        elif isinstance(blob,dict):
            for v in blob.values():
                if isinstance(v,list):
                    for e in v:
                        if isinstance(e,dict) and e.get('teamName') == team_name:
                            events.append(normalize_event(e))
    if not events: return None

    df = pd.DataFrame(events)
    xs=[]; ys=[]
    for _,row in df.iterrows():
        xm, ym = percent_to_meters(row.get('x_raw'), row.get('y_raw'))
        xs.append(xm); ys.append(ym)
    df['x_m'] = xs; df['y_m'] = ys
    df['dist_m'] = df.apply(lambda r: math.hypot(105-r['x_m'],34-r['y_m']) if not np.isnan(r['x_m']) else np.nan, axis=1)
    df['xG'] = df['dist_m'].apply(simple_xg_from_distance)
    df['xGOT'] = df.apply(lambda r: r['xG'] if r['is_goal'] or True else 0, axis=1) # para simplificação: todos os chutes certos contam
    df['opponent'] = away_team if location=="HOME" else home_team
    df['location'] = location
    out_cols = ['minute','player','x_m','y_m','dist_m','xG','xGOT','is_goal','opponent','location','raw']
    for c in out_cols:
        if c not in df.columns: df[c] = np.nan
    return df[out_cols]

# ------------------------------
# FUNÇÃO PRINCIPAL
# ------------------------------

def main():
    if len(sys.argv)<2:
        print("Uso: python team_performance_analysis.py jogos.txt")
        return

    team_name = input("Digite o nome do time a ser analisado (ex: Hässleholms IF): ").strip()
    file_links = sys.argv[1]
    with open(file_links,'r') as f:
        urls = [line.strip() for line in f if line.strip()]
    if len(urls)>30: urls = urls[:30]

    writer = pd.ExcelWriter("team_database.xlsx", engine='openpyxl')
    all_games = []
    for i,url in enumerate(urls,1):
        print(f"Processando jogo {i}/{len(urls)}: {url}")
        df = extract_game(url, team_name)
        if df is not None and not df.empty:
            sheet_name = f"Jogo_{i}"
            df.to_excel(writer, sheet_name=sheet_name, index=False)
            all_games.append(df)
        else:
            print(f"Nenhum dado encontrado para {team_name} nesse jogo.")

    if not all_games:
        print("Nenhum dado de jogos extraído. Encerrando.")
        return

    # ------------------------------
    # Resumo geral do time
    # ------------------------------
    df_all = pd.concat(all_games, ignore_index=True)
    resumo = pd.DataFrame({
        'Total_Chutes': [len(df_all)],
        'Total_Gols': [df_all['is_goal'].sum()],
        'xG_total': [df_all['xG'].sum()],
        'xGOT_total': [df_all['xGOT'].sum()],
        'Média_xG_por_jogo': [df_all['xG'].sum()/len(all_games)],
        'Média_xGOT_por_jogo': [df_all['xGOT'].sum()/len(all_games)],
        'Conversão_chutes': [df_all['is_goal'].sum()/len(df_all)*100 if len(df_all)>0 else 0],
        'Jogos': [len(all_games)]
    })
    resumo.to_excel(writer, sheet_name='Resumo', index=False)

    # ------------------------------
    # Stats por jogador
    # ------------------------------
    by_player = df_all.groupby(['player','location'], dropna=False).agg(
        Chutes=('xG','count'),
        Gols=('is_goal','sum'),
        xG=('xG','sum'),
        xGOT=('xGOT','sum')
    ).reset_index()
    by_player.to_excel(writer, sheet_name='Por_Jogador', index=False)

    # ------------------------------
    # Stats por local (HOME/AWAY)
    # ------------------------------
    by_location = df_all.groupby('location').agg(
        Chutes=('xG','count'),
        Gols=('is_goal','sum'),
        xG=('xG','sum'),
        xGOT=('xGOT','sum')
    ).reset_index()
    by_location.to_excel(writer, sheet_name='Por_Local', index=False)

    writer.save()
    print("Arquivo final salvo: team_database.xlsx")

# ------------------------------
# EXECUÇÃO
# ------------------------------

if __name__=="__main__":
    main()
