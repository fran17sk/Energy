from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from .forms import TramitePublicoForm, ConsultaTramiteForm
from .models import Tramite


def inicio(request):
    return render(request, 'public/inicio.html')


def nuevo(request):
    if request.method == 'POST':
        form = TramitePublicoForm(request.POST, request.FILES)
        if form.is_valid():
            tramite = form.save()
            # El evento de notificación se implementará en la siguiente iteración.
            return render(request, 'public/alta_ok.html', {'tramite': tramite})
    else:
        form = TramitePublicoForm()
    return render(request, 'public/nuevo.html', {'form': form})


def consultar(request):
    resultado = None
    if request.method == 'POST':
        form = ConsultaTramiteForm(request.POST)
        if form.is_valid():
            cd = form.cleaned_data
            resultado = Tramite.objects.filter(
                numero__iexact=cd['numero'],
                nis=cd['nis'],
                titular_dni_cuit=cd['dni_cuit'],
            ).select_related('etapa_actual', 'organismo_actual').first()
            if not resultado:
                messages.error(request, 'No se encontró un trámite con los datos ingresados.')
    else:
        form = ConsultaTramiteForm()
    return render(request, 'public/consultar.html', {'form': form, 'resultado': resultado})


@login_required
def dashboard(request):
    qs = Tramite.objects.select_related('etapa_actual', 'organismo_actual')
    if request.user.organismo_id:
        pendientes = qs.filter(organismo_actual=request.user.organismo).count()
    else:
        pendientes = qs.count()
    return render(request, 'institutional/dashboard.html', {
        'total': qs.count(),
        'pendientes': pendientes,
        'conectados': qs.filter(estado_actual='FINALIZADO').count(),
        'ultimos': qs[:5],
    })


@login_required
def lista(request):
    qs = Tramite.objects.select_related('etapa_actual', 'organismo_actual')
    q = request.GET.get('q', '').strip()
    organismo = request.GET.get('organismo', '').strip()
    estado = request.GET.get('estado', '').strip()
    if q:
        qs = qs.filter(Q(numero__icontains=q) | Q(nis__icontains=q) | Q(titular_nombre__icontains=q) | Q(titular_dni_cuit__icontains=q))
    if organismo:
        qs = qs.filter(organismo_actual_id=organismo)
    if estado:
        qs = qs.filter(estado_actual=estado)
    return render(request, 'institutional/tramites.html', {'tramites': qs, 'q': q})


@login_required
def detalle(request, pk):
    tramite = get_object_or_404(Tramite.objects.select_related('etapa_actual', 'organismo_actual'), pk=pk)
    return render(request, 'institutional/detalle.html', {'tramite': tramite})
