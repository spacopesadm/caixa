# -*- coding: utf-8 -*-
"""
Painel de configurações do Painel do Caixa.
Aberto pelo botão "Configurações" do checklist ou pelo ícone perto do relógio.
Tudo o que for salvo aqui vale na hora e fica gravado no config.json.
"""
import copy
import re
import threading
import tkinter as tk
import uuid
from tkinter import filedialog, messagebox, ttk

FONT = "Segoe UI"
GREY = "#5B6878"
DIAS_NOMES = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
MAX_FUNC = 6

LISTAS = [
    ("ao_chegar", "Tarefas de ao chegar (uma por linha)"),
    ("conferencias", "Conferências do dia (nome | observação opcional)"),
    ("durante_atendimento", "Avisos durante o atendimento"),
    ("quando_livre", "Avisos para quando estiver livre"),
    ("avisos_alegres", "Avisos alegres (use {nome} para o nome do caixa)"),
    ("mensagens_alegres", "Mensagens ao concluir uma tarefa"),
    ("mensagens_dia_completo", "Mensagens ao completar o dia"),
]


def _hm(nome, texto):
    t = str(texto).strip()
    try:
        h, m = t.split(":")
        h, m = int(h), int(m)
        if not (0 <= h <= 23 and 0 <= m <= 59):
            raise ValueError
    except ValueError:
        raise ValueError("%s: use o formato HH:MM, por exemplo 09:30." % nome)
    return "%02d:%02d" % (h, m)


def _min(t):
    h, m = t.split(":")
    return int(h) * 60 + int(m)


def _num(nome, valor, lo, hi):
    try:
        v = int(str(valor).strip())
    except ValueError:
        raise ValueError("%s: digite um número inteiro." % nome)
    if not lo <= v <= hi:
        raise ValueError("%s: use um valor entre %d e %d." % (nome, lo, hi))
    return v


def _turno(nome, texto):
    """Lê '09:00-13:00' (ou '9-13'). Vazio = folga. Devolve [início, fim] ou None."""
    t = str(texto).strip()
    if not t:
        return None
    m = re.match(r"^(\d{1,2})(?::(\d{2}))?\s*(?:-|–|às|as|a)\s*(\d{1,2})(?::(\d{2}))?$", t)
    if not m:
        raise ValueError("%s: use o formato 09:00-13:00 (ou deixe vazio para folga)." % nome)
    h1, m1, h2, m2 = int(m.group(1)), int(m.group(2) or 0), int(m.group(3)), int(m.group(4) or 0)
    ini, fim = _hm(nome, "%d:%02d" % (h1, m1)), _hm(nome, "%d:%02d" % (h2, m2))
    if _min(fim) <= _min(ini):
        raise ValueError("%s: o fim precisa ser depois do início." % nome)
    return [ini, fim]


def _linhas(txt):
    return [x.strip() for x in txt.replace("\r", "").split("\n") if x.strip()]


def abrir(app):
    old = getattr(app, "settings_win", None)
    try:
        if old is not None and old.winfo_exists():
            old.deiconify()
            old.lift()
            return
    except Exception:
        pass

    cfg = copy.deepcopy(app.cfg)
    w = tk.Toplevel(app.root)
    app.settings_win = w
    w.title("Configurações do Painel do Caixa")
    sh = w.winfo_screenheight()
    w.geometry("860x%d+60+30" % max(480, min(720, sh - 100)))
    w.minsize(780, 460)
    w.configure(bg="#E9EDF2")

    style = ttk.Style(w)
    try:
        style.configure("TNotebook.Tab", padding=(12, 6), font=(FONT, 10, "bold"))
        style.configure("TLabel", font=(FONT, 10))
        style.configure("TCheckbutton", font=(FONT, 10))
        style.configure("TButton", font=(FONT, 10, "bold"), padding=(10, 5))
    except Exception:
        pass

    nb = ttk.Notebook(w)
    nb.pack(fill="both", expand=True, padx=12, pady=(12, 6))
    V = {}

    def tab(titulo):
        f = ttk.Frame(nb, padding=16)
        f.columnconfigure(0, weight=1)
        nb.add(f, text=titulo)
        return f

    def spin(parent, r, texto, chave, valor, lo, hi, dica=""):
        V[chave] = tk.StringVar(value=str(valor))
        ttk.Label(parent, text=texto, wraplength=400, justify="left").grid(row=r, column=0, sticky="w", pady=4)
        ttk.Spinbox(parent, from_=lo, to=hi, textvariable=V[chave], width=7).grid(row=r, column=1, sticky="w", padx=10)
        if dica:
            ttk.Label(parent, text=dica, foreground=GREY).grid(row=r, column=2, sticky="w")

    def campo(parent, r, texto, chave, valor, largura=30, show=None):
        V[chave] = tk.StringVar(value=str(valor))
        ttk.Label(parent, text=texto, wraplength=300, justify="left").grid(row=r, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=V[chave], width=largura, show=show).grid(row=r, column=1, columnspan=2, sticky="w", padx=10)

    def marca(parent, r, texto, chave, valor):
        V[chave] = tk.BooleanVar(value=bool(valor))
        ttk.Checkbutton(parent, text=texto, variable=V[chave]).grid(row=r, column=0, columnspan=3, sticky="w", pady=4)

    # ---------------- Avisos
    t1 = tab("Avisos")
    ttk.Label(t1, text="Com que frequência os avisos aparecem", font=(FONT, 11, "bold")).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 6))
    spin(t1, 1, "Aviso aleatório a cada, no mínimo", "min", cfg["aviso_aleatorio_min_minutos"], 1, 240, "minutos")
    spin(t1, 2, "Aviso aleatório a cada, no máximo", "max", cfg["aviso_aleatorio_max_minutos"], 1, 240, "minutos (o app sorteia entre os dois)")
    spin(t1, 3, "Chance de o aviso ser alegre", "chance", cfg.get("chance_aviso_alegre", 25), 0, 100, "% dos avisos aleatórios")
    spin(t1, 4, "Botão Cliente na frente pausa por", "pausa", cfg["pausa_atendimento_minutos"], 1, 60, "minutos")
    ttk.Label(t1, text="Quando uma tarefa fica pendente", font=(FONT, 11, "bold")).grid(row=5, column=0, columnspan=3, sticky="w", pady=(14, 6))
    esc = cfg.get("escalonar_apos_minutos", [4, 8])
    spin(t1, 6, "Aviso fica laranja (maior, com som) depois de", "esc1", esc[0], 1, 120, "minutos")
    spin(t1, 7, "Aviso fica vermelho (faixa no topo) depois de", "esc2", esc[1], 2, 240, "minutos")
    spin(t1, 8, "Aviso vermelho se repete a cada", "urg", cfg["repetir_urgente_minutos"], 1, 60, "minutos")
    spin(t1, 9, "Botão Adiar espera", "adiar", cfg["adiar_minutos"], 1, 60, "minutos")
    ttk.Label(t1, text="Conferências (Pix, vendas, entregas, promissórias)", font=(FONT, 11, "bold")).grid(row=10, column=0, columnspan=3, sticky="w", pady=(14, 6))
    spin(t1, 11, "Pedir cada conferência de novo a cada", "rep", cfg["repetir_conferencia_minutos"], 20, 600, "minutos")
    spin(t1, 12, "Intervalo entre uma conferência e a próxima", "gap", cfg["intervalo_entre_conferencias_minutos"], 0, 120, "minutos")
    marca(t1, 13, "Tocar sons junto com os avisos", "som", cfg.get("som", True))

    # ---------------- Horários por dia da semana
    t2 = tab("Horários por dia")
    ttk.Label(t2, text="Horário de cada dia da semana (formato HH:MM)", font=(FONT, 11, "bold")).grid(row=0, column=0, columnspan=8, sticky="w")
    ttk.Label(t2, text="Dias sem a opção Aberto ficam em silêncio e sem relatório (por exemplo, domingo).",
              foreground=GREY).grid(row=1, column=0, columnspan=8, sticky="w", pady=(0, 8))
    for c, tx in enumerate(["Dia", "Aberto", "Ao chegar: início", "Ao chegar: fim", "Tarde: início", "Tarde: fim", "Horas do caixa"]):
        ttk.Label(t2, text=tx, foreground=GREY, font=(FONT, 9, "bold")).grid(row=2, column=c, sticky="w", padx=4)
    dias_cfg = cfg.get("dias_semana") or {}
    for i in range(7):
        d = dias_cfg.get(str(i)) or {}
        ao, ta = d.get("ao_chegar") or ["09:00", "10:30"], d.get("tarde") or ["13:00", "19:00"]
        V["d%d_on" % i] = tk.BooleanVar(value=bool(d.get("aberto", i != 6)))
        ttk.Label(t2, text=DIAS_NOMES[i], font=(FONT, 10, "bold")).grid(row=3 + i, column=0, sticky="w", padx=4, pady=3)
        ttk.Checkbutton(t2, variable=V["d%d_on" % i]).grid(row=3 + i, column=1, sticky="w", padx=4)
        for c, (k, val, wd) in enumerate([("a0", ao[0], 7), ("a1", ao[1], 7), ("p0", ta[0], 7), ("p1", ta[1], 7)], start=2):
            V["d%d_%s" % (i, k)] = tk.StringVar(value=val)
            ttk.Entry(t2, textvariable=V["d%d_%s" % (i, k)], width=wd).grid(row=3 + i, column=c, sticky="w", padx=4)
        V["d%d_h" % i] = tk.StringVar(value=", ".join(str(h) for h in (d.get("horas") or [13, 14, 15, 16, 17, 18])))
        ttk.Entry(t2, textvariable=V["d%d_h" % i], width=22).grid(row=3 + i, column=6, sticky="w", padx=4)

    def copiar_segunda():
        for i in range(1, 7):
            for k in ("on", "a0", "a1", "p0", "p1", "h"):
                V["d%d_%s" % (i, k)].set(V["d0_%s" % k].get())
    ttk.Button(t2, text="Copiar a segunda para todos os dias", command=copiar_segunda).grid(row=11, column=0, columnspan=4, sticky="w", pady=(12, 0), padx=4)
    ttk.Label(t2, text="Horas do caixa: as horas cheias em que o caixa é conferido, separadas por vírgula (ex.: 13, 14, 15, 16, 17, 18).\n"
                       "Exemplo de sábado curto: Ao chegar 09:00 a 10:30, Tarde 13:00 a 17:00, horas 13, 14, 15, 16.",
              foreground=GREY, wraplength=760, justify="left").grid(row=12, column=0, columnspan=8, sticky="w", pady=(10, 0), padx=4)

    # ---------------- Funcionários
    tf = tab("Funcionários")
    ttk.Label(tf, text="Funcionários do caixa e o turno de cada um", font=(FONT, 11, "bold")).grid(row=0, column=0, columnspan=9, sticky="w")
    ttk.Label(tf, text="Em cada dia escreva o turno no formato 09:00-13:00. Deixe vazio para folga. Cada funcionário tem os próprios "
                       "pontos, sequência e meta da semana. O app sabe quem está no caixa pelo horário.",
              foreground=GREY, wraplength=780, justify="left").grid(row=1, column=0, columnspan=9, sticky="w", pady=(0, 8))
    ttk.Label(tf, text="Nome", foreground=GREY, font=(FONT, 9, "bold")).grid(row=2, column=0, sticky="w", padx=3)
    for i in range(7):
        ttk.Label(tf, text=DIAS_NOMES[i], foreground=GREY, font=(FONT, 9, "bold")).grid(row=2, column=1 + i, sticky="w", padx=3)
    emps = cfg.get("funcionarios", [])
    emp_ids = []
    for r in range(MAX_FUNC):
        e = emps[r] if r < len(emps) else {}
        emp_ids.append(e.get("id") or "")
        V["f%d_nome" % r] = tk.StringVar(value=e.get("nome", ""))
        ttk.Entry(tf, textvariable=V["f%d_nome" % r], width=16).grid(row=3 + r, column=0, sticky="w", padx=3, pady=3)
        for i in range(7):
            sh_ = (e.get("dias") or {}).get(str(i))
            V["f%d_d%d" % (r, i)] = tk.StringVar(value=("%s-%s" % (sh_[0], sh_[1])) if sh_ else "")
            ttk.Entry(tf, textvariable=V["f%d_d%d" % (r, i)], width=11).grid(row=3 + r, column=1 + i, sticky="w", padx=3, pady=3)
    ttk.Label(tf, text="Sem nenhum funcionário cadastrado, o app funciona como antes, com um placar único.\n"
                       "No caixa, o botão Trocar funcionário permite escolher quem está atendendo se alguém cobrir o outro.",
              foreground=GREY, wraplength=780, justify="left").grid(row=3 + MAX_FUNC, column=0, columnspan=9, sticky="w", pady=(12, 0), padx=3)

    # ---------------- Maquininha e lembretes
    t3 = tab("Maquininha")
    ttk.Label(t3, text="Lembretes por horário", font=(FONT, 11, "bold")).grid(row=0, column=0, sticky="w")
    ttk.Label(t3, text="Um por linha, neste formato:   HH:MM | nome curto | texto do aviso\n"
                       "Exemplo:   10:15 | Carregar a maquininha | Confira a bateria e coloque para carregar\n"
                       "Cada lembrete fica pendente e aparece cada vez mais chamativo até ser marcado como feito.",
              foreground=GREY, wraplength=620, justify="left").grid(row=1, column=0, sticky="w", pady=(2, 8))
    t3.rowconfigure(2, weight=1)
    fr3 = ttk.Frame(t3)
    fr3.grid(row=2, column=0, sticky="nsew")
    fr3.rowconfigure(0, weight=1)
    fr3.columnconfigure(0, weight=1)
    tx_lem = tk.Text(fr3, wrap="word", font=(FONT, 11), height=10, undo=True)
    sb3 = ttk.Scrollbar(fr3, orient="vertical", command=tx_lem.yview)
    tx_lem.configure(yscrollcommand=sb3.set)
    tx_lem.grid(row=0, column=0, sticky="nsew")
    sb3.grid(row=0, column=1, sticky="ns")
    tx_lem.insert("1.0", "\n".join(" | ".join(r) for r in cfg.get("lembretes_fixos", [])))

    # ---------------- Frases e tarefas
    t4 = tab("Frases e tarefas")
    ttk.Label(t4, text="Escolha a lista que quer editar:", font=(FONT, 11, "bold")).grid(row=0, column=0, sticky="w")
    nomes = [n for _, n in LISTAS]
    sel = tk.StringVar(value=nomes[0])
    cb = ttk.Combobox(t4, textvariable=sel, values=nomes, state="readonly", width=60)
    cb.grid(row=1, column=0, sticky="w", pady=(4, 8))
    t4.rowconfigure(2, weight=1)
    fr4 = ttk.Frame(t4)
    fr4.grid(row=2, column=0, sticky="nsew")
    fr4.rowconfigure(0, weight=1)
    fr4.columnconfigure(0, weight=1)
    tx_l = tk.Text(fr4, wrap="word", font=(FONT, 11), height=12, undo=True)
    sb4 = ttk.Scrollbar(fr4, orient="vertical", command=tx_l.yview)
    tx_l.configure(yscrollcommand=sb4.set)
    tx_l.grid(row=0, column=0, sticky="nsew")
    sb4.grid(row=0, column=1, sticky="ns")

    def para_texto(chave):
        if chave == "ao_chegar":
            return "\n".join(r[1] for r in cfg["ao_chegar"])
        if chave == "conferencias":
            return "\n".join(r[1] + ((" | " + r[2]) if len(r) > 2 and r[2] else "") for r in cfg["conferencias"])
        return "\n".join(cfg.get(chave, []))
    buf = {c: para_texto(c) for c, _ in LISTAS}
    atual = {"k": LISTAS[0][0]}
    tx_l.insert("1.0", buf[atual["k"]])

    def trocar(_e=None):
        buf[atual["k"]] = tx_l.get("1.0", "end").rstrip("\n")
        novo = next(c for c, n in LISTAS if n == sel.get())
        atual["k"] = novo
        tx_l.delete("1.0", "end")
        tx_l.insert("1.0", buf[novo])
    cb.bind("<<ComboboxSelected>>", trocar)
    ttk.Label(t4, text="Dica: mudar o nome de uma tarefa de ao chegar ou conferência cria uma tarefa nova no dia. "
                       "Prefira mexer nisso antes do expediente.", foreground=GREY, wraplength=620,
              justify="left").grid(row=3, column=0, sticky="w", pady=(8, 0))

    # ---------------- Pontos e prêmio
    t5 = tab("Pontos e prêmio")
    marca(t5, 0, "Mostrar pontos e mensagens de pontos para o caixa", "mostrar", cfg.get("mostrar_pontos", True))
    spin(t5, 1, "Pontos por tarefa feita em até 5 min do horário", "p_ok", cfg.get("pontos_no_prazo", 2), 0, 100)
    spin(t5, 2, "Pontos por tarefa feita em até 15 min", "p_leve", cfg.get("pontos_atraso_leve", 1), 0, 100)
    spin(t5, 3, "Pontos por tarefa feita com mais de 15 min", "p_atr", cfg.get("pontos_atrasado", 0), 0, 100)
    spin(t5, 4, "Quantas vezes por dia a mesma conferência pontua", "combo", cfg.get("limite_pontos_conferencia_dia", 4), 1, 20)
    spin(t5, 5, "Bônus por completar todas as tarefas do dia", "p_dia", cfg.get("bonus_dia_completo", 5), 0, 500)
    spin(t5, 6, "Meta de pontos da semana (0 = sem meta)", "meta", cfg.get("meta_semana_pontos", 150), 0, 20000)
    campo(t5, 7, "Prêmio quando bater a meta da semana", "premio", cfg.get("premio_semana", ""), 46)
    ttk.Label(t5, text="Cada tarefa dá poucos pontos conforme a rapidez (feita na hora vale mais). Não existe combo: o que vale é fazer de verdade. "
                       "Se o líder marcar uma tarefa como não feita, os pontos dela são tirados. Completar o dia dá o bônus e conta na sequência. Ao chegar na meta da semana, aparece "
                       "uma comemoração com o prêmio que você escrever acima.",
              foreground=GREY, wraplength=620, justify="left").grid(row=8, column=0, columnspan=3, sticky="w", pady=(14, 0))

    # ---------------- Penalidades
    t7 = tab("Penalidades")
    marca(t7, 0, "Descontar pontos de quem demora demais para fazer uma tarefa", "pen_on", cfg.get("penalidade_ativa", True))
    spin(t7, 1, "Começa a descontar depois de", "pen_apos", cfg.get("penalidade_apos_minutos", 15), 1, 240, "minutos de atraso")
    spin(t7, 2, "Desconta a cada", "pen_cada", cfg.get("penalidade_a_cada_minutos", 10), 1, 240, "minutos a mais")
    spin(t7, 3, "Pontos descontados em cada período", "pen_pts", cfg.get("penalidade_pontos", 1), 0, 100, "pontos")
    spin(t7, 4, "Máximo descontado por tarefa", "pen_max", cfg.get("penalidade_max_por_tarefa", 3), 0, 200, "pontos")
    spin(t7, 5, "Tarefa que não foi feita de jeito nenhum", "pen_nf", cfg.get("penalidade_nao_feito", 2), 0, 200, "pontos")
    ttk.Label(t7, text="Exemplo com os valores acima: uma conferência feita 40 minutos atrasada (25 minutos além dos 15) perde 3 períodos de "
                       "10 minutos, ou seja 6 pontos. Uma tarefa que ficou o expediente inteiro sem ser feita perde 5 pontos. "
                       "O aviso vermelho mostra quanto já foi perdido, e o relatório lista cada desconto. "
                       "Os pontos nunca ficam abaixo de zero.",
              foreground=GREY, wraplength=700, justify="left").grid(row=6, column=0, columnspan=3, sticky="w", pady=(14, 0))

    # ---------------- E-mail
    t8 = tab("E-mail")
    marca(t8, 0, "Enviar o relatório do dia por e-mail, sozinho, quando o expediente acabar", "em_on", cfg.get("email_ativo", False))
    ttk.Label(t8, text="Provedor:").grid(row=1, column=0, sticky="w", pady=4)
    prov = ttk.Combobox(t8, values=["Escolha...", "Gmail", "Outlook / Hotmail", "Yahoo", "Outro"], state="readonly", width=22)
    prov.set("Escolha...")
    prov.grid(row=1, column=1, columnspan=2, sticky="w", padx=10)
    campo(t8, 2, "Servidor de e-mail (SMTP)", "em_srv", cfg.get("email_servidor", "smtp.gmail.com"), 30)
    campo(t8, 3, "Porta", "em_port", cfg.get("email_porta", 465), 8)
    ttk.Label(t8, text="Segurança").grid(row=4, column=0, sticky="w", pady=4)
    V["em_seg"] = tk.StringVar(value=cfg.get("email_seguranca", "ssl"))
    ttk.Combobox(t8, textvariable=V["em_seg"], values=["ssl", "starttls", "nenhuma"], state="readonly", width=12).grid(row=4, column=1, sticky="w", padx=10)
    campo(t8, 5, "E-mail de quem envia (usuário)", "em_user", cfg.get("email_usuario", ""), 34)
    campo(t8, 6, "Senha (no Gmail: senha de app)", "em_pass", cfg.get("email_senha", ""), 34, show="*")
    campo(t8, 7, "Mostrar como remetente (vazio = o mesmo)", "em_de", cfg.get("email_de", ""), 34)
    campo(t8, 8, "E-mail de quem recebe (vários: separe por vírgula)", "em_para", cfg.get("email_para", ""), 34)
    campo(t8, 9, "Assunto  ({data} vira a data)", "em_ass", cfg.get("email_assunto", "Relatório do Caixa - {data}"), 34)

    def escolher_prov(_e=None):
        mapa = {"Gmail": ("smtp.gmail.com", 465, "ssl"), "Outlook / Hotmail": ("smtp-mail.outlook.com", 587, "starttls"),
                "Yahoo": ("smtp.mail.yahoo.com", 465, "ssl")}
        if prov.get() in mapa:
            V["em_srv"].set(mapa[prov.get()][0])
            V["em_port"].set(str(mapa[prov.get()][1]))
            V["em_seg"].set(mapa[prov.get()][2])
    prov.bind("<<ComboboxSelected>>", escolher_prov)
    res_teste = tk.StringVar(value="")
    ttk.Label(t8, textvariable=res_teste, wraplength=620, justify="left").grid(row=11, column=0, columnspan=4, sticky="w", pady=(6, 0))

    def testar():
        try:
            import envio
        except Exception:
            res_teste.set("O arquivo envio.py não está na pasta do programa.")
            return
        c = {"email_servidor": V["em_srv"].get().strip(), "email_porta": V["em_port"].get().strip() or "465",
             "email_seguranca": "none" if V["em_seg"].get() == "nenhuma" else V["em_seg"].get(),
             "email_usuario": V["em_user"].get().strip(), "email_senha": V["em_pass"].get(),
             "email_de": V["em_de"].get().strip(), "email_para": V["em_para"].get()}
        res_teste.set("Enviando o e-mail de teste...")
        saida = []

        def run():
            try:
                envio.enviar(c, "Teste do Painel do Caixa", "Se você recebeu este e-mail, o envio automático do relatório está funcionando.", [])
                saida.append("Enviado! Confira a caixa de entrada (e o spam) de: " + c["email_para"])
            except Exception as e:
                saida.append("Não funcionou: " + envio.erro_amigavel(e))
        threading.Thread(target=run, daemon=True).start()

        def espera():
            if saida:
                res_teste.set(saida[0])
            else:
                w.after(300, espera)
        espera()
    ttk.Button(t8, text="Enviar e-mail de teste", command=testar).grid(row=10, column=0, sticky="w", pady=(12, 0))
    ttk.Label(t8, text="Gmail: ligue a verificação em duas etapas e crie uma senha de app em Conta Google > Segurança > Senhas de app. "
                       "A senha fica gravada no arquivo config.json deste computador, então use um e-mail só para isso, se puder. "
                       "O computador precisa estar ligado e com internet na hora do fechamento. Se estiver sem internet, o app tenta de novo "
                       "a cada 10 minutos.",
              foreground=GREY, wraplength=700, justify="left").grid(row=12, column=0, columnspan=4, sticky="w", pady=(10, 0))

    # ---------------- Líder e celular (nuvem)
    t9 = tab("Líder e celular")
    marca(t9, 0, "Enviar as tarefas para a nuvem para o líder ver e validar no celular", "nv_on", cfg.get("nuvem_ativa", False))
    campo(t9, 1, "Endereço do Firebase (Realtime Database)", "nv_url", cfg.get("nuvem_url", ""), 44)
    campo(t9, 2, "Código secreto da loja", "nv_cod", cfg.get("nuvem_codigo", ""), 44)
    campo(t9, 3, "Endereço da página do líder", "nv_lider", cfg.get("lider_url", ""), 44)
    marca(t9, 5, "Avisar o líder no celular (app ntfy) quando uma tarefa ficar urgente", "nt_on", cfg.get("ntfy_ativo", False))
    campo(t9, 6, "Tópico do ntfy (o líder assina este nome)", "nt_top", cfg.get("ntfy_topico", ""), 44)
    try:
        import nuvem as _nv
    except Exception:
        _nv = None
    res_nv = tk.StringVar(value="")

    def gerar_cod():
        if V["nv_cod"].get().strip() and not messagebox.askyesno("Novo código", "Trocar o código faz a página do líder atual parar de funcionar. Continuar?", parent=w):
            return
        V["nv_cod"].set(_nv.novo_codigo() if _nv else "")
        if not V["nt_top"].get().strip():
            V["nt_top"].set("caixa-" + V["nv_cod"].get()[:12])
    ttk.Button(t9, text="Gerar código", command=gerar_cod).grid(row=2, column=2, sticky="w", padx=6)

    def link_atual():
        if not _nv:
            return ""
        return _nv.link_lider({"lider_url": V["nv_lider"].get(), "nuvem_url": V["nv_url"].get(), "nuvem_codigo": V["nv_cod"].get()})

    link_var = tk.StringVar(value="")

    def copiar():
        l = link_atual()
        if not l:
            res_nv.set("Preencha o endereço do Firebase, o código e o endereço da página do líder.")
            return
        link_var.set(l)
        try:
            w.clipboard_clear()
            w.clipboard_append(l)
            w.update()
        except Exception:
            pass
        res_nv.set("Link copiado. Se ao colar não aparecer nada, selecione o link na caixa abaixo (clique e Ctrl+A, Ctrl+C) e cole no WhatsApp.")

    def abrir_no_navegador():
        import webbrowser
        l = link_atual()
        if not l:
            res_nv.set("Preencha o endereço do Firebase, o código e o endereço da página do líder.")
            return
        link_var.set(l)
        webbrowser.open(l)

    def testar_nv():
        if not _nv:
            res_nv.set("O arquivo nuvem.py não está na pasta do programa.")
            return
        res_nv.set("Testando...")
        saida = []

        def run():
            try:
                _nv.testar_conexao(V["nv_url"].get(), V["nv_cod"].get())
                saida.append("Conexão com o Firebase funcionando.")
            except Exception as e:
                saida.append("Não funcionou: " + _nv.erro_amigavel(e))
        threading.Thread(target=run, daemon=True).start()

        def espera():
            if saida:
                res_nv.set(saida[0])
            else:
                w.after(300, espera)
        espera()

    def testar_nt():
        top = V["nt_top"].get().strip()
        if not (_nv and top):
            res_nv.set("Preencha o tópico do ntfy.")
            return
        saida = []

        def run():
            try:
                _nv.testar_ntfy(top)
                saida.append("Aviso de teste enviado. Se o líder assinou o tópico no app ntfy, ele recebe agora.")
            except Exception as e:
                saida.append("Não funcionou: " + _nv.erro_amigavel(e))
        threading.Thread(target=run, daemon=True).start()

        def espera():
            if saida:
                res_nv.set(saida[0])
            else:
                w.after(300, espera)
        espera()
    ttk.Button(t9, text="Testar conexão", command=testar_nv).grid(row=4, column=0, sticky="w", pady=(10, 0))
    ttk.Button(t9, text="Copiar link do líder", command=copiar).grid(row=4, column=1, sticky="w", pady=(10, 0), padx=10)
    ttk.Button(t9, text="Testar aviso no celular", command=testar_nt).grid(row=7, column=0, sticky="w", pady=(10, 0))
    ttk.Button(t9, text="Abrir página do líder aqui", command=abrir_no_navegador).grid(row=4, column=2, sticky="w", pady=(10, 0))
    ttk.Entry(t9, textvariable=link_var, width=70, state="readonly").grid(row=10, column=0, columnspan=3, sticky="w", pady=(8, 0))
    ttk.Label(t9, textvariable=res_nv, wraplength=700, justify="left").grid(row=8, column=0, columnspan=3, sticky="w", pady=(8, 0))
    ttk.Label(t9, text="Como funciona: o caixa marca a tarefa e ela aparece na hora na página do líder. O líder toca em \"Conferido\" ou "
                       "\"Não estava feito\"; se não estava, os pontos são tirados e a tarefa volta para a lista do caixa. "
                       "O passo a passo para criar o Firebase está no arquivo LIDER.txt.",
              foreground=GREY, wraplength=700, justify="left").grid(row=9, column=0, columnspan=3, sticky="w", pady=(12, 0))

    # ---------------- Geral
    t6 = tab("Geral")
    campo(t6, 0, "Nome da loja (aparece no relatório)", "loja", cfg.get("nome_loja", ""), 34)
    campo(t6, 1, "Nome do caixa (aparece no relatório e nas frases)", "caixa", cfg.get("nome_caixa", ""), 34)
    campo(t6, 2, "Pasta dos relatórios (vazio = Área de Trabalho)", "pasta", cfg.get("pasta_relatorios", ""), 34)
    ttk.Button(t6, text="Procurar...", command=lambda: V["pasta"].set(filedialog.askdirectory(parent=w) or V["pasta"].get())).grid(row=2, column=3, padx=4)
    marca(t6, 3, "Gerar o relatório sozinho no fim do expediente", "fim", cfg.get("gerar_relatorio_no_fim", True))
    campo(t6, 4, "Senha para abrir estas configurações (vazio = sem senha)", "senha", cfg.get("senha_config", ""), 20, show="*")
    ttk.Label(t6, text="Se você colocar uma senha, só quem souber consegue mudar os avisos. Guarde a senha: "
                       "para recuperar, apague o arquivo config.json (volta tudo ao padrão).",
              foreground=GREY, wraplength=620, justify="left").grid(row=5, column=0, columnspan=4, sticky="w", pady=(14, 0))

    # ---------------- salvar
    def coletar():
        n = copy.deepcopy(cfg)
        n["aviso_aleatorio_min_minutos"] = _num("Aviso aleatório (mínimo)", V["min"].get(), 1, 240)
        n["aviso_aleatorio_max_minutos"] = _num("Aviso aleatório (máximo)", V["max"].get(), 1, 240)
        if n["aviso_aleatorio_max_minutos"] < n["aviso_aleatorio_min_minutos"]:
            raise ValueError("Aviso aleatório: o máximo não pode ser menor que o mínimo.")
        n["chance_aviso_alegre"] = _num("Chance de aviso alegre", V["chance"].get(), 0, 100)
        n["pausa_atendimento_minutos"] = _num("Pausa Cliente na frente", V["pausa"].get(), 1, 60)
        e1 = _num("Aviso laranja", V["esc1"].get(), 1, 120)
        e2 = _num("Aviso vermelho", V["esc2"].get(), 2, 240)
        if e2 <= e1:
            raise ValueError("O aviso vermelho precisa vir depois do laranja.")
        n["escalonar_apos_minutos"] = [e1, e2]
        n["repetir_urgente_minutos"] = _num("Repetir aviso vermelho", V["urg"].get(), 1, 60)
        n["adiar_minutos"] = _num("Adiar", V["adiar"].get(), 1, 60)
        n["repetir_conferencia_minutos"] = _num("Repetir conferências", V["rep"].get(), 20, 600)
        n["intervalo_entre_conferencias_minutos"] = _num("Intervalo entre conferências", V["gap"].get(), 0, 120)
        n["som"] = bool(V["som"].get())

        dias = {}
        for i in range(7):
            nm = DIAS_NOMES[i]
            on = bool(V["d%d_on" % i].get())
            a0, a1 = _hm("%s, ao chegar (início)" % nm, V["d%d_a0" % i].get()), _hm("%s, ao chegar (fim)" % nm, V["d%d_a1" % i].get())
            p0, p1 = _hm("%s, tarde (início)" % nm, V["d%d_p0" % i].get()), _hm("%s, tarde (fim)" % nm, V["d%d_p1" % i].get())
            if on and not (_min(a0) < _min(a1) <= _min(p0) < _min(p1)):
                raise ValueError("%s: horários fora de ordem. Use: ao chegar início < ao chegar fim <= tarde início < tarde fim." % nm)
            horas = set()
            for parte in V["d%d_h" % i].get().replace(";", ",").split(","):
                if parte.strip():
                    horas.add(_num("%s, horas do caixa" % nm, parte, 0, 23))
            if on and not horas:
                raise ValueError("%s: informe pelo menos uma hora do caixa, por exemplo 13, 14, 15." % nm)
            dias[str(i)] = {"aberto": on, "ao_chegar": [a0, a1], "tarde": [p0, p1], "horas": sorted(horas)}
        n["dias_semana"] = dias

        funcs, usados = [], set()
        for r in range(MAX_FUNC):
            nome = V["f%d_nome" % r].get().strip()
            if not nome:
                continue
            turnos = {}
            for i in range(7):
                t_ = _turno("%s, %s" % (nome, DIAS_NOMES[i]), V["f%d_d%d" % (r, i)].get())
                if t_:
                    turnos[str(i)] = t_
            fid = emp_ids[r] or "f" + uuid.uuid4().hex[:6]
            if fid in usados:
                fid = "f" + uuid.uuid4().hex[:6]
            usados.add(fid)
            funcs.append({"id": fid, "nome": nome, "dias": turnos})
        n["funcionarios"] = funcs

        lem = []
        for i, lin in enumerate(_linhas(tx_lem.get("1.0", "end")), start=1):
            partes = [x.strip() for x in lin.split("|")]
            if len(partes) < 2:
                raise ValueError("Maquininha, linha %d: use  HH:MM | nome | texto do aviso." % i)
            hora = _hm("Maquininha, linha %d" % i, partes[0])
            texto = partes[2] if len(partes) > 2 and partes[2] else partes[1]
            lem.append([hora, partes[1], texto])
        n["lembretes_fixos"] = lem

        buf[atual["k"]] = tx_l.get("1.0", "end").rstrip("\n")
        for chave in ("durante_atendimento", "quando_livre", "avisos_alegres", "mensagens_alegres", "mensagens_dia_completo"):
            n[chave] = _linhas(buf[chave])
        for chave, partes_min in (("ao_chegar", 2), ("conferencias", 3)):
            antigos = {r[1]: r[0] for r in cfg[chave]}
            novos, usados = [], set()
            for lin in _linhas(buf[chave]):
                if chave == "conferencias":
                    pedacos = [x.strip() for x in lin.split("|", 1)]
                    nome, obs = pedacos[0], (pedacos[1] if len(pedacos) > 1 else "")
                else:
                    nome, obs = lin, ""
                iid = antigos.get(nome)
                if iid is None or iid in usados:
                    iid = "t" + uuid.uuid4().hex[:6]
                usados.add(iid)
                novos.append([iid, nome, obs] if chave == "conferencias" else [iid, nome])
            if not novos:
                raise ValueError("A lista \"%s\" não pode ficar vazia." % dict(LISTAS)[chave])
            n[chave] = novos

        n["mostrar_pontos"] = bool(V["mostrar"].get())
        n["pontos_no_prazo"] = _num("Pontos no prazo", V["p_ok"].get(), 0, 100)
        n["pontos_atraso_leve"] = _num("Pontos com atraso leve", V["p_leve"].get(), 0, 100)
        n["pontos_atrasado"] = _num("Pontos com atraso", V["p_atr"].get(), 0, 100)
        n["limite_pontos_conferencia_dia"] = _num("Limite de pontos por conferência", V["combo"].get(), 1, 20)
        n["bonus_dia_completo"] = _num("Bônus do dia completo", V["p_dia"].get(), 0, 500)
        n["meta_semana_pontos"] = _num("Meta da semana", V["meta"].get(), 0, 20000)
        n["premio_semana"] = V["premio"].get().strip()

        n["penalidade_ativa"] = bool(V["pen_on"].get())
        n["penalidade_apos_minutos"] = _num("Penalidade: começa depois de", V["pen_apos"].get(), 1, 240)
        n["penalidade_a_cada_minutos"] = _num("Penalidade: a cada", V["pen_cada"].get(), 1, 240)
        n["penalidade_pontos"] = _num("Penalidade: pontos por período", V["pen_pts"].get(), 0, 100)
        n["penalidade_max_por_tarefa"] = _num("Penalidade: máximo por tarefa", V["pen_max"].get(), 0, 200)
        n["penalidade_nao_feito"] = _num("Penalidade: tarefa não feita", V["pen_nf"].get(), 0, 200)

        n["email_ativo"] = bool(V["em_on"].get())
        n["email_servidor"] = V["em_srv"].get().strip()
        n["email_porta"] = _num("E-mail: porta", V["em_port"].get() or "465", 1, 65535)
        n["email_seguranca"] = "none" if V["em_seg"].get() == "nenhuma" else V["em_seg"].get()
        n["email_usuario"] = V["em_user"].get().strip()
        n["email_senha"] = V["em_pass"].get()
        n["email_de"] = V["em_de"].get().strip()
        n["email_para"] = V["em_para"].get().strip()
        n["email_assunto"] = V["em_ass"].get().strip() or "Relatório do Caixa - {data}"
        if n["email_ativo"] and (not n["email_servidor"] or not n["email_para"] or not (n["email_usuario"] or n["email_de"])):
            raise ValueError("E-mail: para enviar sozinho, preencha o servidor, o e-mail de quem envia e o e-mail de quem recebe.")

        n["nuvem_ativa"] = bool(V["nv_on"].get())
        n["nuvem_url"] = V["nv_url"].get().strip().rstrip("/")
        n["nuvem_codigo"] = V["nv_cod"].get().strip()
        n["lider_url"] = V["nv_lider"].get().strip()
        n["ntfy_ativo"] = bool(V["nt_on"].get())
        n["ntfy_topico"] = V["nt_top"].get().strip()
        if n["nuvem_ativa"] and (not n["nuvem_url"].startswith("https://") or not n["nuvem_codigo"]):
            raise ValueError("Líder e celular: preencha o endereço do Firebase (começa com https://) e clique em Gerar código.")
        if n["ntfy_ativo"] and not n["ntfy_topico"]:
            raise ValueError("Líder e celular: preencha o tópico do ntfy.")

        n["nome_loja"] = V["loja"].get().strip()
        n["nome_caixa"] = V["caixa"].get().strip()
        n["pasta_relatorios"] = V["pasta"].get().strip()
        n["gerar_relatorio_no_fim"] = bool(V["fim"].get())
        n["senha_config"] = V["senha"].get()
        return n

    def salvar():
        try:
            novo = coletar()
        except ValueError as e:
            messagebox.showerror("Confira os dados", str(e), parent=w)
            return
        w.destroy()
        app.settings_win = None
        app.apply_config(novo)
        app.show("Configurações", "Salvo! As mudanças já estão valendo.", "joy", 4000, True)

    def restaurar():
        if messagebox.askyesno("Restaurar padrões", "Voltar TODAS as configurações ao padrão do programa?\n"
                               "Isso apaga as suas mudanças (e a senha).", parent=w):
            w.destroy()
            app.settings_win = None
            app.apply_config(copy.deepcopy(app.defaults))

    def fechar():
        w.destroy()
        app.settings_win = None

    w.protocol("WM_DELETE_WINDOW", fechar)
    bar = ttk.Frame(w, padding=(12, 0, 12, 12))
    bar.pack(fill="x")
    ttk.Button(bar, text="Salvar", command=salvar).pack(side="right")
    ttk.Button(bar, text="Cancelar", command=fechar).pack(side="right", padx=8)
    ttk.Button(bar, text="Restaurar padrões", command=restaurar).pack(side="left")
