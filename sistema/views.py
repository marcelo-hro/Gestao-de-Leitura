import json

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Avg, Count, F, Max, Q
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from sistema.forms import (
    AvaliacaoForm,
    CapituloForm,
    EstanteForm,
    LeituraForm,
    ObraForm,
    RegistroForm,
    VolumeCapitulosForm,
    VolumeForm,
)
from .models import (
    Avaliacao,
    Capitulo,
    CapituloLido,
    Estante,
    Genero,
    Leitura,
    Obra,
    Volume,
)
from .permissoes import (
    admin_requerido,
    e_admin,
    moderador_requerido,
    pode_gerenciar_obra,
    pode_visualizar_obra,
)
#leitor 123
#mod 123
#dashboard
def dashboard(request):
    obras_ativas = Obra.objects.filter(estado=Obra.Estado.ATIVA)
    destaques = (
        obras_ativas.prefetch_related("generos").order_by("-criado_em")[:8]
    )
    recentes = obras_ativas.order_by("-criado_em")[:6]

    minhas_submissoes = None
    continuar_lendo = None
    minhas_estantes = None
    estatisticas = None
    if request.user.is_authenticated:
        minhas_submissoes = (
            Obra.objects.filter(submetido_por=request.user)
            .exclude(estado=Obra.Estado.ATIVA)
            .order_by("-criado_em")[:5]
        )
        continuar_lendo = (
            Leitura.objects.filter(
                usuario=request.user,
                status=Leitura.Status.LENDO,
            )
            .select_related("obra", "ultimo_capitulo")
            .order_by("-atualizado_em")[:4]
        )
        minhas_estantes = (
            Estante.objects.filter(usuario=request.user)
            .annotate(
                qtd_obras=Count(
                    "obras",
                    filter=Q(obras__estado=Obra.Estado.ATIVA),
                )
            )
            .order_by("nome")[:4]
        )
        estatisticas = {
            "obras_ativas": obras_ativas.count(),
            "lendo": Leitura.objects.filter(
                usuario=request.user,
                status=Leitura.Status.LENDO,
            ).count(),
            "concluidas": Leitura.objects.filter(
                usuario=request.user,
                status=Leitura.Status.CONCLUIDO,
            ).count(),
            "avaliacoes": Avaliacao.objects.filter(
                usuario=request.user,
            ).count(),
            "estantes": Estante.objects.filter(
                usuario=request.user,
            ).count(),
        }

    return render(
        request,
        "dashboard.html",
        {
            "destaques": destaques,
            "recentes": recentes,
            "minhas_submissoes": minhas_submissoes,
            "continuar_lendo": continuar_lendo,
            "minhas_estantes": minhas_estantes,
            "estatisticas": estatisticas,
        },
    )

#onde o usuario pode ver todas as obras disponiveis no sistema
def catalogo(request):
    termo = request.GET.get("q", "").strip()
    obras = (
        Obra.objects.filter(estado=Obra.Estado.ATIVA)
        .prefetch_related("generos")
        .order_by("titulo")
    )

    if termo:
        obras = obras.filter(
            Q(titulo__icontains=termo)
            | Q(autor__icontains=termo)
            | Q(sinopse__icontains=termo)
            | Q(generos__nome__icontains=termo)
        ).distinct()

    paginador = Paginator(obras, 9)
    pagina = paginador.get_page(request.GET.get("page"))

    return render(
        request,
        "sistema/catalogo.html",
        {"obras": pagina, "pagina": pagina, "termo": termo},
    )


@moderador_requerido
def adicionar_obra(request):
    if request.method == "POST":
        form = ObraForm(
            request.POST,
            request.FILES,
            permitir_novo_genero=True,
        )

        if form.is_valid() and request.FILES.get("arquivo_pdf"):
            form.add_error(
                None,
                "O PDF só pode ser anexado após o cadastro, na edição da obra.",
            )

        if form.is_valid():
            novo_genero_nome = form.cleaned_data.get("novo_genero", "")

            with transaction.atomic():
                obra = form.save(commit=False)
                obra.submetido_por = request.user
                if e_admin(request.user):
                    obra.estado = Obra.Estado.ATIVA
                else:
                    obra.estado = Obra.Estado.PENDENTE
                obra.save()
                form.save_m2m()

                if novo_genero_nome:
                    genero = Genero.objects.filter(
                        nome__iexact=novo_genero_nome
                    ).first()
                    if genero is None:
                        genero = Genero.objects.create(nome=novo_genero_nome)
                    obra.generos.add(genero)

            if obra.estado == Obra.Estado.ATIVA:
                messages.success(
                    request,
                    "Obra publicada no catálogo com sucesso.",
                )
            else:
                messages.success(
                    request,
                    "Obra enviada para aprovação do administrador.",
                )
            return redirect("visualizar_obra", obra_id=obra.id)
    else:
        form = ObraForm(permitir_novo_genero=True)

    return render(
        request,
        "sistema/adicionar_obra.html",
        {
            "form": form,
            "publica_direto": e_admin(request.user),
        },
    )

#edição de obra, onde o moderador ou admin pode editar a obra
@moderador_requerido
def editar_obra(request, obra_id):
    obra = get_object_or_404(Obra, id=obra_id)

    if not pode_gerenciar_obra(request.user, obra):
        raise PermissionDenied("Você não tem permissão para editar esta obra.")

    if request.method == "POST":
        form = ObraForm(
            request.POST,
            request.FILES,
            instance=obra,
            incluir_pdf=True,
        )
        if form.is_valid():
            form.save()
            messages.success(request, "Obra atualizada com sucesso.")
            if obra.estado == Obra.Estado.PENDENTE:
                return redirect("painel_moderacao")
            return redirect("visualizar_obra", obra_id=obra.id)
    else:
        form = ObraForm(instance=obra, incluir_pdf=True)

    return render(
        request,
        "sistema/editar_obra.html",
        {"form": form, "obra": obra},
    )

#deletar obra, onde o moderador ou admin pode deletar a obra
@moderador_requerido
def deletar_obra(request, obra_id):
    obra = get_object_or_404(Obra, id=obra_id)

    if not pode_gerenciar_obra(request.user, obra):
        raise PermissionDenied("Você não tem permissão para excluir esta obra.")

    era_pendente = obra.estado == Obra.Estado.PENDENTE

    if request.method == "POST":
        titulo = obra.titulo
        obra.delete()
        messages.success(request, f'Obra "{titulo}" eliminada com sucesso.')
        if era_pendente:
            return redirect("painel_moderacao")
        return redirect("catalogo")

    return render(request, "sistema/deletar_obra.html", {"obra": obra})

#visualizar obra, onde o usuario pode ver a obra e seus detalhes
def visualizar_obra(request, obra_id):
    obra = get_object_or_404(Obra, id=obra_id)

    if not pode_visualizar_obra(request.user, obra):
        raise Http404("Obra não encontrada.")

    if obra.formato == "WEBNOVEL":
        capitulos = obra.capitulos.select_related("volume").order_by(
            F("volume__ordem").asc(nulls_last=True),
            F("volume_id").asc(nulls_last=True),
            "numero",
        )
        quantidade_capitulos = capitulos.count()
        primeiro_capitulo = obra.capitulos.order_by("numero").first()
    else:
        capitulos = []
        quantidade_capitulos = 0
        primeiro_capitulo = None

    leitura = None
    leitura_form = None
    capitulos_lidos_ids = set()
    estantes_usuario = None
    estantes_da_obra = None
    avaliacoes = None
    media_notas = None
    total_avaliacoes = 0
    minha_avaliacao = None
    avaliacao_form = None

    if obra.estado == Obra.Estado.ATIVA:
        avaliacoes = obra.avaliacoes.select_related("usuario").order_by(
            "-atualizada_em"
        )
        total_avaliacoes = avaliacoes.count()
        media_notas = avaliacoes.aggregate(media=Avg("nota"))["media"]

    if request.user.is_authenticated:
        leitura = (
            Leitura.objects.filter(
                usuario=request.user,
                obra=obra,
            )
            .select_related("ultimo_capitulo")
            .first()
        )
        if obra.formato == "WEBNOVEL":
            capitulos_lidos_ids = set(
                CapituloLido.objects.filter(
                    usuario=request.user,
                    obra=obra,
                ).values_list("capitulo_id", flat=True)
            )
            if leitura is not None:
                leitura._total_capitulos_cache = quantidade_capitulos
                leitura._capitulos_lidos_cache = len(capitulos_lidos_ids)
        else:
            leitura_form = LeituraForm(instance=leitura or Leitura(obra=obra))
        estantes_usuario = Estante.objects.filter(
            usuario=request.user
        ).order_by("nome")
        estantes_da_obra = obra.estantes.filter(
            usuario=request.user
        ).order_by("nome")

        if obra.estado == Obra.Estado.ATIVA:
            minha_avaliacao = obra.avaliacoes.filter(
                usuario=request.user
            ).first()
            avaliacao_form = AvaliacaoForm(
                instance=minha_avaliacao
                or Avaliacao(obra=obra, usuario=request.user)
            )

    return render(
        request,
        "sistema/visualizar_obra.html",
        {
            "obra": obra,
            "leitura": leitura,
            "leitura_form": leitura_form,
            "estantes_usuario": estantes_usuario,
            "estantes_da_obra": estantes_da_obra,
            "avaliacoes": avaliacoes,
            "media_notas": media_notas,
            "total_avaliacoes": total_avaliacoes,
            "minha_avaliacao": minha_avaliacao,
            "avaliacao_form": avaliacao_form,
            "pode_gerenciar": pode_gerenciar_obra(request.user, obra),
            "capitulos": capitulos,
            "quantidade_capitulos": quantidade_capitulos,
            "primeiro_capitulo": primeiro_capitulo,
            "capitulos_lidos_ids": capitulos_lidos_ids,
        },
    )

#leitura de obra, onde o usuario pode ler a obra em formato PDF sendo mais  especifico ler livros
def ler_pdf(request, obra_id):
    obra = get_object_or_404(Obra, id=obra_id)

    if not pode_visualizar_obra(request.user, obra):
        raise Http404("Obra não encontrada.")

    if obra.formato != "BOOK" or not obra.arquivo_pdf:
        raise Http404("PDF indisponível.")

    try:
        arquivo = obra.arquivo_pdf.open("rb")
    except (FileNotFoundError, OSError):
        raise Http404("PDF indisponível.")

    resposta = FileResponse(
        arquivo,
        content_type="application/pdf",
        as_attachment=False,
        filename=f"{obra.titulo}.pdf",
    )
    resposta["Cache-Control"] = "private, no-store"
    resposta["X-Content-Type-Options"] = "nosniff"
    return resposta

#local onde o moderador ou admin pode gerenciar os volumes de uma obra do tipo WEBNOVEL
def gerenciar_volumes(request, obra_id):
    obra = get_object_or_404(Obra, id=obra_id, formato="WEBNOVEL")

    if not pode_visualizar_obra(request.user, obra):
        raise Http404("Obra não encontrada.")

    volumes = (
        obra.volumes.annotate(qtd_capitulos=Count("capitulos"))
        .order_by("ordem", "id")
    )
    capitulos_sem_volume = obra.capitulos.filter(volume__isnull=True).count()

    return render(
        request,
        "sistema/gerenciar_volumes.html",
        {
            "obra": obra,
            "volumes": volumes,
            "capitulos_sem_volume": capitulos_sem_volume,
            "pode_gerenciar": pode_gerenciar_obra(request.user, obra),
        },
    )

#onde o moderador ou admin pode criar um volume para uma obra do tipo WEBNOVEL
@moderador_requerido
def criar_volume(request, obra_id):
    obra = get_object_or_404(Obra, id=obra_id, formato="WEBNOVEL")

    if not pode_gerenciar_obra(request.user, obra):
        raise PermissionDenied(
            "Você não tem permissão para gerenciar volumes desta obra."
        )

    proxima_ordem = (
        obra.volumes.aggregate(maior=Max("ordem"))["maior"] or 0
    ) + 1
    volume = Volume(obra=obra, ordem=proxima_ordem)

    if request.method == "POST":
        form = VolumeForm(request.POST, instance=volume)
        if form.is_valid():
            volume = form.save()
            messages.success(
                request,
                f'Volume "{volume.titulo}" criado com sucesso. '
                "Selecione os capítulos que pertencem a ele.",
            )
            return redirect(
                "gerenciar_capitulos_volume",
                volume_id=volume.id,
            )
    else:
        form = VolumeForm(instance=volume)

    return render(
        request,
        "sistema/form_volume.html",
        {"form": form, "obra": obra, "volume": None},
    )

#onde o moderador ou admin pode editar um volume de uma obra do tipo WEBNOVEL
@moderador_requerido
def editar_volume(request, volume_id):
    volume = get_object_or_404(
        Volume.objects.select_related("obra"),
        id=volume_id,
    )
    obra = volume.obra

    if obra.formato != "WEBNOVEL":
        raise Http404("Volume não encontrado.")

    if not pode_gerenciar_obra(request.user, obra):
        raise PermissionDenied(
            "Você não tem permissão para gerenciar volumes desta obra."
        )

    if request.method == "POST":
        form = VolumeForm(request.POST, instance=volume)
        if form.is_valid():
            volume = form.save()
            messages.success(
                request,
                f'Volume "{volume.titulo}" atualizado com sucesso.',
            )
            return redirect("gerenciar_volumes", obra_id=obra.id)
    else:
        form = VolumeForm(instance=volume)

    return render(
        request,
        "sistema/form_volume.html",
        {"form": form, "obra": obra, "volume": volume},
    )

#local onde gerenciar os capítulos de um volume de uma obra do tipo WEBNOVEL, onde o moderador ou admin pode adicionar ou remover capítulos do volume
@moderador_requerido
def gerenciar_capitulos_volume(request, volume_id):
    volume = get_object_or_404(
        Volume.objects.select_related("obra"),
        id=volume_id,
    )
    obra = volume.obra

    if obra.formato != "WEBNOVEL":
        raise Http404("Volume não encontrado.")

    if not pode_gerenciar_obra(request.user, obra):
        raise PermissionDenied(
            "Você não tem permissão para gerenciar os capítulos deste volume."
        )

    capitulos = obra.capitulos.select_related("volume").order_by("numero")

    if request.method == "POST":
        form = VolumeCapitulosForm(request.POST, obra=obra)
        if form.is_valid():
            selecionados = form.capitulos_selecionados()
            ids_selecionados = {
                capitulo.id for capitulo in selecionados
            }
            ids_atuais = set(
                volume.capitulos.values_list("id", flat=True)
            )
            movidos = sum(
                1
                for capitulo in selecionados
                if capitulo.volume_id is not None
                and capitulo.volume_id != volume.id
            )

            with transaction.atomic():
                remover = ids_atuais - ids_selecionados
                if remover:
                    Capitulo.objects.filter(id__in=remover).update(
                        volume=None
                    )

                adicionar = ids_selecionados - ids_atuais
                if adicionar:
                    Capitulo.objects.filter(id__in=adicionar).update(
                        volume=volume
                    )

            total = len(ids_selecionados)
            mensagem = (
                f'Volume "{volume.titulo}" atualizado: {total} '
                f"capítulo{'s' if total != 1 else ''} "
                f"vinculado{'s' if total != 1 else ''}."
            )
            if movidos:
                mensagem += (
                    f" {movidos} capítulo{'s' if movidos != 1 else ''} "
                    f"movido{'s' if movidos != 1 else ''} de outro"
                    f"{'s' if movidos != 1 else ''} volume"
                    f"{'s' if movidos != 1 else ''}."
                )
            messages.success(request, mensagem)
            return redirect("gerenciar_volumes", obra_id=obra.id)

        selecionados_ids = set()
        for valor in request.POST.getlist("capitulos"):
            try:
                selecionados_ids.add(int(valor))
            except (TypeError, ValueError):
                continue
        selecionados_ids &= set(
            capitulos.values_list("id", flat=True)
        )
    else:
        form = VolumeCapitulosForm(obra=obra)
        selecionados_ids = set(
            volume.capitulos.values_list("id", flat=True)
        )

    return render(
        request,
        "sistema/volume_capitulos.html",
        {
            "obra": obra,
            "volume": volume,
            "capitulos": capitulos,
            "form": form,
            "selecionados_ids": selecionados_ids,
            "qtd_selecionados": len(selecionados_ids),
            "qtd_no_volume": volume.capitulos.count(),
            "qtd_sem_volume": obra.capitulos.filter(
                volume__isnull=True
            ).count(),
            "qtd_outros_volumes": obra.capitulos.filter(
                volume__isnull=False
            ).exclude(volume=volume).count(),
        },
    )

#onde o moderador ou admin pode adicionar um capítulo a uma obra do tipo WEBNOVEL
@moderador_requerido
def adicionar_capitulo(request, obra_id):
    obra = get_object_or_404(Obra, id=obra_id, formato="WEBNOVEL")

    if not pode_gerenciar_obra(request.user, obra):
        raise PermissionDenied(
            "Você não tem permissão para adicionar capítulos a esta obra."
        )

    capitulo = Capitulo(obra=obra)

    if request.method == "POST":
        form = CapituloForm(request.POST, instance=capitulo)
        if form.is_valid():
            form.save()
            messages.success(request, "Capítulo adicionado com sucesso.")
            return redirect("visualizar_obra", obra_id=obra.id)
    else:
        form = CapituloForm(instance=capitulo)

    return render(
        request,
        "sistema/form_capitulo.html",
        {"form": form, "obra": obra, "capitulo": None},
    )

#onde se pode editar um capítulo de uma obra do tipo WEBNOVEL, onde o moderador ou admin pode editar o capítulo
@moderador_requerido
def editar_capitulo(request, capitulo_id):
    capitulo = get_object_or_404(
        Capitulo.objects.select_related("obra"),
        id=capitulo_id,
    )
    obra = capitulo.obra

    if obra.formato != "WEBNOVEL":
        raise Http404("Capítulo não encontrado.")

    if not pode_gerenciar_obra(request.user, obra):
        raise PermissionDenied(
            "Você não tem permissão para editar este capítulo."
        )

    if request.method == "POST":
        form = CapituloForm(request.POST, instance=capitulo)
        if form.is_valid():
            form.save()
            messages.success(request, "Capítulo atualizado com sucesso.")
            return redirect("visualizar_obra", obra_id=obra.id)
    else:
        form = CapituloForm(instance=capitulo)

    return render(
        request,
        "sistema/form_capitulo.html",
        {"form": form, "obra": obra, "capitulo": capitulo},
    )

#onde pode se deletar um capítulo de uma obra do tipo WEBNOVEL, onde o moderador ou admin pode deletar o capítulo
@moderador_requerido
def deletar_capitulo(request, capitulo_id):
    capitulo = get_object_or_404(
        Capitulo.objects.select_related("obra"),
        id=capitulo_id,
    )
    obra = capitulo.obra

    if obra.formato != "WEBNOVEL":
        raise Http404("Capítulo não encontrado.")

    if not pode_gerenciar_obra(request.user, obra):
        raise PermissionDenied(
            "Você não tem permissão para excluir este capítulo."
        )

    if request.method == "POST":
        numero = capitulo.numero
        capitulo.delete()
        messages.success(request, f"Capítulo {numero} excluído com sucesso.")
        return redirect("visualizar_obra", obra_id=obra.id)

    return render(
        request,
        "sistema/deletar_capitulo.html",
        {"capitulo": capitulo, "obra": obra},
    )

#onde se torna possivel a leitur dentro do site
def ler_capitulo(request, capitulo_id):
    capitulo = get_object_or_404(
        Capitulo.objects.select_related("obra"),
        id=capitulo_id,
    )
    obra = capitulo.obra

    if obra.formato != "WEBNOVEL" or not pode_visualizar_obra(
        request.user,
        obra,
    ):
        raise Http404("Capítulo não encontrado.")

    anterior = (
        Capitulo.objects.filter(obra=obra, numero__lt=capitulo.numero)
        .order_by("-numero")
        .first()
    )
    proximo = (
        Capitulo.objects.filter(obra=obra, numero__gt=capitulo.numero)
        .order_by("numero")
        .first()
    )

    return render(
        request,
        "sistema/ler_capitulo.html",
        {
            "obra": obra,
            "capitulo": capitulo,
            "anterior": anterior,
            "proximo": proximo,
            "quantidade_capitulos": obra.capitulos.count(),
        },
    )

#onde ocorre o registro do progresso de leitura de um capítulo de uma obra do tipo WEBNOVEL, onde o usuario pode registrar se leu ou apenas acessou o capítulo
@login_required
@require_POST
def registrar_progresso_capitulo(request, capitulo_id):
    capitulo = get_object_or_404(
        Capitulo.objects.select_related("obra"),
        id=capitulo_id,
    )
    obra = capitulo.obra

    if obra.formato != "WEBNOVEL" or obra.estado != Obra.Estado.ATIVA:
        raise Http404("Capítulo não encontrado.")

    acao = request.POST.get("acao", "").strip()
    if not acao and request.content_type == "application/json":
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
            acao = str(payload.get("acao", "")).strip()
        except (ValueError, UnicodeDecodeError):
            acao = ""
    if acao not in ("acesso", "lido"):
        acao = "acesso"

    with transaction.atomic():
        leitura, _ = Leitura.objects.get_or_create(
            usuario=request.user,
            obra=obra,
        )
        leitura.ultimo_capitulo = capitulo

        if acao == "lido":
            CapituloLido.objects.get_or_create(
                usuario=request.user,
                obra=obra,
                capitulo=capitulo,
            )

        lidos = CapituloLido.objects.filter(
            usuario=request.user,
            obra=obra,
        ).count()
        total = obra.capitulos.count()
        leitura.progresso_atual = lidos
        if total > 0 and lidos >= total:
            leitura.status = Leitura.Status.CONCLUIDO
            if not leitura.concluido_em:
                leitura.concluido_em = timezone.now()
        else:
            leitura.status = Leitura.Status.LENDO
            leitura.concluido_em = None
        leitura.save()

    leitura._total_capitulos_cache = total
    leitura._capitulos_lidos_cache = lidos

    return JsonResponse(
        {
            "ok": True,
            "acao": acao,
            "ultimo_capitulo_id": capitulo.id,
            "lidos": lidos,
            "total": total,
            "percentual": leitura.percentual,
        }
    )

#onde o usuario pode ver todas as leituras que ele iniciou, seja de obras do tipo BOOK ou WEBNOVEL
@login_required
def minhas_leituras(request):
    base = Leitura.objects.filter(usuario=request.user).select_related(
        "obra",
        "ultimo_capitulo",
    )
    lendo = base.filter(status=Leitura.Status.LENDO).order_by("-atualizado_em")
    concluidas = base.filter(status=Leitura.Status.CONCLUIDO).order_by(
        "-concluido_em"
    )

    return render(
        request,
        "sistema/minhas_leituras.html",
        {"lendo": lendo, "concluidas": concluidas},
    )

#onde o usuario pode iniciar a leitura de uma obra do tipo BOOK ou WEBNOVEL, registrando o progresso de leitura
@login_required
@require_POST
def iniciar_leitura(request, obra_id):
    obra = get_object_or_404(Obra, id=obra_id, estado=Obra.Estado.ATIVA)

    if obra.formato == "WEBNOVEL":
        messages.info(
            request,
            "O progresso de Web Novels é registrado automaticamente durante a leitura dos capítulos.",
        )
        return redirect("visualizar_obra", obra_id=obra.id)

    if Leitura.objects.filter(usuario=request.user, obra=obra).exists():
        messages.info(request, "Você já acompanha esta obra.")
        return redirect("visualizar_obra", obra_id=obra.id)

    leitura = Leitura(usuario=request.user, obra=obra)
    form = LeituraForm(request.POST, instance=leitura)

    if form.is_valid():
        leitura = form.save(commit=False)
        leitura.save()
        if leitura.status == Leitura.Status.CONCLUIDO:
            messages.success(request, "Leitura registrada como concluída.")
        else:
            messages.success(request, "Acompanhamento iniciado.")
    else:
        erro = form.errors.get("progresso_atual")
        messages.error(
            request,
            erro[0] if erro else "Não foi possível iniciar o acompanhamento.",
        )

    return redirect("visualizar_obra", obra_id=obra.id)

#onde se atualiza o progresso de leitura de uma obra do tipo BOOK, registrando o progresso de leitura
@login_required
@require_POST
def atualizar_progresso(request, leitura_id):
    leitura = get_object_or_404(
        Leitura.objects.select_related("obra"),
        id=leitura_id,
        usuario=request.user,
    )

    if leitura.obra.formato == "WEBNOVEL":
        messages.info(
            request,
            "O progresso de Web Novels é atualizado automaticamente ao ler os capítulos.",
        )
        return redirect("visualizar_obra", obra_id=leitura.obra_id)

    form = LeituraForm(request.POST, instance=leitura)

    if form.is_valid():
        leitura = form.save(commit=False)
        leitura.save()
        if leitura.status == Leitura.Status.CONCLUIDO:
            messages.success(request, "Leitura concluída! Parabéns.")
        else:
            messages.success(request, "Progresso atualizado.")
    else:
        erro = form.errors.get("progresso_atual")
        messages.error(
            request,
            erro[0] if erro else "Não foi possível atualizar o progresso.",
        )

    return redirect("visualizar_obra", obra_id=leitura.obra_id)

#onde o usuario pode ver todas as estantes que ele criou, podendo criar, editar e deletar estantes
@login_required
def minhas_estantes(request):
    estantes = (
        Estante.objects.filter(usuario=request.user)
        .annotate(
            qtd_obras=Count(
                "obras",
                filter=Q(obras__estado=Obra.Estado.ATIVA),
            )
        )
        .order_by("nome")
    )
    return render(
        request,
        "sistema/minhas_estantes.html",
        {"estantes": estantes},
    )

#onde o usuario pode criar uma estante, podendo adicionar obras a ela
@login_required
def criar_estante(request):
    estante = Estante(usuario=request.user)

    if request.method == "POST":
        form = EstanteForm(request.POST, instance=estante)
        if form.is_valid():
            estante = form.save()
            messages.success(request, f'Estante "{estante.nome}" criada.')
            return redirect("visualizar_estante", estante_id=estante.id)
    else:
        form = EstanteForm(instance=estante)

    return render(
        request,
        "sistema/form_estante.html",
        {"form": form, "estante": None},
    )

#onde o usuario pode editar uma estante, podendo adicionar ou remover obras dela
@login_required
def editar_estante(request, estante_id):
    estante = get_object_or_404(
        Estante,
        id=estante_id,
        usuario=request.user,
    )

    if request.method == "POST":
        form = EstanteForm(request.POST, instance=estante)
        if form.is_valid():
            estante = form.save()
            messages.success(request, "Estante atualizada.")
            return redirect("visualizar_estante", estante_id=estante.id)
    else:
        form = EstanteForm(instance=estante)

    return render(
        request,
        "sistema/form_estante.html",
        {"form": form, "estante": estante},
    )

#onde o usuario pode deletar uma estante, removendo todas as obras dela
@login_required
def deletar_estante(request, estante_id):
    estante = get_object_or_404(
        Estante,
        id=estante_id,
        usuario=request.user,
    )

    if request.method == "POST":
        nome = estante.nome
        estante.delete()
        messages.success(request, f'Estante "{nome}" excluída.')
        return redirect("minhas_estantes")

    return render(
        request,
        "sistema/deletar_estante.html",
        {"estante": estante},
    )

#onde o usuario pode visualizar uma estante, podendo ver todas as obras que ela contém e adicionar novas obras a ela
@login_required
def visualizar_estante(request, estante_id):
    estante = get_object_or_404(
        Estante,
        id=estante_id,
        usuario=request.user,
    )
    obras = (
        estante.obras.filter(estado=Obra.Estado.ATIVA)
        .prefetch_related("generos")
        .order_by("titulo")
    )

    termo = request.GET.get("q", "").strip()
    candidatas = (
        Obra.objects.filter(estado=Obra.Estado.ATIVA)
        .exclude(estantes=estante)
        .order_by("titulo")
    )
    if termo:
        candidatas = candidatas.filter(
            Q(titulo__icontains=termo) | Q(autor__icontains=termo)
        )
    candidatas = candidatas[:12]

    return render(
        request,
        "sistema/visualizar_estante.html",
        {
            "estante": estante,
            "obras": obras,
            "candidatas": candidatas,
            "termo": termo,
        },
    )

#redireciona para a página de visualização da estante ou para a URL especificada no parâmetro "next" do POST
def _redirecionar_acao_estante(request, estante):
    destino = request.POST.get("next", "")
    if destino and url_has_allowed_host_and_scheme(
        destino,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(destino)
    return redirect("visualizar_estante", estante_id=estante.id)

#onde o usuario pode adicionar uma obra a uma estante, caso a obra já esteja na estante, uma mensagem de informação é exibida
@login_required
@require_POST
def adicionar_obra_estante(request):
    estante = get_object_or_404(
        Estante,
        id=request.POST.get("estante_id"),
        usuario=request.user,
    )
    obra = get_object_or_404(
        Obra,
        id=request.POST.get("obra_id"),
        estado=Obra.Estado.ATIVA,
    )

    if estante.obras.filter(id=obra.id).exists():
        messages.info(
            request,
            f'"{obra.titulo}" já está na estante "{estante.nome}".',
        )
    else:
        estante.obras.add(obra)
        messages.success(
            request,
            f'"{obra.titulo}" adicionada à estante "{estante.nome}".',
        )

    return _redirecionar_acao_estante(request, estante)

#onde o usuario pode remover uma obra de uma estante, caso a obra não esteja na estante, uma mensagem de informação é exibida
@login_required
@require_POST
def remover_obra_estante(request):
    estante = get_object_or_404(
        Estante,
        id=request.POST.get("estante_id"),
        usuario=request.user,
    )
    obra = get_object_or_404(Obra, id=request.POST.get("obra_id"))

    if estante.obras.filter(id=obra.id).exists():
        estante.obras.remove(obra)
        messages.success(
            request,
            f'"{obra.titulo}" removida da estante "{estante.nome}".',
        )
    else:
        messages.info(
            request,
            f'"{obra.titulo}" não está nesta estante.',
        )

    return _redirecionar_acao_estante(request, estante)

#onde o usuario pode salvar uma avaliação de uma obra, caso o usuário já tenha avaliado a obra, a avaliação será atualizada
@login_required
@require_POST
def salvar_avaliacao(request, obra_id):
    obra = get_object_or_404(
        Obra,
        id=obra_id,
        estado=Obra.Estado.ATIVA,
    )
    avaliacao = Avaliacao.objects.filter(
        usuario=request.user,
        obra=obra,
    ).first()
    form = AvaliacaoForm(
        request.POST,
        instance=avaliacao
        or Avaliacao(usuario=request.user, obra=obra),
    )

    if form.is_valid():
        form.save()
        if avaliacao:
            messages.success(request, "Avaliação atualizada.")
        else:
            messages.success(request, "Avaliação registrada.")
    else:
        erro = form.errors.get("nota") or form.errors.get("comentario")
        messages.error(
            request,
            erro[0] if erro else "Não foi possível salvar a avaliação.",
        )

    return redirect("visualizar_obra", obra_id=obra.id)

#onde o usuario pode deletar uma avaliação de uma obra, caso a avaliação não exista, uma mensagem de erro é exibida
@login_required
@require_POST
def deletar_avaliacao(request, avaliacao_id):
    avaliacao = get_object_or_404(
        Avaliacao,
        id=avaliacao_id,
        usuario=request.user,
    )
    obra_id = avaliacao.obra_id
    avaliacao.delete()
    messages.success(request, "Avaliação removida.")
    return redirect("visualizar_obra", obra_id=obra_id)

#onde o moderador ou admin pode ver todas as obras pendentes de aprovação, podendo aprovar ou rejeitar as obras
@moderador_requerido
def painel_moderacao(request):
    pendentes = (
        Obra.objects.filter(estado=Obra.Estado.PENDENTE)
        .select_related("submetido_por")
        .prefetch_related("generos")
        .order_by("criado_em")
    )
    return render(
        request,
        "sistema/painel_moderacao.html",
        {"pendentes": pendentes},
    )

#onde somente o admin pode aprovar ou rejeitar uma obra pendente de aprovação, caso a obra não esteja pendente, uma mensagem de erro é exibida
@admin_requerido
@require_POST
def moderar_obra(request, obra_id):
    obra = get_object_or_404(
        Obra,
        id=obra_id,
        estado=Obra.Estado.PENDENTE,
    )
    acao = request.POST.get("acao")

    if acao == "aprovar":
        obra.estado = Obra.Estado.ATIVA
        obra.motivo_rejeicao = ""
        obra.save()
        messages.success(
            request,
            f'Obra "{obra.titulo}" aprovada e publicada no catálogo.',
        )
    elif acao == "rejeitar":
        motivo = request.POST.get("motivo", "").strip()
        if not motivo:
            messages.error(request, "Informe o motivo da rejeição.")
            return redirect("painel_moderacao")
        obra.estado = Obra.Estado.REJEITADA
        obra.motivo_rejeicao = motivo
        obra.save()
        messages.success(request, f'Obra "{obra.titulo}" rejeitada.')
    else:
        messages.error(request, "Ação inválida.")

    return redirect("painel_moderacao")
#leitor 123
#mod 123

# criacao do login e registro de usuario
def registrar(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":
        form = RegistroForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(
                request,
                "Conta criada com sucesso. Bem-vindo(a) ao Gestão de Leitura!",
            )
            return redirect("dashboard")
    else:
        form = RegistroForm()

    return render(request, "registration/registro.html", {"form": form})

