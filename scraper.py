import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import requests, re, json, math, time
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

# Configuração da página
st.set_page_config(layout="wide")
st.title("Análise Completa de Time - Sofascore")

# ------------------------------
# FUNÇÕES DE EXTRAÇÃO
# ------------------------------

def fetch_html(url):
    """
    Tenta buscar o HTML do link com requests e fallback para Selenium.
    """
    headers = {"User-Agent":"Mozilla/5.0"}
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        return response.text
    except:
        options = Options()
        options.add_argument("--headless=new")
        driver = webdriver.Chrome(ChromeDriverManager().install(), options=options)
        try:
            driver.get(url)
            time.sleep(3)
            return driver.page_source
        finally:
            try: driver.quit()
            except: pass

def extract_json_from_html(html):
    """
    Extrai os dados em JSON do HTML do Sofascore.
    """
    patterns = [
        r"window\.__INITIAL_STATE__\s*=\s*({.+?});\s*(?:window|\n)",
        r"window\.__PRELOADED_STATE__\s*=\s*({.+?});",
    ]
    for pattern in patterns:
        match = re.search(pattern, html, flags=re.S)
        if match:
            txt = match.group(1)
            try:
                return json.loads(txt)
            except Exception:
                try:
                    cleaned = re.sub(r",\s*}", "}", txt)
                    cleaned = re.sub(r",\s*]", "]", cleaned)
                    return json.loads(cleaned)
                except Exception:
                    pass
    soup = BeautifulSoup(html, "lxml")
    for script in soup.find_all("script", {"type":"application/ld+json"}):
        try:
            return json.loads(script.string)
        except:
            continue
    return None

def recursive_find_shots(obj):
    """
    Procura recursivamente objetos de chutes ou eventos no JSON.
    """
    shots = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(k, str) and ("shot" in k.lower() or "shots" == k.lower() or "events" in k.lower()):
                if isinstance(v, list):
                    for e in v:
                        if isinstance(e, dict):
                            s = json.dumps(e).lower()
                            if any(x in s for x in ["x", "y", "isgoal", "shot", "xpercent", "ypercent"]):
                                shots.append(e)
                else:
                    shots += recursive_find_shots(v)
            else:
                shots += recursive_find_shots(v)
    elif isinstance(obj, list):
        for item in obj:
            shots += recursive_find_shots(item)
    return shots

def normalize_event(event):
    """
    Normaliza os campos do evento para dataframe.
    """
    output = {}
    for key in ('minute', 'time', 'min', 'matchMinute', 'minuteInMatch'):
        if key in event:
            output['minute'] = event.get(key)
            break
    for key in ('player', 'playerName', 'player_name', 'playerId', 'player_id'):
        if key in event:
            output['player'] = event.get(key)
            break
    for key in ('team', 'side', 'teamId', 'teamName'):
        if key in event:
            output['team'] = event.get(key)
            break
    x = None; y = None
    for k in ('x', 'xCoord', 'xPosition', 'xPercent', 'percentX', 'posX'):
        if k in event: x = event.get(k); break
    for k in ('y', 'yCoord', 'yPosition', 'yPercent', 'percentY', 'posY'):
        if k in event: y = event.get(k); break
    output['x_raw'] = x
    output['y_raw'] = y
    output['is_goal'] = bool(event.get('isGoal') or event.get('goal') or event.get('is_goal'))
    output['on_target'] = event.get('onTarget', False)
    output['raw'] = event
    return output

def percent_to_meters(x_pct, y_pct, pitch_length=105.0, pitch_width=68.0):
    try: xm = (float(x_pct) * pitch_length) / 100.0
    except: xm = np.nan
    try: ym = (float(y_pct) * pitch_width) / 100.0
    except: ym = np.nan
    return xm, ym

def simple_xg_from_distance(dist_m):
    if dist_m is None or np.isnan(dist_m): return np.nan
    return 1.0 / (1.0 + math.exp((dist_m - 16.0)/5.0))

def extract_game(url):
    """
    Extrai os dados do jogo completo: nomes dos times, eventos de chutes e estatísticas.
    """
    html = fetch_html(url)
    data = extract_json_from_html(html)
    if data is None: return None, None, None, None, None, None

    home_team = data.get('events', data).get('homeTeam', {}).get('name') or data.get('home', {}).get('name')
    away_team = data.get('events', data).get('awayTeam', {}).get('name') or data.get('away', {}).get('name')

    shots_blobs = recursive_find_shots(data)
    events_home = []
    events_away = []

    for blob in shots_blobs:
        if isinstance(blob, list):
            for e in blob:
                if isinstance(e, dict):
                    if e.get('teamName') == home_team: events_home.append(normalize_event(e))
                    else: events_away.append(normalize_event(e))
        elif isinstance(blob, dict):
            for v in blob.values():
                if isinstance(v, list):
                    for e in v:
                        if isinstance(e, dict):
                            if e.get('teamName') == home_team: events_home.append(normalize_event(e))
                            else: events_away.append(normalize_event(e))

    df_home = pd.DataFrame(events_home)
    df_away = pd.DataFrame(events_away)

    for df in [df_home, df_away]:
        xs = []
        ys = []
        for _, row in df.iterrows():
            xm, ym = percent_to_meters(row.get('x_raw'), row.get('y_raw'))
            xs.append(xm)
            ys.append(ym)
        df['x_m'] = xs
        df['y_m'] = ys
        df['dist_m'] = df.apply(lambda r: math.hypot(105-r['x_m'],34-r['y_m']) if not np.isnan(r['x_m']) else np.nan, axis=1)
        df['xG'] = df['dist_m'].apply(simple_xg_from_distance)
        df['xGOT'] = df.apply(lambda r: r['xG'] if r.get('on_target') or r['is_goal'] else 0, axis=1)

    stats_home = data.get('events', data).get('homeTeamStatistics')
    stats_away = data.get('events', data).get('awayTeamStatistics')
    stats_dict_home = {s['type']: s.get('value') for s in stats_home.get('statistics', [])} if stats_home else {}
    stats_dict_away = {s['type']: s.get('value') for s in stats_away.get('statistics', [])} if stats_away else {}

    return home_team, away_team, df_home, df_away, stats_dict_home, stats_dict_away

# ------------------------------
# STREAMLIT INTERFACE
# ------------------------------

if 'links' not in st.session_state: st.session_state.links = []
if 'teams' not in st.session_state: st.session_state.teams = []

st.subheader("Fase 1: Inserir Links de Jogos (até 30)")
new_link = st.text_input("Cole o link do jogo e pressione Enter", key="link_input")
if new_link:
    if len(st.session_state.links) < 30:
        st.session_state.links.append(new_link)
        st.success("Link adicionado!")
        st.session_state.link_input = ""
    else:
        st.warning("Máximo de 30 links atingido!")

st.write("Links adicionados:")
for i, link in enumerate(st.session_state.links):
    cols = st.columns([0.9, 0.1])
    cols[0].write(f"{i+1}. {link}")
    if cols[1].button("Remover", key=f"remove_{i}"):
        st.session_state.links.pop(i)
        st.experimental_rerun()

# Ler nomes de times automaticamente
if st.session_state.links:
    st.subheader("Selecione o Time Alvo")
    teams_set = set()
    for url in st.session_state.links:
        h_team, a_team, *_ = extract_game(url)
        if h_team: teams_set.add(h_team)
        if a_team: teams_set.add(a_team)
    st.session_state.teams = sorted(list(teams_set))
    team_name = st.selectbox("Escolha o time alvo:", st.session_state.teams)
else:
    team_name = None

# Processamento
if st.button("Processar Jogos") and team_name:
    st.subheader("Fase 2: Processamento dos Dados e Criação do Excel")
    all_team = []
    all_opp = []
    all_stats_team = []
    all_stats_opp = []

    for i, url in enumerate(st.session_state.links, 1):
        st.write(f"Processando {i}/{len(st.session_state.links)}")
        h_team, a_team, df_home, df_away, stats_home, stats_away = extract_game(url)
        if df_home is None: continue

        if team_name == h_team:
            df_team, df_opp = df_home.copy(), df_away.copy()
            stats_team, stats_opp = stats_home.copy(), stats_away.copy()
            location_team = "HOME"
        else:
            df_team, df_opp = df_away.copy(), df_home.copy()
            stats_team, stats_opp = stats_away.copy(), stats_home.copy()
            location_team = "AWAY"

        df_team['Jogo'] = f"Jogo_{i}"
        df_team['location'] = location_team
        df_opp['Jogo'] = f"Jogo_{i}"
        df_opp['location'] = "AWAY" if location_team=="HOME" else "HOME"

        all_team.append(df_team)
        all_opp.append(df_opp)

        stats_team['Jogo'] = f"Jogo_{i}"; stats_team['location'] = location_team
        stats_team['opponent'] = a_team if location_team=="HOME" else h_team
        stats_opp['Jogo'] = f"Jogo_{i}"; stats_opp['location'] = df_opp['location'].iloc[0]
        stats_opp['opponent'] = df_opp['team'].iloc[0] if 'team' in df_opp.columns else ""

        all_stats_team.append(stats_team)
        all_stats_opp.append(stats_opp)

    if not all_team:
        st.error("Nenhum dado extraído.")
    else:
        df_all_team = pd.concat(all_team, ignore_index=True)
        df_all_opp = pd.concat(all_opp, ignore_index=True)
        df_stats_team = pd.DataFrame(all_stats_team)
        df_stats_opp = pd.DataFrame(all_stats_opp)

        st.success("Dataframe completo e Excel gerado.")

        excel_file = "team_database_full.xlsx"
        with pd.ExcelWriter(excel_file, engine='openpyxl') as writer:
            for i, df in enumerate(all_team, 1):
                df.to_excel(writer, sheet_name=f"Jogo_{i}_shots", index=False)
            df_stats_team.to_excel(writer, sheet_name="Stats_Time", index=False)
            df_stats_opp.to_excel(writer, sheet_name="Stats_Adversario", index=False)
        st.download_button("Download Excel Completo", data=open(excel_file,"rb").read(), file_name=excel_file)

        # ------------------------------
        # Fase 3: Análise Interativa
        # ------------------------------
        st.subheader("Fase 3: Análise Interativa do Time")

        jogadores = ["Todos"] + sorted(df_all_team['player'].dropna().unique().tolist())
        selected_jogador = st.selectbox("Filtrar por jogador", jogadores)
        locais = ["Todos"] + sorted(df_all_team['location'].dropna().unique().tolist())
        selected_local = st.selectbox("Filtrar por local", locais)
        jogos = ["Todos"] + sorted(df_all_team['Jogo'].unique().tolist())
        selected_jogo = st.selectbox("Filtrar por jogo", jogos)

        df_plot_team = df_all_team.copy()
        df_plot_opp = df_all_opp.copy()
        if selected_jogador != "Todos": df_plot_team = df_plot_team[df_plot_team['player']==selected_jogador]
        if selected_local != "Todos":
            df_plot_team = df_plot_team[df_plot_team['location']==selected_local]
            df_plot_opp = df_plot_opp[df_plot_opp['location']==selected_local]
        if selected_jogo != "Todos":
            df_plot_team = df_plot_team[df_plot_team['Jogo']==selected_jogo]
            df_plot_opp = df_plot_opp[df_plot_opp['Jogo']==selected_jogo]

        st.subheader("Heatmap de Chutes do Time")
        if not df_plot_team.empty:
            plt.figure(figsize=(10,6))
            sns.kdeplot(x='x_m', y='y_m', data=df_plot_team, fill=True, cmap="Reds", bw_adjust=0.5)
            plt.title("Heatmap de Chutes (xG/xGOT)")
            plt.xlim(0,105)
            plt.ylim(0,68)
            st.pyplot(plt)
        else:
            st.info("Nenhum chute do time nesse filtro.")

        st.subheader("Heatmap de Chutes Sofridos (Goleiro)")
        if not df_plot_opp.empty:
            plt.figure(figsize=(10,6))
            sns.kdeplot(x='x_m', y='y_m', data=df_plot_opp, fill=True, cmap="Blues", bw_adjust=0.5)
            plt.title("Heatmap de Chutes Sofridos")
            plt.xlim(0,105)
            plt.ylim(0,68)
            st.pyplot(plt)
        else:
            st.info("Nenhum chute sofrido nesse filtro.")

        st.subheader("Estatísticas do Time")
        st.dataframe(df_stats_team)

        st.subheader("Estatísticas do Adversário")
        st.dataframe(df_stats_opp)
import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import requests, re, json, math, time
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

st.set_page_config(layout="wide")
st.title("Análise Completa do Time - Sofascore")

# ------------------------------
# FUNÇÕES DE EXTRAÇÃO
# ------------------------------

def fetch_with_requests(url, timeout=15):
    headers = {"User-Agent":"Mozilla/5.0"}
    r = requests.get(url, headers=headers, timeout=timeout)
    r.raise_for_status()
    return r.text

def fetch_with_selenium(url):
    opts = Options()
    opts.add_argument("--headless=new")
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
        except: continue
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
    out['on_target'] = e.get('onTarget', False)
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

def extract_game(url, team_name):
    html = None
    data = None
    try:
        html = fetch_with_requests(url)
        data = extract_json_from_html(html)
    except:
        try:
            html = fetch_with_selenium(url)
            data = extract_json_from_html(html)
        except:
            return None

    if data is None:
        return None

    # Times e local
    home_team = data.get('events', data).get('homeTeam', {}).get('name') or data.get('home', {}).get('name')
    away_team = data.get('events', data).get('awayTeam', {}).get('name') or data.get('away', {}).get('name')
    location = "HOME" if team_name == home_team else "AWAY"
    opponent = away_team if location=="HOME" else home_team

    # Shots
    shots_blobs = recursive_find_shots(data)
    events_team = []
    events_opp = []
    for blob in shots_blobs:
        if isinstance(blob,list):
            for e in blob:
                if isinstance(e,dict):
                    if e.get('teamName')==team_name:
                        events_team.append(normalize_event(e))
                    else:
                        events_opp.append(normalize_event(e))
        elif isinstance(blob,dict):
            for v in blob.values():
                if isinstance(v,list):
                    for e in v:
                        if isinstance(e,dict):
                            if e.get('teamName')==team_name:
                                events_team.append(normalize_event(e))
                            else:
                                events_opp.append(normalize_event(e))
    if not events_team: return None

    df_team = pd.DataFrame(events_team)
    df_opp = pd.DataFrame(events_opp)

    for df in [df_team, df_opp]:
        xs=[]; ys=[]
        for _,row in df.iterrows():
            xm, ym = percent_to_meters(row.get('x_raw'), row.get('y_raw'))
            xs.append(xm); ys.append(ym)
        df['x_m'] = xs; df['y_m'] = ys
        df['dist_m'] = df.apply(lambda r: math.hypot(105-r['x_m'],34-r['y_m']) if not np.isnan(r['x_m']) else np.nan, axis=1)
        df['xG'] = df['dist_m'].apply(simple_xg_from_distance)
        df['xGOT'] = df.apply(lambda r: r['xG'] if r.get('on_target') or r['is_goal'] else 0, axis=1)
        df['opponent'] = opponent
        df['location'] = location

    # Estatísticas do time (aba "Statistics" Sofascore)
    stats_team = data.get('events', data).get('homeTeamStatistics') if location=="HOME" else data.get('events', data).get('awayTeamStatistics')
    stats_opp = data.get('events', data).get('awayTeamStatistics') if location=="HOME" else data.get('events', data).get('homeTeamStatistics')

    stats_dict = {}
    if stats_team:
        for s in stats_team.get('statistics', []):
            stats_dict[s['type']] = s.get('value')
    stats_dict_op = {}
    if stats_opp:
        for s in stats_opp.get('statistics', []):
            stats_dict_op[s['type']] = s.get('value')

    return df_team, df_opp, opponent, location, stats_dict, stats_dict_op

# ------------------------------
# STREAMLIT INTERFACE
# ------------------------------

if 'links' not in st.session_state:
    st.session_state.links = []

st.subheader("Fase 1: Inserir Links de Jogos")
new_link = st.text_input("Cole o link do jogo e pressione Enter")
if new_link:
    st.session_state.links.append(new_link)
    st.success("Link adicionado!")

# Listagem com botão remover
st.write("Links adicionados:")
for i, link in enumerate(st.session_state.links):
    cols = st.columns([0.9,0.1])
    cols[0].write(f"{i+1}. {link}")
    if cols[1].button("Remover", key=f"remove_{i}"):
        st.session_state.links.pop(i)
        st.experimental_rerun()

team_name = st.text_input("Digite o nome do time alvo")

if st.button("Processar Jogos") and team_name:
    st.subheader("Fase 2: Processamento dos Dados e Criação do Excel")
    all_team = []
    all_opp = []
    all_stats_team = []
    all_stats_opp = []
    for i, url in enumerate(st.session_state.links,1):
        st.write(f"Processando {i}/{len(st.session_state.links)}")
        result = extract_game(url, team_name)
        if result is not None:
            df_team, df_opp, opponent, location, stats_team, stats_opp = result
            df_team['Jogo'] = f"Jogo_{i}"
            df_opp['Jogo'] = f"Jogo_{i}"
            all_team.append(df_team)
            all_opp.append(df_opp)
            stats_team['Jogo'] = f"Jogo_{i}"
            stats_team['location'] = location
            stats_team['opponent'] = opponent
            stats_opp['Jogo'] = f"Jogo_{i}"
            stats_opp['location'] = location
            stats_opp['opponent'] = opponent
            all_stats_team.append(stats_team)
            all_stats_opp.append(stats_opp)
        else:
            st.warning(f"Nenhum dado para {team_name} nesse jogo.")

    if not all_team:
        st.error("Nenhum dado extraído.")
    else:
        df_all_team = pd.concat(all_team, ignore_index=True)
        df_all_opp = pd.concat(all_opp, ignore_index=True)
        df_stats_team = pd.DataFrame(all_stats_team)
        df_stats_opp = pd.DataFrame(all_stats_opp)

        st.success("Dataframe completo e Excel gerado com todas as estatísticas do time e adversário.")

        # Exportação Excel
        excel_file = "team_database_full.xlsx"
        with pd.ExcelWriter(excel_file, engine='openpyxl') as writer:
            for i, df in enumerate(all_team,1):
                df.to_excel(writer, sheet_name=f"Jogo_{i}_shots", index=False)
            df_stats_team.to_excel(writer, sheet_name="Stats_Time", index=False)
            df_stats_opp.to_excel(writer, sheet_name="Stats_Adversario", index=False)
        st.download_button("Download Excel Completo", data=open(excel_file,"rb").read(), file_name=excel_file)

        # ------------------------------
        # Fase 2: Análise interativa
        # ------------------------------
        st.subheader("Fase 2: Análise do Time")

        # Filtros dinâmicos
        jogadores = ["Todos"] + sorted(df_all_team['player'].dropna().unique().tolist())
        selected_jogador = st.selectbox("Filtrar por jogador (opcional)", jogadores)
        locais = ["Todos"] + sorted(df_all_team['location'].dropna().unique().tolist())
        selected_location = st.selectbox("Filtrar por local", locais)
        jogos = ["Todos"] + sorted(df_all_team['Jogo'].unique().tolist())
        selected_jogo = st.selectbox("Filtrar por jogo", jogos)

        # Aplicar filtros
        df_plot_team = df_all_team.copy()
        df_plot_opp = df_all_opp.copy()
        if selected_jogador != "Todos":
            df_plot_team = df_plot_team[df_plot_team['player']==selected_jogador]
        if selected_location != "Todos":
            df_plot_team = df_plot_team[df_plot_team['location']==selected_location]
            df_plot_opp = df_plot_opp[df_plot_opp['location']==selected_location]
        if selected_jogo != "Todos":
            df_plot_team = df_plot_team[df_plot_team['Jogo']==selected_jogo]
            df_plot_opp = df_plot_opp[df_plot_opp['Jogo']==selected_jogo]

        # Heatmaps
        st.subheader("Heatmap de Chutes do Time")
        if not df_plot_team.empty:
            plt.figure(figsize=(10,6))
            sns.kdeplot(x='x_m', y='y_m', data=df_plot_team, fill=True, cmap="Reds", bw_adjust=0.5)
            plt.title("Heatmap de chutes (xG/xGOT)")
            plt.xlim(0,105)
            plt.ylim(0,68)
            st.pyplot(plt)
        else:
            st.info("Nenhum chute do time no filtro selecionado.")

        st.subheader("Heatmap de Chutes Sofridos (Goleiro)")
        if not df_plot_opp.empty:
            plt.figure(figsize=(10,6))
            sns.kdeplot(x='x_m', y='y_m', data=df_plot_opp, fill=True, cmap="Blues", bw_adjust=0.5)
            plt.title("Heatmap de chutes sofridos pelo goleiro")
            plt.xlim(0,105)
            plt.ylim(0,68)
            st.pyplot(plt)
        else:
            st.info("Nenhum chute sofrido nesse filtro.")

        st.subheader("Exibir Estatísticas do Time (seleção filtrada)")
        st.dataframe(df_stats_team)

        st.subheader("Exibir Estatísticas do Adversário (seleção filtrada)")
        st.dataframe(df_stats_opp)

