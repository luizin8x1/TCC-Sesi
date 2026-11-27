(function () {
  const janela = document.getElementById("janela");
  const titulo = document.getElementById("janela-titulo");
  const area = document.getElementById("janela-videos");
  const msg = document.getElementById("janela-msg");
  const btnConcluir = document.getElementById("concluir");
  // Nomes em portugues. A chave e o nome do arquivo sem o numero e sem ".mp4"
  // (ex.: 01-bench-press.mp4 -> "bench-press"). Para um video novo, basta adicionar uma linha aqui.
  const NOMES = {
    "bench-press": "Supino reto com barra",
    "incline-bench-press": "Supino inclinado com barra",
    "dumbbell-bench-press": "Supino reto com halteres",
    "chest-press": "Supino na máquina",
    "machine-chest-fly": "Crucifixo na máquina",
    "cable-crossover": "Crossover na polia",
    "around-the-world": "Around the world",
    "svend-press": "Svend press",
    "pull-up": "Barra fixa",
    "lat-pulldown": "Puxada na polia alta",
    "barbell-row": "Remada curvada com barra",
    "t-bar-row": "Remada cavalinho",
    "chest-supported-row": "Remada apoiada no peito",
    "seated-cable-row": "Remada sentada na polia",
    "dumbbell-pullover": "Pullover com halter",
    "farmers-walk": "Caminhada do fazendeiro",
    "romanian-deadlift": "Levantamento terra romeno",
    "dumbbell-romanian-deadlift": "Levantamento terra romeno com halteres",
    "single-leg-rdl": "Levantamento terra romeno unilateral",
    "hip-thrust": "Elevação de quadril (hip thrust)",
    "lying-leg-curl": "Mesa flexora",
    "seated-leg-curl": "Cadeira flexora",
    "cable-hip-abduction": "Abdução de quadril na polia",
    "cable-hip-adduction": "Adução de quadril na polia",
    "hip-adduction": "Cadeira adutora",
    "dumbbell-shoulder-press": "Desenvolvimento com halteres",
    "machine-shoulder-press": "Desenvolvimento na máquina",
    "dumbbell-lateral-raise": "Elevação lateral com halteres",
    "cable-lateral-raise": "Elevação lateral na polia",
    "rear-delt-fly": "Crucifixo inverso",
    "reverse-pec-deck": "Crucifixo inverso na máquina",
    "close-grip-bench-press": "Supino fechado",
    "dips": "Mergulho nas paralelas",
    "barbell-biceps-curl": "Rosca direta com barra",
    "dumbbell-biceps-curl": "Rosca direta com halteres",
    "preacher-curl": "Rosca Scott",
    "hammer-curl": "Rosca martelo",
    "triceps-pushdown": "Tríceps na polia",
    "triceps-extension": "Extensão de tríceps",
    "overhead-triceps-extension": "Tríceps francês",
    "overhead-cable-triceps-extension": "Tríceps francês na polia",
    "ab-wheel-rollout": "Roda abdominal",
    "hanging-leg-raise": "Elevação de pernas na barra",
    "hanging-knee-raise": "Elevação de joelhos na barra",
    "cable-crunch": "Abdominal na polia",
    "crunch": "Abdominal tradicional",
    "lying-leg-raise": "Elevação de pernas deitado",
    "front-plank": "Prancha",
    "push-up": "Flexão de braço",
    "standing-calf-raise": "Panturrilha em pé",
    "seated-calf-raise": "Panturrilha sentado",
    "calf-press": "Panturrilha no leg press",
    "smith-machine-calf-raise": "Panturrilha no Smith",
    "incline-dumbbell-curl": "Rosca inclinada com halteres",
    "reverse-curl": "Rosca inversa",
    "cable-wrist-curl": "Rosca de punho na polia"
  };

  let atual = null;      // {semana, dia}
  let videos = [];       // urls do treino aberto
  let pos = 0;           // video mostrado

  function parar() {
    const v = area.querySelector("video");
    if (v) { v.pause(); v.removeAttribute("src"); v.load(); }
  }
  function limpar() { parar(); area.innerHTML = ""; videos = []; pos = 0; }
  function mostrarMsg(t) { msg.textContent = t; msg.hidden = !t; }

  function nomeDe(url) {
    let n = decodeURIComponent(url.split("/").pop()).replace(/\.mp4$/i, "");
    n = n.replace(/^\d+[-_ ]*/, "").replace(/\s*\(\d+\)$/, "").trim().toLowerCase();
    if (NOMES[n]) return NOMES[n];
    n = n.replace(/[-_]+/g, " ");   // sem traducao: mostra o nome do arquivo
    return n ? n.charAt(0).toUpperCase() + n.slice(1) : "Vídeo";
  }

  function montar() {
    area.innerHTML =
      '<div class="quadro"><p class="nome"></p><video controls playsinline preload="metadata"></video></div>' +
      '<div class="setas">' +
      '<button type="button" class="seta" id="ant" aria-label="Vídeo anterior">&#8249;</button>' +
      '<span class="contador" aria-live="polite"></span>' +
      '<button type="button" class="seta" id="prox" aria-label="Próximo vídeo">&#8250;</button></div>';
    area.querySelector("#ant").addEventListener("click", () => ir(pos - 1));
    area.querySelector("#prox").addEventListener("click", () => ir(pos + 1));
    if (videos.length < 2) area.querySelector(".setas").hidden = true;
    ir(0);
  }

  function ir(i) {
    if (i < 0 || i >= videos.length) return;
    pos = i;
    const v = area.querySelector("video");
    v.pause(); v.src = videos[i]; v.load();
    area.querySelector(".nome").textContent = nomeDe(videos[i]);
    area.querySelector(".contador").textContent = "Vídeo " + (i + 1) + " de " + videos.length;
    area.querySelector("#ant").disabled = i === 0;
    area.querySelector("#prox").disabled = i === videos.length - 1;
  }

  async function abrir(btn) {
    const semana = Number(btn.dataset.semana), dia = Number(btn.dataset.dia);
    atual = { semana, dia };
    titulo.textContent = "Semana " + semana + " · Treino " + dia;
    limpar(); mostrarMsg("Carregando vídeos...");
    btnConcluir.hidden = !(btn.dataset.estado === "aberto" && btn.dataset.atual === "1");
    btnConcluir.disabled = false;
    janela.showModal();
    try {
      const r = await fetch("/api/videos/" + semana + "/" + dia);
      const d = await r.json();
      if (!r.ok) { mostrarMsg(d.erro || "Não foi possível carregar."); return; }
      if (!d.videos.length) {
        mostrarMsg("Ainda não há vídeos neste treino. Coloque os arquivos .mp4 em static/videos/semana-" + semana + "/dia-" + dia + "/");
        return;
      }
      mostrarMsg("");
      videos = d.videos;
      montar();
    } catch (e) { mostrarMsg("Erro de conexão. Tente novamente."); }
  }

  document.querySelectorAll(".no").forEach(b => b.addEventListener("click", () => abrir(b)));
  document.getElementById("fechar").addEventListener("click", () => janela.close());
  janela.addEventListener("click", e => { if (e.target === janela) janela.close(); });
  janela.addEventListener("close", limpar);
  // setas do teclado trocam de video (quando o foco nao esta no player)
  janela.addEventListener("keydown", e => {
    if (!videos.length || e.target.tagName === "VIDEO") return;
    if (e.key === "ArrowRight") ir(pos + 1);
    if (e.key === "ArrowLeft") ir(pos - 1);
  });

  btnConcluir.addEventListener("click", async () => {
    if (!atual) return;
    btnConcluir.disabled = true;
    try {
      const r = await fetch("/api/concluir", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(atual)
      });
      if (r.ok) { location.reload(); return; }
      const d = await r.json().catch(() => ({}));
      mostrarMsg(d.erro || "Não foi possível concluir.");
    } catch (e) { mostrarMsg("Erro de conexão. Tente novamente."); }
    btnConcluir.disabled = false;
  });

  // abre a trilha ja na semana atual
  const alvo = document.querySelector(".comecar") || document.querySelector(".semana.atual");
  if (alvo) alvo.scrollIntoView({ block: "center" });
})();
