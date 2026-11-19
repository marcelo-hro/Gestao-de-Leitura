from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Avg, Count, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from sistema.forms import (
    AvaliacaoForm,
    EstanteForm,
    LeituraForm,
    ObraForm,
    RegistroForm,
)
from .models import Avaliacao, Estante, Leitura, Obra
from .permissoes import e_moderador, moderador_requerido


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
            .select_related("obra")
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
        form = ObraForm(request.POST, request.FILES)

        if form.is_valid():
            obra = form.save(commit=False)
            obra.submetido_por = request.user
            obra.estado = Obra.Estado.PENDENTE
            obra.save()
            form.save_m2m()

            messages.success(request, "Obra enviada para aprovação do administrador.")
            return redirect("visualizar_obra", obra_id=obra.id)

            
        form = ObraForm()

    return render(
        request,
        "sistema/adicionar_obra.html",
        {"form": form},
    )


@moderador_requerido
def editar_obra(request, obra_id):
    obra = get_object_or_404(Obra, id=obra_id)

    if request.method == "POST":
        form = ObraForm(request.POST, request.FILES, instance=obra)
        if form.is_valid():
            form.save()
            messages.success(request, "Obra atualizada com sucesso.")
            if obra.estado == Obra.Estado.PENDENTE:
                return redirect("painel_moderacao")
            return redirect("visualizar_obra", obra_id=obra.id)
    else:
        form = ObraForm(instance=obra)

    return render(
        request,
        "sistema/editar_obra.html",
        {"form": form, "obra": obra},
    )


@moderador_requerido
def deletar_obra(request, obra_id):
    obra = get_object_or_404(Obra, id=obra_id)
    era_pendente = obra.estado == Obra.Estado.PENDENTE

    if request.method == "POST":
        titulo = obra.titulo
        obra.delete()
        messages.success(request, f'Obra "{titulo}" eliminada com sucesso.')
        if era_pendente:
            return redirect("painel_moderacao")
        return redirect("catalogo")

    return render(request, "sistema/deletar_obra.html", {"obra": obra})


def visualizar_obra(request, obra_id):
    obra = get_object_or_404(Obra, id=obra_id)

    if obra.estado != Obra.Estado.ATIVA:
        pode_ver = e_moderador(request.user) or (
            request.user.is_authenticated
            and obra.submetido_por_id == request.user.id
        )
        if not pode_ver:
            raise Http404("Obra não encontrada.")

    leitura = None
    leitura_form = None
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
        leitura = Leitura.objects.filter(
            usuario=request.user,
            obra=obra,
        ).first()
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
        },
    )


@login_required
def minhas_leituras(request):
    base = Leitura.objects.filter(usuario=request.user).select_related("obra")
    lendo = base.filter(status=Leitura.Status.LENDO).order_by("-atualizado_em")
    concluidas = base.filter(status=Leitura.Status.CONCLUIDO).order_by(
        "-concluido_em"
    )

    return render(
        request,
        "sistema/minhas_leituras.html",
        {"lendo": lendo, "concluidas": concluidas},
    )


@login_required
@require_POST
def iniciar_leitura(request, obra_id):
    obra = get_object_or_404(Obra, id=obra_id, estado=Obra.Estado.ATIVA)

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


@login_required
@require_POST
def atualizar_progresso(request, leitura_id):
    leitura = get_object_or_404(
        Leitura,
        id=leitura_id,
        usuario=request.user,
    )
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


def _redirecionar_acao_estante(request, estante):
    destino = request.POST.get("next", "")
    if destino and url_has_allowed_host_and_scheme(
        destino,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(destino)
    return redirect("visualizar_estante", estante_id=estante.id)


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


@moderador_requerido
@require_POST
def moderar_obra(request, obra_id):
    obra = get_object_or_404(Obra, id=obra_id)
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


#perfis criados até entao
# Usuario: marcelo Senha:reis1234
# Usuario: leitor Senha: 123
# Usuario: moderador Senha: 123

