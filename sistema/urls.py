from django.contrib.auth import views as auth_views
from django.urls import path

from sistema import views, views_epub
from sistema.forms import LoginForm

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path(
        "login/",
        auth_views.LoginView.as_view(
            template_name="registration/login.html",
            authentication_form=LoginForm,
        ),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("registro/", views.registrar, name="registro"),
    path("obras/", views.catalogo, name="catalogo"),
    path("minhas_leituras/", views.minhas_leituras, name="minhas_leituras"),
    path(
        "iniciar_leitura/<int:obra_id>/",
        views.iniciar_leitura,
        name="iniciar_leitura",
    ),
    path(
        "atualizar_progresso/<int:leitura_id>/",
        views.atualizar_progresso,
        name="atualizar_progresso",
    ),
    path("estantes/", views.minhas_estantes, name="minhas_estantes"),
    path("estantes/nova/", views.criar_estante, name="criar_estante"),
    path(
        "estantes/adicionar/",
        views.adicionar_obra_estante,
        name="adicionar_obra_estante",
    ),
    path(
        "estantes/remover/",
        views.remover_obra_estante,
        name="remover_obra_estante",
    ),
    path(
        "estantes/<int:estante_id>/",
        views.visualizar_estante,
        name="visualizar_estante",
    ),
    path(
        "estantes/<int:estante_id>/editar/",
        views.editar_estante,
        name="editar_estante",
    ),
    path(
        "estantes/<int:estante_id>/deletar/",
        views.deletar_estante,
        name="deletar_estante",
    ),
    path(
        "avaliar_obra/<int:obra_id>/",
        views.salvar_avaliacao,
        name="salvar_avaliacao",
    ),
    path(
        "deletar_avaliacao/<int:avaliacao_id>/",
        views.deletar_avaliacao,
        name="deletar_avaliacao",
    ),
    path("moderacao/", views.painel_moderacao, name="painel_moderacao"),
    path("moderacao/<int:obra_id>/", views.moderar_obra, name="moderar_obra"),
    path("adicionar_obra/", views.adicionar_obra, name="adicionar_obra"),
    path("editar_obra/<int:obra_id>/", views.editar_obra, name="editar_obra"),
    path("deletar_obra/<int:obra_id>/", views.deletar_obra, name="deletar_obra"),
    path(
        "visualizar_obra/<int:obra_id>/",
        views.visualizar_obra,
        name="visualizar_obra",
    ),
    path("ler_pdf/<int:obra_id>/", views.ler_pdf, name="ler_pdf"),
    path(
        "obras/<int:obra_id>/volumes/",
        views.gerenciar_volumes,
        name="gerenciar_volumes",
    ),
    path(
        "obras/<int:obra_id>/volumes/novo/",
        views.criar_volume,
        name="criar_volume",
    ),
    path(
        "volumes/<int:volume_id>/editar/",
        views.editar_volume,
        name="editar_volume",
    ),
    path(
        "obras/<int:obra_id>/capitulos/novo/",
        views.adicionar_capitulo,
        name="adicionar_capitulo",
    ),
    path(
        "obras/<int:obra_id>/capitulos/importar-epub/",
        views_epub.importar_epub,
        name="importar_epub",
    ),
    path(
        "obras/<int:obra_id>/capitulos/importar-epub/<uuid:token>/",
        views_epub.previa_importacao_epub,
        name="previa_importacao_epub",
    ),
    path(
        "obras/<int:obra_id>/capitulos/importar-epub/<uuid:token>/salvar/",
        views_epub.salvar_previa_epub,
        name="salvar_previa_epub",
    ),
    path(
        "capitulos/<int:capitulo_id>/ler/",
        views.ler_capitulo,
        name="ler_capitulo",
    ),
    path(
        "capitulos/<int:capitulo_id>/progresso/",
        views.registrar_progresso_capitulo,
        name="registrar_progresso_capitulo",
    ),
    path(
        "capitulos/<int:capitulo_id>/editar/",
        views.editar_capitulo,
        name="editar_capitulo",
    ),
    path(
        "capitulos/<int:capitulo_id>/deletar/",
        views.deletar_capitulo,
        name="deletar_capitulo",
    ),
]
