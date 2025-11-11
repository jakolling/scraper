import streamlit as st
import pandas as pd
import re
import matplotlib.pyplot as plt
from mplsoccer.pitch import Pitch

st.set_page_config(layout="wide", page_title="Pipeline Chutes Meio-Campo")
st.title("Pipeline Interativa de Chutes - Standardized Coordinates")

st.markdown("""
Clique no ponto do chute no campo padronizado (0-100 x 0-100) e responda as perguntas.
""")

# Upload do XLS
xls_file = st.file_uploader("Upload do XLS com aba 'shots'", type=["xlsx"])

# Nome dos times
home_name = st.text_input("Nome do time da casa")
away_name = st.text_input("Nome do time visitante")

if xls_file and home_name and away_name:

    # Lê XLS
    df_shots = pd.read_excel(xls_file, sheet_name="shots")

    # Extrai apenas nome do jogador
    def extract_player_name(raw_name):
        match = re.search(r"'name':\s*'([^']+)'", str(raw_name))
        if match:
            return match.group(1)
        return str(raw_name)

    df_shots['player_name'] = df_shots['player_name'].apply(extract_player_name)
    df_shots = df_shots.sort_values(by="minute").reset_index(drop=True)

    # Inicializa listas para resultados
    player_list = []
    team_list = []
    x_list = []
    y_list = []
    xg_list = []
    xgot_list = []
    is_goal_list = []
    tipo_chute_list = []
    situacao_list = []

    st.write("Pipeline começa chute a chute.")

    # Controle do chute atual
    if 'current_shot' not in st.session_state:
        st.session_state.current_shot = 0

    while st.session_state.current_shot < len(df_shots):
        i = st.session_state.current_shot
        row = df_shots.iloc[i]

        st.subheader(f"Chute {i+1}: {row['player_name']} - minuto {row['minute']}")
        st.write(f"xG: {row['xg']}, xGOT: {row['xgot']}, Resultado anterior: {row['is_goal']}")

        # Perguntas
        team = st.radio("Selecione o time do jogador", options=[home_name, away_name], key=f"team_{i}")
        is_goal = st.radio("Foi gol?", options=["Gol", "Não Gol"], key=f"gol_{i}") == "Gol"
        tipo_chute = st.text_input("Tipo de chute", key=f"tipo_{i}")
        situacao = st.text_input("Situação do chute", key=f"situacao_{i}")

        # Plot do campo padronizado
        pitch = Pitch(pitch_type='statsbomb', pitch_color='grass', line_color='white', figsize=(8,6))
        fig, ax = pitch.draw()
        plt.xlim(0, 100)
        plt.ylim(0, 100)
        st.pyplot(fig)

        # Captura de coordenadas via st.slider (substituindo clique direto)
        x = st.slider("X do chute (0-100)", min_value=0, max_value=100, value=50, key=f"x_{i}")
        y = st.slider("Y do chute (0-100)", min_value=0, max_value=100, value=50, key=f"y_{i}")

        if st.button("Registrar chute"):
            player_list.append(row['player_name'])
            team_list.append(team)
            x_list.append(x)
            y_list.append(y)
            xg_list.append(row['xg'])
            xgot_list.append(row['xgot'])
            is_goal_list.append(is_goal)
            tipo_chute_list.append(tipo_chute)
            situacao_list.append(situacao)

            st.session_state.current_shot += 1
            st.experimental_rerun()

    # Ao final, salva XLS
    if st.session_state.current_shot >= len(df_shots):
        df_final = pd.DataFrame({
            "player_name": player_list,
            "team": team_list,
            "minute": df_shots["minute"],
            "x": x_list,
            "y": y_list,
            "xg": xg_list,
            "xgot": xgot_list,
            "is_goal": is_goal_list,
            "tipo_chute": tipo_chute_list,
            "situacao": situacao_list
        })
        df_final.to_excel("shots_standardized.xlsx", index=False)
        st.success("Arquivo final salvo como shots_standardized.xlsx")
