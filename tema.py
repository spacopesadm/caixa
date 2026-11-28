# -*- coding: utf-8 -*-
"""Aparência do Painel do Caixa: temas prontos, fundo em degradê e botões com efeito ao passar o mouse."""
import base64
import io
import tkinter as tk
import tkinter.font as tkfont

TEMAS = {
    "Azul claro":   ("#EAF0FA", "#C9D9F2"),
    "Rosa Spaço":   ("#FDEDF4", "#F7C6DC"),
    "Lavanda":      ("#F1EBFB", "#D5C6F2"),
    "Menta":        ("#E8F6F0", "#BFE6D4"),
    "Pôr do sol":   ("#FFF1E3", "#F9C6D3"),
    "Grafite":      ("#E4E8EE", "#B9C2CF"),
    "Noite":        ("#2B3548", "#0F1623"),
    "Branco":       ("#F4F6F9", "#F4F6F9"),
}
PADRAO = {"tema_nome": "Azul claro", "tema_cor1": "#EAF0FA", "tema_cor2": "#C9D9F2", "tema_degrade": "vertical"}
DIRECOES = ("vertical", "horizontal", "diagonal", "nenhum")


def _hex_ok(c):
    c = str(c or "").strip()
    if len(c) == 7 and c[0] == "#":
        try:
            int(c[1:], 16)
            return True
        except ValueError:
            pass
    return False


AUTO = "Muda com o dia"
# (hora, cor1, cor2): madrugada -> amanhecer -> manhã -> meio-dia -> tarde -> entardecer -> anoitecer -> noite
CICLO = [
    (0.0, "#26304A", "#0D1322"),
    (5.0, "#2D3652", "#121A30"),
    (6.0, "#FFD3BE", "#B3B9EE"),
    (8.0, "#FFF1DA", "#CFE4F7"),
    (12.0, "#EAF4FF", "#C9DFF7"),
    (16.0, "#FFF0D2", "#F5D7A6"),
    (18.0, "#FFC49C", "#E58DB0"),
    (19.5, "#6F5C9E", "#2B3060"),
    (21.0, "#2B3548", "#0F1623"),
    (24.0, "#26304A", "#0D1322"),
]


def cores_do_dia(agora=None):
    """Cores do degradê para a hora do dia (suave entre um momento e outro)."""
    import datetime as _dt
    agora = agora or _dt.datetime.now()
    h = agora.hour + agora.minute / 60.0
    for (h0, a0, b0), (h1, a1, b1) in zip(CICLO, CICLO[1:]):
        if h0 <= h <= h1:
            t = (h - h0) / (h1 - h0) if h1 > h0 else 0
            return mistura(a0, a1, t), mistura(b0, b1, t)
    return CICLO[0][1], CICLO[0][2]


def cores(cfg):
    """Devolve (cor1, cor2, direcao) válidos, mesmo com configuração estragada."""
    if cfg.get("tema_nome") == AUTO:
        a, b = cores_do_dia()
        return a, b, "vertical"
    c1 = cfg.get("tema_cor1") if _hex_ok(cfg.get("tema_cor1")) else PADRAO["tema_cor1"]
    c2 = cfg.get("tema_cor2") if _hex_ok(cfg.get("tema_cor2")) else PADRAO["tema_cor2"]
    d = cfg.get("tema_degrade") if cfg.get("tema_degrade") in DIRECOES else "vertical"
    return c1, c2, d


def _rgb(c):
    return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))


def _hex(t):
    return "#%02X%02X%02X" % tuple(max(0, min(255, int(round(v)))) for v in t)


def mistura(a, b, t):
    ra, rb = _rgb(a), _rgb(b)
    return _hex([ra[i] + (rb[i] - ra[i]) * t for i in range(3)])


def escurece(c, t=0.12):
    return mistura(c, "#000000", t)


def clareia(c, t=0.12):
    return mistura(c, "#FFFFFF", t)


def luminosidade(c):
    r, g, b = _rgb(c)
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255.0


def cor_media(cfg):
    c1, c2, d = cores(cfg)
    return c1 if d == "nenhum" else mistura(c1, c2, 0.5)


def imagem_degrade(tk, largura, altura, c1, c2, direcao):
    """PhotoImage com o degradê (None se não der: aí usa-se cor lisa)."""
    largura, altura = max(2, int(largura)), max(2, int(altura))
    if direcao == "nenhum" or c1 == c2:
        return None
    try:
        from PIL import Image
        # gera pequeno e amplia: leve e sem faixas visíveis
        n = 256
        if direcao == "horizontal":
            im = Image.new("RGB", (n, 1))
            im.putdata([_rgb(mistura(c1, c2, i / (n - 1.0))) for i in range(n)])
        elif direcao == "diagonal":
            im = Image.new("RGB", (n, n))
            im.putdata([_rgb(mistura(c1, c2, (x + y) / (2.0 * (n - 1)))) for y in range(n) for x in range(n)])
        else:
            im = Image.new("RGB", (1, n))
            im.putdata([_rgb(mistura(c1, c2, i / (n - 1.0))) for i in range(n)])
        im = im.resize((largura, altura), Image.BILINEAR)
        buf = io.BytesIO()
        im.save(buf, "PNG")
        return tk.PhotoImage(data=base64.b64encode(buf.getvalue()))
    except Exception:
        return None


def hover(b, normal=None):
    """Botão plano ganha cor mais forte ao passar o mouse (funciona mesmo se o programa trocar a cor do botão)."""
    st = {}

    def entra(_e):
        try:
            if str(b.cget("state")) == "disabled":
                return
            cur = b.cget("bg")
            if not _hex_ok(cur) and not cur.startswith("#"):
                return
            st["orig"] = cur
            alvo = escurece(cur, 0.10) if luminosidade(cur) < 0.8 else escurece(cur, 0.06)
            st["hov"] = alvo
            b.configure(bg=alvo)
        except Exception:
            pass

    def sai(_e):
        try:
            if st.get("hov") and b.cget("bg") == st["hov"]:
                b.configure(bg=st["orig"])
        except Exception:
            pass
        st.clear()
    b.bind("<Enter>", entra, add="+")
    b.bind("<Leave>", sai, add="+")


def polir(raiz):
    """Percorre uma janela e dá efeito de hover e cursor de mão em todos os botões planos."""
    try:
        for f in raiz.winfo_children():
            if f.winfo_class() == "Button":
                if not getattr(f, "_hover_ok", False):
                    f._hover_ok = True
                    try:
                        f.configure(cursor="hand2", activebackground=f.cget("bg"), borderwidth=f.cget("bd"))
                    except Exception:
                        pass
                    hover(f)
            polir(f)
    except Exception:
        pass


def _pontos_arredondados(x1, y1, x2, y2, r):
    r = max(1, min(r, (x2 - x1) / 2.0, (y2 - y1) / 2.0))
    return [x1 + r, y1, x1 + r, y1, x2 - r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y1 + r, x2, y2 - r, x2, y2 - r,
            x2, y2, x2 - r, y2, x2 - r, y2, x1 + r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y2 - r, x1, y1 + r, x1, y1 + r, x1, y1]


def retangulo_arredondado(cv, x1, y1, x2, y2, r, **kw):
    return cv.create_polygon(_pontos_arredondados(x1, y1, x2, y2, r), smooth=True, **kw)


class Pilha:
    """Empilha cartões (Frames) sobre um Canvas; cada um ganha fundo arredondado com sombra suave e o degradê aparece entre eles."""

    def __init__(self, canvas, margem=18, gap=12, topo=8, ao_medir=None, cartao="#FFFFFF", sombra="#C5CCD8", borda="#E3E8F0", raio=18, pad=8):
        self.cv, self.margem, self.gap, self.topo = canvas, margem, gap, topo
        self.itens, self.ao_medir, self._agendado, self.altura = [], ao_medir, False, 0
        self.cor, self.sombra, self.borda, self.raio, self.pad = cartao, sombra, borda, raio, pad
        canvas.bind("<Configure>", lambda e: self.agendar(), add="+")

    def add(self, frame):
        sh = retangulo_arredondado(self.cv, 0, 0, 10, 10, self.raio, fill=self.sombra, outline="")
        bg = retangulo_arredondado(self.cv, 0, 0, 10, 10, self.raio, fill=self.cor, outline=self.borda)
        item = self.cv.create_window(0, 0, window=frame, anchor="nw")
        self.itens.append((item, frame, sh, bg))
        frame.bind("<Configure>", lambda e: self.agendar(), add="+")
        self.agendar()

    def recolorir(self, sombra, borda):
        self.sombra, self.borda = sombra, borda
        for item, fr, sh, bg in self.itens:
            self.cv.itemconfigure(sh, fill=sombra)
            self.cv.itemconfigure(bg, outline=borda)

    def agendar(self):
        if not self._agendado:
            self._agendado = True
            self.cv.after_idle(self.organizar)

    def organizar(self):
        self._agendado = False
        try:
            if not self.cv.winfo_exists():
                return
            larg = max(160, self.cv.winfo_width() - 2 * self.margem)
            y, p = self.topo, self.pad
            for item, fr, sh, bg in self.itens:
                h = fr.winfo_reqheight() + 2 * p
                x1, x2 = self.margem, self.margem + larg
                self.cv.coords(sh, *_pontos_arredondados(x1, y + 3, x2, y + h + 3, self.raio))
                self.cv.coords(bg, *_pontos_arredondados(x1, y, x2, y + h, self.raio))
                self.cv.coords(item, x1 + p, y + p)
                self.cv.itemconfigure(item, width=larg - 2 * p)
                y += h + self.gap
            self.altura = y
            self.cv.tag_lower("fundo")
            if self.ao_medir:
                self.ao_medir(y)
        except Exception:
            pass


class Pilula(tk.Canvas):
    """Botão de cantos arredondados (desenhado num Canvas) com efeito ao passar o mouse.
    Aceita config(text=, bg=, fg=, command=, state=) como um botão comum."""

    def __init__(self, pai, text="", command=None, bg="#E9EDF2", fg="#14202E", font=("Segoe UI", 10, "bold"),
                 padx=14, pady=6, minw=0, raio=12, fundo=None, state="normal", **_ignorado):
        if fundo is None:
            try:
                fundo = pai.cget("bg")
            except Exception:
                fundo = "#FFFFFF"
        super().__init__(pai, bg=fundo, highlightthickness=0, bd=0, cursor="hand2")
        self._d = {"text": text, "command": command, "bg": bg, "fg": fg, "state": state}
        self._fonte, self._padx, self._pady, self._minw, self._raio = tkfont.Font(font=font), padx, pady, minw, raio
        self._hover = False
        self._medir()
        self.bind("<Configure>", lambda e: self._desenha())
        self.bind("<Enter>", lambda e: self._muda_hover(True))
        self.bind("<Leave>", lambda e: self._muda_hover(False))
        self.bind("<ButtonRelease-1>", self._solta)

    def _medir(self):
        w = max(self._minw, self._fonte.measure(self._d["text"]) + 2 * self._padx)
        h = self._fonte.metrics("linespace") + 2 * self._pady
        tk.Canvas.configure(self, width=w, height=h)

    def _muda_hover(self, v):
        self._hover = v
        self._desenha()

    def _solta(self, e):
        if self._d["state"] == "disabled":
            return
        if 0 <= e.x <= self.winfo_width() and 0 <= e.y <= self.winfo_height() and self._d["command"]:
            self._d["command"]()

    def invoke(self):
        if self._d["state"] != "disabled" and self._d["command"]:
            return self._d["command"]()

    def _desenha(self):
        try:
            self.delete("all")
            w, h = self.winfo_width(), self.winfo_height()
            if w < 4 or h < 4:
                return
            bg, fg = self._d["bg"], self._d["fg"]
            if self._d["state"] == "disabled":
                bg, fg = mistura(bg, "#FFFFFF", 0.5), mistura(fg, "#FFFFFF", 0.5)
            elif self._hover:
                bg = escurece(bg, 0.10 if luminosidade(bg) < 0.8 else 0.06)
            retangulo_arredondado(self, 1, 1, w - 1, h - 1, self._raio, fill=bg, outline=bg)
            self.create_text(w / 2.0, h / 2.0, text=self._d["text"], fill=fg, font=self._fonte)
        except Exception:
            pass

    def configure(self, cnf=None, **kw):
        kw = dict(cnf or {}, **kw)
        mudou = False
        for k in ("text", "command", "bg", "fg", "state"):
            if k in kw:
                self._d[k] = kw.pop(k)
                mudou = True
        for k in ("relief", "bd", "activebackground", "activeforeground", "cursor", "padx", "pady", "font", "width", "anchor"):
            kw.pop(k, None)
        if kw:
            tk.Canvas.configure(self, **kw)
        if mudou:
            self._medir()
            self._desenha()
    config = configure

    def cget(self, k):
        if k in self._d:
            return self._d[k]
        return tk.Canvas.cget(self, k)

    def __getitem__(self, k):
        return self.cget(k)

    def __setitem__(self, k, v):
        self.configure(**{k: v})


class Marca(tk.Canvas):
    """Caixa de seleção arredondada (substitui o Checkbutton)."""

    def __init__(self, pai, text="", variable=None, command=None, font=("Segoe UI", 13), fg="#14202E",
                 cor="#13805A", fundo="#FFFFFF", **_ignorado):
        super().__init__(pai, bg=fundo, highlightthickness=0, bd=0, cursor="hand2")
        self._var = variable if variable is not None else tk.BooleanVar(value=False)
        self._cmd, self._txt, self._cor, self._fg = command, text, cor, fg
        self._fonte = tkfont.Font(font=font)
        tk.Canvas.configure(self, height=max(30, self._fonte.metrics("linespace") + 8), width=60)
        self._hover = False
        self.bind("<Configure>", lambda e: self._desenha())
        self.bind("<Button-1>", self._clica)
        self.bind("<Enter>", lambda e: self._h(True))
        self.bind("<Leave>", lambda e: self._h(False))
        try:
            self._var.trace_add("write", lambda *a: self._desenha())
        except Exception:
            pass

    def _h(self, v):
        self._hover = v
        self._desenha()

    def _clica(self, _e):
        self._var.set(not self._var.get())
        if self._cmd:
            self._cmd()

    def _desenha(self):
        try:
            self.delete("all")
            h = self.winfo_height()
            t = 22
            y = (h - t) / 2.0
            on = bool(self._var.get())
            if on:
                retangulo_arredondado(self, 2, y, 2 + t, y + t, 8, fill=self._cor, outline=self._cor)
                self.create_line(2 + 6, y + 11.5, 2 + 10, y + 15.5, 2 + 17, y + 7, fill="#FFFFFF", width=2.5, capstyle="round", joinstyle="round")
            else:
                retangulo_arredondado(self, 2, y, 2 + t, y + t, 8, fill="#FFFFFF" if not self._hover else "#F1F4F9", outline="#B8C2D1", width=2)
            self.create_text(2 + t + 12, h / 2.0, text=self._txt, anchor="w", font=self._fonte,
                             fill="#8A96A6" if on else self._fg)
        except Exception:
            pass


def botao_generico(pai, **kw):
    """Substitui tk.Button: mesmos argumentos de sempre, visual arredondado."""
    bg = kw.get("bg") or kw.get("background") or "#E9EDF2"
    fg = kw.get("fg") or kw.get("foreground") or "#14202E"
    return Pilula(pai, text=kw.get("text", ""), command=kw.get("command"), bg=bg, fg=fg,
                  font=kw.get("font") or ("Segoe UI", 10, "bold"), padx=int(kw.get("padx", 14) or 14),
                  pady=int(kw.get("pady", 6) or 6) if not isinstance(kw.get("pady"), tuple) else 6,
                  minw=int((kw.get("width") or 0)) * 8, state=kw.get("state", "normal"))
