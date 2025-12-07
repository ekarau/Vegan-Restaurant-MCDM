from flask import Flask, request, redirect, render_template, session, url_for
import sqlite3
import numpy as np
from decimal import Decimal, getcontext
getcontext().prec = 20

app = Flask(__name__)
app.secret_key = 'secret-key'
DATABASE = 'if_aroman_final.db'

T2NN_TABLE = {
    "Very Poor": [(0.2, 0.2, 0.1), (0.65, 0.8, 0.85), (0.45, 0.8, 0.7)],
    "Poor": [(0.35, 0.35, 0.1), (0.5, 0.75, 0.8), (0.5, 0.75, 0.65)],
    "Medium Poor": [(0.4, 0.3, 0.35), (0.5, 0.45, 0.6), (0.45, 0.4, 0.6)],
    "Medium": [(0.5, 0.45, 0.5), (0.4, 0.35, 0.5), (0.35, 0.3, 0.45)],
    "Medium Good": [(0.6, 0.45, 0.5), (0.2, 0.15, 0.25), (0.1, 0.25, 0.15)],
    "Good": [(0.7, 0.75, 0.8), (0.15, 0.2, 0.25), (0.1, 0.15, 0.2)],
    "Very Good": [(0.95, 0.9, 0.95), (0.1, 0.1, 0.05), (0.05, 0.05, 0.05)]
}

FUZZY_SCALE = {
    "Very Important": (0.88, 0.08, 0.04),
    "Important": (0.75, 0.20, 0.05),
    "Medium": (0.50, 0.45, 0.05),
    "Unimportant": (0.35, 0.60, 0.05),
    "Very Unimportant": (0.08, 0.88, 0.04)
}


def init_db():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        experience_years INTEGER,
        experience_label TEXT,
        expertise_label TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS criterion_weights (
        user_id INTEGER,
        criterion TEXT,
        fuzzy_label TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS alternative_evaluations (
        user_id INTEGER,
        alternative TEXT,
        criterion TEXT,
        fuzzy_label TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS criteria (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        type TEXT DEFAULT 'Benefit'
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS alternatives (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT
    )''')
    conn.commit()
    conn.close()

@app.route('/')
def index():
    return render_template("index.html")

@app.route('/evaluate', methods=['GET', 'POST'])
def evaluate():
    if request.method == 'POST':
        name = request.form['name']
        experience_years = int(request.form['experience'])
        expertise_label = request.form['expertise']

        def map_experience_to_level(years):
            if years < 5: return "Very Poor"
            elif years < 10: return "Poor"
            elif years < 15: return "Medium Poor"
            elif years < 20: return "Medium"
            elif years < 25: return "Good"
            elif years < 30: return "Medium"
            else: return "Very Good"

        experience_label = map_experience_to_level(experience_years)

        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()
        c.execute("INSERT INTO users (name, experience_years, experience_label, expertise_label) VALUES (?, ?, ?, ?)",
                  (name, experience_years, experience_label, expertise_label))
        user_id = c.lastrowid
        session['last_user_id'] = user_id

        c.execute("SELECT name FROM criteria")
        criteria = [row[0] for row in c.fetchall()]

        for crit in criteria:
            label = request.form.get(crit, "Medium")  # Eksikse varsayılan "Medium"
            c.execute("INSERT INTO criterion_weights (user_id, criterion, fuzzy_label) VALUES (?, ?, ?)",
                      (user_id, crit, label))

        c.execute("SELECT name FROM alternatives")
        alternatives = [row[0] for row in c.fetchall()]

        for alt in alternatives:
            for crit in criteria:
                key = f"{alt}_{crit}"
                label = request.form.get(key, "Medium")
                c.execute("INSERT INTO alternative_evaluations (user_id, alternative, criterion, fuzzy_label) VALUES (?, ?, ?, ?)",
                          (user_id, alt, crit, label))

        conn.commit()
        conn.close()
        return redirect('/result')

    # GET method: dinamik olarak formu hazırla
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("SELECT name FROM criteria")
    criteria = [row[0] for row in c.fetchall()]
    c.execute("SELECT name FROM alternatives")
    alternatives = [row[0] for row in c.fetchall()]
    conn.close()

    return render_template("evaluate.html",
                           criteria=criteria,
                           alternatives=alternatives,
                           t2nn_options=T2NN_TABLE.keys(),
                           fuzzy_labels=FUZZY_SCALE.keys())

@app.route('/delete_user/<int:user_id>')
def delete_user(user_id):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("DELETE FROM users WHERE id=?", (user_id,))
    c.execute("DELETE FROM criterion_weights WHERE user_id=?", (user_id,))
    c.execute("DELETE FROM alternative_evaluations WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()
    return redirect('/admin')

@app.route('/update_user_info/<int:user_id>', methods=['POST'])
def update_user_info(user_id):
    new_exp = request.form['experience_label']
    new_exp_lvl = request.form['expertise_label']

    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("UPDATE users SET experience_label = ?, expertise_label = ? WHERE id = ?",
              (new_exp, new_exp_lvl, user_id))
    conn.commit()
    conn.close()
    return redirect(url_for('view_user', user_id=user_id))


@app.route('/admin-login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username == 'admin' and password == '1234':
            session['admin_logged_in'] = True
            return redirect('/admin')
        else:
            return "Incorrect credentials", 401
    return render_template('admin_login.html')

@app.route('/view-user/<int:user_id>')
def view_user(user_id):
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # Kullanıcı bilgisi
    c.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = c.fetchone()

    # Kriter ağırlıkları
    c.execute("SELECT criterion, fuzzy_label FROM criterion_weights WHERE user_id = ?", (user_id,))
    weights = c.fetchall()

    # Alternatif değerlendirmeleri
    c.execute("SELECT alternative, criterion, fuzzy_label FROM alternative_evaluations WHERE user_id = ?", (user_id,))
    evals = c.fetchall()

    # Alternatif isimleri
    c.execute("SELECT name FROM alternatives")
    alternatives = [row[0] for row in c.fetchall()]

    # Kriter isimleri
    c.execute("SELECT name FROM criteria")
    criteria = [row[0] for row in c.fetchall()]

    conn.close()

    return render_template(
        "view_user.html",
        user=user,
        weights=weights,
        evals=evals,
        alternatives=alternatives,
        criteria=criteria,
        fuzzy_labels=FUZZY_SCALE.keys(),
        t2nn_labels=T2NN_TABLE.keys()
    )

@app.route('/tables')
def view_tables():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()

    c.execute("SELECT name FROM criteria")
    CRITERIA = [row[0] for row in c.fetchall()]
    c.execute("SELECT name FROM alternatives")
    ALTERNATIVES = [row[0] for row in c.fetchall()]
    c.execute("SELECT id, experience_label, expertise_label FROM users")
    users = c.fetchall()

    deltas = []
    criteria_data = []
    alt_data = {alt: [] for alt in ALTERNATIVES}

    for user_id, exp_label, exp_lvl_label in users:
        T, I, F = aggregate_T2NN(T2NN_TABLE[exp_label], T2NN_TABLE[exp_lvl_label])
        delta = score_T2NN(T, I, F)
        deltas.append(delta)

        c.execute("SELECT criterion, fuzzy_label FROM criterion_weights WHERE user_id = ?", (user_id,))
        crit_row_dict = {crit: label for crit, label in c.fetchall()}
        row_vec = [FUZZY_SCALE.get(crit_row_dict.get(k, 'Medium'), FUZZY_SCALE['Medium']) for k in CRITERIA]
        criteria_data.append(row_vec)

        c.execute("SELECT alternative, criterion, fuzzy_label FROM alternative_evaluations WHERE user_id = ?", (user_id,))
        user_alt_data_dict = {(a, k): l for a, k, l in c.fetchall()}
        for alt in ALTERNATIVES:
            alt_vec = [FUZZY_SCALE.get(user_alt_data_dict.get((alt, k), 'Medium'), FUZZY_SCALE['Medium']) for k in CRITERIA]
            alt_data[alt].append(alt_vec)

    conn.close()

    deltas = np.array(deltas)
    deltas_norm = deltas / np.sum(deltas)

    fuzzy_matrix = np.array(criteria_data)
    agg_fuzzy = aggregate_ifwa(fuzzy_matrix, deltas_norm)
    delta_pos = np.linalg.norm(agg_fuzzy - [1.0, 0.0, 0.0], axis=1)
    delta_neg = np.linalg.norm(agg_fuzzy - [0.0, 1.0, 0.0], axis=1)
    cc = delta_neg / (delta_pos + delta_neg)
    weights = cc / np.sum(cc)

    Xij = np.zeros((len(ALTERNATIVES), len(CRITERIA)))
    all_agg_alt = []

    for i, alt in enumerate(ALTERNATIVES):
        fuzzy_matrix = np.array(alt_data[alt])
        agg = aggregate_ifwa(fuzzy_matrix, deltas_norm)
        all_agg_alt.append(agg)
        scores = np.array([score_if(*triple) for triple in agg])
        Xij[i] = scores

    K1 = normalize_linear(Xij)
    K2 = normalize_vector(Xij)
    Pij = aggregate_normalization(K1, K2)
    Sij = np.zeros((len(ALTERNATIVES), len(CRITERIA)))
    for i, alt in enumerate(ALTERNATIVES):
        fuzzy_matrix = np.array(alt_data[alt])
        agg = aggregate_ifwa(fuzzy_matrix, deltas_norm)
        scores = np.array([score_if(*triple) for triple in agg])
        Sij[i] = scores
    Zij = calculate_Zij(Pij, weights)
    # Kriter türlerini al (Benefit/Cost)
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("SELECT name, type FROM criteria")
    crit_types = dict(c.fetchall())
    conn.close()

    # Cost ve Benefit kriterlerinin indeksleri
    cost_idx = [i for i, crit in enumerate(CRITERIA) if crit_types[crit] == "Cost"]
    benefit_idx = [i for i, crit in enumerate(CRITERIA) if crit_types[crit] == "Benefit"]

    # Eq. 23-24: L_i ve A_i hesapla
    Li = Zij[:, cost_idx].sum(axis=1) if cost_idx else np.zeros(len(ALTERNATIVES))
    Ai = Zij[:, benefit_idx].sum(axis=1) if benefit_idx else np.zeros(len(ALTERNATIVES))

    # Eq. 25: Ri = L^λ + A^(1-λ)
    λ = len(cost_idx) / len(CRITERIA)
    Ri = np.zeros(len(Li))
    for i in range(len(Li)):
        if Li[i] == 0:
            Ri[i] = Ai[i] ** (1 - λ)
        elif Ai[i] == 0:
            Ri[i] = Li[i] ** λ
        else:
            Ri[i] = (Li[i] ** λ) + (Ai[i] ** (1 - λ))

    tables = [
        {"title": "Eq. 11: Normalized Delta Weights", "headers": ["Δ"], "rows": [[v] for v in deltas_norm]},
        {"title": "Eq. 12: Aggregated Fuzzy Criteria", "headers": ["μ", "θ", "π"], "rows": agg_fuzzy.tolist()},
        {"title": "Eq. 13: Δ+ (Ideal Distances)", "headers": ["Δ+"], "rows": [[v] for v in delta_pos]},
        {"title": "Eq. 14: Δ- (Anti-Ideal Distances)", "headers": ["Δ-"], "rows": [[v] for v in delta_neg]},
        {"title": "Eq. 15: Closeness Coefficients", "headers": ["CC"], "rows": [[v] for v in cc]},
        {"title": "Eq. 16: Normalized Criteria Weights", "headers": ["w"], "rows": [[v] for v in weights]},
        {"title": "Eq. 17 & 18: Raw Score Matrix (Sij)", "headers": CRITERIA, "rows": Sij.tolist()},
        {"title": "Eq. 19: Linear Normalized Xij", "headers": CRITERIA, "rows": K1.tolist()},
        {"title": "Eq. 20: Vector Normalized Xij", "headers": CRITERIA, "rows": K2.tolist()},
        {"title": "Eq. 21: Aggregated Pij", "headers": CRITERIA, "rows": Pij.tolist()},
        {"title": "Eq. 22: Final Scores (Zij)", "headers": CRITERIA, "rows": Zij.tolist()},
        {"title": "Final Ranking Ri", "headers": ["Ri"], "rows": [[v] for v in Ri]}
    ]

    return render_template("tables.html", tables=tables)

@app.route('/admin')
def admin_panel():
    if not session.get('admin_logged_in'):
        return redirect('/admin-login')
    
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute("SELECT * FROM criteria")
    criteria = c.fetchall()

    c.execute("SELECT * FROM alternatives")
    alternatives = c.fetchall()


    c.execute("SELECT * FROM users")
    users = c.fetchall()

    c.execute("SELECT * FROM criterion_weights")
    weights = c.fetchall()

    c.execute("SELECT * FROM alternative_evaluations")
    evals = c.fetchall()

    conn.close()
    return render_template("admin.html", users=users, weights=weights, evals=evals, criteria=criteria, alternatives=alternatives)


@app.route('/admin-add', methods=['POST'])
def admin_add():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()

    # Kriter ekle
    if 'new_criterion' in request.form and request.form['new_criterion']:
        name = request.form['new_criterion']
        crit_type = request.form.get('criterion_type', 'Benefit')
        c.execute("INSERT INTO criteria (name, type) VALUES (?, ?)", (name, crit_type))

    # Alternatif ekle
    if 'new_alternative' in request.form and request.form['new_alternative']:
        alt = request.form['new_alternative']
        c.execute("INSERT INTO alternatives (name) VALUES (?)", (alt,))

    conn.commit()
    conn.close()
    return redirect('/admin')

@app.route('/delete_criterion/<int:criterion_id>', methods=['POST'])
def delete_criterion(criterion_id):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("DELETE FROM criteria WHERE id = ?", (criterion_id,))
    conn.commit()
    conn.close()
    return redirect('/admin')

@app.route('/delete_alternative/<int:alt_id>', methods=['POST'])
def delete_alternative(alt_id):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("DELETE FROM alternatives WHERE id = ?", (alt_id,))
    conn.commit()
    conn.close()
    return redirect('/admin')

@app.route('/update_criterion_type/<int:criterion_id>', methods=['POST'])
def update_criterion_type(criterion_id):
    new_type = request.form['criterion_type']
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("UPDATE criteria SET type = ? WHERE id = ?", (new_type, criterion_id))
    conn.commit()
    conn.close()
    return redirect('/admin')


def aggregate_T2NN(exp_vals, exp_lvl_vals, xi1=0.5, xi2=0.5):
    xi1 = Decimal(str(xi1))
    xi2 = Decimal(str(xi2))

    def geo_agg(T_exp, T_lvl):
        return float(1 - (1 - Decimal(str(T_exp)))**xi1 * (1 - Decimal(str(T_lvl)))**xi2)

    def mult_agg(V_exp, V_lvl):
        exp_power = Decimal(str(V_exp)) ** xi1
        lvl_power = Decimal(str(V_lvl)) ** xi2
        result = float(exp_power * lvl_power)
        return result

    T_agg = []
    I_agg = []
    F_agg = []
    T_agg.append(geo_agg(exp_vals[0][0], exp_lvl_vals[0][0]))
    T_agg.append(mult_agg(exp_vals[0][1], exp_lvl_vals[0][1]))
    T_agg.append(mult_agg(exp_vals[0][2], exp_lvl_vals[0][2]))
    I_agg.append(geo_agg(exp_vals[1][0], exp_lvl_vals[1][0]))
    I_agg.append(mult_agg(exp_vals[1][1], exp_lvl_vals[1][1]))
    I_agg.append(mult_agg(exp_vals[1][2], exp_lvl_vals[1][2]))
    F_agg.append(geo_agg(exp_vals[2][0], exp_lvl_vals[2][0]))
    F_agg.append(mult_agg(exp_vals[2][1], exp_lvl_vals[2][1]))
    F_agg.append(mult_agg(exp_vals[2][2], exp_lvl_vals[2][2]))

    return T_agg, I_agg, F_agg

def seed_initial_data():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()

    # İlk kriterler
    if not c.execute("SELECT * FROM criteria").fetchone():
        criteria = ['Hygiene', 'MenuVariety', 'Location', 'InteriorDesign',
                    'StaffFriendliness', 'PriceAffordability', 'Sustainability',
                    'CustomerReview', 'ServiceSpeed', 'FullyVeganMenu']
        for crit in criteria:
            crit_type = 'Cost' if crit == 'PriceAffordability' else 'Benefit'
            c.execute("INSERT INTO criteria (name, type) VALUES (?, ?)", (crit, crit_type))

    # İlk alternatifler
    if not c.execute("SELECT * FROM alternatives").fetchone():
        alternatives = ['VegZone', 'GreenDelight', 'Plantopia']
        for alt in alternatives:
            c.execute("INSERT INTO alternatives (name) VALUES (?)", (alt,))

    conn.commit()
    conn.close()


def score_T2NN(T = [], I = [], F = []):
    return (1/12)*(8 + (T[0]+2*T[1]+T[2]) - (I[0]+2*I[1]+I[2]) - (F[0]+2*F[1]+F[2]))

def aggregate_ifwa(fuzzy_matrix, weights):
    fuzzy_matrix = np.array(fuzzy_matrix)
    w = np.array(weights).reshape(-1, 1)
    mu = fuzzy_matrix[:, :, 0]
    theta = fuzzy_matrix[:, :, 1]
    pi = fuzzy_matrix[:, :, 2]
    mu_agg = 1 - np.prod((1 - mu) ** w, axis=0)
    theta_agg = np.prod(theta ** w, axis=0)
    pi_agg = 1 - mu_agg - theta_agg
    return np.vstack([mu_agg, theta_agg, pi_agg]).T

def score_if(mu, theta, pi):
    return (3 + mu - 2 * theta - pi) / 4 #denklem 18

def normalize_linear(X):
    norm = np.zeros_like(X, dtype=float)
    for j in range(X.shape[1]):
        col = [Decimal(str(x)) for x in X[:, j]]
        min_val = min(col)
        max_val = max(col)
        denom = max_val - min_val if max_val != min_val else Decimal("1")
        for i in range(len(col)):
            norm[i][j] = float((col[i] - min_val) / denom)
    return norm

def normalize_vector(X):
    norm = np.sqrt(np.sum(X**2, axis=0))
    return X / norm

def aggregate_normalization(K1, K2, beta=0.5):
    return (beta * K1 + (1 - beta) * K2) / 2

def calculate_Zij(Pij, weights):
    return Pij * weights

@app.route('/result')
def result():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()

    # Dinamik kriter ve alternatifleri al
    c.execute("SELECT name FROM criteria")
    CRITERIA = [row[0] for row in c.fetchall()]
    c.execute("SELECT name FROM alternatives")
    ALTERNATIVES = [row[0] for row in c.fetchall()]

    c.execute("SELECT id, experience_label, expertise_label FROM users")
    users = c.fetchall()

    deltas = []
    criteria_data = []
    alt_data = {alt: [] for alt in ALTERNATIVES}

    for user_id, exp_label, exp_lvl_label in users:
        T, I, F = aggregate_T2NN(T2NN_TABLE[exp_label], T2NN_TABLE[exp_lvl_label])
        delta = score_T2NN(T, I, F)
        deltas.append(delta)

        c.execute("SELECT criterion, fuzzy_label FROM criterion_weights WHERE user_id = ?", (user_id,))
        crit_row_dict = {crit: label for crit, label in c.fetchall()}
        row_vec = [FUZZY_SCALE.get(crit_row_dict.get(k, 'Medium'), FUZZY_SCALE['Medium']) for k in CRITERIA]
        criteria_data.append(row_vec)

        c.execute("SELECT alternative, criterion, fuzzy_label FROM alternative_evaluations WHERE user_id = ?", (user_id,))
        user_alt_data_dict = {(a, k): l for a, k, l in c.fetchall()}

        for alt in ALTERNATIVES:
            alt_vec = [FUZZY_SCALE.get(user_alt_data_dict.get((alt, k), 'Medium'), FUZZY_SCALE['Medium']) for k in CRITERIA]
            alt_data[alt].append(alt_vec)

    conn.close()

    deltas = np.array(deltas)
    deltas = deltas / np.sum(deltas) # Eq. 11

    fuzzy_matrix = np.array(criteria_data)  # All user inputs for criteria
    agg_fuzzy = aggregate_ifwa(fuzzy_matrix, deltas) # Eq. 12

    ideal = np.array([1.0, 0.0, 0.0])
    anti_ideal = np.array([0.0, 1.0, 0.0])
    delta_pos = np.linalg.norm(agg_fuzzy - ideal, axis=1) # Eq. 13
    delta_neg = np.linalg.norm(agg_fuzzy - anti_ideal, axis=1) # Eq. 14
    cc = delta_neg / (delta_pos + delta_neg) # Eq. 15
    weights = cc / np.sum(cc) # Eq. 16

    Xij = np.zeros((len(ALTERNATIVES), len(CRITERIA)))
    for i, alt in enumerate(ALTERNATIVES):
        fuzzy_matrix = np.array(alt_data[alt])
        agg = aggregate_ifwa(fuzzy_matrix, deltas)
        scores = np.array([score_if(*triple) for triple in agg])
        Xij[i] = scores

    K1 = normalize_linear(Xij) # Eq. 19
    K2 = normalize_vector(Xij) # Eq. 20
    Pij = aggregate_normalization(K1, K2) # Eq. 21
    Zij = calculate_Zij(Pij, weights) # Eq. 22
    # Kriter türlerini al (Benefit/Cost)
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("SELECT name, type FROM criteria")
    crit_types = dict(c.fetchall())
    conn.close()

    # Cost ve Benefit kriterlerinin indeksleri
    cost_idx = [i for i, crit in enumerate(CRITERIA) if crit_types[crit] == "Cost"]
    benefit_idx = [i for i, crit in enumerate(CRITERIA) if crit_types[crit] == "Benefit"]

    # Eq. 23-24: L_i ve A_i hesapla
    Li = Zij[:, cost_idx].sum(axis=1) if cost_idx else np.zeros(len(ALTERNATIVES))
    Ai = Zij[:, benefit_idx].sum(axis=1) if benefit_idx else np.zeros(len(ALTERNATIVES))

    # Eq. 25: Ri = L^λ + A^(1-λ)
    λ = len(cost_idx) / len(CRITERIA)
    Ri = np.zeros(len(Li))
    for i in range(len(Li)):
        if Li[i] == 0:
            Ri[i] = Ai[i] ** (1 - λ)
        elif Ai[i] == 0:
            Ri[i] = Li[i] ** λ
        else:
            Ri[i] = (Li[i] ** λ) + (Ai[i] ** (1 - λ))

    result_html = ""
    result_html += f"<h2>Best Alternative: {ALTERNATIVES[np.argmax(Ri)]}</h2><ul>"
    for i, alt in enumerate(ALTERNATIVES):
        result_html += f"<li>{alt}: {Ri[i]:.4f}</li>"
    result_html += "</ul>"

    scores = list(zip(ALTERNATIVES, Ri))
    best_alt = ALTERNATIVES[np.argmax(Ri)]
    return render_template("result.html", scores=scores, best_alt=best_alt)


@app.route('/validate')
def validate():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()

    # Dinamik kriter ve alternatifleri al
    c.execute("SELECT name FROM criteria")
    CRITERIA = [row[0] for row in c.fetchall()]
    c.execute("SELECT name FROM alternatives")
    ALTERNATIVES = [row[0] for row in c.fetchall()]

    c.execute("SELECT id, experience_label, expertise_label FROM users")
    users = c.fetchall()

    deltas = []
    criteria_data = []
    alt_data = {alt: [] for alt in ALTERNATIVES}

    for user_id, exp_label, exp_lvl_label in users:
        T, I, F = aggregate_T2NN(T2NN_TABLE[exp_label], T2NN_TABLE[exp_lvl_label])
        delta = score_T2NN(T, I, F)
        deltas.append(delta)

        c.execute("SELECT criterion, fuzzy_label FROM criterion_weights WHERE user_id = ?", (user_id,))
        crit_row_dict = {crit: label for crit, label in c.fetchall()}
        row_vec = [FUZZY_SCALE.get(crit_row_dict.get(k, 'Medium'), FUZZY_SCALE['Medium']) for k in CRITERIA]
        criteria_data.append(row_vec)

        c.execute("SELECT alternative, criterion, fuzzy_label FROM alternative_evaluations WHERE user_id = ?", (user_id,))
        user_alt_data_dict = {(a, k): l for a, k, l in c.fetchall()}
        for alt in ALTERNATIVES:
            alt_vec = [FUZZY_SCALE.get(user_alt_data_dict.get((alt, k), 'Medium'), FUZZY_SCALE['Medium']) for k in CRITERIA]
            alt_data[alt].append(alt_vec)

    conn.close()
    deltas = np.array(deltas)
    deltas = deltas / np.sum(deltas)

    validation_table = "<h2>Validation Test (SAS: Criterion Deletion Analysis)</h2>"
    validation_table += "<table border='1' cellpadding='5'><tr><th>SAS #</th><th>Deleted Criteria</th>"

    for alt in ALTERNATIVES:
        validation_table += f"<th>{alt}</th>"
    validation_table += "<th>Best Alternative</th></tr>"

    for idx, crit_to_remove in enumerate(CRITERIA):
        idxs = [i for i, c in enumerate(CRITERIA) if c != crit_to_remove]
        reduced_criteria = [CRITERIA[i] for i in idxs]

        fuzzy_matrix = np.array(criteria_data)
        reduced_fuzzy = fuzzy_matrix[:, idxs, :]
        agg_fuzzy = aggregate_ifwa(reduced_fuzzy, deltas)
        ideal = np.array([1.0, 0.0, 0.0])
        anti_ideal = np.array([0.0, 1.0, 0.0])
        delta_pos = np.linalg.norm(agg_fuzzy - ideal, axis=1)
        delta_neg = np.linalg.norm(agg_fuzzy - anti_ideal, axis=1)
        cc = delta_neg / (delta_pos + delta_neg)
        weights = cc / np.sum(cc)

        Xij = np.zeros((len(ALTERNATIVES), len(reduced_criteria)))
        for i, alt in enumerate(ALTERNATIVES):
            reduced_fuzzy_alt = np.array(alt_data[alt])[:, idxs, :]
            agg = aggregate_ifwa(reduced_fuzzy_alt, deltas)
            scores = np.array([score_if(*triple) for triple in agg])
            Xij[i] = scores

        K1 = normalize_linear(Xij)
        K2 = normalize_vector(Xij)
        Pij = aggregate_normalization(K1, K2)
        Zij = calculate_Zij(Pij, weights)
        # Kriter türlerini al (Benefit/Cost)
        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()
        c.execute("SELECT name, type FROM criteria")
        crit_types = dict(c.fetchall())
        conn.close()

        # Cost ve Benefit kriterlerinin indeksleri
        cost_idx = [i for i, crit in enumerate(reduced_criteria) if crit_types.get(crit) == "Cost"]
        benefit_idx = [i for i, crit in enumerate(reduced_criteria) if crit_types.get(crit) == "Benefit"]

        # Eq. 23-24: L_i ve A_i hesapla
        Li = Zij[:, cost_idx].sum(axis=1) if cost_idx else np.zeros(len(ALTERNATIVES))
        Ai = Zij[:, benefit_idx].sum(axis=1) if benefit_idx else np.zeros(len(ALTERNATIVES))

        # Eq. 25: Ri = L^λ + A^(1-λ)
        λ = len(cost_idx) / len(CRITERIA)
        Ri = np.zeros(len(Li))
        for i in range(len(Li)):
            if Li[i] == 0:
                Ri[i] = Ai[i] ** (1 - λ)
            elif Ai[i] == 0:
                Ri[i] = Li[i] ** λ
            else:
                Ri[i] = (Li[i] ** λ) + (Ai[i] ** (1 - λ))

        best_alt = ALTERNATIVES[np.argmax(Ri)]

        validation_table += f"<tr><td>SAS-{idx+1}</td><td>{crit_to_remove}</td>"
        for score in Ri:
            validation_table += f"<td>{score:.4f}</td>"
        validation_table += f"<td>{best_alt}</td></tr>"

    validation_table += "</table><br>"
    return validation_table

if __name__ == '__main__':
    init_db()
    seed_initial_data()

    import webbrowser
    import threading

    def open_browser():
        webbrowser.open("http://127.0.0.1:5000/")

    threading.Timer(1.0, open_browser).start()
    app.run(debug=True, use_reloader=False)
