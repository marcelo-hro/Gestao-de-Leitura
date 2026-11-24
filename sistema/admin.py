from django.contrib import admin

from .models import (
    Avaliacao,
    Capitulo,
    CapituloLido,
    Estante,
    Genero,
    Leitura,
    Obra,
    Perfil,
    Volume,
)
from .permissoes import e_admin


@admin.register(Perfil)
class PerfilAdmin(admin.ModelAdmin):
    list_display = ("usuario", "papel", "criado_em")
    list_editable = ("papel",)
    list_filter = ("papel",)
    search_fields = ("usuario__username", "usuario__email")


@admin.register(Genero)
class GeneroAdmin(admin.ModelAdmin):
    list_display = ("nome",)
    search_fields = ("nome",)


@admin.register(Obra)
class ObraAdmin(admin.ModelAdmin):
    list_display = (
        "titulo",
        "autor",
        "formato",
        "estado",
        "submetido_por",
        "total_de_unidades",
        "criado_em",
    )
    list_filter = ("estado", "formato", "generos")
    search_fields = ("titulo", "autor", "sinopse")
    filter_horizontal = ("generos",)
    readonly_fields = ("criado_em",)

    def has_add_permission(self, request):
        return e_admin(request.user) and super().has_add_permission(request)

    def has_change_permission(self, request, obj=None):
        return e_admin(request.user) and super().has_change_permission(
            request,
            obj,
        )

    def has_delete_permission(self, request, obj=None):
        return e_admin(request.user) and super().has_delete_permission(
            request,
            obj,
        )


@admin.register(Volume)
class VolumeAdmin(admin.ModelAdmin):
    list_display = ("obra", "ordem", "titulo")
    list_filter = ("obra",)
    search_fields = ("titulo", "obra__titulo")
    list_select_related = ("obra",)
    ordering = ("obra__titulo", "ordem", "id")


@admin.register(Capitulo)
class CapituloAdmin(admin.ModelAdmin):
    list_display = ("obra", "volume", "numero", "titulo")
    list_filter = ("obra__formato",)
    search_fields = ("titulo", "conteudo", "obra__titulo")
    list_select_related = ("obra", "volume")
    ordering = ("obra__titulo", "numero")


@admin.register(CapituloLido)
class CapituloLidoAdmin(admin.ModelAdmin):
    list_display = ("usuario", "obra", "capitulo", "lido_em")
    search_fields = ("usuario__username", "obra__titulo", "capitulo__titulo")
    list_select_related = ("usuario", "obra", "capitulo")
    readonly_fields = ("lido_em",)


@admin.register(Leitura)
class LeituraAdmin(admin.ModelAdmin):
    list_display = (
        "usuario",
        "obra",
        "status",
        "progresso_atual",
        "percentual",
        "atualizado_em",
    )
    list_filter = ("status",)
    search_fields = ("usuario__username", "obra__titulo")
    list_select_related = ("usuario", "obra")
    readonly_fields = ("status", "iniciado_em", "atualizado_em", "concluido_em")


@admin.register(Estante)
class EstanteAdmin(admin.ModelAdmin):
    list_display = ("nome", "usuario", "criada_em", "atualizada_em")
    list_filter = ("usuario",)
    search_fields = ("nome", "usuario__username")
    filter_horizontal = ("obras",)
    list_select_related = ("usuario",)
    readonly_fields = ("criada_em", "atualizada_em")


@admin.register(Avaliacao)
class AvaliacaoAdmin(admin.ModelAdmin):
    list_display = (
        "usuario",
        "obra",
        "nota",
        "atualizada_em",
    )
    list_filter = ("nota",)
    search_fields = ("usuario__username", "obra__titulo", "comentario")
    list_select_related = ("usuario", "obra")
    readonly_fields = ("criada_em", "atualizada_em")
