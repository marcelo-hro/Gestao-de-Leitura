"""Importação em lote de capítulos a partir de arquivos EPUB.

Somente biblioteca padrão: ``zipfile`` (sem extrair para o disco),
``xml.etree`` para container/OPF/NCX (com bloqueio de declarações de
entidade) e ``html.parser`` para os documentos XHTML. Nenhuma URL externa é
carregada.
"""

import json
import posixpath
import re
import unicodedata
import zipfile
from dataclasses import dataclass, field
from datetime import timedelta
from difflib import SequenceMatcher
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urldefrag
from xml.etree import ElementTree as ET

from django.conf import settings
from django.db import transaction
from django.utils import timezone


class EpubInvalido(Exception):
    """Erro de validação com mensagem em português para o usuário."""


# ---------------------------------------------------------------------------
# Leitura segura do ZIP
# ---------------------------------------------------------------------------

_RE_ENTIDADE = re.compile(rb"<!ENTITY", re.IGNORECASE)


class LeitorEpub:
    def __init__(self, arquivo):
        limite = settings.EPUB_MAX_UPLOAD_SIZE
        tamanho = getattr(arquivo, "size", None)
        if tamanho is not None and tamanho > limite:
            raise EpubInvalido(
                f"O arquivo excede o limite de {limite // (1024 * 1024)} MB."
            )
        try:
            arquivo.seek(0)
            assinatura = arquivo.read(4)
            arquivo.seek(0)
        except (OSError, AttributeError):
            raise EpubInvalido("Não foi possível ler o arquivo enviado.")
        if assinatura[:2] != b"PK":
            raise EpubInvalido("O arquivo enviado não é um EPUB válido (ZIP).")
        try:
            self.zip = zipfile.ZipFile(arquivo)
        except (zipfile.BadZipFile, OSError, ValueError):
            raise EpubInvalido("O arquivo enviado está corrompido ou não é um EPUB.")

        infos = self.zip.infolist()
        if len(infos) > settings.EPUB_MAX_ARQUIVOS:
            raise EpubInvalido(
                "O EPUB contém arquivos internos demais "
                f"(máximo {settings.EPUB_MAX_ARQUIVOS})."
            )
        total = sum(i.file_size for i in infos)
        if total > settings.EPUB_MAX_DESCOMPACTADO:
            raise EpubInvalido(
                "O conteúdo descompactado do EPUB excede o limite de "
                f"{settings.EPUB_MAX_DESCOMPACTADO // (1024 * 1024)} MB."
            )
        self.infos = {i.filename: i for i in infos}
        self.lido = 0

        if "mimetype" in self.infos:
            tipo = self.ler("mimetype").strip()
            if tipo != b"application/epub+zip":
                raise EpubInvalido("O arquivo não declara o tipo application/epub+zip.")
        if "META-INF/container.xml" not in self.infos:
            raise EpubInvalido("EPUB inválido: META-INF/container.xml ausente.")

    def existe(self, nome):
        return nome in self.infos

    def ler(self, nome):
        info = self.infos.get(nome)
        if info is None:
            raise EpubInvalido(f"EPUB inválido: arquivo interno ausente ({nome}).")
        if info.flag_bits & 0x1:
            raise EpubInvalido("EPUBs criptografados não são suportados.")
        limite_total = settings.EPUB_MAX_DESCOMPACTADO
        partes = []
        lido_item = 0
        try:
            with self.zip.open(info) as fluxo:
                while True:
                    bloco = fluxo.read(65536)
                    if not bloco:
                        break
                    lido_item += len(bloco)
                    self.lido += len(bloco)
                    # Não confia no tamanho declarado no cabeçalho.
                    if lido_item > info.file_size or self.lido > limite_total:
                        raise EpubInvalido(
                            "O conteúdo descompactado do EPUB excede o limite permitido."
                        )
                    partes.append(bloco)
        except (zipfile.BadZipFile, OSError, RuntimeError, NotImplementedError,
                EOFError):
            raise EpubInvalido(f"Não foi possível descompactar {nome}.")
        return b"".join(partes)

    def xml(self, nome):
        dados = self.ler(nome)
        if _RE_ENTIDADE.search(dados):
            raise EpubInvalido("EPUB rejeitado: declarações de entidade XML não são permitidas.")
        try:
            return ET.fromstring(dados)
        except ET.ParseError:
            raise EpubInvalido(f"EPUB inválido: XML malformado em {nome}.")

    def texto(self, nome):
        dados = self.ler(nome)
        for cod in ("utf-8-sig", "utf-16"):
            try:
                return dados.decode(cod)
            except UnicodeDecodeError:
                continue
        return dados.decode("latin-1")


def _local(tag):
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _resolver(base_dir, href):
    href = unquote(href)
    return posixpath.normpath(posixpath.join(base_dir, href)) if base_dir else posixpath.normpath(href)


# ---------------------------------------------------------------------------
# XHTML -> tokens de texto
# ---------------------------------------------------------------------------

_BLOCOS = {
    "p", "div", "section", "article", "blockquote", "li", "ul", "ol", "dd",
    "dt", "pre", "table", "tr", "td", "th", "figure", "figcaption", "header",
    "footer", "aside", "hr", "body", "main",
}
_TITULOS = {"h1", "h2", "h3", "h4", "h5", "h6"}
_IGNORAR = {"head", "script", "style", "nav", "svg", "math", "title"}


class _ExtratorXhtml(HTMLParser):
    """Gera tokens: ('a', id) | ('p', texto) | ('h', texto)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tokens = []
        self.buf = []
        self.ignorando = 0
        self.em_titulo = False

    def _flush(self):
        texto = "".join(self.buf)
        self.buf = []
        linhas = [re.sub(r"[ \t\r\f\v\u00a0]+", " ", l).strip() for l in texto.split("\n")]
        texto = "\n".join(l for l in linhas if l)
        if texto:
            self.tokens.append(("h" if self.em_titulo else "p", texto))

    def handle_starttag(self, tag, attrs):
        if tag in _IGNORAR:
            self.ignorando += 1
            return
        if self.ignorando:
            return
        attrs = dict(attrs)
        if tag in _BLOCOS or tag in _TITULOS:
            self._flush()
            if tag in _TITULOS:
                self.em_titulo = True
        ident = attrs.get("id") or (attrs.get("name") if tag == "a" else None)
        if ident:
            if self.buf and "".join(self.buf).strip():
                self._flush()
            self.tokens.append(("a", ident))
        if tag == "br":
            self.buf.append("\n")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag in _IGNORAR:
            self.ignorando -= 1

    def handle_endtag(self, tag):
        if tag in _IGNORAR:
            self.ignorando = max(0, self.ignorando - 1)
            return
        if self.ignorando:
            return
        if tag in _BLOCOS or tag in _TITULOS:
            self._flush()
            if tag in _TITULOS:
                self.em_titulo = False

    def handle_data(self, data):
        if not self.ignorando:
            self.buf.append(re.sub(r"\s+", " ", data))

    def close(self):
        super().close()
        self._flush()


def extrair_tokens(xhtml):
    parser = _ExtratorXhtml()
    parser.feed(xhtml)
    parser.close()
    return parser.tokens


class _LeitorNav(HTMLParser):
    """Lê o <nav epub:type="toc"> do EPUB 3 como árvore."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.navs = []  # lista de (tipo, raiz)
        self.nav_nivel = 0
        self.pilha = []
        self.capturando = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "nav":
            if self.nav_nivel == 0:
                raiz = {"titulo": "", "href": None, "filhos": []}
                self.navs.append((attrs.get("epub:type", "") or attrs.get("role", ""), raiz))
                self.pilha = [raiz]
            self.nav_nivel += 1
            return
        if not self.nav_nivel:
            return
        if tag == "li":
            no = {"titulo": "", "href": None, "filhos": []}
            self.pilha[-1]["filhos"].append(no)
            self.pilha.append(no)
        elif tag in ("a", "span") and len(self.pilha) > 1:
            no = self.pilha[-1]
            if tag == "a" and attrs.get("href") and not no["href"]:
                no["href"] = attrs["href"]
            self.capturando = no

    def handle_endtag(self, tag):
        if tag == "nav" and self.nav_nivel:
            self.nav_nivel -= 1
        elif self.nav_nivel and tag == "li" and len(self.pilha) > 1:
            self.pilha.pop()
        elif tag in ("a", "span"):
            self.capturando = None

    def handle_data(self, data):
        if self.capturando is not None:
            self.capturando["titulo"] += data


# ---------------------------------------------------------------------------
# Análise de títulos
# ---------------------------------------------------------------------------

_RE_CAPITULO = re.compile(
    r"\b(?:cap[ií]tulo|cap\.|chapter|ch\.|chap\.)\s*(\d+|[ivxlcdm]+)\b",
    re.IGNORECASE,
)
_RE_CAPITULO_TITULO = re.compile(
    r"^\s*(?:cap[ií]tulo|chapter)\s+\S+", re.IGNORECASE
)
_RE_VOLUME = re.compile(
    r"^\s*(?:volume|vol\.?|livro|book|parte|part|tomo|arco|arc)\b(?!\s*[:\-–—]?\s*(?:cap|chap))",
    re.IGNORECASE,
)
_RE_EXTRAS = re.compile(
    r"pref[aá]cio|sum[aá]rio|[ií]ndice|cr[eé]ditos|copyright|direitos autorais|"
    r"agradecimentos|dedicat[oó]ria|^\s*capa\s*$|\bcover\b|table of contents|"
    r"^\s*contents\s*$|title page|folha de rosto|sobre o autor|about the author|"
    r"ep[ií]grafe|colophon|cólofon|credits|preface|foreword|acknowledg|"
    r"nota d[oa] tradu|translator|pr[oó]logo do tradutor",
    re.IGNORECASE,
)
_ROMANOS = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}


def _romano(txt):
    txt = txt.lower()
    if not re.fullmatch(r"m{0,4}(cm|cd|d?c{0,3})(xc|xl|l?x{0,3})(ix|iv|v?i{0,3})", txt):
        return None
    total = 0
    for i, ch in enumerate(txt):
        v = _ROMANOS[ch]
        if i + 1 < len(txt) and _ROMANOS[txt[i + 1]] > v:
            total -= v
        else:
            total += v
    return total or None


def numero_explicito(titulo):
    m = _RE_CAPITULO.search(titulo or "")
    if not m:
        return None
    bruto = m.group(1)
    n = int(bruto) if bruto.isdigit() else _romano(bruto)
    return n if n and n > 0 else None


def e_volume(titulo):
    return bool(_RE_VOLUME.match(titulo or "")) and numero_explicito(titulo) is None


def e_extra(titulo):
    return bool(_RE_EXTRAS.search(titulo or ""))


def _limpo(txt):
    return re.sub(r"\s+", " ", unescape(txt or "")).strip()


# ---------------------------------------------------------------------------
# Estrutura do livro
# ---------------------------------------------------------------------------

@dataclass
class Livro:
    spine: list = field(default_factory=list)          # caminhos internos
    tokens: list = field(default_factory=list)         # tokens por item do spine
    ancoras: list = field(default_factory=list)        # {id: indice} por item
    toc: list = field(default_factory=list)            # árvore
    fonte_toc: str = ""
    avisos: list = field(default_factory=list)


def ler_livro(arquivo):
    leitor = LeitorEpub(arquivo)
    container = leitor.xml("META-INF/container.xml")
    opf_path = None
    for el in container.iter():
        if _local(el.tag) == "rootfile" and el.get("full-path"):
            opf_path = el.get("full-path")
            break
    if not opf_path or not leitor.existe(opf_path):
        raise EpubInvalido("EPUB inválido: arquivo OPF não encontrado.")
    opf = leitor.xml(opf_path)
    base = posixpath.dirname(opf_path)

    manifest, spine_ids, toc_id = {}, [], None
    for el in opf.iter():
        nome = _local(el.tag)
        if nome == "item" and el.get("id") and el.get("href"):
            manifest[el.get("id")] = {
                "href": _resolver(base, el.get("href")),
                "tipo": el.get("media-type", ""),
                "props": el.get("properties", ""),
            }
        elif nome == "spine":
            toc_id = el.get("toc")
        elif nome == "itemref" and el.get("idref"):
            spine_ids.append(el.get("idref"))

    livro = Livro()
    for idref in spine_ids:
        item = manifest.get(idref)
        if not item or not leitor.existe(item["href"]):
            continue
        if "html" not in item["tipo"] and not item["href"].endswith((".xhtml", ".html", ".htm")):
            continue
        livro.spine.append(item["href"])
        toks = extrair_tokens(leitor.texto(item["href"]))
        livro.tokens.append(toks)
        livro.ancoras.append({t[1]: i for i, t in enumerate(toks) if t[0] == "a"})
    if not livro.spine:
        raise EpubInvalido("EPUB inválido: nenhum documento de texto no spine.")

    # EPUB 3: NAV
    nav = next((v for v in manifest.values() if "nav" in v["props"].split()), None)
    if nav and leitor.existe(nav["href"]):
        parser = _LeitorNav()
        parser.feed(leitor.texto(nav["href"]))
        escolhido = next((r for t, r in parser.navs if "toc" in t), None)
        if escolhido is None and parser.navs:
            escolhido = parser.navs[0][1]
        if escolhido is not None:
            livro.toc = _normalizar_arvore(escolhido["filhos"], posixpath.dirname(nav["href"]))
            livro.fonte_toc = "NAV (EPUB 3)"
    # EPUB 2: NCX
    if not livro.toc:
        ncx = manifest.get(toc_id) if toc_id else None
        if ncx is None:
            ncx = next((v for v in manifest.values() if v["tipo"] == "application/x-dtbncx+xml"), None)
        if ncx and leitor.existe(ncx["href"]):
            raiz = leitor.xml(ncx["href"])
            nav_map = next((e for e in raiz.iter() if _local(e.tag) == "navMap"), None)
            if nav_map is not None:
                livro.toc = _arvore_ncx(nav_map, posixpath.dirname(ncx["href"]))
                livro.fonte_toc = "NCX (EPUB 2)"
    return livro


def _normalizar_arvore(nos, base):
    saida = []
    for no in nos:
        href = no.get("href")
        saida.append({
            "titulo": _limpo(no.get("titulo")),
            "href": _resolver(base, href) if href and not re.match(r"^[a-z]+:", href, re.I) else None,
            "frag": urldefrag(href)[1] if href else "",
            "filhos": _normalizar_arvore(no.get("filhos", []), base),
        })
    for s in saida:
        if s["href"]:
            s["href"] = urldefrag(s["href"])[0]
    return saida


def _arvore_ncx(el, base):
    saida = []
    for np in el:
        if _local(np.tag) != "navPoint":
            continue
        titulo, href = "", None
        for filho in np:
            if _local(filho.tag) == "navLabel":
                titulo = "".join(filho.itertext())
            elif _local(filho.tag) == "content":
                href = filho.get("src")
        saida.append({"titulo": titulo, "href": href, "filhos": []})
        saida[-1]["filhos_el"] = np
    resultado = []
    for s in saida:
        filhos = _arvore_ncx(s.pop("filhos_el"), base)
        resultado.append({"titulo": s["titulo"], "href": s["href"], "filhos": filhos})
    return _normalizar_arvore(resultado, base) if el.tag and _local(el.tag) == "navMap" else resultado


# ---------------------------------------------------------------------------
# Detecção e segmentação de capítulos
# ---------------------------------------------------------------------------

def _achatar(nos, nivel=0, pai=None, saida=None):
    saida = [] if saida is None else saida
    for no in nos:
        item = {**no, "nivel": nivel, "pai": pai}
        saida.append(item)
        _achatar(no["filhos"], nivel + 1, item, saida)
    return saida


def _texto_entre(livro, inicio, fim):
    paragrafos = []
    (si, ti), (sf, tf) = inicio, fim
    for s in range(si, min(sf, len(livro.tokens) - 1) + 1):
        toks = livro.tokens[s]
        a = ti if s == si else 0
        b = tf if s == sf else len(toks)
        for t in toks[a:b]:
            if t[0] != "a":
                paragrafos.append(t[1])
    return paragrafos


def analisar(arquivo):
    """Retorna dict com itens, avisos e ambiguidade."""
    livro = ler_livro(arquivo)
    avisos, ambiguo = [], False
    fim_livro = (len(livro.tokens) - 1, len(livro.tokens[-1]))
    indice_spine = {h: i for i, h in enumerate(livro.spine)}

    # --- candidatos a partir do sumário
    marcos = []  # (pos, titulo, tipo, volume)
    planos = _achatar(livro.toc)
    nao_resolvidos = 0
    for no in planos:
        if not no["href"]:
            continue
        si = indice_spine.get(no["href"])
        if si is None:
            nao_resolvidos += 1
            continue
        ti = 0
        if no["frag"]:
            ti = livro.ancoras[si].get(no["frag"])
            if ti is None:
                nao_resolvidos += 1
                ti = 0
                ambiguo = True
        tipo = "volume" if (no["filhos"] or e_volume(no["titulo"])) else "capitulo"
        volume = no["pai"]["titulo"] if no["pai"] else None
        marcos.append({"pos": (si, ti), "titulo": no["titulo"], "tipo": tipo, "volume": volume})
    if nao_resolvidos:
        avisos.append(
            f"{nao_resolvidos} entrada(s) do sumário apontam para arquivos ou âncoras "
            "inexistentes; confira a separação dos capítulos."
        )

    caps_toc = [m for m in marcos if m["tipo"] == "capitulo"]

    # --- candidatos a partir dos títulos do texto
    def detectar(apenas_titulos):
        achados, vol_atual = [], None
        for si, toks in enumerate(livro.tokens):
            ultimo_anchor = None
            for ti, t in enumerate(toks):
                if t[0] == "a":
                    ultimo_anchor = ti if ultimo_anchor is None else ultimo_anchor
                    continue
                pos = (si, ultimo_anchor if ultimo_anchor is not None else ti)
                ultimo_anchor = None
                texto = t[1].split("\n")[0]
                if (apenas_titulos and t[0] != "h") or len(texto) > 150:
                    continue
                if e_volume(texto):
                    vol_atual = texto
                    achados.append({"pos": pos, "titulo": texto, "tipo": "volume", "volume": None})
                elif _RE_CAPITULO_TITULO.match(texto):
                    titulo = t[1].replace("\n", " — ")
                    achados.append({"pos": pos, "titulo": titulo[:255], "tipo": "capitulo", "volume": vol_atual})
        return achados

    marcos_texto = detectar(True)
    if not any(m["tipo"] == "capitulo" for m in marcos_texto):
        marcos_texto = detectar(False)
    caps_texto = [m for m in marcos_texto if m["tipo"] == "capitulo"]

    if not livro.toc:
        avisos.append("O EPUB não possui sumário (NAV/NCX) utilizável.")
    usados = marcos
    if not caps_toc:
        if caps_texto:
            if livro.toc:
                avisos.append(
                    "O sumário lista apenas volumes/seções; os capítulos foram "
                    "identificados pelos títulos no texto."
                )
            usados = marcos_texto
        else:
            ambiguo = True
            avisos.append(
                "Não foi possível identificar capítulos com segurança. Cada documento "
                "do livro foi listado como um item; revise antes de importar."
            )
            usados = [
                {"pos": (i, 0), "titulo": posixpath.basename(h), "tipo": "capitulo", "volume": None}
                for i, h in enumerate(livro.spine)
            ]
    elif len(caps_texto) >= len(caps_toc) + 3 and len(caps_texto) >= 1.5 * len(caps_toc):
        avisos.append(
            f"O sumário parece incompleto ({len(caps_toc)} capítulos) e o texto contém "
            f"{len(caps_texto)} títulos de capítulo; foram usados os títulos do texto."
        )
        usados = marcos_texto

    usados = sorted(usados, key=lambda m: m["pos"])
    # remove marcos na mesma posição (mantém o capítulo, se houver)
    unicos = []
    for m in usados:
        if unicos and unicos[-1]["pos"] == m["pos"]:
            if unicos[-1]["tipo"] == "capitulo" and m["tipo"] == "capitulo":
                ambiguo = True
                avisos.append(f"Dois itens do sumário começam no mesmo ponto: “{m['titulo']}”.")
                continue
            if m["tipo"] == "capitulo":
                m["volume"] = m["volume"] or unicos[-1]["titulo"]
                unicos[-1] = m
            continue
        unicos.append(m)

    itens = []
    vol_corrente = None
    for i, m in enumerate(unicos):
        if m["tipo"] == "volume":
            vol_corrente = m["titulo"]
            continue
        fim = unicos[i + 1]["pos"] if i + 1 < len(unicos) else fim_livro
        paragrafos = _texto_entre(livro, m["pos"], fim)
        titulo = m["titulo"] or "Sem título"
        if paragrafos and _limpo(paragrafos[0]).lower() == titulo.lower():
            paragrafos = paragrafos[1:]
        conteudo = "\n\n".join(paragrafos).strip()
        itens.append({
            "titulo": titulo[:255],
            "volume": m["volume"] or vol_corrente,
            "conteudo": conteudo,
        })

    if len(itens) > settings.EPUB_MAX_CAPITULOS:
        raise EpubInvalido(
            f"O EPUB contém {len(itens)} capítulos; o máximo permitido é "
            f"{settings.EPUB_MAX_CAPITULOS}."
        )
    if not itens:
        raise EpubInvalido("Nenhum capítulo foi encontrado no EPUB.")

    avisos += numerar(itens)
    return {"itens": itens, "avisos": avisos, "ambiguidade": ambiguo,
            "fonte": livro.fonte_toc or "títulos do texto"}


def numerar(itens):
    """Define numero_detectado, sugerido, selecionado e alertas por item."""
    avisos = []
    for it in itens:
        it["numero_detectado"] = numero_explicito(it["titulo"])
        it["alertas"] = []
        it["selecionado"] = bool(it["conteudo"]) and not (
            it["numero_detectado"] is None and e_extra(it["titulo"])
        )
        if not it["conteudo"]:
            it["alertas"].append("Sem conteúdo")
        elif not it["selecionado"]:
            it["alertas"].append("Possível material extra")

    # Reinício de numeração entre volumes
    reinicio = False
    max_anteriores, vol, max_vol = 0, object(), 0
    for it in itens:
        if it["volume"] != vol:
            max_anteriores = max(max_anteriores, max_vol)
            vol, max_vol = it["volume"], 0
        n = it["numero_detectado"]
        if n:
            if max_anteriores and n <= max_anteriores:
                reinicio = True
            max_vol = max(max_vol, n)

    contador = 0
    for it in itens:
        if not it["selecionado"]:
            it["sugerido"] = None
            continue
        n = it["numero_detectado"]
        if reinicio:
            contador += 1
            it["sugerido"] = contador
            if n != contador:
                it["alertas"].append("Numeração ajustada (volume reinicia)")
        elif n:
            it["sugerido"] = n
            contador = max(contador, n)
        else:
            contador += 1
            it["sugerido"] = contador
            it["alertas"].append("Sem número no título")
    if reinicio:
        avisos.append(
            "A numeração dos capítulos reinicia entre volumes. Foi sugerida uma "
            "numeração contínua; revise antes de confirmar."
        )
    if any("Sem número no título" in it["alertas"] for it in itens):
        avisos.append("Há capítulos sem número no título; confira a numeração sugerida.")
    vistos = {}
    for it in itens:
        if it["sugerido"]:
            vistos.setdefault(it["sugerido"], []).append(it)
    repetidos = [n for n, l in vistos.items() if len(l) > 1]
    for n in repetidos:
        for it in vistos[n]:
            it["alertas"].append("Número repetido no arquivo")
    if repetidos:
        avisos.append(f"{len(repetidos)} número(s) aparecem repetidos no arquivo.")
    return avisos


# ---------------------------------------------------------------------------
# Armazenamento temporário da prévia
# ---------------------------------------------------------------------------

def _raiz():
    raiz = Path(settings.EPUB_PREVIEW_ROOT)
    raiz.mkdir(parents=True, exist_ok=True)
    return raiz


def _caminhos(previa):
    base = _raiz() / Path(previa.arquivo).name
    return base.with_suffix(".indice.json"), base.with_suffix(".conteudo.json")


def remover_previa(previa):
    for caminho in _caminhos(previa):
        caminho.unlink(missing_ok=True)
    if previa.pk:
        previa.delete()


def limpar_previas_expiradas():
    from .models import PreviaImportacaoEpub

    removidas = 0
    for previa in PreviaImportacaoEpub.objects.filter(expira_em__lte=timezone.now()):
        remover_previa(previa)
        removidas += 1
    return removidas


def criar_previa(usuario, obra, resultado):
    from .models import PreviaImportacaoEpub

    limpar_previas_expiradas()
    for antiga in PreviaImportacaoEpub.objects.filter(usuario=usuario, obra=obra):
        remover_previa(antiga)

    volumes_existentes = {
        v.titulo.strip().lower(): v
        for v in obra.volumes.all()
    }

    previa = PreviaImportacaoEpub(
        usuario=usuario,
        obra=obra,
        avisos=resultado["avisos"] + [f"Fonte da estrutura: {resultado['fonte']}."],
        ambiguidade=resultado["ambiguidade"],
        total_detectado=len(resultado["itens"]),
        expira_em=timezone.now() + timedelta(seconds=settings.EPUB_PREVIEW_EXPIRACAO),
    )
    previa.arquivo = f"{previa.token.hex}.json"
    indice, conteudos, selecao = [], [], {}
    for i, it in enumerate(resultado["itens"]):
        trecho = re.sub(r"\s+", " ", it["conteudo"][:400]).strip()
        vol_detectado = (it["volume"] or "").strip()[:150]
        if vol_detectado:
            vol_existente = volumes_existentes.get(vol_detectado.lower())
            vol_sel = f"id:{vol_existente.id}" if vol_existente else f"novo:{vol_detectado}"
        else:
            vol_sel = ""
        indice.append({
            "titulo": it["titulo"],
            "volume": vol_detectado or None,
            "numero_detectado": it["numero_detectado"],
            "sugerido": it["sugerido"],
            "trecho": trecho[:200] + ("…" if len(trecho) > 200 else ""),
            "alertas": it["alertas"],
            "tamanho": len(it["conteudo"]),
        })
        conteudos.append(it["conteudo"])
        selecao[str(i)] = {
            "s": it["selecionado"],
            "n": it["sugerido"],
            "v": vol_sel,
        }
    previa.selecao = selecao
    cam_indice, cam_conteudo = _caminhos(previa)
    cam_indice.write_text(json.dumps(indice, ensure_ascii=False), encoding="utf-8")
    cam_conteudo.write_text(json.dumps(conteudos, ensure_ascii=False), encoding="utf-8")
    previa.save()
    return previa


def ler_indice(previa):
    try:
        return json.loads(_caminhos(previa)[0].read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def ler_conteudos(previa):
    try:
        return json.loads(_caminhos(previa)[1].read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Comparação de títulos e gravação
# ---------------------------------------------------------------------------

_RE_PREFIXO_CAP = re.compile(
    r"^\s*(?:capitulo|cap\.?|chapter|chap\.?|ch\.?)\s*(?:\d+|[ivxlcdm]+)\s*[:\-–—.]*\s*",
    re.IGNORECASE,
)


def _normalizar_titulo(texto):
    sem_acento = "".join(
        ch for ch in unicodedata.normalize("NFKD", texto or "")
        if not unicodedata.combining(ch)
    )
    limpo = re.sub(r"[^a-z0-9\s]", " ", sem_acento.lower())
    return re.sub(r"\s+", " ", limpo).strip()


def titulos_compativeis(titulo_existente, titulo_epub):
    """Confere se o título do capítulo no banco é compatível com o do EPUB."""
    norm_a = _normalizar_titulo(titulo_existente)
    norm_b = _normalizar_titulo(titulo_epub)
    if not norm_a or not norm_b:
        return False
    if norm_a == norm_b:
        return True
    sub_a = _normalizar_titulo(_RE_PREFIXO_CAP.sub("", norm_a))
    sub_b = _normalizar_titulo(_RE_PREFIXO_CAP.sub("", norm_b))
    if not sub_a and not sub_b:
        return True
    if sub_a and sub_b:
        if sub_a == sub_b or sub_a in sub_b or sub_b in sub_a:
            return True
        return SequenceMatcher(None, sub_a, sub_b).ratio() >= 0.65
    return False


def _resolver_volume_selecionado(valor, obra, volumes_por_id, volumes_por_titulo, proxima_ordem):
    """Resolve 'id:<pk>' ou 'novo:<titulo>' em uma instância de Volume (criando se necessário)."""
    from .models import Volume

    valor = (valor or "").strip()
    if not valor:
        return None, proxima_ordem
    if valor.startswith("id:"):
        try:
            vid = int(valor[3:])
        except ValueError:
            return None, proxima_ordem
        return volumes_por_id.get(vid), proxima_ordem
    if valor.startswith("novo:"):
        titulo = valor[5:].strip()[:150]
        if not titulo:
            return None, proxima_ordem
        chave = titulo.lower()
        existente = volumes_por_titulo.get(chave)
        if existente is not None:
            return existente, proxima_ordem
        novo_vol = Volume.objects.create(
            obra=obra,
            titulo=titulo,
            ordem=proxima_ordem,
        )
        volumes_por_id[novo_vol.id] = novo_vol
        volumes_por_titulo[chave] = novo_vol
        return novo_vol, proxima_ordem + 1
    return None, proxima_ordem


def importar(previa, tamanho_lote=200, organizar_sem_volume=False):
    """Grava os capítulos selecionados e opcionalmente organiza existentes sem volume.
    Deve ser chamado com a prévia já bloqueada dentro de transaction.atomic()."""
    from .models import Capitulo

    obra = previa.obra
    indice = ler_indice(previa)
    conteudos = ler_conteudos(previa)
    if indice is None or conteudos is None:
        raise EpubInvalido("Os dados da prévia não estão mais disponíveis. Envie o EPUB novamente.")

    ignorados = {}

    def ignorar(motivo, item):
        ignorados.setdefault(motivo, []).append(item)

    volumes_existentes = list(obra.volumes.order_by("ordem", "id"))
    volumes_por_id = {v.id: v for v in volumes_existentes}
    volumes_por_titulo = {v.titulo.strip().lower(): v for v in volumes_existentes}
    proxima_ordem = max((v.ordem for v in volumes_existentes), default=0) + 1

    existentes_map = {
        c.numero: c for c in obra.capitulos.select_related("volume")
    }
    vistos, novos, para_organizar = set(), [], []
    for i, meta in enumerate(indice):
        sel = previa.selecao.get(str(i), {})
        rotulo = meta["titulo"]
        if not sel.get("s"):
            ignorar("Desmarcado na prévia", rotulo)
            continue
        n = sel.get("n")
        if not isinstance(n, int) or n < 1:
            ignorar("Número ausente ou inválido", rotulo)
            continue
        if n in vistos:
            ignorar("Número repetido na seleção", f"{n} — {rotulo}")
            continue
        vol_sel = sel.get("v", "")
        if n in existentes_map:
            if not organizar_sem_volume:
                ignorar("Número já cadastrado na obra", f"{n} — {rotulo}")
                continue
            cap_existente = existentes_map[n]
            if cap_existente.volume_id is not None:
                ignorar(
                    "Capítulo existente já possui volume",
                    f"{n} — {cap_existente.titulo} ({cap_existente.volume.titulo})",
                )
                continue
            if not vol_sel:
                ignorar("Sem volume selecionado para organizar", f"{n} — {rotulo}")
                continue
            if not titulos_compativeis(cap_existente.titulo, rotulo):
                ignorar(
                    "Correspondência duvidosa (revisão necessária)",
                    f"{n} — banco: “{cap_existente.titulo}” / EPUB: “{rotulo}”",
                )
                continue
            vol_obj, proxima_ordem = _resolver_volume_selecionado(
                vol_sel, obra, volumes_por_id, volumes_por_titulo, proxima_ordem
            )
            if vol_obj is None:
                ignorar("Volume selecionado inválido", f"{n} — {rotulo}")
                continue
            vistos.add(n)
            cap_existente.volume = vol_obj
            para_organizar.append(cap_existente)
            continue
        if not conteudos[i].strip():
            ignorar("Sem conteúdo", rotulo)
            continue
        vol_obj, proxima_ordem = _resolver_volume_selecionado(
            vol_sel, obra, volumes_por_id, volumes_por_titulo, proxima_ordem
        )
        vistos.add(n)
        novos.append(
            Capitulo(
                obra=obra,
                numero=n,
                titulo=rotulo[:255] or f"Capítulo {n}",
                conteudo=conteudos[i],
                volume=vol_obj,
            )
        )

    organizados = 0
    if para_organizar:
        for inicio in range(0, len(para_organizar), tamanho_lote):
            lote_org = para_organizar[inicio:inicio + tamanho_lote]
            Capitulo.objects.bulk_update(lote_org, ["volume"])
            organizados += len(lote_org)

    antes = criados = 0
    concorrentes = []
    for inicio in range(0, len(novos), tamanho_lote):
        lote = novos[inicio:inicio + tamanho_lote]
        # Revalida no banco: números gravados por outra importação desde a prévia.
        ocupados = set(obra.capitulos.filter(numero__in=[c.numero for c in lote])
                       .values_list("numero", flat=True))
        if ocupados:
            concorrentes += [f"{c.numero} — {c.titulo}" for c in lote if c.numero in ocupados]
            lote = [c for c in lote if c.numero not in ocupados]
        numeros = [c.numero for c in lote]
        antes = obra.capitulos.filter(numero__in=numeros).count()
        Capitulo.objects.bulk_create(lote, ignore_conflicts=True)
        criados_lote = obra.capitulos.filter(numero__in=numeros).count() - antes
        if criados_lote < len(lote):
            concorrentes += ["—"] * (len(lote) - criados_lote)
        criados += criados_lote
    if concorrentes:
        ignorados.setdefault("Número cadastrado simultaneamente por outra importação", []).extend(
            concorrentes
        )
    return {
        "importados": criados,
        "organizados": organizados,
        "ignorados": sum(len(v) for v in ignorados.values()),
        "motivos": [(m, len(v), v[:20]) for m, v in ignorados.items()],
    }
