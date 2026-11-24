from django import forms
from django.conf import settings
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User

from .models import Avaliacao, Capitulo, Estante, Leitura, Obra, Volume

ESTILO_INPUT = (
    "w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 "
    "text-slate-100 placeholder:text-slate-500 focus:border-indigo-400 "
    "focus:outline-none focus:ring-2 focus:ring-indigo-500/30"
)


class LoginForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({"class": ESTILO_INPUT})

        self.fields["username"].widget.attrs.update(
            {"autofocus": True, "placeholder": "Nome de usuário"}
        )
        self.fields["password"].widget.attrs.update({"placeholder": "Senha"})


class RegistroForm(UserCreationForm):
    email = forms.EmailField(label="E-mail", required=True)

    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({"class": ESTILO_INPUT})

        self.fields["username"].widget.attrs.update(
            {"autofocus": True, "placeholder": "Nome de usuário"}
        )
        self.fields["email"].widget.attrs.update(
            {"placeholder": "voce@exemplo.com"}
        )
        self.fields["password1"].widget.attrs.update({"placeholder": "Senha"})
        self.fields["password2"].widget.attrs.update(
            {"placeholder": "Confirme a senha"}
        )

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        if commit:
            user.save()
        return user


class ObraForm(forms.ModelForm):
    novo_genero = forms.CharField(
        label="Novo gênero",
        required=False,
        max_length=80,
        help_text=(
            "Opcional. Se o gênero ainda não existir, ele será criado e "
            "vinculado à obra."
        ),
        widget=forms.TextInput(
            attrs={"placeholder": "Ex.: Fantasia", "maxlength": 80}
        ),
    )

    class Meta:
        model = Obra
        fields = [
            "titulo",
            "autor",
            "sinopse",
            "formato",
            "total_de_unidades",
            "generos",
            "imagem",
            "arquivo_pdf",
        ]
        widgets = {
            "sinopse": forms.Textarea(attrs={"rows": 5}),
        }

    def __init__(
        self,
        *args,
        permitir_novo_genero=False,
        incluir_pdf=False,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.permitir_novo_genero = permitir_novo_genero
        self.incluir_pdf = incluir_pdf

        if not incluir_pdf:
            self.fields.pop("arquivo_pdf", None)
        else:
            limite_mb = getattr(
                settings,
                "PDF_MAX_UPLOAD_SIZE",
                20 * 1024 * 1024,
            ) / (1024 * 1024)
            limite_texto = f"{limite_mb:.0f}" if limite_mb >= 1 else "< 1"
            ajuda = (
                "Opcional. Apenas para o formato Livro. "
                f"Envie um arquivo .pdf de até {limite_texto} MB."
            )
            if self.instance.pk and self.instance.arquivo_pdf:
                ajuda += (
                    f" PDF atual: {self.instance.arquivo_pdf.name}. "
                    "Envie outro arquivo apenas para substituir."
                )
            self.fields["arquivo_pdf"].help_text = ajuda
            self.fields["arquivo_pdf"].widget = forms.FileInput(
                attrs={
                    "accept": ".pdf,application/pdf",
                    "class": "w-full rounded-lg border border-slate-300 "
                    "bg-white px-3 py-2 text-slate-900",
                }
            )

        campos_ordenados = [
            "titulo",
            "autor",
            "sinopse",
            "formato",
            "total_de_unidades",
            "generos",
            "novo_genero",
            "imagem",
        ]
        if incluir_pdf:
            campos_ordenados.append("arquivo_pdf")

        if permitir_novo_genero:
            self.fields["generos"].required = False
            self.order_fields(campos_ordenados)
        else:
            self.fields.pop("novo_genero", None)

        for field_name, field in self.fields.items():
            if field_name != "generos":
                field.widget.attrs.update(
                    {
                        "class": "w-full rounded-lg border border-slate-300 "
                        "bg-white px-3 py-2 text-slate-900"
                    }
                )

        self.fields["generos"].widget = forms.CheckboxSelectMultiple(
            choices=self.fields["generos"].choices,
            attrs={"id": "id_generos"},
        )

    def clean_novo_genero(self):
        return (self.cleaned_data.get("novo_genero") or "").strip()

    def clean(self):
        cleaned_data = super().clean()
        if (
            self.permitir_novo_genero
            and not cleaned_data.get("generos")
            and not cleaned_data.get("novo_genero")
        ):
            self.add_error(
                "generos",
                "Selecione ao menos um gênero ou informe um novo gênero.",
            )

        formato = cleaned_data.get("formato")
        if (
            formato
            and formato != "BOOK"
            and "arquivo_pdf" in self.files
        ):
            self.add_error(
                "arquivo_pdf",
                "O arquivo PDF só pode ser enviado para obras do formato Livro.",
            )

        return cleaned_data


class VolumeForm(forms.ModelForm):
    class Meta:
        model = Volume
        fields = ["titulo", "ordem"]
        labels = {
            "titulo": "Título do volume",
            "ordem": "Ordem de exibição",
        }
        widgets = {
            "titulo": forms.TextInput(
                attrs={"placeholder": "Ex.: Volume 1 ou Volume Bônus"}
            ),
            "ordem": forms.NumberInput(attrs={"min": 1}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({"class": ESTILO_INPUT})
        self.fields["titulo"].widget.attrs.update({"autofocus": True})

    def clean_titulo(self):
        titulo = (self.cleaned_data.get("titulo") or "").strip()
        if not titulo:
            raise forms.ValidationError("Informe um título para o volume.")
        if self.instance.obra_id:
            existentes = Volume.objects.filter(
                obra_id=self.instance.obra_id,
                titulo__iexact=titulo,
            )
            if self.instance.pk:
                existentes = existentes.exclude(pk=self.instance.pk)
            if existentes.exists():
                raise forms.ValidationError(
                    "Já existe um volume com este título nesta obra."
                )
        return titulo

    def clean_ordem(self):
        ordem = self.cleaned_data.get("ordem")
        if ordem is None or ordem < 1:
            raise forms.ValidationError(
                "A ordem de exibição deve ser maior que zero."
            )
        return ordem


class CapituloForm(forms.ModelForm):
    class Meta:
        model = Capitulo
        fields = ["numero", "volume", "titulo", "conteudo"]
        labels = {
            "numero": "Número do capítulo",
            "volume": "Volume",
            "titulo": "Título",
            "conteudo": "Conteúdo",
        }
        widgets = {
            "numero": forms.NumberInput(attrs={"min": 1}),
            "titulo": forms.TextInput(
                attrs={"placeholder": "Ex.: O começo de tudo"}
            ),
            "conteudo": forms.Textarea(
                attrs={
                    "rows": 16,
                    "placeholder": "Escreva o conteúdo do capítulo...",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.obra_id:
            self.fields["volume"].queryset = Volume.objects.filter(
                obra_id=self.instance.obra_id
            ).order_by("ordem", "id")
        else:
            self.fields["volume"].queryset = Volume.objects.none()
        self.fields["volume"].required = False
        self.fields["volume"].empty_label = "Sem volume"
        for field in self.fields.values():
            field.widget.attrs.update({"class": ESTILO_INPUT})

    def clean_volume(self):
        volume = self.cleaned_data.get("volume")
        if volume and self.instance.obra_id and volume.obra_id != self.instance.obra_id:
            raise forms.ValidationError(
                "O volume selecionado não pertence a esta obra."
            )
        return volume

    def clean_numero(self):
        numero = self.cleaned_data["numero"]
        if numero < 1:
            raise forms.ValidationError(
                "O número do capítulo deve ser maior que zero."
            )

        if self.instance.obra_id:
            existentes = Capitulo.objects.filter(
                obra_id=self.instance.obra_id,
                numero=numero,
            )
            if self.instance.pk:
                existentes = existentes.exclude(pk=self.instance.pk)
            if existentes.exists():
                raise forms.ValidationError(
                    "Já existe um capítulo com este número nesta obra."
                )

        return numero

    def clean_titulo(self):
        return self.cleaned_data["titulo"].strip()

    def clean_conteudo(self):
        return self.cleaned_data["conteudo"].strip()


class LeituraForm(forms.ModelForm):
    class Meta:
        model = Leitura
        fields = ["progresso_atual"]
        labels = {"progresso_atual": "Progresso atual"}
        widgets = {"progresso_atual": forms.NumberInput(attrs={"min": 0})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        total = self.instance.obra.total_de_unidades if self.instance.obra_id else ""
        self.fields["progresso_atual"].widget.attrs.update(
            {
                "class": ESTILO_INPUT,
                "min": 0,
                "max": total,
                "inputmode": "numeric",
            }
        )

    def clean_progresso_atual(self):
        valor = self.cleaned_data["progresso_atual"]
        if self.instance.obra_id:
            total = self.instance.obra.total_de_unidades
            if valor > total:
                raise forms.ValidationError(
                    f"O progresso não pode ultrapassar o total de {total}."
                )
        return valor


class EstanteForm(forms.ModelForm):
    class Meta:
        model = Estante
        fields = ["nome"]
        labels = {"nome": "Nome da estante"}
        widgets = {
            "nome": forms.TextInput(
                attrs={"placeholder": "Ex.: Fantasia favorita"}
            )
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["nome"].widget.attrs.update(
            {
                "class": ESTILO_INPUT,
                "autofocus": True,
                "maxlength": 100,
            }
        )

    def clean_nome(self):
        nome = self.cleaned_data["nome"].strip()
        if not nome:
            raise forms.ValidationError("Informe um nome para a estante.")

        if self.instance.usuario_id:
            existentes = Estante.objects.filter(
                usuario_id=self.instance.usuario_id,
                nome__iexact=nome,
            )
            if self.instance.pk:
                existentes = existentes.exclude(pk=self.instance.pk)
            if existentes.exists():
                raise forms.ValidationError(
                    "Você já tem uma estante com esse nome."
                )

        return nome


class AvaliacaoForm(forms.ModelForm):
    class Meta:
        model = Avaliacao
        fields = ["nota", "comentario"]
        labels = {
            "nota": "Nota",
            "comentario": "Comentário (opcional)",
        }
        widgets = {
            "nota": forms.Select(),
            "comentario": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": (
                        "Conte o que você achou da obra (opcional)."
                    ),
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({"class": ESTILO_INPUT})

    def clean_comentario(self):
        return self.cleaned_data["comentario"].strip()
