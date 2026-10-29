from django import forms
from .models import Obra

class ObraForm(forms.ModelForm):
    class Meta:
        model = Obra
        fields = '__all__'
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            if field_name != 'generos':
                field.widget.attrs.update({
                    'class': 'w-full p-2.5 rounded-lg border border-slate-300 bg-white text-slate-900'
                })
        
        self.fields['generos'].widget = forms.CheckboxSelectMultiple(
    choices=self.fields['generos'].choices,
    attrs={'id': 'id_generos'}
)
           