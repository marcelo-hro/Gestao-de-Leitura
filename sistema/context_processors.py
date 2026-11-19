from .models import Obra
from .permissoes import e_admin, e_moderador


def papeis(request):
    pode_moderar = e_moderador(request.user)
    return {
        "pode_moderar": pode_moderar,
        "pode_administrar": e_admin(request.user),
        "obras_pendentes": (
            Obra.objects.filter(estado=Obra.Estado.PENDENTE).count()
            if pode_moderar
            else 0
        ),
    }
