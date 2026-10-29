from django.contrib import admin
from django.urls import path
from sistema import views
from sistema.views import catalogo
urlpatterns = [

    path('', views.catalogo, name='catalogo'),
    path('adicionar_obra/', views.adicionar_obra, name='adicionar_obra'),
    path('editar_obra/<int:obra_id>/', views.editar_obra, name='editar_obra'),
    path('deletar_obra/<int:obra_id>/', views.deletar_obra, name='deletar_obra'),
    path('visualizar_obra/<int:obra_id>/', views.visualizar_obra, name='visualizar_obra'),

]