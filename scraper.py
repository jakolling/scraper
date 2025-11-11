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
