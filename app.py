import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import sqlite3
import io
from datetime import datetime

# --- CONFIGURAÇÃO E ESTILO ---
st.set_page_config(page_title="InvestPro Ultimate AI", layout="wide", page_icon="🚀")

# --- BANCO DE DADOS (Preservando Estrutura) ---
def init_db():
    conn = sqlite3.connect('investpro_ultimate_v4.db')
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS clientes (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT UNIQUE)')
    c.execute('''CREATE TABLE IF NOT EXISTS transacoes (id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER, 
                  ativo TEXT, tipo TEXT, operacao TEXT, quantidade REAL, preco REAL, data TEXT)''')
    c.execute('CREATE TABLE IF NOT EXISTS proventos (id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER, ativo TEXT, valor REAL, data TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS alertas (id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER, ativo TEXT, preco_alvo REAL)')
    conn.commit()
    conn.close()

init_db()

# --- FUNÇÕES DE APOIO ---
def get_clientes():
    conn = sqlite3.connect('investpro_ultimate_v4.db')
    df = pd.read_sql("SELECT * FROM clientes", conn); conn.close()
    return df

def add_transacao(client_id, ativo, tipo, operacao, qtd, preco, data=None):
    if not data or data == 'None' or data == 'nan': 
        data = datetime.now().strftime("%Y-%m-%d")
    conn = sqlite3.connect('investpro_ultimate_v4.db')
    c = conn.cursor()
    c.execute("INSERT INTO transacoes (client_id, ativo, tipo, operacao, quantidade, preco, data) VALUES (?,?,?,?,?,?,?)",
              (client_id, str(ativo).upper(), tipo, str(operacao).upper(), qtd, preco, data))
    conn.commit(); conn.close()

def add_provento(client_id, ativo, valor, data):
    conn = sqlite3.connect('investpro_ultimate_v4.db')
    c = conn.cursor()
    c.execute("INSERT INTO proventos (client_id, ativo, valor, data) VALUES (?, ?, ?, ?)",
              (client_id, str(ativo).upper(), valor, data))
    conn.commit(); conn.close()

def calcular_carteira_completa(client_id):
    conn = sqlite3.connect('investpro_ultimate_v4.db')
    df = pd.read_sql(f"SELECT * FROM transacoes WHERE client_id = {client_id}", conn); conn.close()
    if df.empty: return pd.DataFrame(), 0.0, 0.0
    
    ativos = {}; lucro_realizado = 0.0; vendas_mes_atual = 0.0
    mes_atual = datetime.now().strftime("%Y-%m")
    
    for _, row in df.sort_values('data').iterrows():
        at = row['ativo']
        if at not in ativos: ativos[at] = {'qtd': 0.0, 'custo': 0.0, 'tipo': row['tipo']}
        
        if row['operacao'] == 'COMPRA':
            ativos[at]['qtd'] += row['quantidade']
            ativos[at]['custo'] += row['quantidade'] * row['preco']
        else: # VENDA
            pm_venda = ativos[at]['custo'] / ativos[at]['qtd'] if ativos[at]['qtd'] > 0 else 0
            lucro_realizado += (row['preco'] - pm_venda) * row['quantidade']
            if str(row['data']).startswith(mes_atual):
                vendas_mes_atual += (row['quantidade'] * row['preco'])
            ativos[at]['qtd'] -= row['quantidade']
            ativos[at]['custo'] -= row['quantidade'] * pm_venda
            
    res = [{'Ativo': k, 'Tipo': v['tipo'], 'Quantidade': v['qtd'], 'PM': v['custo']/v['qtd'] if v['qtd']>0 else 0, 'Total_Investido': v['custo']} for k,v in ativos.items() if v['qtd'] > 0]
    return pd.DataFrame(res), lucro_realizado, vendas_mes_atual

@st.cache_data(ttl=600)
def fetch_prices(tickers):
    prices = {}
    try: usd_brl = yf.Ticker("USDBRL=X").history(period="1d")['Close'].iloc[-1]
    except: usd_brl = 5.60
    for t in tickers:
        try:
            tk = t if "." in t or len(t) > 5 else f"{t}.SA"
            d = yf.Ticker(tk).history(period="1d")
            if not d.empty: prices[t] = d['Close'].iloc[-1]
            else:
                d_us = yf.Ticker(t).history(period="1d")
                prices[t] = d_us['Close'].iloc[-1] * usd_brl if not d_us.empty else 0
        except: prices[t] = 0
    return prices

# --- INTERFACE ---
st.sidebar.title("💎 InvestPro Ultimate v4.1")
clientes_df = get_clientes()
sel_cliente = st.sidebar.selectbox("Cliente:", ["Selecionar..."] + clientes_df['nome'].tolist() + ["+ Novo"])
cliente_id = int(clientes_df[clientes_df['nome'] == sel_cliente]['id'].values[0]) if sel_cliente not in ["Selecionar...", "+ Novo"] else None

if sel_cliente == "+ Novo":
    n = st.sidebar.text_input("Nome")
    if st.sidebar.button("Salvar Cliente"):
        conn = sqlite3.connect('investpro_ultimate_v4.db'); c = conn.cursor()
        c.execute("INSERT INTO clientes (nome) VALUES (?)", (n,)); conn.commit(); conn.close(); st.rerun()

menu = st.sidebar.radio("Navegação", ["Dashboard", "Boleta & Importação", "Proventos", "Extrato & Histórico", "Tributos (IR)", "Alertas", "Custódia & Export"])

if not cliente_id:
    st.title("Sistema Gestor de Património")
    st.info("Selecione um cliente para começar.")
else:
    df_pos, lucro_total, vol_vendas = calcular_carteira_completa(cliente_id)

    if menu == "Dashboard":
        st.title(f"📊 Resumo: {sel_cliente}")
        if not df_pos.empty:
            p_map = fetch_prices(df_pos['Ativo'].tolist())
            df_pos['Valor_Atual'] = df_pos['Quantidade'] * df_pos['Ativo'].map(p_map)
            c1, c2, c3 = st.columns(3)
            c1.metric("Património", f"R$ {df_pos['Valor_Atual'].sum():,.2f}")
            c2.metric("Lucro Realizado", f"R$ {lucro_total:,.2f}")
            c3.metric("Vendas no Mês", f"R$ {vol_vendas:,.2f}")
            col_a, col_b = st.columns(2)
            col_a.plotly_chart(px.pie(df_pos, values='Valor_Atual', names='Tipo', hole=.4, title="Alocação"), use_container_width=True)
            col_b.plotly_chart(px.bar(df_pos, x='Ativo', y='Valor_Atual', color='Tipo', title="Posições"), use_container_width=True)

    elif menu == "Boleta & Importação":
        st.title("📥 Entrada de Dados")
        tab_man, tab_auto = st.tabs(["Manual", "Importar Excel/CSV"])
        with tab_man:
            with st.form("f1"):
                at = st.text_input("Ticker").upper()
                tp = st.selectbox("Tipo", ["Ação","FII","ETF","Exterior","Renda Fixa"])
                op = st.selectbox("Operação", ["COMPRA", "VENDA"])
                qt = st.number_input("Qtd", 0.0)
                pr = st.number_input("Preço", 0.0)
                dt = st.date_input("Data")
                if st.form_submit_button("Lançar"):
                    add_transacao(cliente_id, at, tp, op, qt, pr, dt.strftime("%Y-%m-%d"))
                    st.success("Registado!"); st.rerun()
        
        with tab_auto:
            st.info("O arquivo deve conter colunas similares a: ativo, tipo, operacao, quantidade, preco, data")
            up = st.file_uploader("Arquivo de Importação", type=['csv', 'xlsx'])
            if up:
                try:
                    df_up = pd.read_csv(up) if up.name.endswith('.csv') else pd.read_excel(up)
                    # --- CORREÇÃO DO KEYERROR ---
                    df_up.columns = [str(c).strip().lower() for c in df_up.columns]
                    mapa = {'ticker': 'ativo', 'operação': 'operacao', 'qtd': 'quantidade', 'preço': 'preco'}
                    df_up = df_up.rename(columns=mapa)
                    
                    st.write("Dados detectados:", df_up.head(3))
                    if st.button("Confirmar Importação de " + str(len(df_up)) + " linhas"):
                        for _, r in df_up.iterrows():
                            # Busca as colunas com fallback para evitar novos erros de chave
                            v_ativo = r.get('ativo', r.get('ticker', 'ERRO'))
                            v_tipo = r.get('tipo', 'Ação')
                            v_op = r.get('operacao', 'COMPRA')
                            v_qtd = r.get('quantidade', 0)
                            v_pr = r.get('preco', 0)
                            v_dt = str(r.get('data', datetime.now().strftime("%Y-%m-%d")))
                            
                            add_transacao(cliente_id, v_ativo, v_tipo, v_op, v_qtd, v_pr, v_dt)
                        st.success("Importação concluída com sucesso!")
                        st.rerun()
                except Exception as e:
                    st.error(f"Erro ao processar arquivo: {e}")

    elif menu == "Proventos":
        st.title("💰 Dividendos e Rendimentos")
        with st.form("prov"):
            c1, c2, c3 = st.columns(3)
            at_p = c1.text_input("Ticker").upper()
            vl_p = c2.number_input("Valor R$", min_value=0.0)
            dt_p = c3.date_input("Data Pagamento")
            if st.form_submit_button("Salvar Provento"):
                add_provento(cliente_id, at_p, vl_p, dt_p.strftime("%Y-%m-%d"))
                st.success("Salvo!"); st.rerun()

    elif menu == "Extrato & Histórico":
        st.title("📜 Histórico e Extrato")
        conn = sqlite3.connect('investpro_ultimate_v4.db')
        df_tr = pd.read_sql(f"SELECT data, ativo, tipo, operacao, quantidade, preco FROM transacoes WHERE client_id = {cliente_id}", conn)
        df_pr = pd.read_sql(f"SELECT data, ativo, valor as preco, 'PROVENTO' as operacao, 'Rendimento' as tipo, 1 as quantidade FROM proventos WHERE client_id = {cliente_id}", conn)
        conn.close()
        
        df_hist = pd.concat([df_tr, df_pr], ignore_index=True).sort_values('data', ascending=False)
        
        at_filter = st.selectbox("Filtrar por Ativo:", ["TODOS"] + sorted(df_hist['ativo'].unique().tolist()))
        if at_filter != "TODOS":
            df_hist = df_hist[df_hist['ativo'] == at_filter]
        
        st.dataframe(df_hist, use_container_width=True)

    elif menu == "Tributos (IR)":
        st.title("⚖️ Gestão Fiscal")
        st.metric("Total de Vendas (Mês Atual)", f"R$ {vol_vendas:,.2f}")
        if vol_vendas > 20000:
            st.error("⚠️ Limite de isenção ultrapassado!")
        else:
            st.success("Isento de IR para vendas de Ações até R$ 20.000,00.")

    elif menu == "Alertas":
        st.title("🔔 Alertas de Preço")
        with st.form("a"):
            at_a = st.text_input("Ticker").upper(); pr_a = st.number_input("Preço Alvo")
            if st.form_submit_button("Definir Alerta"):
                conn = sqlite3.connect('investpro_ultimate_v4.db'); c = conn.cursor()
                c.execute("INSERT INTO alertas (client_id, ativo, preco_alvo) VALUES (?,?,?)",(cliente_id, at_a, pr_a))
                conn.commit(); conn.close(); st.success("Alerta registrado.")

    elif menu == "Custódia & Export":
        st.title("📑 Posição Detalhada")
        if not df_pos.empty:
            p_map = fetch_prices(df_pos['Ativo'].tolist())
            df_pos['Cotação'] = df_pos['Ativo'].map(p_map)
            df_pos['Total_Atual'] = df_pos['Quantidade'] * df_pos['Cotação']
            df_pos['Lucro_R$'] = df_pos['Total_Atual'] - df_pos['Total_Investido']
            st.dataframe(df_pos.style.format({'PM': '{:.2f}', 'Cotação': '{:.2f}', 'Total_Atual': '{:.2f}', 'Lucro_R$': '{:.2f}'}))
            
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                df_pos.to_excel(writer, index=False, sheet_name='Custódia')
            st.download_button("📥 Baixar Planilha de Custódia", data=buffer.getvalue(), file_name="Relatorio_InvestPro.xlsx")