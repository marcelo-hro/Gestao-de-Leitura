from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

from .models import Obra, Perfil


def obter_papel(user):
    if not getattr(user, "is_authenticated", False):
        return None

    if hasattr(user, "_papel_cache"):
        return user._papel_cache

    if user.is_superuser:
        papel = Perfil.Papel.ADMIN
    else:
        perfil = Perfil.objects.filter(usuario=user).only("papel").first()
        papel = perfil.papel if perfil else Perfil.Papel.LEITOR

    user._papel_cache = papel
    return papel


def e_moderador(user):
    return obter_papel(user) in (Perfil.Papel.MODERADOR, Perfil.Papel.ADMIN)


def e_admin(user):
    return obter_papel(user) == Perfil.Papel.ADMIN


def pode_gerenciar_obra(user, obra):
    if e_admin(user):
        return True
    return (
        e_moderador(user)
        and obra.estado == Obra.Estado.PENDENTE
        and obra.submetido_por_id == getattr(user, "id", None)
    )


def pode_visualizar_obra(user, obra):
    if obra.estado == Obra.Estado.ATIVA:
        return True
    return e_moderador(user) or (
        getattr(user, "is_authenticated", False)
        and obra.submetido_por_id == getattr(user, "id", None)
    )


def moderador_requerido(view_func):
    @login_required
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not e_moderador(request.user):
            raise PermissionDenied("Apenas moderadores podem executar esta ação.")
        return view_func(request, *args, **kwargs)

    return _wrapped


def admin_requerido(view_func):
    @login_required
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not e_admin(request.user):
            raise PermissionDenied(
                "Apenas administradores podem aprovar ou rejeitar obras."
            )
        return view_func(request, *args, **kwargs)

    return _wrapped
