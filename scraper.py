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
home_img = st.file_uploader("Imagem do time da casa (meio-campo)", type=["png", "jpg", "jpeg"])
away_img = st.file_uploader("Imagem do time visitante (meio-campo)", type=["png", "jpg", "jpeg"])

# Nome dos times
home_name = st.text_input("Nome do time da casa")
away_name = st.text_input("Nome do time visitante")

# Upload do XLS
xls_file = st.file_uploader("Upload do XLS com aba 'shots'", type=["xlsx"])

# Avançar somente se tudo estiver carregado
if home_img and away_img and home_name and away_name and xls_file:
    
    # Converte uploads para PIL
    home_img_pil = Image.open(home_img)
    away_img_pil = Image.open(away_img)
    
    # Lê XLS
    df_shots = pd.read_excel(xls_file, sheet_name="shots")

    # Extrai apenas nome do jogador
    def extract_player_name(raw_name):
        match = re.search(r"'name':\s*'([^']+)'", str(raw_name))
        if match:
            return match.group(1)
        return str(raw_name)
    
    df_shots['player_name'] = df_shots['player_name'].apply(extract_player_name)
    
    # Ordena pelo minuto
    df_shots = df_shots.sort_values(by="minute").reset_index(drop=True)
    
    # Inicializa listas para resultados
    player_list = []
    team_list = []
    x_list = []
    y_list = []
    xg_list = []
    xgot_list = []
    is_goal_list = []
    
    st.write("⚠️ Pipeline começa chute a chute. Clique nos pontos solicitados na imagem.")
    
    for i, row in df_shots.iterrows():
        st.subheader(f"Chute {i+1}: {row['player_name']} - minuto {row['minute']}")
        st.write(f"xG: {row['xg']}, xGOT: {row['xgot']}, Resultado anterior: {row['is_goal']}")
        
        # Escolher time do jogador
        team = st.radio("Selecione o time do jogador", options=[home_name, away_name], key=f"team_{i}")
        
        # Selecionar imagem correspondente
        img_file = home_img_pil if team == home_name else away_img_pil
        
        st.markdown("**Clique nos 4 cantos do meio-campo para calibrar a imagem (esq-baixo, esq-cima, dir-cima, dir-baixo)**")
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
                
                # Normaliza coordenadas (X:0-50, Y:0-100)
                x_norm = (x_px - x_min) / (x_max - x_min) * 50
                y_norm = (y_px - y_min) / (y_max - y_min) * 100
                
                # Perguntar se foi gol
                is_goal = st.radio("Foi gol?", options=["Gol", "Não Gol"], key=f"gol_{i}") == "Gol"
                
                # Salvar dados
                player_list.append(row['player_name'])
                team_list.append(team)
                x_list.append(x_norm)
                y_list.append(y_norm)
                xg_list.append(row['xg'])
                xgot_list.append(row['xgot'])
                is_goal_list.append(is_goal)
    
    # Criar DataFrame final
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
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt

st.set_page_config(layout="wide", page_title="Preenchimento de Shots XLS")
st.title("Preenchimento Interativo da Coluna is_goal")

st.markdown("""
Este app permite revisar chute a chute e corrigir a coluna **is_goal**.  
Você pode também normalizar as coordenadas para a imagem do campo e exportar um XLS atualizado.
""")

# Upload das imagens
home_img = st.file_uploader("Upload da imagem do time da casa", type=['png','jpg','jpeg'], key='home')
away_img = st.file_uploader("Upload da imagem do time visitante", type=['png','jpg','jpeg'], key='away')

# Upload do XLS com aba 'shots'
xls_file = st.file_uploader("Upload do arquivo XLS com aba 'shots'", type=['xlsx'])

if home_img and away_img and xls_file:
    # Lê Excel
    df_shots = pd.read_excel(xls_file, sheet_name='shots')

    # Verifica colunas obrigatórias
    required_cols = ['player_id','player_name','team','minute','x','y','xg','xgot','result','is_goal']
    if not all(col in df_shots.columns for col in required_cols):
        st.error(f"A aba 'shots' precisa conter as colunas: {required_cols}")
    else:
        # Define tamanho do campo em pixels
        field_width, field_height = 800, 500

        # Normaliza coordenadas
        df_shots['x_px'] = df_shots['x'] / 100 * field_width
        df_shots['y_px'] = df_shots['y'] / 100 * field_height

        # Revisão dos chutes
        st.subheader("Revisão dos chutes (confirme se foi gol ou não)")

        updated_is_goal = []

        for i, row in df_shots.iterrows():
            st.markdown(f"**{row['player_name']} ({row['team']}) - {row['minute']}'**")
            st.markdown(f"xG: {row['xg']}, xGOT: {row['xgot']}, Resultado no XLS: {row['is_goal']}")
            
            # Radio buttons para Gol / Não Gol
            choice = st.radio(
                "Foi gol?", 
                options=["Gol", "Não Gol"], 
                index=0 if row['is_goal'] else 1,
                key=f"gol_radio_{i}"
            )
            updated_is_goal.append(choice == "Gol")

        df_shots['is_goal'] = updated_is_goal

        # Separar chutes por time
        df_home = df_shots[df_shots['team'].str.lower() == 'home']
        df_away = df_shots[df_shots['team'].str.lower() == 'away']

        # Função para plotar chutes
        def plot_shots(df, field_img, title):
            fig, ax = plt.subplots(figsize=(8,5))
            img = plt.imread(field_img)
            ax.imshow(img, extent=[0, field_width, 0, field_height])
            for _, row in df.iterrows():
                color = 'red' if row['is_goal'] else 'blue'
                ax.scatter(row['x_px'], row['y_px'], c=color, s=100, alpha=0.7)
            ax.set_title(title)
            ax.axis('off')
            return fig

        # Plot home
        st.subheader("Chutes - Time da Casa")
        fig_home = plot_shots(df_home, home_img, "Time da Casa")
        st.pyplot(fig_home)

        # Plot away
        st.subheader("Chutes - Time Visitante")
        fig_away = plot_shots(df_away, away_img, "Time Visitante")
        st.pyplot(fig_away)

        # Exportar XLS atualizado
        export_file = 'shots_updated.xlsx'
        df_shots.to_excel(export_file, index=False)
        st.success(f"Arquivo XLS atualizado exportado: {export_file}")

