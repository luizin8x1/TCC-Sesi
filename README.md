# App de Treino (TCC)

Site em Flask (Python) + SQLite, feito para celular.

## Como rodar
1. Instale o Python 3.10 ou mais novo.
2. Na pasta do projeto:
   ```
   python -m venv venv
   venv\Scripts\activate        (Windows)   |   source venv/bin/activate   (Linux/Mac)
   pip install -r requirements.txt
   python app.py
   ```
3. Abra http://localhost:5000
4. No celular (mesmo Wi-Fi): http://IP-DO-COMPUTADOR:5000

## Videos
Veja `static/videos/LEIA-ME.txt`.

## Login com Google (opcional)
1. https://console.cloud.google.com/ -> APIs e servicos -> Credenciais -> Criar ID do cliente OAuth (Aplicativo da Web).
2. Em "Origens JavaScript autorizadas" coloque `http://localhost:5000` (e o endereco que for usar).
3. Rode com a variavel definida:
   - Windows (PowerShell): `$env:GOOGLE_CLIENT_ID="SEU_ID.apps.googleusercontent.com"; python app.py`
   - Linux/Mac: `GOOGLE_CLIENT_ID=SEU_ID.apps.googleusercontent.com python app.py`
Sem o ID, o botao do Google nao aparece e o resto funciona normalmente.
Obs.: o Google so aceita origens `localhost` ou https; um IP como 192.168.x.x nao funciona para o login Google.

## Regras
- Primeiro acesso: criar conta -> escolher dias por semana (1 a 7) -> trilha. Quem ja tem conta e fica logado vai direto para a trilha.
- Ate 10 semanas. Cada semana dura 7 dias a partir do dia em que a pessoa escolheu os dias de treino.
- A semana seguinte so libera quando o tempo da anterior acaba. Treinos so podem ser concluidos na semana atual.
- Cor e personagens de cada semana sao sorteados uma vez por usuario (4 cores, 10 personagens).

## Seguranca
- Para testar: ligue o site (`python app.py`) e, em outro terminal, rode `python teste_seguranca.py`. Rode com o site recem-iniciado: o ultimo teste (forca bruta) bloqueia seu IP por alguns minutos.
- Ja implementado: senha com hash, sessao em cookie HttpOnly/SameSite, protecao contra SQL injection e XSS, videos so para quem esta logado e na semana liberada,
  limite de tentativas de login/cadastro, limite de tamanho dos dados, cabecalhos de seguranca (CSP, X-Frame-Options etc.).

## Colocar online (hospedar)
1. **HTTPS e obrigatorio** (senhas passam pela internet). A maioria das hospedagens (Render, Railway, PythonAnywhere, VPS com Caddy/Nginx) da HTTPS.
2. **Nao use `python app.py` online** (e o servidor de testes). Use o waitress:
   `waitress-serve --port=8000 app:app`
3. Defina estas variaveis de ambiente no servidor:
   - `PRODUCAO=1`  (liga cookie Secure e HSTS)
   - `TRUST_PROXY=1`  (se o site ficar atras de proxy/hospedagem, para o limite de tentativas ver o IP real)
   - `SECRET_KEY=` uma frase longa e aleatoria (se nao definir, o programa cria o arquivo `.secret_key`)
   - `GOOGLE_CLIENT_ID=` (se usar login Google; cadastre o endereco https do site em "Origens JavaScript autorizadas")
4. O banco (`app.db`) e a pasta `static/videos` precisam ficar em **disco que nao apaga** quando o servidor reinicia. Faca copia do `app.db` de tempos em tempos.
5. Nunca envie `app.db` nem `.secret_key` para o GitHub (o `.gitignore` ja bloqueia).
6. Rode com 1 processo (o limite de tentativas fica na memoria). Para varios processos, troque por Flask-Limiter com Redis.
7. O site guarda nome e e-mail dos usuarios: avise isso (politica de privacidade simples, LGPD).
