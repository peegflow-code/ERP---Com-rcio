import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, date, timedelta
import hashlib
import altair as alt
import io
import random

# ==========================================
# CONFIGURAÇÃO DA PÁGINA & ESTILO (CSS)
# ==========================================
st.set_page_config(
    page_title='PeegFlow - Comercial',
    page_icon='🔹',
    layout='wide',
    initial_sidebar_state="expanded"
)

# Paleta de Cores: Azul Royal (#4169E1 a #1A237E) e Verde Menta (#98FF98 a #00C896)
st.markdown("""
    <style>
        /* Fundo Geral (Dark Mode suave) */
        .stApp {
            background-color: #0e1117;
        }
        
        /* Sidebar - Azul Royal Gradiente */
        [data-testid="stSidebar"] {
            background-color: #1a237e;
            background-image: linear-gradient(180deg, #1a237e 0%, #0d1b3e 100%);
            border-right: 1px solid #4169E1;
        }
        
        /* Textos da Sidebar */
        [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3, [data-testid="stSidebar"] span, [data-testid="stSidebar"] p {
            color: #ffffff !important;
        }
        
        /* Botões Primários (Verde Menta) */
        div.stButton > button:first-child {
            background-color: #00C896; 
            color: #0d1b3e;
            font-weight: bold;
            border-radius: 8px;
            border: none;
            padding: 0.5rem 1rem;
        }
        div.stButton > button:first-child:hover {
            background-color: #98FF98;
            color: #000000;
            box-shadow: 0 0 10px #00C896;
        }

        /* Títulos Principais (H1) */
        h1 {
            color: #4169E1 !important; /* Azul Royal Claro */
            font-weight: 800;
        }
        
        /* Subtítulos (H2, H3) */
        h2, h3 {
            color: #00C896 !important; /* Menta */
        }

        /* Cards de Métricas */
        [data-testid="stMetricValue"] {
            color: #98FF98 !important; /* Texto do valor em Menta */
        }
        [data-testid="stMetricLabel"] {
            color: #aaaaaa !important;
        }
        
        /* Inputs e Selectboxes */
        div[data-baseweb="select"] > div, div[data-baseweb="input"] > div {
            background-color: #1c1f26;
            border-color: #4169E1;
            color: white;
        }
        
        /* Tabelas */
        [data-testid="stDataFrame"] {
            border: 1px solid #4169E1;
        }
        
        /* Radio Buttons na Sidebar */
        .st-emotion-cache-16txtl3 {
            color: white;
        }
        
    </style>
""", unsafe_allow_html=True)

DB_PATH = 'sistema.db'

# ----------------- Helpers DB -----------------
@st.cache_resource
def get_connection(path=DB_PATH):
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db(conn):
    c = conn.cursor()
    # users
    c.execute('''
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY,
            username TEXT UNIQUE,
            password_hash TEXT,
            role TEXT
        )
    ''')
    # products
    c.execute('''
        CREATE TABLE IF NOT EXISTS products(
            id INTEGER PRIMARY KEY,
            sku TEXT UNIQUE,
            name TEXT,
            category TEXT,
            price_retail REAL,
            price_wholesale REAL,
            stock INTEGER,
            stock_min INTEGER,
            supplier_id INTEGER
        )
    ''')
    # suppliers
    c.execute('''
        CREATE TABLE IF NOT EXISTS suppliers(
            id INTEGER PRIMARY KEY,
            name TEXT,
            contact TEXT
        )
    ''')
    # sales
    c.execute('''
        CREATE TABLE IF NOT EXISTS sales(
            id INTEGER PRIMARY KEY,
            product_id INTEGER,
            quantity INTEGER,
            price REAL,
            kind TEXT,
            date TEXT,
            user_id INTEGER
        )
    ''')
    # purchases (incoming stock)
    c.execute('''
        CREATE TABLE IF NOT EXISTS purchases(
            id INTEGER PRIMARY KEY,
            product_id INTEGER,
            quantity INTEGER,
            unit_price REAL,
            supplier_id INTEGER,
            date TEXT
        )
    ''')
    # expenses
    c.execute('''
        CREATE TABLE IF NOT EXISTS expenses(
            id INTEGER PRIMARY KEY,
            description TEXT,
            amount REAL,
            date TEXT,
            category TEXT
        )
    ''')
    # settings
    c.execute('''
        CREATE TABLE IF NOT EXISTS settings(
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    conn.commit()

# ----------------- Auth -----------------
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def create_user(conn, username, password, role='user'):
    c = conn.cursor()
    try:
        c.execute('INSERT INTO users(username,password_hash,role) VALUES(?,?,?)', (username, hash_password(password), role))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False

def authenticate(conn, username, password):
    c = conn.cursor()
    c.execute('SELECT * FROM users WHERE username=?', (username,))
    r = c.fetchone()
    if not r:
        return None
    if r['password_hash'] == hash_password(password):
        return {'id': r['id'], 'username': r['username'], 'role': r['role']}
    return None

# ----------------- CRUD Produtos / Suppliers -----------------
def add_supplier(conn, name, contact):
    c = conn.cursor()
    c.execute('INSERT INTO suppliers(name,contact) VALUES(?,?)', (name, contact))
    conn.commit()

def list_suppliers(conn):
    return pd.read_sql_query('SELECT * FROM suppliers', conn)

def add_product(conn, sku, name, category, price_retail, price_wholesale, stock, stock_min, supplier_id=None):
    c = conn.cursor()
    c.execute('''INSERT OR REPLACE INTO products(sku,name,category,price_retail,price_wholesale,stock,stock_min,supplier_id)
                 VALUES(?,?,?,?,?,?,?,?)''', (sku, name, category, price_retail, price_wholesale, stock, stock_min, supplier_id))
    conn.commit()

def list_products(conn):
    df = pd.read_sql_query('SELECT p.*, s.name as supplier FROM products p LEFT JOIN suppliers s ON p.supplier_id = s.id', conn)
    return df

def get_product(conn, product_id):
    c = conn.cursor()
    c.execute('SELECT * FROM products WHERE id=?', (product_id,))
    return c.fetchone()

def update_stock(conn, product_id, delta):
    c = conn.cursor()
    c.execute('SELECT stock FROM products WHERE id=?', (product_id,))
    r = c.fetchone()
    if r is None:
        return False
    new_stock = int(r['stock']) + int(delta)
    if new_stock < 0:
        return False
    c.execute('UPDATE products SET stock=? WHERE id=?', (new_stock, product_id))
    conn.commit()
    return True

# ----------------- Vendas / Compras / Expenses -----------------
def record_sale(conn, product_id, quantity, kind, user_id=None, sale_price=None, when=None):
    if when is None:
        when = datetime.now().isoformat()
    c = conn.cursor()
    if sale_price is None:
        c.execute('SELECT price_retail, price_wholesale FROM products WHERE id=?', (product_id,))
        r = c.fetchone()
        if r is None:
            return False, 'Produto não encontrado'
        sale_price = float(r['price_retail']) if kind == 'varejo' else float(r['price_wholesale'])

    ok = update_stock(conn, product_id, -int(quantity))
    if not ok:
        return False, 'Estoque insuficiente'

    c.execute('INSERT INTO sales(product_id,quantity,price,kind,date,user_id) VALUES(?,?,?,?,?,?)', (product_id, quantity, sale_price, kind, when, user_id))
    conn.commit()
    return True, None

def record_purchase(conn, product_id, quantity, unit_price, supplier_id=None, when=None):
    if when is None:
        when = datetime.now().isoformat()
    c = conn.cursor()
    c.execute('INSERT INTO purchases(product_id,quantity,unit_price,supplier_id,date) VALUES(?,?,?,?,?)', (product_id, quantity, unit_price, supplier_id, when))
    conn.commit()
    update_stock(conn, product_id, int(quantity))

def add_expense(conn, description, amount, when=None, category=None):
    if when is None:
        when = datetime.now().isoformat()
    c = conn.cursor()
    c.execute('INSERT INTO expenses(description,amount,date,category) VALUES(?,?,?,?)', (description, amount, when, category))
    conn.commit()

# ----------------- Consultas / Relatórios -----------------
def get_sales_df(conn, since=None, until=None):
    q = 'SELECT s.*, p.name FROM sales s LEFT JOIN products p ON p.id = s.product_id'
    df = pd.read_sql_query(q, conn)
    if df.empty:
        return df
    df['date'] = pd.to_datetime(df['date'], format='mixed', errors='coerce')

    if since is not None:
        df = df[df['date'] >= pd.to_datetime(since)]
    if until is not None:
        df = df[df['date'] <= pd.to_datetime(until)]
    return df

def get_purchases_df(conn, since=None, until=None):
    df = pd.read_sql_query('SELECT pu.*, p.name FROM purchases pu LEFT JOIN products p ON p.id = pu.product_id', conn)
    if df.empty:
        return df
    df['date'] = pd.to_datetime(df['date'], format='mixed', errors='coerce')

    if since is not None:
        df = df[df['date'] >= pd.to_datetime(since)]
    if until is not None:
        df = df[df['date'] <= pd.to_datetime(until)]
    return df

def get_expenses_df(conn, since=None, until=None):
    df = pd.read_sql_query('SELECT * FROM expenses', conn)
    if df.empty:
        return df
    df['date'] = pd.to_datetime(df['date'], format='mixed', errors='coerce')

    if since is not None:
        df = df[df['date'] >= pd.to_datetime(since)]
    if until is not None:
        df = df[df['date'] <= pd.to_datetime(until)]
    return df

def financial_summary(conn, since, until):
    sales = get_sales_df(conn, since, until)
    purchases = get_purchases_df(conn, since, until)
    expenses = get_expenses_df(conn, since, until)

    total_revenue = (sales['price'] * sales['quantity']).sum() if not sales.empty else 0.0
    total_cost_purchases = (purchases['unit_price'] * purchases['quantity']).sum() if not purchases.empty else 0.0
    total_expenses = expenses['amount'].sum() if not expenses.empty else 0.0

    net = total_revenue - total_cost_purchases - total_expenses
    return {'revenue': total_revenue, 'purchases_cost': total_cost_purchases, 'expenses': total_expenses, 'net': net, 'sales_df': sales, 'purchases_df': purchases, 'expenses_df': expenses}

# ----------------- Settings -----------------
def set_setting(conn, key, value):
    c = conn.cursor()
    c.execute('INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)', (key, str(value)))
    conn.commit()

def get_setting(conn, key, default=None):
    c = conn.cursor()
    c.execute('SELECT value FROM settings WHERE key=?', (key,))
    r = c.fetchone()
    return r[0] if r else default

# ----------------- DEMO GENERATOR -----------------
def populate_demo_db(conn, user_id):
    """Gera dados fictícios para demonstração."""
    c = conn.cursor()
    # 2. Criar Fornecedores
    suppliers_data = [
        ("Distribuidora Aliança", "contato@alianca.com.br"),
        ("Importados & Cia", "vendas@importados.com"),
        ("Fazenda Doce Mel", "produtor@docemel.com"),
        ("Tech Supplies Ltda", "suporte@tech.com")
    ]
    supplier_ids = []
    for nome, contato in suppliers_data:
        add_supplier(conn, nome, contato)
        c.execute("SELECT id FROM suppliers WHERE name=?", (nome,))
        row = c.fetchone()
        if row: supplier_ids.append(row[0])

    if not supplier_ids: return False 

    # 3. Criar Produtos
    products_data = [
        ("BEB-001", "Refrigerante Cola 2L", "Bebidas", 8.50, 6.00, 0, 50),
        ("ALI-002", "Arroz Branco 5kg", "Alimentos", 25.00, 21.50, 0, 20),
        ("LIM-003", "Detergente Neutro", "Limpeza", 2.50, 1.80, 0, 100),
        ("BEB-004", "Água Mineral 500ml", "Bebidas", 3.00, 1.50, 0, 200),
        ("ALI-005", "Feijão Carioca 1kg", "Alimentos", 8.90, 7.50, 0, 30),
        ("ELE-006", "Mouse Óptico USB", "Eletrônicos", 35.00, 22.00, 0, 10),
        ("PAP-007", "Papel A4 Resma", "Escritório", 28.00, 24.00, 0, 50)
    ]

    product_ids = []
    for sku, nome, cat, pv, pa, st_ini, st_min in products_data:
        sup_id = random.choice(supplier_ids)
        add_product(conn, sku, nome, cat, pv, pa, st_ini, st_min, sup_id)
        c.execute("SELECT id FROM products WHERE sku=?", (sku,))
        product_ids.append(c.fetchone()[0])

    # 4. Simular Compras e Vendas
    today = datetime.now()
    for pid in product_ids:
        qty = random.randint(200, 600)
        cost = random.uniform(1.0, 20.0)
        past_date = (today - timedelta(days=random.randint(25, 30))).isoformat()
        record_purchase(conn, pid, qty, cost, random.choice(supplier_ids), when=past_date)

    kinds = ['varejo', 'atacado']
    for _ in range(150): 
        pid = random.choice(product_ids)
        qty = random.randint(1, 15)
        kind = random.choice(kinds)
        days_ago = random.randint(0, 30)
        sale_date = (today - timedelta(days=days_ago)).isoformat()
        record_sale(conn, pid, qty, kind, user_id=user_id, when=sale_date)

    expenses_data = [
        ("Aluguel Galpão", 2500.00, "Fixa"),
        ("Conta de Luz", 450.00, "Variável"),
        ("Internet Fibra", 120.00, "Fixa"),
        ("Manutenção PC", 150.00, "Manutenção"),
        ("Material Limpeza", 80.00, "Consumo"),
        ("Café da Tarde", 200.00, "Consumo")
    ]
    for desc, valor, cat in expenses_data:
        days_ago = random.randint(1, 28)
        exp_date = (today - timedelta(days=days_ago)).isoformat()
        add_expense(conn, desc, valor, when=exp_date, category=cat)

    return True

# ----------------- Inicialização -----------------
conn = get_connection()
init_db(conn)

c = conn.cursor()
c.execute('SELECT COUNT(*) as cnt FROM users')
r = c.fetchone()
if r['cnt'] == 0:
    create_user(conn, 'admin', 'admin123', role='admin')

# ----------------- Autenticação -----------------
if 'user' not in st.session_state:
    st.session_state['user'] = None

if st.session_state['user'] is None:
    st.markdown("<h1 style='text-align: center; color: #4169E1;'>PeegFlow</h1>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1,2,1])
    with c2:
        with st.container(border=True):
            st.markdown("### Acesso Restrito")
            username = st.text_input('Usuário')
            password = st.text_input('Senha', type='password')
            submit_login = st.button('Entrar', type='primary', use_container_width=True)
            if submit_login:
                user = authenticate(conn, username.strip(), password)
                if user:
                    st.session_state['user'] = user
                    st.rerun()
                else:
                    st.error('Usuário ou senha inválidos')
            st.info('Usuário padrão: admin / admin123')
    st.stop()

user = st.session_state['user']

# ----------------- Layout principal (Sidebar) -----------------
# Estilização do Logo/Marca na Sidebar
st.sidebar.markdown(
    """
    <div style="text-align: center; margin-bottom: 20px;">
        <h1 style="color: #00C896 !important; font-size: 40px; margin-bottom: -10px;">P</h1>
        <h2 style="color: white !important; font-size: 24px;">PeegFlow</h2>
        <h5 style="color: #98FF98 !important; font-weight: 300;">COMERCIAL</h5>
    </div>
    """, 
    unsafe_allow_html=True
)
st.sidebar.divider()
st.sidebar.caption(f'👤 Olá, {user["username"]} ({user["role"]})')
menu = st.sidebar.radio('MENU', ['Dashboard', 'Produtos', 'Vendas', 'Compras', 'Estoque', 'Financeiro', 'Fornecedores', 'Configurações'])

# ----------------- Dashboard -----------------
if menu == 'Dashboard':
    st.title('📊 Dashboard Gerencial')
    today = date.today()
    col_d1, col_d2 = st.columns(2)
    start = col_d1.date_input('Data inicial', value=today.replace(day=1), key='db_start')
    end = col_d2.date_input('Data final', value=today, key='db_end')

    if start > end:
        st.error('Data inicial não pode ser maior que a final')
    else:
        summary = financial_summary(conn, pd.to_datetime(start), pd.to_datetime(end) + pd.Timedelta(days=1))

        # Cards de Métricas
        c1, c2, c3, c4 = st.columns(4)
        c1.metric('Receita Bruta', f'R$ {summary["revenue"]:.2f}')
        c2.metric('Custo (Produtos)', f'R$ {summary["purchases_cost"]:.2f}')
        c3.metric('Despesas Op.', f'R$ {summary["expenses"]:.2f}')

        lucro = summary["net"]
        c4.metric('Lucro Estimado', f'R$ {lucro:.2f}', delta_color="normal" if lucro >= 0 else "inverse")

        st.markdown('---')

        # Gráficos
        sales = summary['sales_df']
        if not sales.empty:
            sales['day'] = sales['date'].dt.date
            daily = sales.groupby('day').apply(lambda x: (x['price'] * x['quantity']).sum()).reset_index(name='revenue')

            st.subheader('📈 Evolução de Vendas')
            # Gráfico com as cores da marca
            chart = alt.Chart(daily).mark_area(
                line={'color':'#4169E1'}, # Azul Royal na linha
                color=alt.Gradient(
                    gradient='linear',
                    stops=[alt.GradientStop(color='#4169E1', offset=0),
                           alt.GradientStop(color='#00C896', offset=1)], # Verde Menta no gradiente
                    x1=1, x2=1, y1=1, y2=0
                )
            ).encode(
                x=alt.X('day:T', title='Data'),
                y=alt.Y('revenue:Q', title='Receita (R$)'),
                tooltip=['day', 'revenue']
            ).properties(height=300)

            st.altair_chart(chart, use_container_width=True)

            col_g1, col_g2 = st.columns(2)

            if 'category' in list_products(conn).columns:
                 merged = sales.copy()
                 pie_data = merged.groupby('name')['quantity'].sum().reset_index()
                 with col_g1:
                     st.subheader('Top Produtos (Qtd)')
                     st.dataframe(pie_data.sort_values('quantity', ascending=False).head(5), hide_index=True, use_container_width=True)

            with col_g2:
                st.subheader('Últimas Vendas')
                st.dataframe(sales.sort_values('date', ascending=False).head(5)[['date', 'name', 'quantity', 'price']], hide_index=True, use_container_width=True)
        else:
            st.info("Sem dados de vendas neste período.")

# ----------------- Produtos -----------------
elif menu == 'Produtos':
    st.title('📦 Produtos')
    with st.expander('Cadastrar novo produto'):
        suppliers = list_suppliers(conn)
        supplier_options = [None] + list(suppliers['id'].astype(str)) if not suppliers.empty else [None]
        with st.form('add_product'):
            c1, c2 = st.columns(2)
            sku = c1.text_input('SKU (Código)')
            name = c2.text_input('Nome')
            category = st.text_input('Categoria')

            c3, c4 = st.columns(2)
            price_retail = c3.number_input('Preço Varejo', min_value=0.0, format='%.2f')
            price_wholesale = c4.number_input('Preço Atacado', min_value=0.0, format='%.2f')

            c5, c6 = st.columns(2)
            stock = c5.number_input('Estoque Inicial', min_value=0, step=1, value=0)
            stock_min = c6.number_input('Estoque Mínimo (Alerta)', min_value=0, step=1, value=0)

            supplier_sel = st.selectbox('Fornecedor (ID)', supplier_options)
            submit = st.form_submit_button('Salvar produto')

            if submit:
                supplier_id = int(supplier_sel) if supplier_sel not in (None, 'None') else None
                add_product(conn, sku.strip(), name.strip(), category.strip(), float(price_retail), float(price_wholesale), int(stock), int(stock_min), supplier_id)
    
    st.markdown('---')
    dfp = list_products(conn)
    st.dataframe(dfp, use_container_width=True)
    if not dfp.empty:
        st.download_button('Exportar CSV', dfp.to_csv(index=False), file_name='produtos.csv')

# ----------------- Vendas -----------------
elif menu == 'Vendas':
    st.title('🛒 PDV - Registrar Venda')
    dfp = list_products(conn)

    if dfp.empty:
        st.warning('Nenhum produto cadastrado.')
    else:
        dfp['label'] = dfp['name'] + ' | Estoque: ' + dfp['stock'].astype(str)

        with st.container(border=True):
            with st.form('sale'):
                prod = st.selectbox('Selecione o Produto', dfp['label'])
                # obter id
                product_row = dfp[dfp['label'] == prod].iloc[0]
                product_id = int(product_row['id'])

                c1, c2 = st.columns(2)
                kind = c1.radio('Tipo de Venda', ['varejo', 'atacado'], horizontal=True)
                qty = c2.number_input('Quantidade', min_value=1, step=1, value=1)

                with st.expander('Opções Avançadas'):
                    manual_price = st.checkbox('Sobrescrever preço?')
                    sale_price = st.number_input('Novo Preço Unitário', min_value=0.0, format='%.2f') if manual_price else None

                submit_sale = st.form_submit_button('✅ Finalizar Venda', type='primary')

                if submit_sale:
                    ok, err = record_sale(conn, product_id, int(qty), kind, user_id=user['id'], sale_price=float(sale_price) if sale_price is not None else None)
                    if ok:
                        st.success(f'Venda de {qty}x {product_row["name"]} registrada!')
                    else:
                        st.error(f'Erro: {err}')

    st.markdown('### Histórico Recente')
    sales = get_sales_df(conn)
    if not sales.empty:
        st.dataframe(sales.sort_values('date', ascending=False).head(50), use_container_width=True)

# ----------------- Compras -----------------
elif menu == 'Compras':
    st.title('📥 Entrada de Estoque')
    dfp = list_products(conn)
    suppliers = list_suppliers(conn)

    if dfp.empty:
        st.warning('Cadastre produtos antes de dar entrada.')
    else:
        dfp['label'] = dfp['name'] + ' (SKU: ' + dfp['sku'].astype(str) + ')'
        with st.form('purchase'):
            prod = st.selectbox('Produto', dfp['label'])
            product_row = dfp[dfp['label'] == prod].iloc[0]
            product_id = int(product_row['id'])

            c1, c2, c3 = st.columns(3)
            qty = c1.number_input('Quantidade', min_value=1, step=1, value=1)
            unit_price = c2.number_input('Custo Unitário', min_value=0.0, format='%.2f')

            supplier_opts = [None] + list(suppliers['id'].astype(str)) if not suppliers.empty else [None]
            supplier_sel = c3.selectbox('Fornecedor', supplier_opts)

            submit_p = st.form_submit_button('Registrar Entrada')
            if submit_p:
                supplier_id = int(supplier_sel) if supplier_sel not in (None, 'None') else None
                record_purchase(conn, product_id, int(qty), float(unit_price), supplier_id)
                st.success('Estoque atualizado com sucesso!')

    st.markdown('### Histórico de Compras')
    purchases = get_purchases_df(conn)
    if not purchases.empty:
        st.dataframe(purchases.sort_values('date', ascending=False).head(50), use_container_width=True)

# ----------------- Estoque -----------------
elif menu == 'Estoque':
    st.title('📋 Gestão de Estoque')
    dfp = list_products(conn)

    if dfp.empty:
        st.info('Sem dados.')
    else:
        tab1, tab2 = st.tabs(["Ajuste Rápido", "Alertas de Reposição"])

        with tab1:
            st.write("Use para correções de inventário (perdas, doações, erros).")
            dfp['label'] = dfp['name'] + ' | Atual: ' + dfp['stock'].astype(str)

            c1, c2, c3 = st.columns([2, 1, 1])
            prod = c1.selectbox('Produto para Ajuste', dfp['label'])
            row = dfp[dfp['label'] == prod].iloc[0]
            pid = int(row['id'])

            delta = c2.number_input('Qtd Ajuste (+/-)', value=0, step=1, help="Negativo para retirar, Positivo para adicionar")

            if c3.button('Aplicar Ajuste'):
                ok = update_stock(conn, pid, int(delta))
                if ok:
                    st.success('Ajustado!')
                    st.rerun()
                else:
                    st.error('Falha. Verifique se o estoque ficaria negativo.')

        with tab2:
            st.subheader('Produtos abaixo do Mínimo')
            low = dfp[dfp['stock'] <= dfp['stock_min']]
            if low.empty:
                st.success("Tudo certo! Nenhum produto com estoque crítico.")
            else:
                st.dataframe(low, use_container_width=True)
                st.download_button('Baixar Lista de Compra', low.to_csv(index=False), 'lista_compra.csv')

# ----------------- Financeiro -----------------
elif menu == 'Financeiro':
    st.title('💲 Controle Financeiro')

    with st.expander("Nova Despesa / Saída", expanded=False):
        with st.form('expense'):
            c1, c2 = st.columns(2)
            desc = c1.text_input('Descrição')
            cat = c2.text_input('Categoria (ex: Luz, Aluguel)')

            c3, c4 = st.columns(2)
            amount = c3.number_input('Valor (R$)', min_value=0.0, format='%.2f')
            when = c4.date_input('Data', value=date.today())

            if st.form_submit_button('Lançar Despesa'):
                add_expense(conn, desc, float(amount), when.isoformat(), cat)
                st.success('Salvo!')

    st.divider()

    col_p1, col_p2 = st.columns([1, 3])
    with col_p1:
        st.subheader('Metas')
        current_target = float(get_setting(conn, 'target_profit') or 0.0)
        target = st.number_input('Meta de Lucro Mensal', value=current_target, step=100.0)
        if st.button('Atualizar Meta'):
            set_setting(conn, 'target_profit', target)
            st.toast('Meta atualizada')

    with col_p2:
        st.subheader('Relatório Detalhado')
        start = st.date_input('Início', value=date.today().replace(day=1), key='f_start')
        end = st.date_input('Fim', value=date.today(), key='f_end')

        summary = financial_summary(conn, pd.to_datetime(start), pd.to_datetime(end) + pd.Timedelta(days=1))

        t1, t2 = st.tabs(['Vendas', 'Despesas'])
        t1.dataframe(summary['sales_df'], use_container_width=True)
        t2.dataframe(summary['expenses_df'], use_container_width=True)

# ----------------- Fornecedores -----------------
elif menu == 'Fornecedores':
    st.title('🤝 Base de Fornecedores')
    with st.form('add_supplier'):
        c1, c2 = st.columns(2)
        sname = c1.text_input('Nome Empresa')
        scontact = c2.text_input('Email / Telefone')
        if st.form_submit_button('Cadastrar'):
            add_supplier(conn, sname, scontact)
            st.success('Cadastrado!')
            st.rerun()

    st.dataframe(list_suppliers(conn), use_container_width=True)

# ----------------- Configurações -----------------
elif menu == 'Configurações':
    st.title('⚙️ Configurações do Sistema')

    st.subheader('🔐 Gerenciar Usuários')
    if user['role'] == 'admin':
        with st.form('create_user'):
            c1, c2, c3 = st.columns(3)
            uname = c1.text_input('Novo Usuário')
            pwd = c2.text_input('Senha', type='password')
            role = c3.selectbox('Permissão', ['user', 'admin'])
            if st.form_submit_button('Criar Usuário'):
                ok = create_user(conn, uname.strip(), pwd.strip(), role)
                if ok: st.success('Criado!')
                else: st.error('Erro: Usuário já existe.')
    else:
        st.info('Contate o administrador para adicionar usuários.')

    st.markdown('---')

    st.subheader('⚡ Modo Demonstração (Demo)')
    st.info("Use esta opção para preencher o sistema com dados fictícios e testar os gráficos.")

    col_demo1, col_demo2 = st.columns([1, 2])
    with col_demo1:
        if st.button('✨ Gerar Dados de Demo', type='primary'):
            with st.spinner('Criando produtos, vendas e despesas fictícias...'):
                try:
                    populate_demo_db(conn, user['id'])
                    st.success('Dados gerados! Vá ao Dashboard ver o resultado.')
                    st.balloons()
                except Exception as e:
                    st.error(f"Erro: {e}")

    st.markdown('---')
    st.subheader('⚠️ Zona de Perigo')
    if st.button('🗑️ Resetar Banco de Dados Completo'):
        conn.close()
        import os
        if os.path.exists(DB_PATH):
            os.remove(DB_PATH)
        st.warning('Banco deletado. Por favor, recarregue a página (F5).')

# Rodapé lateral estilizado
st.sidebar.markdown('---')
st.sidebar.markdown(
    """
    <div style="text-align: center; color: gray; font-size: 0.8em;">
        PeegFlow System v2.1