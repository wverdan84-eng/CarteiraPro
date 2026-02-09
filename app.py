import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import plotly.graph_objects as go
import sqlite3
import numpy as np

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title='InvestPro Titanium v15.2', layout='wide', page_icon='💎')

def run_db(sql, params=(), select=True):
    conn = sqlite3.connect('titanium_ultimate.db')
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS clientes (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT UNIQUE)')
    c.execute('''CREATE TABLE IF NOT EXISTS transacoes 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER, ativo TEXT, 
                  tipo TEXT, operacao TEXT, quantidade REAL, preco REAL, data TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS metas 
                 (client_id INTEGER, ativo TEXT, porcentagem REAL, PRIMARY KEY(client_id, ativo))''')
    if select:
        res = pd.read_sql(sql, conn)
        conn.close()
        return res
    else:
        c.execute(sql, params); conn.commit(); conn.close()

@st.cache_data(ttl=3600)
def get_usd_rate():
    try: return float(yf.Ticker('USDBRL=X').history(period='1d')['Close'].iloc[-1])
    except: return 5.85

@st.cache_data(ttl=600)
def get_live_prices(tickers):
    if not tickers: return {}
    try:
        data = yf.download(tickers, period='1d', progress=False)['Close']
        if len(tickers) == 1: return {tickers[0]: float(data.iloc[-1])}
        return {t: float(data[t].iloc[-1]) for t in tickers}
    except: return {}

# --- INTERFACE ---
st.sidebar.title('💎 TITANIUM v15.2')
run_db("SELECT 1", select=False)
clis = run_db('SELECT * FROM clientes')
sel_cli = st.sidebar.selectbox('Usuário', ['Selecionar...'] + clis['nome'].tolist() + ['+ Novo'])

if sel_cli == '+ Novo':
    n = st.sidebar.text_input('Nome')
    if st.sidebar.button('Criar'):
        run_db('INSERT INTO clientes (nome) VALUES (?)', (n,), False); st.rerun()

elif sel_cli != 'Selecionar...':
    cid = int(clis[clis['nome'] == sel_cli]['id'].values[0])
    usd = get_usd_rate()
    st.sidebar.metric('Dólar Comercial', f'R$ {usd:.2f}')
    df_t = run_db(f'SELECT * FROM transacoes WHERE client_id={cid}')
    
    tabs = st.tabs(['📊 Dash', '💰 Dividendos & Yield', '🔬 Valuation Completo', '📈 Evolução', '🎯 Metas', '📜 Extrato'])
    
    # --- LOGICA DE POSIÇÃO (Unificada para Variável e Fixa) ---
    posicao = []
    if not df_t.empty:
        ativos_u = df_t['ativo'].unique()
        tickers_para_baixar = []
        for a in ativos_u:
            d = df_t[df_t['ativo'] == a]
            qtd = d[d['operacao']=='COMPRA']['quantidade'].sum() - d[d['operacao']=='VENDA']['quantidade'].sum()
            if qtd > 0.001:
                tipo_ativo = d['tipo'].iloc[0]
                tk = a
                if tipo_ativo != 'Renda Fixa':
                    tk = f"{a}.SA" if ".SA" not in a.upper() and tipo_ativo != 'Exterior' else a
                    tickers_para_baixar.append(tk)
                
                compras = d[d['operacao'] == 'COMPRA']
                p_medio = (compras['quantidade'] * compras['preco']).sum() / compras['quantidade'].sum() if not compras.empty else 0
                posicao.append({'Ativo': a, 'Qtd': qtd, 'Tipo': tipo_ativo, 'tk': tk, 'PM': p_medio})
        
        precos_mercado = get_live_prices(tickers_para_baixar)
        for p in posicao:
            if p['Tipo'] == 'Renda Fixa':
                p['Preço Atual'] = p['PM'] # Renda fixa manual mantém o preço de custo
            else:
                p['Preço Atual'] = precos_mercado.get(p['tk'], 0)
            
            val_un = p['Preço Atual'] * usd if p['Tipo'] == 'Exterior' else p['Preço Atual']
            p['Patrimônio'] = p['Qtd'] * val_un

    with tabs[0]: # DASHBOARD
        if posicao:
            df_f = pd.DataFrame(posicao)
            total_patrimonio = float(df_f['Patrimônio'].sum())
            st.metric('Patrimônio Total', f"R$ {total_patrimonio:,.2f}")
            st.plotly_chart(px.pie(df_f, values='Patrimônio', names='Ativo', hole=0.4, title="Distribuição por Ativo"))
            st.plotly_chart(px.pie(df_f, values='Patrimônio', names='Tipo', title="Alocação por Classe de Ativo"))
        else: st.info("Sua carteira está vazia.")

    with tabs[1]: # DIVIDENDOS (Apenas Variável)
        posicao_var = [p for p in posicao if p['Tipo'] != 'Renda Fixa']
        if posicao_var:
            st.subheader("💰 Rendimentos e Yield on Cost")
            div_data = []
            for p in posicao_var:
                t_obj = yf.Ticker(p['tk'])
                dpa = t_obj.info.get('dividendRate', 0) or 0
                yoc = (dpa / p['PM']) * 100 if p['PM'] > 0 else 0
                dy_at = (dpa / p['Preço Atual']) * 100 if p['Preço Atual'] > 0 else 0
                div_data.append({
                    'Ativo': p['Ativo'], 'PM': p['PM'], 'Preço': p['Preço Atual'],
                    'DY Atual %': dy_at, 'YOC %': yoc, 'Renda Anual Est.': dpa * p['Qtd']
                })
            df_div = pd.DataFrame(div_data)
            c1, c2, c3 = st.columns(3)
            total_anual = df_div['Renda Anual Est.'].sum()
            c1.metric("Renda Anual Est.", f"R$ {total_anual:,.2f}")
            c2.metric("Renda Mensal Est.", f"R$ {total_anual/12:,.2f}")
            c3.metric("YOC Médio", f"{df_div['YOC %'].mean():.2f}%")
            st.dataframe(df_div.style.format({'PM': 'R$ {:.2f}', 'Preço': 'R$ {:.2f}', 'DY Atual %': '{:.2f}%', 'YOC %': '{:.2f}%', 'Renda Anual Est.': 'R$ {:.2f}'}), use_container_width=True)
            st.plotly_chart(px.bar(df_div, x='Ativo', y='YOC %', title="Yield On Cost por Ativo"))
        else: st.info("Adicione Ações ou FIIs para ver dividendos.")

    with tabs[2]: # VALUATION COMPLETO
        posicao_val = [p for p in posicao if p['Tipo'] in ['Ação', 'FII', 'Exterior']]
        if posicao_val:
            st.subheader("🔬 Análise de Preço Justo")
            at_x = st.selectbox('Escolha o Ativo:', [p['Ativo'] for p in posicao_val], key='val_s')
            if st.button('Calcular Valuation Profundo'):
                p_i = next(item for item in posicao_val if item["Ativo"] == at_x)
                tk_o = yf.Ticker(p_i['tk'])
                inf = tk_o.info
                lpa, vpa, dpa = inf.get('trailingEps', 0), inf.get('bookValue', 0), inf.get('dividendRate', 0)
                c1, c2, c3 = st.columns(3)
                with c1:
                    st.markdown("### 🏛️ Graham")
                    if lpa > 0 and vpa > 0: st.metric("Preço Justo", f"R$ {np.sqrt(22.5 * lpa * vpa):.2f}")
                with c2:
                    st.markdown("### 💰 Bazin (6%)")
                    if dpa > 0: st.metric("Preço Justo", f"R$ {dpa/0.06:.2f}")
                with c3:
                    st.markdown("### 📈 P/L 15x")
                    if lpa > 0: st.metric("Preço Justo", f"R$ {lpa * 15:.2f}")
                
                h_v = tk_o.history(period='max')['Close']
                if not h_v.empty:
                    fig_v = go.Figure()
                    fig_v.add_trace(go.Scatter(x=h_v.index, y=h_v.values, name='Mercado'))
                    if lpa > 0 and vpa > 0:
                        fig_v.add_hline(y=np.sqrt(22.5 * lpa * vpa), line_dash="dot", line_color="green", annotation_text="Graham")
                    st.plotly_chart(fig_v, use_container_width=True)
        else: st.info("Valuation disponível apenas para Renda Variável.")

    with tabs[3]: # EVOLUÇÃO
        if posicao:
            at_h = st.selectbox('Selecione o Ativo:', [p['Ativo'] for p in posicao], key='evol_s')
            p_inf = next(item for item in posicao if item["Ativo"] == at_h)
            if p_inf['Tipo'] != 'Renda Fixa':
                h_d = yf.Ticker(p_inf['tk']).history(period='max')['Close']
                if not h_d.empty:
                    fig_h = go.Figure()
                    fig_h.add_trace(go.Scatter(x=h_d.index, y=h_d.values, name='Preço'))
                    fig_h.add_trace(go.Scatter(x=h_d.index, y=[p_inf['PM']]*len(h_d), name='Seu Médio', line=dict(color='red', dash='dash')))
                    st.plotly_chart(fig_h, use_container_width=True)
            else: st.warning("Histórico de cotação não disponível para ativos de Renda Fixa manual.")

    with tabs[4]: # METAS
        if not df_t.empty:
            with st.form("metas_v152"):
                for a in df_t['ativo'].unique():
                    m_db = run_db(f"SELECT porcentagem FROM metas WHERE client_id={cid} AND ativo='{a}'")
                    v_ini = float(m_db['porcentagem'].iloc[0]) if not m_db.empty else 0.0
                    st.number_input(f"Meta % {a}", 0.0, 100.0, v_ini, key=f"m_{a}")
                if st.form_submit_button("Salvar Metas"):
                    for a in df_t['ativo'].unique():
                        run_db("INSERT OR REPLACE INTO metas VALUES (?,?,?)", (cid, a, st.session_state[f"m_{a}"]), False)
                    st.rerun()

    with tabs[5]: # EXTRATO (COM RENDA FIXA)
        with st.expander("➕ Nova Operação"):
            with st.form("op_v152"):
                c1, c2, c3 = st.columns(3)
                at = c1.text_input("Nome/Ticker (Ex: CDB ITAU ou PETR4)").upper()
                tp = c2.selectbox("Tipo", ["Ação", "FII", "Exterior", "Renda Fixa"])
                op = c3.selectbox("Operação", ["COMPRA", "VENDA"])
                qt = c1.number_input("Quantidade", 0.0)
                pr = c2.number_input("Preço Unitário", 0.0)
                if st.form_submit_button("Lançar Operação"):
                    run_db("INSERT INTO transacoes (client_id, ativo, tipo, operacao, quantidade, preco) VALUES (?,?,?,?,?,?)", (cid, at, tp, op, qt, pr), False)
                    st.rerun()
        st.subheader("Histórico de Movimentações")
        st.dataframe(df_t, use_container_width=True)