"""Testes de seguranca do site (rodam contra o site ligado).

1) Em um terminal:   python app.py
2) Em outro:         python teste_seguranca.py            (ou:  python teste_seguranca.py http://localhost:5000)

Pre-requisito: ter pelo menos 1 video em static/videos/semana-1/dia-1/ e outro em semana-2/dia-1/
(o proprio teste cria arquivos de teste se as pastas estiverem vazias e apaga depois).
Rode com o site recem-iniciado: o teste final de forca bruta ativa o bloqueio do seu IP por alguns minutos.
"""
import os
import re
import shutil
import sqlite3
import sys
import time
import uuid
from pathlib import Path

import requests

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:5000").rstrip("/")
RAIZ = Path(__file__).parent
VIDEOS = RAIZ / "static" / "videos"
resultados = []


def check(nome, ok, detalhe=""):
    resultados.append((nome, ok, detalhe))
    print(("[OK]   " if ok else "[FALHA]") + " " + nome + (f"  -> {detalhe}" if detalhe else ""))


def novo_usuario(nome="Teste Seguranca", dias=3):
    s = requests.Session()
    email = f"t{uuid.uuid4().hex[:10]}@teste.com"
    r = s.post(BASE + "/cadastro", data={"nome": nome, "email": email, "senha": "senha123"}, allow_redirects=False)
    assert r.status_code == 302, f"cadastro falhou ({r.status_code})"
    r = s.post(BASE + "/dias", data={"dias": dias}, allow_redirects=False)
    assert r.status_code == 302
    return s, email


# ---- preparar videos de teste ----
criados = []
for sem, dia in ((1, 1), (2, 1), (1, 5)):
    pasta = VIDEOS / f"semana-{sem}" / f"dia-{dia}"
    if not pasta.exists():
        pasta.mkdir(parents=True)
        criados.append(VIDEOS / f"semana-{sem}")
    arq = pasta / "zz-teste-seguranca.mp4"
    arq.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"0" * 64)
    criados.append(arq)

try:
    anon = requests.Session()
    A, emailA = novo_usuario()

    # 1. arquivos do servidor nao podem ser baixados
    caminhos = ["/app.db", "/.secret_key", "/app.py", "/templates/trilha.html", "/requirements.txt",
                "/static/../app.py", "/static/%2e%2e/app.py", "/static/..%2fapp.py", "/static/%2e%2e%2f.secret_key"]
    vazou = [c for c in caminhos if requests.get(BASE + c, allow_redirects=False).status_code == 200]
    check("Arquivos internos (banco, chave, codigo) nao ficam expostos", not vazou, ", ".join(vazou))

    # 2. paginas e API exigem login
    r1 = [anon.get(BASE + p, allow_redirects=False).status_code for p in ("/trilha", "/dias")]
    r2 = [anon.get(BASE + "/api/videos/1/1").status_code, anon.post(BASE + "/api/concluir", json={"semana": 1, "dia": 1}).status_code]
    check("Trilha e API exigem login", r1 == [302, 302] and r2 == [401, 401], f"paginas={r1} api={r2}")

    # 3. videos sem login
    r = anon.get(BASE + "/static/videos/semana-1/dia-1/zz-teste-seguranca.mp4")
    check("Video nao baixa sem estar logado", r.status_code in (401, 403), f"status {r.status_code}")

    # 4. semana futura
    r_api = A.get(BASE + "/api/videos/2/1").status_code
    r_dir = A.get(BASE + "/static/videos/semana-2/dia-1/zz-teste-seguranca.mp4").status_code
    check("Video da semana futura bloqueado (API e link direto)", r_api == 403 and r_dir in (401, 403), f"api={r_api} direto={r_dir}")

    # 4b. truque do ".." para chegar na semana futura
    codigos = [A.get(BASE + c).status_code for c in ("/static/videos/semana-1/%2e%2e/semana-2/dia-1/zz-teste-seguranca.mp4",
                                                   "/static/videos/semana-1/dia-1/..%2f..%2fsemana-2/dia-1/zz-teste-seguranca.mp4",
                                                   "/static/videos/semana-1/dia-1/%2e%2e/%2e%2e/%2e%2e/app.py")]
    check("Truque com '..' nao libera video bloqueado nem codigo", all(c in (400, 403, 404) for c in codigos), str(codigos))

    # 5. dia alem do escolhido
    r_api = A.get(BASE + "/api/videos/1/5").status_code
    r_dir = A.get(BASE + "/static/videos/semana-1/dia-5/zz-teste-seguranca.mp4").status_code
    check("Video de dia acima do escolhido bloqueado", r_api in (400, 403) and r_dir in (401, 403), f"api={r_api} direto={r_dir}")

    # 6. concluir com dados invalidos
    casos = [{"semana": 2, "dia": 1}, {"semana": 1, "dia": 9}, {"semana": "1", "dia": "1"}, {"semana": True, "dia": True},
             {"semana": 1.5, "dia": 1}, {"semana": -1, "dia": 1}, {}, {"semana": None, "dia": None}]
    codigos = [A.post(BASE + "/api/concluir", json=c).status_code for c in casos]
    check("Concluir treino rejeita semana futura, dia invalido e tipos errados", all(c in (400, 403) for c in codigos), str(codigos))
    ok = A.post(BASE + "/api/concluir", json={"semana": 1, "dia": 1}).status_code == 200
    check("Concluir treino valido funciona", ok)

    # 7. injecao SQL
    s = requests.Session()
    r = s.post(BASE + "/entrar", data={"email": "' OR '1'='1' --", "senha": "' OR '1'='1"}, allow_redirects=False)
    check("Login resiste a injecao SQL", r.status_code == 200, f"status {r.status_code}")
    S2 = requests.Session()
    email_sql = f"t{uuid.uuid4().hex[:8]}@teste.com"
    r = S2.post(BASE + "/cadastro", data={"nome": "x'); DROP TABLE users;--", "email": email_sql, "senha": "senha123"}, allow_redirects=False)
    r2 = requests.post(BASE + "/entrar", data={"email": email_sql, "senha": "senha123"}, allow_redirects=False)
    check("Cadastro com SQL no nome nao quebra o banco", r.status_code == 302 and r2.status_code == 302)

    # 8. XSS
    X = requests.Session()
    email_x = f"t{uuid.uuid4().hex[:8]}@teste.com"
    X.post(BASE + "/cadastro", data={"nome": "<script>alert(1)</script><img src=x onerror=alert(2)>", "email": email_x, "senha": "senha123"})
    X.post(BASE + "/dias", data={"dias": 2})
    html = X.get(BASE + "/dias").text + X.get(BASE + "/trilha").text
    check("Nome com HTML/JS e exibido como texto (sem XSS)", "<script>alert(1)" not in html and "<img src=x" not in html)

    # 9. cookie de sessao
    sc = requests.post(BASE + "/entrar", data={"email": emailA, "senha": "senha123"}, allow_redirects=False).headers.get("Set-Cookie", "")
    check("Cookie de sessao com HttpOnly e SameSite", "HttpOnly" in sc and "SameSite" in sc, sc.split(";")[0][:20] + "...")
    print(("[OK]    " if "Secure" in sc else "[AVISO] ") + "Cookie com flag Secure"
          + ("" if "Secure" in sc else "  -> desligado de proposito neste teste (http). Ligue com PRODUCAO=1 quando o site tiver HTTPS"))

    # 10. cookie adulterado
    ck = A.cookies.get("session")
    adult = requests.get(BASE + "/trilha", cookies={"session": ck[:-3] + ("AAA" if not ck.endswith("AAA") else "BBB")}, allow_redirects=False)
    check("Cookie adulterado e rejeitado", adult.status_code == 302)

    # 11. CSRF basico
    r = A.post(BASE + "/api/concluir", data='{"semana":1,"dia":2}', headers={"Content-Type": "text/plain"})
    check("API nao aceita pedido simples de outro site (text/plain)", r.status_code in (400, 415), f"status {r.status_code}")
    r = A.get(BASE + "/sair", allow_redirects=False)
    check("Sair so funciona por POST", r.status_code == 405, f"status {r.status_code}")

    # 12. cabecalhos
    h = requests.get(BASE + "/entrar").headers
    falta = [n for n in ("Content-Security-Policy", "X-Content-Type-Options", "X-Frame-Options", "Referrer-Policy") if n not in h]
    check("Cabecalhos de seguranca presentes", not falta, "faltam: " + ", ".join(falta) if falta else "")

    # 13. tamanho de dados
    t0 = time.time()
    try:
        r = requests.post(BASE + "/cadastro", data={"nome": "Teste", "email": f"t{uuid.uuid4().hex[:8]}@t.com", "senha": "a" * 5_000_000}, allow_redirects=False, timeout=15)
        cod = r.status_code
    except requests.RequestException:
        cod = "erro"
    dt = time.time() - t0
    check("Dados enormes (5 MB) sao recusados rapido", cod in (400, 413) and dt < 3, f"status {cod} em {dt:.1f}s")
    r = requests.post(BASE + "/cadastro", data={"nome": "Teste", "email": f"t{uuid.uuid4().hex[:8]}@t.com", "senha": "a" * 5000}, allow_redirects=False)
    check("Senha gigante (5000 caracteres) e recusada", r.status_code != 302, f"status {r.status_code}")
    r = requests.post(BASE + "/cadastro", data={"nome": "x" * 5000, "email": f"t{uuid.uuid4().hex[:8]}@t.com", "senha": "senha123"}, allow_redirects=False)
    check("Nome gigante (5000 letras) e recusado", r.status_code != 302, f"status {r.status_code}")

    # 14. modo debug / vazamento de erro
    r = requests.get(BASE + "/console")
    check("Console de debug desligado", r.status_code == 404)
    corpos = "".join(requests.get(BASE + p).text for p in ("/nao-existe", "/api/videos/abc/1"))
    check("Erros nao mostram trecho de codigo (Traceback)", "Traceback" not in corpos)

    # 15. senha guardada com hash
    db = RAIZ / "app.db"
    if db.exists():
        con = sqlite3.connect(db)
        hs = con.execute("SELECT senha_hash FROM users WHERE email = ?", (emailA,)).fetchone()
        con.close()
        check("Senha guardada com hash (nao em texto)", bool(hs and hs[0] and "senha123" not in hs[0] and re.match(r"^(scrypt|pbkdf2):", hs[0])))

    # 15b. vinculo com Google nao deixa a senha de um invasor valer (teste interno, sem internet)
    try:
        import tempfile
        from unittest import mock
        sys.path.insert(0, str(RAIZ))
        import google.oauth2.id_token  # noqa: F401
        import app as meu_app
        meu_app.DB_PATH = Path(tempfile.mkdtemp()) / "teste.db"
        meu_app.init_db()
        meu_app.GOOGLE_CLIENT_ID = "teste"
        c1 = meu_app.app.test_client()
        c1.post("/cadastro", data={"nome": "Invasor", "email": "vitima@exemplo.com", "senha": "senhadoinvasor"})
        info = {"sub": "123", "email": "vitima@exemplo.com", "email_verified": True, "name": "Vitima"}
        with mock.patch("google.oauth2.id_token.verify_oauth2_token", return_value=info):
            vitima = meu_app.app.test_client()
            rg = vitima.post("/auth/google", json={"credential": "x"})
        c2 = meu_app.app.test_client()
        r2 = c2.post("/entrar", data={"email": "vitima@exemplo.com", "senha": "senhadoinvasor"})
        check("Login com Google desativa a senha de quem criou a conta antes (pre-sequestro)", rg.status_code == 200 and r2.status_code == 200)
    except ImportError as e:
        check("Teste do Google (precisa do pacote google-auth)", False, str(e))

    # 16. forca bruta (por ultimo)
    alvo = requests.Session()
    codigos = [alvo.post(BASE + "/entrar", data={"email": emailA, "senha": f"errada{i}"}, allow_redirects=False).status_code for i in range(15)]
    check("Muitas senhas erradas seguidas sao bloqueadas (forca bruta)", 429 in codigos, f"codigos: {sorted(set(codigos))}")
finally:
    for c in criados:
        if c.is_file():
            c.unlink(missing_ok=True)
    for c in criados:
        if c.is_dir():
            shutil.rmtree(c, ignore_errors=True)

falhas = [r for r in resultados if not r[1]]
print(f"\n{len(resultados) - len(falhas)} de {len(resultados)} testes passaram.")
sys.exit(1 if falhas else 0)
