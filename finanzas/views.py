from datetime import date, timedelta
import secrets

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.forms import SetPasswordForm
from django.contrib.auth.decorators import login_required
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import servicios
from .forms import (
    CategoriaForm,
    ConfirmarCompraMetaForm,
    MetaAhorroForm,
    MovimientoForm,
    PresupuestoForm,
    RegistroForm,
    CodigoRecuperacionForm,
    SolicitarRecuperacionForm,
    SimulacionMetaForm,
)
from .models import (
    Categoria,
    CodigoRecuperacion,
    CuotaMeta,
    MetaAhorro,
    Movimiento,
    Presupuesto,
    crear_categorias_iniciales,
)

MESES = ["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio",
         "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]


def _mes_desde_request(request):
    hoy = date.today()
    try:
        anio = int(request.GET.get("anio", hoy.year))
        mes = int(request.GET.get("mes", hoy.month))
        date(anio, mes, 1)
    except (TypeError, ValueError):
        anio, mes = hoy.year, hoy.month
    return anio, mes


def _mes_vecino(anio, mes, delta):
    total = anio * 12 + (mes - 1) + delta
    return total // 12, total % 12 + 1


def registro(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    form = RegistroForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        usuario = form.save()
        crear_categorias_iniciales(usuario)
        login(request, usuario)
        messages.success(request, "¡Cuenta creada! Ya puedes registrar tus movimientos.")
        return redirect("dashboard")
    return render(request, "registration/registro.html", {"form": form})


def solicitar_recuperacion(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    form = SolicitarRecuperacionForm(request.POST or None)
    enviado = False
    if request.method == "POST" and form.is_valid():
        usuarios = User.objects.filter(email__iexact=form.cleaned_data["email"])
        if usuarios.count() == 1:
            usuario = usuarios.get()
            codigo = f"{secrets.randbelow(1_000_000):06d}"
            send_mail(
                "Código para recuperar tu contraseña",
                f"Tu código de recuperación es {codigo}. Vence en 10 minutos.",
                settings.DEFAULT_FROM_EMAIL,
                [usuario.email],
                fail_silently=False,
            )
            CodigoRecuperacion.objects.update_or_create(
                usuario=usuario,
                defaults={"codigo_hash": make_password(codigo), "intentos": 0},
            )
        enviado = True
    return render(
        request,
        "registration/password_reset_request.html",
        {"form": form, "enviado": enviado},
    )


def confirmar_recuperacion(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    form = CodigoRecuperacionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        usuarios = User.objects.filter(email__iexact=form.cleaned_data["email"])
        usuario = usuarios.first() if usuarios.count() == 1 else None
        registro_codigo = (
            CodigoRecuperacion.objects.filter(usuario=usuario).first()
            if usuario
            else None
        )
        ahora = timezone.now()
        codigo_valido = bool(
            registro_codigo
            and ahora - registro_codigo.creado < timedelta(minutes=10)
            and registro_codigo.intentos < 5
            and check_password(form.cleaned_data["codigo"], registro_codigo.codigo_hash)
        )
        if not codigo_valido:
            if registro_codigo:
                registro_codigo.intentos += 1
                if registro_codigo.intentos >= 5:
                    registro_codigo.delete()
                else:
                    registro_codigo.save(update_fields=["intentos"])
            form.add_error("codigo", "El correo o el código no es válido o ya venció.")
        else:
            formulario_contrasena = SetPasswordForm(usuario, request.POST)
            if formulario_contrasena.is_valid():
                usuario.set_password(formulario_contrasena.cleaned_data["new_password1"])
                usuario.save(update_fields=["password"])
                registro_codigo.delete()
                messages.success(request, "Contraseña actualizada. Ya puedes ingresar.")
                return redirect("login")
            for campo, errores in formulario_contrasena.errors.items():
                for error in errores:
                    form.add_error(None if campo == "__all__" else campo, error)
    return render(
        request,
        "registration/password_reset_code.html",
        {"form": form},
    )


@login_required
def dashboard(request):
    anio, mes = _mes_desde_request(request)
    resumen = servicios.resumen_mes(request.user, anio, mes)
    grafico = {
        "labels": [c["categoria"] for c in resumen["por_categoria"]],
        "valores": [c["total"] for c in resumen["por_categoria"]],
    }
    ant, sig = _mes_vecino(anio, mes, -1), _mes_vecino(anio, mes, 1)
    return render(request, "finanzas/dashboard.html", {
        "r": resumen,
        "saldos": servicios.saldos_por_cuenta(request.user),
        "resumen_cuotas": servicios.resumen_cuotas(request.user),
        "nombre_mes": f"{MESES[mes]} {anio}",
        "grafico": grafico,
        "anterior": {"anio": ant[0], "mes": ant[1]},
        "siguiente": {"anio": sig[0], "mes": sig[1]},
        "ultimos": servicios.movimientos_del_mes(request.user, anio, mes).select_related("categoria")[:5],
    })


@login_required
def movimientos(request):
    anio, mes = _mes_desde_request(request)
    qs = servicios.movimientos_del_mes(request.user, anio, mes).select_related("categoria")
    ant, sig = _mes_vecino(anio, mes, -1), _mes_vecino(anio, mes, 1)
    return render(request, "finanzas/movimientos.html", {
        "movimientos": qs,
        "nombre_mes": f"{MESES[mes]} {anio}",
        "anterior": {"anio": ant[0], "mes": ant[1]},
        "siguiente": {"anio": sig[0], "mes": sig[1]},
    })


@login_required
def movimiento_form(request, pk=None):
    # get_object_or_404 con usuario=request.user: si el id es de otra persona responde 404
    instancia = get_object_or_404(Movimiento, pk=pk, usuario=request.user) if pk else None
    inicial = {"fecha": date.today(), "tipo": request.GET.get("tipo", "gasto")}
    form = MovimientoForm(request.POST or None, instance=instancia, initial=inicial, usuario=request.user)
    if request.method == "POST" and form.is_valid():
        mov = form.save(commit=False)
        mov.usuario = request.user
        mov.save()
        messages.success(request, "Movimiento guardado.")
        return redirect("movimientos")
    return render(request, "finanzas/form.html", {
        "form": form, "titulo": "Editar movimiento" if instancia else "Nuevo movimiento",
        "volver": "movimientos",
    })


@login_required
@require_POST
def movimiento_borrar(request, pk):
    get_object_or_404(Movimiento, pk=pk, usuario=request.user).delete()
    messages.success(request, "Movimiento eliminado.")
    return redirect("movimientos")


@login_required
def categorias(request):
    form = CategoriaForm(request.POST or None, usuario=request.user)
    if request.method == "POST" and form.is_valid():
        cat = form.save(commit=False)
        cat.usuario = request.user
        cat.save()
        messages.success(request, f"Categoría «{cat}» creada.")
        return redirect("categorias")
    return render(request, "finanzas/categorias.html", {
        "form": form, "categorias": Categoria.objects.filter(usuario=request.user),
    })


@login_required
@require_POST
def categoria_borrar(request, pk):
    cat = get_object_or_404(Categoria, pk=pk, usuario=request.user)
    try:
        cat.delete()
        messages.success(request, f"Categoría «{cat}» eliminada.")
    except ProtectedError:
        messages.error(request, f"«{cat}» tiene movimientos asociados; no se puede borrar.")
    return redirect("categorias")


@login_required
def presupuestos(request):
    hoy = date.today()
    form = PresupuestoForm(request.POST or None, usuario=request.user)
    if request.method == "POST" and form.is_valid():
        p = form.save(commit=False)
        p.usuario = request.user
        p.save()
        messages.success(request, "Presupuesto guardado.")
        return redirect("presupuestos")
    return render(request, "finanzas/presupuestos.html", {
        "form": form,
        "presupuestos": Presupuesto.objects.filter(usuario=request.user).select_related("categoria"),
        "estado": servicios.estado_presupuestos(request.user, hoy.year, hoy.month),
    })


@login_required
def presupuesto_editar(request, pk):
    instancia = get_object_or_404(Presupuesto, pk=pk, usuario=request.user)
    form = PresupuestoForm(request.POST or None, instance=instancia, usuario=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Presupuesto actualizado.")
        return redirect("presupuestos")
    return render(request, "finanzas/form.html", {"form": form, "titulo": "Editar presupuesto", "volver": "presupuestos"})


@login_required
@require_POST
def presupuesto_borrar(request, pk):
    get_object_or_404(Presupuesto, pk=pk, usuario=request.user).delete()
    messages.success(request, "Presupuesto eliminado.")
    return redirect("presupuestos")


@login_required
def metas(request):
    formulario = MetaAhorroForm()
    if request.method == "POST":
        formulario = MetaAhorroForm(request.POST)
        if formulario.is_valid():
            meta = formulario.save(commit=False)
            meta.usuario = request.user
            meta.save()
            messages.success(request, "Meta creada. Puedes simular sus cuotas cuando quieras.")
            return redirect("meta_detalle", pk=meta.pk)
    return render(request, "finanzas/metas.html", {
        "form": formulario,
        "metas": MetaAhorro.objects.filter(usuario=request.user),
    })


@login_required
def meta_detalle(request, pk):
    meta = get_object_or_404(MetaAhorro, pk=pk, usuario=request.user)
    simulacion = None
    formulario = SimulacionMetaForm(initial={"cuotas": 6, "tasa_mensual": 0})
    seleccionada = None
    if request.method == "POST":
        formulario = SimulacionMetaForm(request.POST)
        if meta.estado != "simulacion":
            messages.error(request, "Solo puedes simular una meta que aún no has comprado.")
            return redirect("meta_detalle", pk=meta.pk)
        if formulario.is_valid():
            simulacion = servicios.simular_meta(
                request.user, meta.precio, formulario.cleaned_data["tasa_mensual"]
            )
            seleccionada = formulario.cleaned_data["cuotas"]
    progreso = servicios.progreso_meta(meta) if meta.estado != "simulacion" else None
    return render(request, "finanzas/meta_detalle.html", {
        "meta": meta,
        "form": formulario,
        "simulacion": simulacion,
        "seleccionada": seleccionada,
        "progreso": progreso,
        "hoy": date.today(),
    })


@login_required
@require_POST
def meta_comprar(request, pk):
    meta = get_object_or_404(MetaAhorro, pk=pk, usuario=request.user)
    if meta.estado != "simulacion":
        messages.error(request, "Esta meta ya no está disponible para compra.")
        return redirect("meta_detalle", pk=meta.pk)
    formulario = ConfirmarCompraMetaForm(request.POST)
    if not formulario.is_valid():
        messages.error(request, "Revisa los datos de la simulación e inténtalo nuevamente.")
        return redirect("meta_detalle", pk=meta.pk)

    datos = formulario.cleaned_data
    plan = servicios.calcular_plan(meta.precio, datos["cuotas"], datos["tasa_mensual"])
    if request.POST.get("confirmar") != "1":
        return render(request, "finanzas/meta_confirmar.html", {
            "meta": meta,
            "form": formulario,
            "plan": plan,
        })

    with transaction.atomic():
        meta = get_object_or_404(
            MetaAhorro.objects.select_for_update(), pk=pk, usuario=request.user
        )
        if meta.estado != "simulacion":
            messages.error(request, "Esta compra ya fue registrada.")
            return redirect("meta_detalle", pk=meta.pk)
        categoria, _ = Categoria.objects.get_or_create(
            usuario=request.user, nombre="Cuotas", tipo="gasto"
        )
        fecha_inicial = datos["fecha_primera_cuota"]
        meta.estado = "comprada"
        meta.cuotas = datos["cuotas"]
        meta.tasa_mensual = datos["tasa_mensual"]
        meta.valor_cuota = plan["valor_cuota"]
        meta.total_pagar = plan["total_pagar"]
        meta.fecha_compra = date.today()
        meta.fecha_primera_cuota = fecha_inicial
        meta.save()
        for indice, (fecha, monto) in enumerate(
            ((servicios.fecha_cuota(fecha_inicial, i), monto)
             for i, monto in enumerate(plan["importes"])),
            start=1,
        ):
            movimiento = Movimiento.objects.create(
                usuario=request.user,
                tipo="gasto",
                cuenta="banco",
                monto=monto,
                fecha=fecha,
                categoria=categoria,
                descripcion=f"{meta.nombre} — cuota {indice}/{datos['cuotas']}",
            )
            CuotaMeta.objects.create(
                meta=meta, movimiento=movimiento, numero=indice, fecha=fecha, monto=monto
            )
    messages.success(request, "Compra registrada y cuotas agregadas a tus movimientos.")
    return redirect("meta_detalle", pk=meta.pk)


@login_required
@require_POST
def meta_cancelar(request, pk):
    meta = get_object_or_404(MetaAhorro, pk=pk, usuario=request.user)
    if meta.estado == "simulacion":
        meta.delete()
        messages.success(request, "Meta eliminada.")
        return redirect("metas")
    if meta.estado == "comprada":
        with transaction.atomic():
            meta = get_object_or_404(
                MetaAhorro.objects.select_for_update(), pk=pk, usuario=request.user
            )
            if meta.estado == "comprada":
                futuras = meta.cuotas_programadas.filter(fecha__gt=date.today())
                Movimiento.objects.filter(cuota_meta__in=futuras).delete()
                futuras.delete()
                meta.estado = "anulada"
                meta.save(update_fields=["estado"])
        messages.success(request, "Compra anulada; las cuotas futuras fueron eliminadas.")
        return redirect("meta_detalle", pk=meta.pk)
    messages.error(request, "Esta meta ya está anulada.")
    return redirect("meta_detalle", pk=meta.pk)
