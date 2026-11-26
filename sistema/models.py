import uuid

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import (
    FileExtensionValidator,
    MaxValueValidator,
    MinValueValidator,
)
from django.db import models
from django.utils import timezone

from .storage import ArmazenamentoPdfPrivado
from .validators import validar_assinatura_pdf, validar_tamanho_pdf

#onde se define o papel de um usuario
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

#onde se define o gênero de uma obra
class Genero(models.Model):
    nome = models.CharField("Nome", max_length=80, unique=True)

    def __str__(self):
        return self.nome


#representa uma obra literária, que pode ser um livro ou uma web novel, com informações como título, autor, sinopse, formato, total de unidades (páginas ou capítulos), gêneros, imagem, arquivo PDF, estado (pendente, ativa ou rejeitada), usuário que submeteu a obra e motivo de rejeição. Além disso, possui relacionamentos com volumes e capítulos no caso de web novels.
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
    arquivo_pdf = models.FileField(
        "Arquivo PDF",
        upload_to="obras/pdf/%Y/%m/",
        storage=ArmazenamentoPdfPrivado(),
        null=True,
        blank=True,
        max_length=255,
        validators=[
            FileExtensionValidator(
                allowed_extensions=["pdf"],
                message="Envie um arquivo com extensão .pdf.",
            ),
            validar_assinatura_pdf,
            validar_tamanho_pdf,
        ],
    )
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

#local onde agrupa os capitulos de uma obra do tipo Web Novel, permitindo organizar os capítulos em volumes com título e ordem de exibição. Cada volume pertence a uma obra específica e possui restrições de validação para garantir que só possa ser vinculado a obras do formato Web Novel.
class Volume(models.Model):
    obra = models.ForeignKey(
        Obra,
        on_delete=models.CASCADE,
        related_name="volumes",
        verbose_name="Obra",
    )
    titulo = models.CharField("Título", max_length=150)
    ordem = models.PositiveIntegerField(
        "Ordem de exibição",
        default=1,
        validators=[MinValueValidator(1)],
    )

    class Meta:
        verbose_name = "Volume"
        verbose_name_plural = "Volumes"
        ordering = ["ordem", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["obra", "titulo"],
                name="volume_titulo_unico_por_obra",
            ),
        ]

    def __str__(self):
        return self.titulo

    def clean(self):
        super().clean()
        if self.obra_id and self.obra.formato != "WEBNOVEL":
            raise ValidationError(
                {
                    "obra": (
                        "Volumes só podem ser vinculados a obras do "
                        "formato Web Novel."
                    )
                }
            )

#onde guarda a obra do tipo Web Novel, com informações como número, título, conteúdo e volume associado. Cada capítulo pertence a uma obra específica e possui restrições de validação para garantir que só possa ser vinculado a obras do formato Web Novel e que o volume escolhido pertença à mesma obra.
class Capitulo(models.Model):
    obra = models.ForeignKey(
        Obra,
        on_delete=models.CASCADE,
        related_name="capitulos",
        verbose_name="Obra",
    )
    numero = models.PositiveIntegerField(
        "Número",
        validators=[MinValueValidator(1)],
    )
    titulo = models.CharField("Título", max_length=255)
    conteudo = models.TextField("Conteúdo")
    volume = models.ForeignKey(
        Volume,
        on_delete=models.SET_NULL,
        related_name="capitulos",
        verbose_name="Volume",
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = "Capítulo"
        verbose_name_plural = "Capítulos"
        ordering = ["numero"]
        constraints = [
            models.UniqueConstraint(
                fields=["obra", "numero"],
                name="capitulo_numero_unico_por_obra",
            ),
            models.CheckConstraint(
                condition=models.Q(numero__gt=0),
                name="capitulo_numero_positivo",
            ),
        ]

    def __str__(self):
        return f"{self.obra.titulo} - Capítulo {self.numero}"

    def clean(self):
        super().clean()
        if self.obra_id and self.obra.formato != "WEBNOVEL":
            raise ValidationError(
                {
                    "obra": (
                        "Capítulos só podem ser vinculados a obras do "
                        "formato Web Novel."
                    )
                }
            )
        if self.volume_id and self.obra_id and self.volume.obra_id != self.obra_id:
            raise ValidationError(
                {
                    "volume": "O volume escolhido precisa pertencer à mesma obra."
                }
            )

#onde representa uma prévia de importação de capítulos a partir de um arquivo EPUB, associada a um usuário e uma obra específica. Contém informações sobre o arquivo da prévia, a seleção de capítulos, avisos gerados durante a importação, se há ambiguidade na seleção, o total de capítulos detectados, a data de criação e a data de expiração da prévia.
class PreviaImportacaoEpub(models.Model):
    token = models.UUIDField(
        "Token",
        default=uuid.uuid4,
        unique=True,
        editable=False,
    )
    usuario = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="previas_importacao_epub",
        verbose_name="Usuário",
    )
    obra = models.ForeignKey(
        Obra,
        on_delete=models.CASCADE,
        related_name="previas_importacao_epub",
        verbose_name="Obra",
    )
    arquivo = models.CharField("Arquivo da prévia", max_length=255)
    selecao = models.JSONField("Seleção", default=dict, blank=True)
    avisos = models.JSONField("Avisos", default=list, blank=True)
    ambiguidade = models.BooleanField("Ambiguidade", default=False)
    total_detectado = models.PositiveIntegerField("Total detectado", default=0)
    criado_em = models.DateTimeField("Criada em", auto_now_add=True)
    expira_em = models.DateTimeField("Expira em", db_index=True)

    class Meta:
        verbose_name = "Prévia de importação de EPUB"
        verbose_name_plural = "Prévias de importação de EPUB"
        ordering = ["-criado_em"]

    def __str__(self):
        return f"Prévia {self.token} - {self.obra.titulo}"

    @property
    def expirada(self):
        return self.expira_em <= timezone.now()

#onde se guarda o progresso de leitura de uma obra por um usuário, incluindo informações como status (lendo ou concluído), progresso atual, último capítulo acessado, datas de início, atualização e conclusão da leitura. Além disso, possui propriedades para calcular o total de capítulos disponíveis, o total de capítulos lidos e o percentual de progresso da leitura.
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
    ultimo_capitulo = models.ForeignKey(
        Capitulo,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="leituras_ultimo_acesso",
        verbose_name="Último capítulo acessado",
    )
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
    def total_capitulos_disponiveis(self):
        if hasattr(self, "_total_capitulos_cache"):
            return self._total_capitulos_cache
        if self.obra.formato == "WEBNOVEL":
            return self.obra.capitulos.count()
        return self.obra.total_de_unidades

    @property
    def capitulos_lidos_total(self):
        if hasattr(self, "_capitulos_lidos_cache"):
            return self._capitulos_lidos_cache
        if self.obra.formato == "WEBNOVEL":
            return CapituloLido.objects.filter(
                usuario_id=self.usuario_id,
                obra_id=self.obra_id,
            ).count()
        return self.progresso_atual

    @property
    def percentual(self):
        if self.obra.formato == "WEBNOVEL":
            total_disp = self.total_capitulos_disponiveis
            if total_disp > 0:
                return min(100, round(self.capitulos_lidos_total * 100 / total_disp))
        total = self.obra.total_de_unidades
        if not total:
            return 100 if self.status == self.Status.CONCLUIDO else 0
        return min(100, round(self.progresso_atual * 100 / total))

    def clean(self):
        super().clean()
        if not self.obra_id:
            return

        if self.obra.formato == "WEBNOVEL":
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
        if self.obra.formato == "WEBNOVEL":
            total_disp = self.obra.capitulos.count()
            if total_disp > 0:
                if self.progresso_atual >= total_disp:
                    self.progresso_atual = total_disp
                    self.status = self.Status.CONCLUIDO
                    if not self.concluido_em:
                        self.concluido_em = timezone.now()
                else:
                    self.status = self.Status.LENDO
                    self.concluido_em = None
            else:
                if self.obra.total_de_unidades and self.progresso_atual >= self.obra.total_de_unidades:
                    self.progresso_atual = self.obra.total_de_unidades
                    self.status = self.Status.CONCLUIDO
                    if not self.concluido_em:
                        self.concluido_em = timezone.now()
                else:
                    self.status = self.Status.LENDO
                    self.concluido_em = None
        else:
            if self.progresso_atual >= self.obra.total_de_unidades:
                self.progresso_atual = self.obra.total_de_unidades
                self.status = self.Status.CONCLUIDO
                if not self.concluido_em:
                    self.concluido_em = timezone.now()
            else:
                self.status = self.Status.LENDO
                self.concluido_em = None

        super().save(*args, **kwargs)

#registra o fato de um usuário ter lido um capítulo específico de uma obra, armazenando informações como o usuário, a obra, o capítulo e a data em que foi lido. Além disso, possui restrições para garantir que cada usuário só possa registrar a leitura de um capítulo uma vez e índices para otimizar consultas relacionadas a leituras de capítulos por usuário e obra.
class CapituloLido(models.Model):
    usuario = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="capitulos_lidos",
        verbose_name="Usuário",
    )
    obra = models.ForeignKey(
        Obra,
        on_delete=models.CASCADE,
        related_name="capitulos_lidos",
        verbose_name="Obra",
    )
    capitulo = models.ForeignKey(
        Capitulo,
        on_delete=models.CASCADE,
        related_name="leituras_concluidas",
        verbose_name="Capítulo",
    )
    lido_em = models.DateTimeField("Lido em", auto_now_add=True)

    class Meta:
        verbose_name = "Capítulo lido"
        verbose_name_plural = "Capítulos lidos"
        constraints = [
            models.UniqueConstraint(
                fields=["usuario", "capitulo"],
                name="capitulo_lido_unico_por_usuario",
            ),
        ]
        indexes = [
            models.Index(fields=["usuario", "obra"], name="cap_lido_usr_obra_idx"),
        ]

    def __str__(self):
        return f"{self.usuario.username} - {self.capitulo}"

#onde representa uma estante de livros de um usuário, permitindo que ele organize suas obras favoritas em diferentes estantes com nomes personalizados. Cada estante pertence a um usuário específico e pode conter várias obras, enquanto cada obra pode estar presente em várias estantes. Além disso, possui restrições para garantir que cada usuário não tenha estantes com nomes duplicados.
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

#onde representa uma avaliação de uma obra feita por um usuário, incluindo informações como a nota atribuída, o comentário opcional, a data de criação e atualização da avaliação. Cada avaliação está associada a um usuário e a uma obra específica, e possui restrições para garantir que cada usuário só possa avaliar uma obra uma vez.
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
