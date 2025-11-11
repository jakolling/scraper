import streamlit as st
import pandas as pd
import re
from PIL import Image
from streamlit_drawable_canvas import st_canvas

st.set_page_config(layout="wide", page_title="Pipeline Chutes Meio-Campo")
st.title("Revisão Interativa de Chutes - Meio-Campo")

st.markdown("""
Pipeline interativa para revisar chute a chute, calibrar imagem do meio-campo, definir time do jogador e gol/não gol.
""")

# Upload imagens
home_img_file = st.file_uploader("Imagem do time da casa (meio-campo)", type=["png", "jpg", "jpeg"])
away_img_file = st.file_uploader("Imagem do time visitante (meio-campo)", type=["png", "jpg", "jpeg"])

# Nome dos times
home_name = st.text_input("Nome do time da casa")
away_name = st.text_input("Nome do time visitante")

# Upload do XLS
xls_file = st.file_uploader("Upload do XLS com aba 'shots'", type=["xlsx"])

# Avançar somente se tudo estiver carregado
if home_img_file and away_img_file and home_name and away_name and xls_file:

    # Converte uploads em PIL
    home_img = Image.open(home_img_file)
    away_img = Image.open(away_img_file)

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

    # Inicializa listas de resultados
    player_list = []
    team_list = []
    x_list = []
    y_list = []
    xg_list = []
    xgot_list = []
    is_goal_list = []

    st.write("⚠️ Pipeline começa chute a chute. Clique nos pontos solicitados na imagem.")

    # Controle do chute atual
    if 'current_shot' not in st.session_state:
        st.session_state.current_shot = 0

    while st.session_state.current_shot < len(df_shots):
        i = st.session_state.current_shot
        row = df_shots.iloc[i]

        st.subheader(f"Chute {i + 1}: {row['player_name']} - minuto {row['minute']}")
        st.write(f"xG: {row['xg']}, xGOT: {row['xgot']}, Resultado anterior: {row['is_goal']}")

        # Escolher time
        team = st.radio("Selecione o time do jogador", options=[home_name, away_name], key=f"team_{i}")
        img_file = home_img if team == home_name else away_img

        # Canvas calibração
        st.markdown("**Clique nos 4 cantos do meio-campo para calibrar (esq-baixo, esq-cima, dir-cima, dir-baixo)**")
        canvas_calib = st_canvas(
            fill_color="rgba(0,0,0,0)",
            stroke_width=3,
            stroke_color="#FF0000",
            background_image=img_file,
            height=500,
            width=800,
            drawing_mode="point",
            key=f"calib_{i}"
        )

        if canvas_calib.json_data and len(canvas_calib.json_data["objects"]) == 4:
            calib_points = [(obj["left"], obj["top"]) for obj in canvas_calib.json_data["objects"]]
            x_coords = [p[0] for p in calib_points]
            y_coords = [p[1] for p in calib_points]
            x_min, x_max = min(x_coords), max(x_coords)
            y_min, y_max = min(y_coords), max(y_coords)

            st.success("Calibração concluída!")

            # Canvas chute
            st.markdown("**Clique no ponto do chute**")
            canvas_shot = st_canvas(
                fill_color="rgba(0,0,0,0)",
                stroke_width=3,
                stroke_color="#0000FF",
                background_image=img_file,
                height=500,
                width=800,
                drawing_mode="point",
                key=f"shot_{i}"
            )

            if canvas_shot.json_data and len(canvas_shot.json_data["objects"]) == 1:
                shot_point = canvas_shot.json_data["objects"][0]
                x_px, y_px = shot_point["left"], shot_point["top"]

                # Normaliza X=0–50, Y=0–100
                x_norm = (x_px - x_min) / (x_max - x_min) * 50
                y_norm = (y_px - y_min) / (y_max - y_min) * 100

                # Gol
                is_goal = st.radio("Foi gol?", options=["Gol", "Não Gol"], key=f"gol_{i}") == "Gol"

                # Salva dados
                player_list.append(row['player_name'])
                team_list.append(team)
                x_list.append(x_norm)
                y_list.append(y_norm)
                xg_list.append(row['xg'])
                xgot_list.append(row['xgot'])
                is_goal_list.append(is_goal)

                # Botão avançar chute
                if st.button("Próximo chute"):
                    st.session_state.current_shot += 1
                    st.experimental_rerun()  # força re-renderização do próximo chute
        break  # importante para evitar múltiplos loops no mesmo render

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
            "is_goal": is_goal_list
        })
        df_final.to_excel("shots_updated.xlsx", index=False)
        st.success("Arquivo final salvo como shots_updated.xlsx")
