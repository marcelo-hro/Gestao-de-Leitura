from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User

from .models import Avaliacao, Estante, Leitura, Obra

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
        ]
        widgets = {
            "sinopse": forms.Textarea(attrs={"rows": 5}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
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
