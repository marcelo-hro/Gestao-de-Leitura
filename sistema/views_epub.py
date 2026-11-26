from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import epub_importacao as epub
from .models import Obra, PreviaImportacaoEpub
from .permissoes import moderador_requerido, pode_gerenciar_obra

## Views relacionadas à importação de capítulos a partir de arquivos EPUB.
def _obra_gerenciavel(request, obra_id, bloquear=False):
    consulta = Obra.objects.filter(formato="WEBNOVEL")
    if bloquear:
        consulta = consulta.select_for_update()
    obra = get_object_or_404(consulta, id=obra_id)
    if not pode_gerenciar_obra(request.user, obra):
        raise PermissionDenied(
            "Você não tem permissão para importar capítulos nesta obra."
        )
    return obra

#onde ocorre a previa da importação de capítulos a partir de um arquivo EPUB, 
    consulta = PreviaImportacaoEpub.objects.filter(
        token=token, obra=obra, usuario=request.user
    )
    if bloquear:
        consulta = consulta.select_for_update()
    previa = consulta.first()
    if previa is None:
        return None
    if previa.expirada:
        epub.remover_previa(previa)
        return None
    return previa

#onde de fato ocorre a importação de capítulos a partir de um arquivo EPUB, 
@moderador_requerido
def importar_epub(request, obra_id):
    obra = _obra_gerenciavel(request, obra_id)
    erro = None

    if request.method == "POST":
        arquivo = request.FILES.get("arquivo_epub")
        if not arquivo:
            erro = "Selecione um arquivo .epub."
        elif not arquivo.name.lower().endswith(".epub"):
            erro = "Envie um arquivo com extensão .epub."
        else:
            try:
                resultado = epub.analisar(arquivo)
            except epub.EpubInvalido as exc:
                erro = str(exc)
            else:
                previa = epub.criar_previa(request.user, obra, resultado)
                return redirect(
                    "previa_importacao_epub", obra_id=obra.id, token=previa.token
                )

    return render(
        request,
        "sistema/importar_epub.html",
        {
            "obra": obra,
            "erro": erro,
            "limite_mb": settings.EPUB_MAX_UPLOAD_SIZE // (1024 * 1024),
        },
        status=400 if erro else 200,
    )

#onde ocorre a previa dos volumes
def _opcoes_volume(obra, indice):
    volumes_obra = list(obra.volumes.order_by("ordem", "id"))
    titulos_existentes = {v.titulo.strip().lower() for v in volumes_obra}
    opcoes = [{"valor": "", "rotulo": "Sem volume"}]
    for v in volumes_obra:
        opcoes.append({"valor": f"id:{v.id}", "rotulo": v.titulo})
    vistos_novos = set()
    for meta in indice:
        vol = (meta.get("volume") or "").strip()[:150]
        if vol and vol.lower() not in titulos_existentes and vol.lower() not in vistos_novos:
            vistos_novos.add(vol.lower())
            opcoes.append({"valor": f"novo:{vol}", "rotulo": f"{vol} (novo)"})
    return opcoes

#onde valida o valor do volume, verificando se ele é válido e retornando o valor correto
def _validar_valor_volume(valor, volumes_ids_validos, novos_validos):
    valor = (valor or "").strip()
    if not valor:
        return ""
    if valor.startswith("id:"):
        try:
            vid = int(valor[3:])
        except ValueError:
            return ""
        return valor if vid in volumes_ids_validos else ""
    if valor.startswith("novo:"):
        titulo = valor[5:].strip()[:150]
        return f"novo:{titulo}" if titulo and titulo.lower() in novos_validos else ""
    return ""

#onde ocorre a previa da importacao dos capitulos e volumes a partir de um arquivo EPUB, exibindo as opções de seleção para o usuário
@moderador_requerido
def previa_importacao_epub(request, obra_id, token):
    obra = _obra_gerenciavel(request, obra_id)
    previa = _previa_do_usuario(request, obra, token)
    if previa is None:
        messages.error(request, "A prévia expirou ou não existe. Envie o EPUB novamente.")
        return redirect("importar_epub", obra_id=obra.id)
    indice = epub.ler_indice(previa)
    if indice is None:
        epub.remover_previa(previa)
        messages.error(request, "Os dados da prévia não estão mais disponíveis.")
        return redirect("importar_epub", obra_id=obra.id)

    existentes_map = {
        c.numero: c for c in obra.capitulos.select_related("volume")
    }
    opcoes_volume = _opcoes_volume(obra, indice)
    contagem = {}
    for sel in previa.selecao.values():
        if sel.get("s") and sel.get("n"):
            contagem[sel["n"]] = contagem.get(sel["n"], 0) + 1
    selecionados = sum(1 for s in previa.selecao.values() if s.get("s"))
    conflitos = sum(
        1 for s in previa.selecao.values() if s.get("s") and s.get("n") in existentes_map
    )
    sem_volume_existentes = sum(
        1 for c in existentes_map.values() if c.volume_id is None
    )

    paginador = Paginator(range(len(indice)), settings.EPUB_PREVIEW_PAGINA)
    pagina = paginador.get_page(request.GET.get("page"))
    linhas = []
    for i in pagina.object_list:
        meta = indice[i]
        sel = previa.selecao.get(str(i), {})
        n = sel.get("n")
        cap_existente = existentes_map.get(n)
        duvidosa = False
        if cap_existente is not None and cap_existente.volume_id is None:
            duvidosa = not epub.titulos_compativeis(cap_existente.titulo, meta["titulo"])
        linhas.append({
            "idx": i,
            **meta,
            "selecionado": sel.get("s", False),
            "numero": n,
            "volume_selecionado": sel.get("v", ""),
            "conflito": cap_existente is not None,
            "existente_titulo": cap_existente.titulo if cap_existente else None,
            "existente_volume": cap_existente.volume.titulo if (cap_existente and cap_existente.volume) else None,
            "duvidosa": duvidosa,
            "duplicado": bool(sel.get("s") and n and contagem.get(n, 0) > 1),
        })

    return render(
        request,
        "sistema/previa_importacao_epub.html",
        {
            "obra": obra,
            "previa": previa,
            "linhas": linhas,
            "pagina": pagina,
            "selecionados": selecionados,
            "conflitos": conflitos,
            "existentes": len(existentes_map),
            "sem_volume_existentes": sem_volume_existentes,
            "opcoes_volume": opcoes_volume,
        },
    )

#onde aplica as alterações feitas pelo usuário na pagina de previa da importação de capítulos a partir de um arquivo EPUB, atualizando a seleção de capítulos e volumes na prévia
def _aplicar_pagina(request, previa, obra, indice):
    volumes_ids_validos = set(obra.volumes.values_list("id", flat=True))
    novos_validos = {
        (m.get("volume") or "").strip()[:150].lower()
        for m in (indice or [])
        if m.get("volume")
    }
    selecao = dict(previa.selecao)
    for bruto in request.POST.getlist("itens"):
        if bruto not in selecao:
            continue
        numero = request.POST.get(f"num_{bruto}", "").strip()
        try:
            numero = int(numero)
            if numero < 1:
                numero = None
        except ValueError:
            numero = None
        atual = selecao[bruto]
        if f"vol_{bruto}" in request.POST:
            vol_val = _validar_valor_volume(
                request.POST.get(f"vol_{bruto}", ""),
                volumes_ids_validos,
                novos_validos,
            )
        else:
            vol_val = atual.get("v", "")
        selecao[bruto] = {
            "s": f"sel_{bruto}" in request.POST,
            "n": numero,
            "v": vol_val,
        }
    acao_massa = request.POST.get("massa")
    if acao_massa in ("todos", "nenhum"):
        for chave in selecao:
            selecao[chave] = {**selecao[chave], "s": acao_massa == "todos"}
    elif acao_massa == "aplicar_volume":
        vol_lote = _validar_valor_volume(
            request.POST.get("volume_lote", ""),
            volumes_ids_validos,
            novos_validos,
        )
        for chave in selecao:
            if selecao[chave].get("s"):
                selecao[chave] = {**selecao[chave], "v": vol_lote}
    previa.selecao = selecao

#onde salva a prévia da importação de capítulos a partir de um arquivo EPUB, aplicando as alterações feitas pelo usuário e redirecionando para a página de pré-visualização ou confirmando a importação
@moderador_requerido
@require_POST
def salvar_previa_epub(request, obra_id, token):
    if request.POST.get("acao") == "confirmar":
        return _confirmar(request, obra_id, token)

    obra = _obra_gerenciavel(request, obra_id)
    with transaction.atomic():
        previa = _previa_do_usuario(request, obra, token, bloquear=True)
        if previa is None:
            messages.error(request, "A prévia expirou ou não existe. Envie o EPUB novamente.")
            return redirect("importar_epub", obra_id=obra.id)
        indice = epub.ler_indice(previa)
        _aplicar_pagina(request, previa, obra, indice)
        previa.save(update_fields=["selecao"])

    if request.POST.get("acao") == "cancelar":
        epub.remover_previa(previa)
        messages.info(request, "Importação cancelada.")
        return redirect("visualizar_obra", obra_id=obra.id)

    destino = reverse("previa_importacao_epub", args=[obra.id, previa.token])
    pagina = request.POST.get("ir_para", "").strip()
    if pagina.isdigit():
        destino += f"?page={pagina}"
    return redirect(destino)

#onde confirma a importação de capítulos a partir de um arquivo EPUB, aplicando as alterações feitas pelo usuário e redirecionando para a página de resultado da importação
def _confirmar(request, obra_id, token):
    with transaction.atomic():
        # Bloqueia obra e prévia: confirmações simultâneas são serializadas
        # e a segunda encontra a prévia já consumida.
        obra = _obra_gerenciavel(request, obra_id, bloquear=True)
        previa = _previa_do_usuario(request, obra, token, bloquear=True)
        if previa is None:
            messages.error(
                request,
                "A prévia expirou ou já foi utilizada. Envie o EPUB novamente.",
            )
            return redirect("visualizar_obra", obra_id=obra.id)
        indice = epub.ler_indice(previa)
        _aplicar_pagina(request, previa, obra, indice)
        previa.save(update_fields=["selecao"])

        if previa.ambiguidade and not request.POST.get("revisei_ambiguidade"):
            messages.error(
                request,
                "A separação dos capítulos é ambígua. Revise a prévia e marque "
                "a confirmação de revisão antes de importar.",
            )
            return redirect("previa_importacao_epub", obra_id=obra.id, token=previa.token)

        organizar_sem_volume = bool(request.POST.get("organizar_sem_volume"))
        try:
            resultado = epub.importar(
                previa,
                organizar_sem_volume=organizar_sem_volume,
            )
        except epub.EpubInvalido as exc:
            messages.error(request, str(exc))
            return redirect("importar_epub", obra_id=obra.id)
        total = previa.total_detectado
        epub.remover_previa(previa)

    return render(
        request,
        "sistema/resultado_importacao_epub.html",
        {"obra": obra, "resultado": resultado, "total": total},
    )
