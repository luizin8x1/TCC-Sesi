"""App de treino (TCC) - Flask + SQLite.
Rodar:  python app.py   ->  http://localhost:5000
"""
import json
import os
import random
import re
import secrets
import sqlite3
import threading
import time
from collections import defaultdict, deque
from datetime import date, datetime, timedelta
from functools import wraps
from pathlib import Path

from flask import (Flask, abort, g, jsonify, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

BASE = Path(__file__).parent
DB_PATH = BASE / "app.db"
VIDEOS_DIR = BASE / "static" / "videos"
MAX_WEEKS = 10
NUM_SPRITES = 10
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
# PRODUCAO=1 quando o site estiver online com HTTPS (liga cookie Secure e HSTS)
PRODUCAO = os.environ.get("PRODUCAO", "") == "1"
MAX_NOME, MAX_EMAIL, MIN_SENHA, MAX_SENHA = 80, 254, 6, 128

COLORS = [
    {"nome": "verde", "main": "#2E9E3E", "dark": "#1F7A33"},
    {"nome": "laranja", "main": "#EA7A1A", "dark": "#B45309"},
    {"nome": "azul", "main": "#2F7DE1", "dark": "#1D5FB8"},
    {"nome": "roxo", "main": "#8B5CF6", "dark": "#6D3CC4"},
]

app = Flask(__name__)
_key_file = BASE / ".secret_key"
if not _key_file.exists():
    _key_file.write_text(secrets.token_hex(32))
    try:
        os.chmod(_key_file, 0o600)
    except OSError:
        pass
app.secret_key = os.environ.get("SECRET_KEY") or _key_file.read_text().strip()
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=PRODUCAO,
    PERMANENT_SESSION_LIFETIME=timedelta(days=365),
    MAX_CONTENT_LENGTH=16 * 1024,  # nenhum formulario/JSON do site passa disso
)
if os.environ.get("TRUST_PROXY") == "1":  # atras de nginx/Cloudflare/host com proxy
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

# ---------- limite de tentativas (em memoria) ----------
_tentativas = defaultdict(deque)
_trava = threading.Lock()


def bloqueado(chave, maximo, janela):
    agora = time.time()
    with _trava:
        fila = _tentativas[chave]
        while fila and agora - fila[0] > janela:
            fila.popleft()
        return len(fila) >= maximo


def registrar(chave):
    with _trava:
        _tentativas[chave].append(time.time())
        if len(_tentativas) > 20000:  # limpeza simples
            for k in [k for k, v in _tentativas.items() if not v or time.time() - v[-1] > 3600]:
                _tentativas.pop(k, None)


def ip_cliente():
    return request.remote_addr or "?"


SENHA_FALSA = generate_password_hash("senha-falsa-para-igualar-o-tempo")

# ---------- cabecalhos de seguranca / protecao dos videos ----------
VIDEO_RE = re.compile(r"^/static/videos/semana-(\d+)/dia-(\d+)(?:\.mp4|/[^/]+\.mp4)$")


@app.before_request
def antes():
    g.nonce = secrets.token_urlsafe(16)
    caminho = request.path
    if caminho.startswith("/static/videos"):
        # so .mp4 no formato semana-N/dia-N, sem ".." e so para quem tem acesso
        m = VIDEO_RE.match(caminho)
        if not m or ".." in caminho or "\\" in caminho or "//" in caminho:
            abort(404)
        user = usuario_atual()
        if user is None or not user["dias"]:
            return jsonify(erro="Faça login para ver os vídeos."), 401
        semana, dia = int(m.group(1)), int(m.group(2))
        if semana > semana_atual(user) or dia > user["dias"]:
            return jsonify(erro="Esse vídeo ainda não está liberado."), 403


@app.context_processor
def injetar_nonce():
    return {"nonce": g.get("nonce", "")}


@app.after_request
def depois(resp):
    n = g.get("nonce", "")
    resp.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        f"script-src 'self' 'nonce-{n}' https://accounts.google.com/gsi/client; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://accounts.google.com/gsi/style; "
        "font-src https://fonts.gstatic.com; img-src 'self' data: https://*.googleusercontent.com; media-src 'self'; "
        "connect-src 'self' https://accounts.google.com/gsi/; frame-src https://accounts.google.com/gsi/; "
        "frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'"
    )
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    resp.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if PRODUCAO:
        resp.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    if request.path.startswith("/static/videos"):
        resp.headers["Cache-Control"] = "private, max-age=3600"
    elif not request.path.startswith("/static/"):
        resp.headers["Cache-Control"] = "no-store"
    return resp


# ---------- banco de dados ----------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DB_PATH)
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            senha_hash TEXT,
            google_sub TEXT UNIQUE,
            dias INTEGER,
            inicio TEXT,
            plano TEXT NOT NULL,
            criado_em TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS progresso (
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            semana INTEGER NOT NULL,
            dia INTEGER NOT NULL,
            concluido_em TEXT NOT NULL,
            PRIMARY KEY (user_id, semana, dia)
        );
        """
    )
    db.commit()
    db.close()


# ---------- plano aleatorio (cor + 2 personagens por semana) ----------
def gerar_plano():
    plano, ultima_cor, ultimos = [], None, set()
    for _ in range(MAX_WEEKS):
        cor = random.choice([i for i in range(len(COLORS)) if i != ultima_cor])
        pool = [s for s in range(1, NUM_SPRITES + 1) if s not in ultimos]
        chars = random.sample(pool, 2)
        plano.append({"cor": cor, "chars": chars})
        ultima_cor, ultimos = cor, set(chars)
    return plano


def criar_usuario(nome, email, senha_hash=None, google_sub=None):
    db = get_db()
    cur = db.execute(
        "INSERT INTO users (nome, email, senha_hash, google_sub, plano, criado_em)"
        " VALUES (?,?,?,?,?,?)",
        (nome, email, senha_hash, google_sub, json.dumps(gerar_plano()),
         datetime.now().isoformat(timespec="seconds")),
    )
    db.commit()
    return cur.lastrowid


# ---------- sessao ----------
def usuario_atual():
    uid = session.get("uid")
    if not uid:
        return None
    return get_db().execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()


def login_necessario(f):
    @wraps(f)
    def wrapper(*a, **kw):
        user = usuario_atual()
        if user is None:
            session.clear()
            if request.path.startswith("/api/"):
                return jsonify(erro="Faça login novamente."), 401
            return redirect(url_for("entrar"))
        g.user = user
        return f(*a, **kw)
    return wrapper


def entrar_na_sessao(uid):
    session.clear()
    session.permanent = True
    session["uid"] = uid


def semana_atual(user):
    """1..10 enquanto o programa roda; 11 quando as 10 semanas terminaram."""
    inicio = date.fromisoformat(user["inicio"])
    return max(1, (date.today() - inicio).days // 7 + 1)


# ---------- paginas ----------
@app.route("/")
def raiz():
    user = usuario_atual()
    if user is None:
        return redirect(url_for("cadastro"))
    return redirect(url_for("trilha") if user["dias"] else url_for("dias"))


@app.route("/cadastro", methods=["GET", "POST"])
def cadastro():
    if usuario_atual():
        return redirect(url_for("raiz"))
    erro, nome, email = None, "", ""
    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        email = request.form.get("email", "").strip().lower()
        senha = request.form.get("senha", "")
        if bloqueado("cad-ip:" + ip_cliente(), 60, 3600):
            return render_template("cadastro.html", erro="Muitas contas criadas por aqui. Tente mais tarde.",
                                   nome="", email="", google_id=GOOGLE_CLIENT_ID), 429
        registrar("cad-ip:" + ip_cliente())
        if len(nome) < 2:
            erro = "Digite seu nome."
        elif len(nome) > MAX_NOME:
            erro = "Nome muito longo."
        elif len(email) > MAX_EMAIL or "@" not in email or "." not in email.split("@")[-1]:
            erro = "Digite um e-mail válido."
        elif len(senha) < MIN_SENHA:
            erro = "A senha precisa ter pelo menos 6 caracteres."
        elif len(senha) > MAX_SENHA:
            erro = "A senha pode ter no máximo 128 caracteres."
        elif get_db().execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
            erro = "Este e-mail já tem conta. Use 'Já tenho conta' para entrar."
        else:
            uid = criar_usuario(nome, email, generate_password_hash(senha))
            entrar_na_sessao(uid)
            return redirect(url_for("dias"))
    return render_template("cadastro.html", erro=erro, nome=nome, email=email,
                           google_id=GOOGLE_CLIENT_ID)


@app.route("/entrar", methods=["GET", "POST"])
def entrar():
    if usuario_atual():
        return redirect(url_for("raiz"))
    erro, email = None, ""
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()[:MAX_EMAIL]
        senha = request.form.get("senha", "")[:MAX_SENHA]
        if bloqueado("login-ip:" + ip_cliente(), 30, 600) or bloqueado("login-email:" + email, 5, 600):
            return render_template("entrar.html", erro="Muitas tentativas. Espere alguns minutos e tente de novo.",
                                   email=email, google_id=GOOGLE_CLIENT_ID), 429
        user = get_db().execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        hash_ = user["senha_hash"] if user and user["senha_hash"] else SENHA_FALSA  # mesmo tempo com ou sem conta
        if not check_password_hash(hash_, senha) or user is None or not user["senha_hash"]:
            registrar("login-ip:" + ip_cliente())
            registrar("login-email:" + email)
            erro = "E-mail ou senha incorretos. Se você criou a conta com o Google, use o botão do Google."
        else:
            entrar_na_sessao(user["id"])
            return redirect(url_for("raiz"))
    return render_template("entrar.html", erro=erro, email=email, google_id=GOOGLE_CLIENT_ID)


@app.route("/auth/google", methods=["POST"])
def auth_google():
    if not GOOGLE_CLIENT_ID:
        return jsonify(erro="Login com Google não configurado."), 501
    from google.auth.transport import requests as greq
    from google.oauth2 import id_token
    if bloqueado("google-ip:" + ip_cliente(), 30, 600):
        return jsonify(erro="Muitas tentativas. Espere alguns minutos."), 429
    registrar("google-ip:" + ip_cliente())
    credential = (request.get_json(silent=True) or {}).get("credential", "")
    if not isinstance(credential, str) or len(credential) > 4096:
        return jsonify(erro="Login do Google inválido."), 400
    try:
        info = id_token.verify_oauth2_token(credential, greq.Request(), GOOGLE_CLIENT_ID)
    except Exception:
        return jsonify(erro="Não foi possível validar o login do Google."), 401
    if not info.get("email_verified"):
        return jsonify(erro="E-mail do Google não verificado."), 401
    sub, email = info["sub"], info["email"].lower()
    nome = info.get("name") or email.split("@")[0]
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE google_sub = ? OR email = ?", (sub, email)).fetchone()
    if user is None:
        uid = criar_usuario(nome, email, None, sub)
    else:
        uid = user["id"]
        if user["google_sub"] and user["google_sub"] != sub:
            return jsonify(erro="Este e-mail já está ligado a outra conta Google."), 401
        if not user["google_sub"]:
            # Liga o Google a uma conta criada com senha e APAGA a senha antiga: assim, quem
            # criou a conta com o e-mail de outra pessoa nao consegue mais entrar nela.
            db.execute("UPDATE users SET google_sub = ?, senha_hash = NULL WHERE id = ?", (sub, uid))
            db.commit()
    entrar_na_sessao(uid)
    return jsonify(ok=True, proximo=url_for("raiz"))


@app.route("/dias", methods=["GET", "POST"])
@login_necessario
def dias():
    user = g.user
    if request.method == "POST":
        try:
            n = int(request.form.get("dias", ""))
        except ValueError:
            n = 0
        if 1 <= n <= 7:
            db = get_db()
            inicio = user["inicio"] or date.today().isoformat()
            db.execute("UPDATE users SET dias = ?, inicio = ? WHERE id = ?", (n, inicio, user["id"]))
            db.commit()
            return redirect(url_for("trilha"))
    return render_template("dias.html", user=user, atual=user["dias"])


@app.route("/sair", methods=["POST"])
def sair():
    session.clear()
    return redirect(url_for("cadastro"))


@app.route("/trilha")
@login_necessario
def trilha():
    user = g.user
    if not user["dias"]:
        return redirect(url_for("dias"))
    plano = json.loads(user["plano"])
    atual = semana_atual(user)
    inicio = date.fromisoformat(user["inicio"])
    feitos = {(r["semana"], r["dia"]) for r in get_db().execute(
        "SELECT semana, dia FROM progresso WHERE user_id = ?", (user["id"],))}
    semanas, proximo = [], None
    for n in range(1, MAX_WEEKS + 1):
        p = plano[n - 1]
        status = "atual" if n == atual else ("passada" if n < atual else "futura")
        libera = inicio + timedelta(days=7 * (n - 1))
        dias_lista = []
        for d in range(1, user["dias"] + 1):
            feito = (n, d) in feitos
            if status == "atual" and not feito and proximo is None:
                proximo = (n, d)
            dias_lista.append({"dia": d, "feito": feito})
        semanas.append({
            "n": n, "status": status, "cor": COLORS[p["cor"]], "chars": p["chars"],
            "libera": libera, "faltam": (libera - date.today()).days,
            "dias": dias_lista, "feitos": sum(x["feito"] for x in dias_lista),
        })
    return render_template("trilha.html", user=user, semanas=semanas, atual=atual,
                           proximo=proximo, max_weeks=MAX_WEEKS)


# ---------- API ----------
def listar_videos(semana, dia):
    pasta = VIDEOS_DIR / f"semana-{semana}"
    arquivos = []
    if (pasta / f"dia-{dia}").is_dir():
        arquivos += sorted((pasta / f"dia-{dia}").glob("*.mp4"), key=lambda p: p.name.lower())
    if (pasta / f"dia-{dia}.mp4").is_file():
        arquivos.insert(0, pasta / f"dia-{dia}.mp4")
    return [url_for("static", filename=a.relative_to(BASE / "static").as_posix()) for a in arquivos]


def validar_semana_dia(user, semana, dia):
    if type(semana) is not int or type(dia) is not int:  # nao aceita texto nem true/false
        abort(400)
    if not (1 <= semana <= MAX_WEEKS and 1 <= dia <= user["dias"]):
        abort(400)
    if semana > semana_atual(user):
        abort(403)


@app.route("/api/videos/<int:semana>/<int:dia>")
@login_necessario
def api_videos(semana, dia):
    validar_semana_dia(g.user, semana, dia)
    return jsonify(videos=listar_videos(semana, dia))


@app.route("/api/concluir", methods=["POST"])
@login_necessario
def api_concluir():
    dados = request.get_json(silent=True) or {}
    semana, dia = dados.get("semana"), dados.get("dia")
    validar_semana_dia(g.user, semana, dia)
    if semana != semana_atual(g.user):
        return jsonify(erro="Só dá para concluir treinos da semana atual."), 400
    db = get_db()
    db.execute("INSERT OR IGNORE INTO progresso (user_id, semana, dia, concluido_em) VALUES (?,?,?,?)",
               (g.user["id"], semana, dia, datetime.now().isoformat(timespec="seconds")))
    db.commit()
    return jsonify(ok=True)


@app.errorhandler(413)
def grande_demais(_e):
    return jsonify(erro="Dados grandes demais."), 413


@app.errorhandler(403)
def proibido(_e):
    return jsonify(erro="Essa semana ainda não foi liberada."), 403


init_db()

if __name__ == "__main__":
    # 0.0.0.0 permite abrir no celular (mesmo Wi-Fi) em http://IP-DO-PC:5000
    app.run(host="0.0.0.0", port=5000, debug=False)
