# -*- coding: utf-8 -*-
"""
Relatório do dia do Painel do Caixa.
Gera um PDF (precisa do reportlab) ou, se faltar, uma página HTML.
Usado pelo caixa.pyw; não precisa abrir este arquivo.
"""
import datetime as dt
import html
import json
import os
import time

META_MIN = 5      # até 5 min depois do horário: no prazo
LIMITE_MIN = 15   # acima de 15 min: muito atrasado

DIAS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
         "setembro", "outubro", "novembro", "dezembro"]


def hm(ts):
    return dt.datetime.fromtimestamp(ts).strftime("%H:%M")


def minutos_txt(v):
    v = int(round(v))
    if v < 60:
        return "%d min" % v
    return "%d h %02d min" % (v // 60, v % 60)


def lembretes(cfg):
    """Lembretes fixos como (id, minuto, nome com hora)."""
    out = []
    for row in cfg.get("lembretes_fixos", []):
        try:
            hora, nome = row[0].strip(), row[1]
            out.append(("lem" + hora.replace(":", ""), _to_min(hora), "%s (%s)" % (nome, hora)))
        except Exception:
            pass
    return out


def situacao(delay):
    if delay <= META_MIN:
        return "No prazo"
    if delay <= LIMITE_MIN:
        return "Atrasou"
    return "Muito atrasado"


def _to_min(s):
    h, m = s.split(":")
    return int(h) * 60 + int(m)


# ------------------------------------------------------------------ dados
def coletar(state, cfg, agora=None):
    agora = agora or time.time()
    dia = dt.date.fromisoformat(state["date"])
    cfg = dict(cfg)
    sc = state.get("sched") or {}            # horário que valia naquele dia da semana
    for k in ("ao_chegar_horario", "tarde_horario", "horas_caixa"):
        if sc.get(k):
            cfg[k] = sc[k]
    nowd = dt.datetime.fromtimestamp(agora)
    m_agora = nowd.hour * 60 + nowd.minute if nowd.date() == dia else 24 * 60

    linhas = []
    for e in sorted(state.get("log", []), key=lambda x: x["done"]):
        atraso = max(0.0, (e["done"] - e["due"]) / 60.0)
        linhas.append({
            "tipo": e["k"], "id": str(e["id"]), "nome": e["nome"], "previsto": e["due"], "feito": e["done"],
            "atraso": atraso, "situacao": situacao(atraso), "nivel": e.get("nivel", 0), "adiou": e.get("adiou", 0),
            "pts": e.get("pts"), "pen": e.get("pen", 0), "func_id": e.get("func"),
        })

    feitos_am = {l["id"] for l in linhas if l["tipo"] == "am"} | {k for k, v in state.get("am", {}).items() if v}
    feitos_cx = {l["id"] for l in linhas if l["tipo"] == "cx"} | {k for k, v in state.get("cx", {}).items() if v}
    feitos_cf = {l["id"] for l in linhas if l["tipo"] == "conf"} | {k for k, v in state.get("last", {}).items() if v}

    pendentes, total = [], 0
    for iid, nome in cfg["ao_chegar"]:
        total += 1
        if iid not in feitos_am:
            pendentes.append(nome)
    for h in cfg["horas_caixa"]:
        if h * 60 <= m_agora:
            total += 1
            if str(h) not in feitos_cx:
                pendentes.append("Caixa das %dh" % h)
    for row in cfg["conferencias"]:
        total += 1
        if row[0] not in feitos_cf:
            pendentes.append(row[1])
    feitos_lem = {l["id"] for l in linhas if l["tipo"] == "lem"} | {k for k, v in state.get("lem", {}).items() if v}
    for lid, mn, nome in lembretes(cfg):
        if mn <= m_agora:
            total += 1
            if lid not in feitos_lem:
                pendentes.append(nome)
    concluidas = total - len(pendentes)

    atrasos = [l["atraso"] for l in linhas]
    media = sum(atrasos) / len(atrasos) if atrasos else 0.0
    no_prazo = sum(1 for a in atrasos if a <= META_MIN)
    vermelhos = sum(1 for l in linhas if l["nivel"] >= 2)
    adiadas = sum(l["adiou"] for l in linhas)

    horas = []
    for h in cfg["horas_caixa"]:
        l = next((x for x in linhas if x["tipo"] == "cx" and x["id"] == str(h)), None)
        if l:
            horas.append((h, l["atraso"]))
        elif h * 60 <= m_agora:
            horas.append((h, None))      # faltou
        else:
            horas.append((h, -1))        # ainda não chegou a hora

    melhorar, fortes = analisar(linhas, pendentes, vermelhos, adiadas)

    emps = [e for e in cfg.get("funcionarios", []) if str(e.get("nome", "")).strip()]
    nomes = {e["id"]: e["nome"] for e in emps}
    penal = list(state.get("penal", []))
    for l in linhas:
        l["func"] = nomes.get(l["func_id"], "")
    perda_demora = sum(l["pen"] or 0 for l in linhas)
    perda_nao_feito = sum(x.get("pen", 0) for x in penal)
    perdas = [(l["nome"], l["func"], "Demorou %s" % minutos_txt(l["atraso"]), l["pen"]) for l in linhas if l["pen"]]
    perdas += [(x.get("nome", ""), nomes.get(x.get("func"), ""), x.get("motivo", "Não feito"), x.get("pen", 0)) for x in penal]
    por_func = []
    pf = state.get("pts_func", {})
    for e in emps:
        mine = [l for l in linhas if l["func_id"] == e["id"]]
        perd = sum(l["pen"] or 0 for l in mine) + sum(x.get("pen", 0) for x in penal if x.get("func") == e["id"])
        if not mine and not pf.get(e["id"]) and not perd:
            continue
        por_func.append({"nome": e["nome"], "tarefas": len(mine),
                         "media": (sum(l["atraso"] for l in mine) / len(mine)) if mine else None,
                         "pontos": pf.get(e["id"], 0), "perdidos": perd})
    if perda_demora + perda_nao_feito:
        melhorar.append("Pontos perdidos hoje: %d (demora: %d, tarefa não feita: %d)." %
                        (perda_demora + perda_nao_feito, perda_demora, perda_nao_feito))
    pi = state.get("placar_info") or {}
    if pi.get("sequencia", 0) >= 2:
        fortes.append("Sequência de %d dias com todas as tarefas concluídas." % pi["sequencia"])
    if pi.get("meta") and pi.get("semana", 0) >= pi["meta"]:
        fortes.append("Meta da semana batida (%d de %d pontos)." % (pi["semana"], pi["meta"]))

    return {
        "dia": dia, "loja": cfg.get("nome_loja", ""), "caixa": cfg.get("nome_caixa", ""),
        "linhas": linhas, "pendentes": pendentes, "total": total, "concluidas": concluidas,
        "media": media, "no_prazo": no_prazo, "vermelhos": vermelhos, "adiadas": adiadas,
        "horas": horas, "avisos": state.get("shown", 0), "confirmados": state.get("ok", 0),
        "pausas": state.get("pausas", 0), "melhorar": melhorar, "fortes": fortes,
        "gerado": agora, "placar": pi, "emps": emps, "por_func": por_func, "perdas": perdas,
        "perda_total": perda_demora + perda_nao_feito, "perda_demora": perda_demora, "perda_nao_feito": perda_nao_feito,
        "fechado": bool(sc) and sc.get("aberto") is False,
    }


def analisar(linhas, pendentes, vermelhos, adiadas):
    """Gera os textos de 'o que melhorar' e 'pontos fortes' a partir dos números do dia."""
    melhorar, fortes = [], []
    if pendentes:
        melhorar.append("Não foi feito hoje: %s." % ", ".join(pendentes))

    grupos = {}
    for l in linhas:
        nome = "Abertura" if l["tipo"] == "am" else ("Caixa de hora em hora" if l["tipo"] == "cx" else l["nome"])
        grupos.setdefault(nome, []).append(l["atraso"])
    resumo = []
    for nome, v in grupos.items():
        valor = max(v) if nome == "Abertura" else sum(v) / len(v)   # abertura: tempo até ficar completa
        resumo.append((valor, nome))
    resumo.sort(reverse=True)

    leves = []
    for valor, nome in resumo:
        if nome == "Abertura":
            if valor > META_MIN:
                melhorar.append("Abertura: o checklist só ficou completo %s depois do horário de abrir." % minutos_txt(valor))
        elif valor > LIMITE_MIN:
            melhorar.append("%s: demorou em média %s, acima do limite de %d min. Prioridade para melhorar." %
                            (nome, minutos_txt(valor), LIMITE_MIN))
        elif valor > META_MIN:
            leves.append("%s (%s)" % (nome, minutos_txt(valor)))
    if leves:
        melhorar.append("Dá para chegar a até %d min em: %s." % (META_MIN, ", ".join(leves[:4]) + ("..." if len(leves) > 4 else "")))

    cx = [l for l in linhas if l["tipo"] == "cx"]
    if cx:
        pior = max(cx, key=lambda x: x["atraso"])
        if pior["atraso"] > LIMITE_MIN:
            melhorar.append("O caixa mais atrasado foi o das %sh (%s)." % (pior["id"], minutos_txt(pior["atraso"])))
    if vermelhos:
        melhorar.append("%d %s ao aviso vermelho (mais de 8 minutos sem ser feita)." %
                        (vermelhos, "tarefa chegou" if vermelhos == 1 else "tarefas chegaram"))
    if adiadas:
        melhorar.append("O aviso foi adiado %d %s; adiar atrasa o fechamento do caixa." %
                        (adiadas, "vez" if adiadas == 1 else "vezes"))
    if not melhorar:
        melhorar.append("Nenhum ponto crítico hoje. Manter o ritmo.")
    melhorar = melhorar[:6]

    ok = [l for l in linhas if l["atraso"] <= META_MIN]
    if ok:
        fortes.append("%d de %d tarefas feitas em até %d min do horário." % (len(ok), len(linhas), META_MIN))
    if linhas:
        rap = min(linhas, key=lambda x: x["atraso"])
        fortes.append("Mais rápido do dia: %s (%s)." % (rap["nome"], "na hora" if rap["atraso"] < 1 else minutos_txt(rap["atraso"])))
    if linhas and not pendentes:
        fortes.append("Todas as tarefas do dia foram concluídas.")
    return melhorar, fortes


# ------------------------------------------------------------------ PDF
def render_pdf(d, caminho):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfbase.pdfmetrics import stringWidth
    from reportlab.graphics.shapes import Drawing, Line, Rect, String
    from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    INK = colors.HexColor("#14202E")
    GREY = colors.HexColor("#5B6878")
    LINE = colors.HexColor("#CBD3DE")
    PINK = colors.HexColor("#E0246F")
    GREEN = colors.HexColor("#13805A")
    AMBER = colors.HexColor("#D98A00")
    RED = colors.HexColor("#C8102E")
    PAPER = colors.HexColor("#F3F5F8")

    def cor(v):
        return GREEN if v <= META_MIN else (AMBER if v <= LIMITE_MIN else RED)

    W = A4[0] - 36 * mm
    base = ParagraphStyle("b", fontName="Helvetica", fontSize=10, leading=14, textColor=INK)
    small = ParagraphStyle("s", parent=base, fontSize=8.5, leading=11, textColor=GREY)
    h1 = ParagraphStyle("h1", parent=base, fontName="Helvetica-Bold", fontSize=24, leading=28)
    h2 = ParagraphStyle("h2", parent=base, fontName="Helvetica-Bold", fontSize=12.5, leading=16, spaceBefore=14, spaceAfter=6)
    h2k = ParagraphStyle("h2k", parent=h2, keepWithNext=1)
    smallk = ParagraphStyle("smallk", parent=small, keepWithNext=1, spaceAfter=4)
    item = ParagraphStyle("i", parent=base, leftIndent=12, bulletIndent=0, spaceAfter=3)

    dia = d["dia"]
    titulo = "%s, %d de %s de %d" % (DIAS[dia.weekday()], dia.day, MESES[dia.month - 1], dia.year)
    quem = " · ".join(x for x in [("Loja: " + d["loja"]) if d["loja"] else "", ("Caixa: " + d["caixa"]) if d["caixa"] else ""] if x)

    story = []
    story.append(Paragraph("Relatório do Caixa", h1))
    story.append(Paragraph(titulo + (" · " + quem if quem else ""), ParagraphStyle("sub", parent=base, textColor=GREY, spaceBefore=2)))
    story.append(Spacer(1, 10))

    # indicadores
    big = ParagraphStyle("big", parent=base, fontName="Helvetica-Bold", fontSize=20, leading=24)

    def tile(valor, rotulo, cor_v=INK):
        return [Paragraph('<font color="%s">%s</font>' % (cor_v.hexval().replace("0x", "#"), html.escape(valor)), big),
                Paragraph(html.escape(rotulo), small)]
    pct = int(round(100.0 * d["concluidas"] / d["total"])) if d["total"] else 0
    media_txt = minutos_txt(d["media"]) if d["linhas"] else "-"
    tiles = [
        tile("%d de %d" % (d["concluidas"], d["total"]), "tarefas concluídas (%d%%)" % pct, GREEN if pct == 100 else INK),
        tile(media_txt, "demora média após o horário", cor(d["media"]) if d["linhas"] else INK),
        tile("%d de %d" % (d["no_prazo"], len(d["linhas"])), "feitas em até %d min" % META_MIN),
        tile(str(d["vermelhos"]), "chegaram ao aviso vermelho", RED if d["vermelhos"] else INK),
    ]
    t = Table([tiles], colWidths=[W / 4.0] * 4)
    t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.6, LINE), ("INNERGRID", (0, 0), (-1, -1), 0.6, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("BACKGROUND", (0, 0), (-1, -1), PAPER),
        ("LEFTPADDING", (0, 0), (-1, -1), 9), ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(t)
    story.append(Spacer(1, 4))
    story.append(Paragraph("Avisos mostrados: %d · confirmados: %d · pausas &quot;cliente na frente&quot;: %d · adiamentos: %d" %
                           (d["avisos"], d["confirmados"], d["pausas"], d["adiadas"]), small))

    pi = d.get("placar") or {}
    if pi:
        partes = ["Pontos do dia: %d" % pi.get("pontos", 0), "Nível: %s" % pi.get("nivel", "-"),
                  "Sequência: %d %s" % (pi.get("sequencia", 0), "dia" if pi.get("sequencia", 0) == 1 else "dias")]
        if pi.get("meta"):
            partes.append("Semana: %d de %d pontos" % (pi.get("semana", 0), pi["meta"]))
        story.append(Paragraph(html.escape(" · ".join(partes)), small))

    if d["perda_total"]:
        story.append(Paragraph("Pontos perdidos por demora ou tarefa não feita: %d" % d["perda_total"], small))

    # o que melhorar
    bloco = [Paragraph("O que precisa melhorar", h2)]
    for s in d["melhorar"]:
        bloco.append(Paragraph(html.escape(s), item, bulletText="•"))
    story.append(KeepTogether(bloco))
    if d["fortes"]:
        bloco = [Paragraph("Pontos fortes do dia", h2)]
        for s in d["fortes"]:
            bloco.append(Paragraph(html.escape(s), item, bulletText="•"))
        story.append(KeepTogether(bloco))

    cell = ParagraphStyle("c", parent=base, fontSize=9, leading=11)
    def tabela(linhas_t, larguras, extra=()):
        t_ = Table(linhas_t, colWidths=larguras, repeatRows=1)
        t_.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("TEXTCOLOR", (0, 0), (-1, 0), GREY), ("LINEBELOW", (0, 0), (-1, 0), 1, INK),
            ("LINEBELOW", (0, 1), (-1, -1), 0.4, LINE), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ] + list(extra)))
        return t_

    if d["por_func"]:
        story.append(Paragraph("Por funcionário", h2k))
        lf = [["Funcionário", "Tarefas feitas", "Demora média", "Pontos do dia", "Pontos perdidos"]]
        ex = []
        for i, f in enumerate(d["por_func"], start=1):
            lf.append([Paragraph(html.escape(f["nome"]), cell), str(f["tarefas"]),
                       minutos_txt(f["media"]) if f["media"] is not None else "-", str(f["pontos"]),
                       ("-%d" % f["perdidos"]) if f["perdidos"] else "0"])
            if f["perdidos"]:
                ex.append(("TEXTCOLOR", (4, i), (4, i), RED))
        story.append(tabela(lf, [W * 0.32, W * 0.16, W * 0.18, W * 0.17, W * 0.17], ex))
    if d["perdas"]:
        story.append(Paragraph("Pontos perdidos", h2k))
        lp = [["Tarefa", "Funcionário", "Motivo", "Pontos"]]
        for nome, quem_, motivo, n_ in d["perdas"]:
            lp.append([Paragraph(html.escape(nome), cell), Paragraph(html.escape(quem_ or "-"), cell),
                       Paragraph(html.escape(motivo), cell), "-%d" % n_])
        story.append(tabela(lp, [W * 0.38, W * 0.22, W * 0.28, W * 0.12], [("TEXTCOLOR", (3, 1), (3, -1), RED)]))

    # gráfico 1: demora por tarefa
    story.append(Paragraph("Tempo de demora por tarefa", h2k))
    story.append(Paragraph("Quanto tempo passou entre o horário previsto e a conclusão. Verde: até %d min. Amarelo: até %d min. Vermelho: mais que isso ou não feito." %
                           (META_MIN, LIMITE_MIN), smallk))
    barras = []
    cont = {}
    for l in d["linhas"]:
        nome = l["nome"]
        n_igual = sum(1 for x in d["linhas"] if x["nome"] == nome and x["tipo"] == "conf")
        if l["tipo"] == "conf" and n_igual > 1:
            nome = "%s (%s)" % (nome, hm(l["feito"]))
        barras.append((nome, l["atraso"]))
    barras.sort(key=lambda x: x[1], reverse=True)
    barras = [(n, None) for n in d["pendentes"]] + barras
    n_cortadas = 0
    if len(barras) > 30:            # o gráfico precisa caber numa página
        n_cortadas = len(barras) - 30
        barras = barras[:30]
    if not barras:
        story.append(Paragraph("Nenhuma tarefa registrada até agora.", base))
    else:
        row_h, lab_w, val_w = 17, 175, 62
        area = W - lab_w - val_w
        maximo = max([v for _, v in barras if v is not None] + [LIMITE_MIN + 5])
        maximo = min(int(((maximo + 4) // 5) * 5), 60)   # acima de 60 min a barra é cortada
        alt = row_h * len(barras) + 26
        g = Drawing(W, alt)
        topo = alt - 4
        for xv, rot, c in ((META_MIN, "meta %d min" % META_MIN, GREEN), (LIMITE_MIN, "limite %d min" % LIMITE_MIN, RED)):
            x = lab_w + area * xv / float(maximo)
            g.add(Line(x, 16, x, topo, strokeColor=c, strokeWidth=0.6, strokeDashArray=[2, 2]))
            g.add(String(x, 4, rot, fontName="Helvetica", fontSize=7, fillColor=c, textAnchor="middle"))
        for i, (nome, v) in enumerate(barras):
            y = topo - (i + 1) * row_h + 3
            txt = nome
            while stringWidth(txt, "Helvetica", 8.5) > lab_w - 10 and len(txt) > 4:
                txt = txt[:-2]
            if txt != nome:
                txt = txt.rstrip() + "..."
            g.add(String(lab_w - 6, y + 3, txt, fontName="Helvetica", fontSize=8.5, fillColor=INK, textAnchor="end"))
            if v is None:
                g.add(Rect(lab_w, y, area, 11, fillColor=None, strokeColor=RED, strokeWidth=0.8, strokeDashArray=[3, 2]))
                g.add(String(lab_w + 6, y + 3, "NÃO FEITO", fontName="Helvetica-Bold", fontSize=7.5, fillColor=RED))
            else:
                w = max(1.5, area * min(v, maximo) / float(maximo))
                g.add(Rect(lab_w, y, w, 11, fillColor=cor(v), strokeColor=None))
                rot = "na hora" if v < 1 else minutos_txt(v)
                if v > maximo:   # barra cortada: o valor vai dentro dela
                    g.add(String(lab_w + w - 5, y + 3, rot, fontName="Helvetica-Bold", fontSize=8,
                                 fillColor=colors.white, textAnchor="end"))
                else:
                    g.add(String(lab_w + w + 5, y + 3, rot, fontName="Helvetica-Bold", fontSize=8, fillColor=INK))
        story.append(g)
        if n_cortadas:
            story.append(Paragraph("(+ %d registros menores não aparecem no gráfico, mas estão na tabela abaixo.)" % n_cortadas, smallk))

    # gráfico 2: caixa por hora
    story.append(Paragraph("Caixa de hora em hora", h2k))
    story.append(Paragraph("Atraso na conferência do caixa em cada hora cheia.", smallk))
    n = len(d["horas"])
    if n:
        gh = Drawing(W, 120)
        area_h = W - 40
        colw = area_h / float(n)
        maxh = max([v for _, v in d["horas"] if v not in (None, -1)] + [LIMITE_MIN + 5])
        maxh = min(int(((maxh + 4) // 5) * 5), 60)
        base_y, alt_barra = 22, 82
        for xv, c in ((META_MIN, GREEN), (LIMITE_MIN, RED)):
            y = base_y + alt_barra * xv / float(maxh)
            gh.add(Line(0, y, area_h, y, strokeColor=c, strokeWidth=0.6, strokeDashArray=[2, 2]))
            gh.add(String(area_h + 4, y - 2.5, "%d min" % xv, fontName="Helvetica", fontSize=7, fillColor=c))
        gh.add(Line(0, base_y, area_h, base_y, strokeColor=LINE, strokeWidth=0.8))
        for i, (h, v) in enumerate(d["horas"]):
            cx = colw * i + colw / 2.0
            gh.add(String(cx, 8, "%dh" % h, fontName="Helvetica-Bold", fontSize=9, fillColor=INK, textAnchor="middle"))
            if v is None:
                gh.add(String(cx, base_y + 22, "faltou", fontName="Helvetica-Bold", fontSize=8.5, fillColor=RED, textAnchor="middle"))
            elif v == -1:
                gh.add(String(cx, base_y + 6, "-", fontName="Helvetica", fontSize=9, fillColor=GREY, textAnchor="middle"))
            else:
                hb = max(2, alt_barra * min(v, maxh) / float(maxh))
                gh.add(Rect(cx - colw * 0.27, base_y, colw * 0.54, hb, fillColor=cor(v), strokeColor=None))
                gh.add(String(cx, base_y + hb + 4, "na hora" if v < 1 else minutos_txt(v), fontName="Helvetica-Bold",
                              fontSize=8, fillColor=INK, textAnchor="middle"))
        story.append(gh)

    # tabela
    story.append(Paragraph("Detalhe das tarefas", h2))
    com_quem = bool(d["emps"])
    cab = ["Tarefa"] + (["Quem"] if com_quem else []) + ["Previsto", "Concluído", "Demora", "Situação", "Pontos"]
    linhas = [cab]
    estilos = []
    col_sit = cab.index("Situação")
    for i, l in enumerate(d["linhas"], start=1):
        pts = ("%+d" % l["pts"] + (" (-%d)" % l["pen"] if l["pen"] else "")) if l["pts"] is not None else "-"
        linha = [Paragraph(html.escape(l["nome"]), cell)] + ([Paragraph(html.escape(l["func"] or "-"), cell)] if com_quem else []) + [
            hm(l["previsto"]), hm(l["feito"]), "na hora" if l["atraso"] < 1 else minutos_txt(l["atraso"]), l["situacao"], pts]
        linhas.append(linha)
        estilos.append(("TEXTCOLOR", (col_sit, i), (col_sit, i), cor(l["atraso"])))
        estilos.append(("FONTNAME", (col_sit, i), (col_sit, i), "Helvetica-Bold"))
    for nome in d["pendentes"]:
        i = len(linhas)
        linhas.append([Paragraph(html.escape(nome), cell)] + (["-"] if com_quem else []) + ["-", "-", "-", "Não feito", "-"])
        estilos.append(("TEXTCOLOR", (col_sit, i), (col_sit, i), RED))
        estilos.append(("FONTNAME", (col_sit, i), (col_sit, i), "Helvetica-Bold"))
    if com_quem:
        larg = [W * 0.27, W * 0.15, W * 0.10, W * 0.11, W * 0.11, W * 0.14, W * 0.12]
    else:
        larg = [W * 0.38, W * 0.12, W * 0.13, W * 0.12, W * 0.13, W * 0.12]
    story.append(tabela(linhas, larg, estilos))

    def rodape(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(PINK)
        canvas.rect(18 * mm, A4[1] - 10 * mm, 22 * mm, 3 * mm, stroke=0, fill=1)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(GREY)
        canvas.drawString(18 * mm, 10 * mm, "Painel do Caixa · gerado em %s às %s" %
                          (dt.datetime.fromtimestamp(d["gerado"]).strftime("%d/%m/%Y"), hm(d["gerado"])))
        canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, "Página %d" % doc.page)
        canvas.restoreState()

    doc = SimpleDocTemplate(caminho, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=18 * mm, bottomMargin=18 * mm, title="Relatório do Caixa " + dia.isoformat(),
                            author="Painel do Caixa")
    doc.build(story, onFirstPage=rodape, onLaterPages=rodape)


# ------------------------------------------------------------------ HTML (se faltar o reportlab)
def render_html(d, caminho):
    dia = d["dia"]
    def cor(v):
        return "#13805A" if v <= META_MIN else ("#D98A00" if v <= LIMITE_MIN else "#C8102E")
    mx = max([l["atraso"] for l in d["linhas"]] + [LIMITE_MIN + 5])
    barras = ""
    for l in d["linhas"]:
        barras += '<div class="r"><span>%s</span><i style="width:%.0f%%;background:%s"></i><b>%s</b></div>' % (
            html.escape(l["nome"]), max(1, 100 * l["atraso"] / mx), cor(l["atraso"]), minutos_txt(l["atraso"]))
    for n in d["pendentes"]:
        barras += '<div class="r"><span>%s</span><b style="color:#C8102E">NÃO FEITO</b></div>' % html.escape(n)
    lis = lambda xs: "".join("<li>%s</li>" % html.escape(x) for x in xs)
    page = """<!doctype html><html lang="pt-BR"><meta charset="utf-8"><title>Relatório do Caixa</title>
<style>body{font:15px/1.5 Segoe UI,Arial,sans-serif;color:#14202E;max-width:760px;margin:24px auto;padding:0 16px}
h1{margin:0}.r{display:flex;align-items:center;gap:10px;margin:4px 0}.r span{width:230px}.r i{display:block;height:12px}
.k{display:flex;gap:12px;flex-wrap:wrap}.k div{border:1px solid #CBD3DE;padding:10px 14px;background:#F3F5F8}.k b{font-size:22px;display:block}</style>
<h1>Relatório do Caixa</h1><p>%s, %d de %s de %d %s</p>
<div class="k"><div><b>%d de %d</b>tarefas concluídas</div><div><b>%s</b>demora média</div><div><b>%d</b>avisos vermelhos</div></div>
<h2>Tempo de demora por tarefa</h2>%s<h2>O que precisa melhorar</h2><ul>%s</ul><h2>Pontos fortes</h2><ul>%s</ul></html>""" % (
        DIAS[dia.weekday()], dia.day, MESES[dia.month - 1], dia.year, html.escape(d["loja"]),
        d["concluidas"], d["total"], minutos_txt(d["media"]) if d["linhas"] else "-", d["vermelhos"],
        barras, lis(d["melhorar"]), lis(d["fortes"]))
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(page)


# ------------------------------------------------------------------ resumo em texto (corpo do e-mail)
def resumo_texto(state, cfg, agora=None):
    d = coletar(state, cfg, agora)
    dia = d["dia"]
    pct = int(round(100.0 * d["concluidas"] / d["total"])) if d["total"] else 0
    L = []
    if d["loja"]:
        L.append(d["loja"])
    L.append("Relatório do caixa - %s, %d de %s de %d" % (DIAS[dia.weekday()], dia.day, MESES[dia.month - 1], dia.year))
    L.append("")
    L.append("Tarefas concluídas: %d de %d (%d%%)" % (d["concluidas"], d["total"], pct))
    if d["linhas"]:
        L.append("Demora média após o horário: %s" % minutos_txt(d["media"]))
        L.append("Feitas em até %d min: %d de %d" % (META_MIN, d["no_prazo"], len(d["linhas"])))
    L.append("Chegaram ao aviso vermelho: %d" % d["vermelhos"])
    if d["perda_total"]:
        L.append("Pontos perdidos: %d" % d["perda_total"])
    for f in d["por_func"]:
        L.append("- %s: %d pontos, %d tarefas, perdeu %d" % (f["nome"], f["pontos"], f["tarefas"], f["perdidos"]))
    if d["pendentes"]:
        L.append("")
        L.append("Não foi feito: " + ", ".join(d["pendentes"]) + ".")
    L.append("")
    L.append("O que precisa melhorar:")
    L += ["- " + x for x in d["melhorar"]]
    if d["fortes"]:
        L.append("")
        L.append("Pontos fortes:")
        L += ["- " + x for x in d["fortes"]]
    L.append("")
    L.append("O relatório completo, com gráficos, está no arquivo em anexo.")
    return "\n".join(L)


# ------------------------------------------------------------------ entrada
def gerar(state, cfg, pasta, base_dir, agora=None):
    """Gera o relatório do dia e devolve o caminho do arquivo."""
    d = coletar(state, cfg, agora)
    os.makedirs(pasta, exist_ok=True)
    nome = "Relatorio-Caixa-%s" % d["dia"].isoformat()
    try:  # cópia dos números do dia, para comparar com outros dias depois
        hist = os.path.join(base_dir, "historico")
        os.makedirs(hist, exist_ok=True)
        with open(os.path.join(hist, d["dia"].isoformat() + ".json"), "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    try:
        caminho = os.path.join(pasta, nome + ".pdf")
        render_pdf(d, caminho)
    except ImportError:
        caminho = os.path.join(pasta, nome + ".html")
        render_html(d, caminho)
    return caminho
