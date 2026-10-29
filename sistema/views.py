from django.shortcuts import redirect, render

from sistema.forms import ObraForm
from .models import Obra

def catalogo(request):
    todas_as_obras = Obra.objects.all().prefetch_related('generos')
    return render(request, 'sistema/catalogo.html', {'obras': todas_as_obras})


def adicionar_obra(request):
    if request.method == 'POST':
        form = ObraForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            return redirect('catalogo')
    else:
        form = ObraForm()
    return render(request, 'sistema/adicionar_obra.html', {'form': form})

def editar_obra(request, obra_id):
    obra = Obra.objects.get(id=obra_id)
    if request.method == 'POST':
        form = ObraForm(request.POST, request.FILES, instance=obra)
        if form.is_valid():
            form.save()
            return redirect('catalogo')
    else:
        form = ObraForm(instance=obra)
    return render(request, 'sistema/editar_obra.html', {'form': form, 'obra': obra})


def deletar_obra(request, obra_id):
    obra = Obra.objects.get(id=obra_id)
    obra.delete()
    return redirect('catalogo')

def visualizar_obra(request, obra_id):
    obra = Obra.objects.get(id=obra_id)
    return render(request, 'sistema/visualizar_obra.html', {'obra': obra})
