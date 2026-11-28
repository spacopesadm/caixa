# -*- coding: utf-8 -*-
"""Aparência do Painel do Caixa: temas prontos, fundo em degradê e botões com efeito ao passar o mouse."""
import base64
import io

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


def cores(cfg):
    """Devolve (cor1, cor2, direcao) válidos, mesmo com configuração estragada."""
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


class Pilha:
    """Empilha cartões (Frames) sobre um Canvas, deixando o fundo/degradê aparecer entre eles."""

    def __init__(self, canvas, margem=18, gap=10, topo=10, ao_medir=None):
        self.cv, self.margem, self.gap, self.topo = canvas, margem, gap, topo
        self.itens, self.ao_medir, self._agendado, self.altura = [], ao_medir, False, 0
        canvas.bind("<Configure>", lambda e: self.agendar(), add="+")

    def add(self, frame):
        item = self.cv.create_window(0, 0, window=frame, anchor="nw")
        self.itens.append((item, frame))
        frame.bind("<Configure>", lambda e: self.agendar(), add="+")
        self.agendar()

    def agendar(self):
        if not self._agendado:
            self._agendado = True
            self.cv.after_idle(self.organizar)

    def organizar(self):
        self._agendado = False
        try:
            if not self.cv.winfo_exists():
                return
            larg = max(120, self.cv.winfo_width() - 2 * self.margem)
            y = self.topo
            for item, fr in self.itens:
                self.cv.coords(item, self.margem, y)
                self.cv.itemconfigure(item, width=larg)
                y += fr.winfo_reqheight() + self.gap
            self.altura = y
            if self.ao_medir:
                self.ao_medir(y)
        except Exception:
            pass
