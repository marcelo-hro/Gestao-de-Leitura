from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


class Perfil(models.Model):
    class Papel(models.TextChoices):
        LEITOR = "LEITOR", "Leitor"
        MODERADOR = "MODERADOR", "Moderador"
        ADMIN = "ADMIN", "Administrador"

    usuario = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="perfil",
        verbose_name="Usuário",
    )
    papel = models.CharField(
        "Papel",
        max_length=20,
        choices=Papel.choices,
        default=Papel.LEITOR,
    )
    criado_em = models.DateTimeField("Criado em", auto_now_add=True)

    class Meta:
        verbose_name = "Perfil"
        verbose_name_plural = "Perfis"
        ordering = ["usuario__username"]

    def __str__(self):
        return f"{self.usuario.username} ({self.get_papel_display()})"


class Genero(models.Model):
    nome = models.CharField("Nome", max_length=80, unique=True)

    def __str__(self):
        return self.nome



class Obra(models.Model):
    FORMAT_CHOICES = [
        ("BOOK", "Livro (Páginas)"),
        ("WEBNOVEL", "Web Novel (Capítulos)"),
    ]

    class Estado(models.TextChoices):
        PENDENTE = "PENDENTE", "Pendente"
        ATIVA = "ATIVA", "Ativa"
        REJEITADA = "REJEITADA", "Rejeitada"

    titulo = models.CharField("Título", max_length=255, unique=True)
    autor = models.CharField("Autor", max_length=150)
    sinopse = models.TextField(
        "Sinopse",
        default="",
        help_text="Resumo da obra exibido no catálogo.",
    )
    formato = models.CharField("Formato", max_length=15, choices=FORMAT_CHOICES, default="BOOK")
    total_de_unidades = models.PositiveIntegerField("Total de Páginas/Capítulos")
    generos = models.ManyToManyField(Genero, verbose_name="Gêneros")
    imagem = models.ImageField("Imagem", upload_to="obras/", null=True, blank=True)
    estado = models.CharField(
        "Estado",
        max_length=10,
        choices=Estado.choices,
        default=Estado.PENDENTE,
    )
    submetido_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="obras_submetidas",
        verbose_name="Submetido por",
    )
    motivo_rejeicao = models.TextField(
        "Motivo da rejeição",
        blank=True,
        default="",
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.titulo} ({self.get_formato_display()})"


class Leitura(models.Model):
    class Status(models.TextChoices):
        LENDO = "LENDO", "Lendo"
        CONCLUIDO = "CONCLUIDO", "Concluído"

    usuario = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="leituras",
        verbose_name="Usuário",
    )
    obra = models.ForeignKey(
        Obra,
        on_delete=models.CASCADE,
        related_name="leituras",
        verbose_name="Obra",
    )
    status = models.CharField(
        "Status",
        max_length=10,
        choices=Status.choices,
        default=Status.LENDO,
    )
    progresso_atual = models.PositiveIntegerField("Progresso atual", default=0)
    iniciado_em = models.DateTimeField("Iniciado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("Atualizado em", auto_now=True)
    concluido_em = models.DateTimeField("Concluído em", null=True, blank=True)

    class Meta:
        verbose_name = "Leitura"
        verbose_name_plural = "Leituras"
        unique_together = ("usuario", "obra")
        ordering = ["-atualizado_em"]

    def __str__(self):
        return f"{self.usuario.username} - {self.obra.titulo}"

    @property
    def percentual(self):
        total = self.obra.total_de_unidades
        if not total:
            return 100 if self.status == self.Status.CONCLUIDO else 0
        return min(100, round(self.progresso_atual * 100 / total))

    def clean(self):
        super().clean()
        if not self.obra_id:
            return

        total = (
            Obra.objects.filter(pk=self.obra_id)
            .values_list("total_de_unidades", flat=True)
            .first()
        )
        if total is not None and self.progresso_atual > total:
            raise ValidationError(
                {
                    "progresso_atual": (
                        "O progresso não pode ultrapassar o total de "
                        "páginas/capítulos da obra."
                    )
                }
            )

    def save(self, *args, **kwargs):
        if self.progresso_atual >= self.obra.total_de_unidades:
            self.progresso_atual = self.obra.total_de_unidades
            self.status = self.Status.CONCLUIDO
            if not self.concluido_em:
                self.concluido_em = timezone.now()
        else:
            self.status = self.Status.LENDO
            self.concluido_em = None

        super().save(*args, **kwargs)


class Estante(models.Model):
    usuario = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="estantes",
        verbose_name="Usuário",
    )
    nome = models.CharField("Nome", max_length=100)
    obras = models.ManyToManyField(
        Obra,
        related_name="estantes",
        verbose_name="Obras",
        blank=True,
    )
    criada_em = models.DateTimeField("Criada em", auto_now_add=True)
    atualizada_em = models.DateTimeField("Atualizada em", auto_now=True)

    class Meta:
        verbose_name = "Estante"
        verbose_name_plural = "Estantes"
        ordering = ["nome"]
        constraints = [
            models.UniqueConstraint(
                fields=["usuario", "nome"],
                name="estante_unica_por_usuario",
            )
        ]

    def __str__(self):
        return f"{self.nome} ({self.usuario.username})"


class Avaliacao(models.Model):
    NOTA_CHOICES = [
        (1, "1 estrela"),
        (2, "2 estrelas"),
        (3, "3 estrelas"),
        (4, "4 estrelas"),
        (5, "5 estrelas"),
    ]

    usuario = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="avaliacoes",
        verbose_name="Usuário",
    )
    obra = models.ForeignKey(
        Obra,
        on_delete=models.CASCADE,
        related_name="avaliacoes",
        verbose_name="Obra",
    )
    nota = models.PositiveSmallIntegerField(
        "Nota",
        choices=NOTA_CHOICES,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    comentario = models.TextField("Comentário", blank=True, default="")
    criada_em = models.DateTimeField("Criada em", auto_now_add=True)
    atualizada_em = models.DateTimeField("Atualizada em", auto_now=True)

    class Meta:
        verbose_name = "Avaliação"
        verbose_name_plural = "Avaliações"
        unique_together = ("usuario", "obra")
        ordering = ["-atualizada_em"]

    def __str__(self):
        return (
            f"{self.usuario.username} - {self.obra.titulo} "
            f"({self.nota}/5)"
        )
