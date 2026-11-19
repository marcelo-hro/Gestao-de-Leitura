from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Perfil


@receiver(post_save, sender=User)
def garantir_perfil(sender, instance, created, **kwargs):
    papel_padrao = (
        Perfil.Papel.ADMIN if instance.is_superuser else Perfil.Papel.LEITOR
    )
    perfil, perfil_criado = Perfil.objects.get_or_create(
        usuario=instance,
        defaults={"papel": papel_padrao},
    )

    if not perfil_criado and instance.is_superuser and perfil.papel != Perfil.Papel.ADMIN:
        perfil.papel = Perfil.Papel.ADMIN
        perfil.save(update_fields=["papel"])
