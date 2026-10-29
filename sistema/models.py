from django.db import models
from django.contrib.auth.models import User



class Genero(models.Model):
    nome = models.CharField("Nome", max_length=80, unique=True)

    def __str__(self):
        return self.nome



class Obra(models.Model):
    FORMAT_CHOICES = [
        ("BOOK", "Livro (Páginas)"),
        ("WEBNOVEL", "Web Novel (Capítulos)"),
    ]
    titulo = models.CharField("Título", max_length=255, unique=True)
    formato = models.CharField("Formato", max_length=15, choices=FORMAT_CHOICES, default="BOOK")
    autor = models.CharField("Autor", max_length=150)
    total_de_unidades = models.PositiveIntegerField("Total de Páginas/Capítulos")
    generos = models.ManyToManyField(Genero, verbose_name="Gêneros")
    criado_em = models.DateTimeField(auto_now_add=True)
    imagem = models.ImageField("Imagem", upload_to="obras/", null=True, blank=True)

    def __str__(self):
        return f"{self.titulo} ({self.get_formato_display()})"

# Create your models here.
