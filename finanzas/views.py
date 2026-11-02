from datetime import date, timedelta
import secrets

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm, SetPasswordForm
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import ProtectedError, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import servicios
from .forms import (
    CambiarEmailForm,
    CategoriaForm,
    ConfirmarCompraMetaForm,
    IngresoFijoForm,
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
    IngresoFijo,
    MetaAhorro,
    Movimiento,
    Perfil,
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
        Perfil.objects.get_or_create(usuario=usuario)
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
    tu_mes = servicios.calculo_tu_mes(request.user)
    return render(request, "finanzas/dashboard.html", {
        "r": resumen,
        "saldos": servicios.saldos_por_cuenta(request.user),
        "resumen_cuotas": servicios.resumen_cuotas(request.user),
        "nombre_mes": f"{MESES[mes]} {anio}",
        "grafico": grafico,
        "anterior": {"anio": ant[0], "mes": ant[1]},
        "siguiente": {"anio": sig[0], "mes": sig[1]},
        "ultimos": servicios.movimientos_del_mes(request.user, anio, mes).select_related("categoria")[:5],
        "tu_mes": tu_mes,
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
def meta_comprar(request, pk):
    meta = get_object_or_404(MetaAhorro, pk=pk, usuario=request.user)
    if meta.estado != "simulacion":
        messages.error(request, "Esta meta ya no está disponible para compra.")
        return redirect("meta_detalle", pk=meta.pk)
    formulario = ConfirmarCompraMetaForm(request.POST or None)
    if request.method != "POST" or not formulario.is_valid():
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
            CuotaMeta.objects.create(
                meta=meta,
                movimiento=None,
                numero=indice,
                fecha_vencimiento=fecha,
                monto=monto,
                estado="pendiente",
            )
    messages.success(request, "Compra registrada. Las cuotas están pendientes de pago.")
    return redirect("meta_detalle", pk=meta.pk)


@login_required
@require_POST
def cuota_pagar(request, pk):
    with transaction.atomic():
        cuota = get_object_or_404(
            CuotaMeta.objects.select_for_update().select_related("meta"),
            pk=pk,
            meta__usuario=request.user,
        )
        if cuota.estado == "pagada":
            messages.info(request, "Esta cuota ya fue marcada como pagada.")
            return redirect("meta_detalle", pk=cuota.meta_id)

        fecha_pago_val = request.POST.get("fecha_pago")
        if fecha_pago_val:
            try:
                fecha_pago = date.fromisoformat(fecha_pago_val)
            except ValueError:
                fecha_pago = date.today()
        else:
            fecha_pago = date.today()

        try:
            monto = int(request.POST.get("monto", cuota.monto))
            if monto <= 0:
                monto = cuota.monto
        except (TypeError, ValueError):
            monto = cuota.monto

        cuenta = request.POST.get("cuenta", "banco")
        if cuenta not in ("efectivo", "banco"):
            cuenta = "banco"

        categoria, _ = Categoria.objects.get_or_create(
            usuario=request.user, nombre="Cuotas", tipo="gasto"
        )
        movimiento = Movimiento.objects.create(
            usuario=request.user,
            tipo="gasto",
            cuenta=cuenta,
            monto=monto,
            fecha=fecha_pago,
            categoria=categoria,
            descripcion=f"{cuota.meta.nombre} — cuota {cuota.numero}/{cuota.meta.cuotas}",
        )
        cuota.estado = "pagada"
        cuota.fecha_pago = fecha_pago
        cuota.monto = monto
        cuota.movimiento = movimiento
        cuota.save()

        # Si todas las cuotas están pagadas, la meta pasa a estado "pagada"
        if not cuota.meta.cuotas_programadas.filter(estado="pendiente").exists():
            cuota.meta.estado = "pagada"
            cuota.meta.save(update_fields=["estado"])

    messages.success(request, f"Cuota {cuota.numero} marcada como pagada.")
    return redirect("meta_detalle", pk=cuota.meta_id)


@login_required
@require_POST
def cuota_deshacer(request, pk):
    with transaction.atomic():
        cuota = get_object_or_404(
            CuotaMeta.objects.select_for_update().select_related("meta"),
            pk=pk,
            meta__usuario=request.user,
        )
        if cuota.estado == "pagada":
            if cuota.movimiento:
                mov = cuota.movimiento
                cuota.movimiento = None
                cuota.estado = "pendiente"
                cuota.fecha_pago = None
                cuota.save()
                mov.delete()
            else:
                cuota.estado = "pendiente"
                cuota.fecha_pago = None
                cuota.save()

            if cuota.meta.estado == "pagada":
                cuota.meta.estado = "comprada"
                cuota.meta.save(update_fields=["estado"])
            messages.success(request, f"Pago de la cuota {cuota.numero} deshecho.")
        else:
            messages.info(request, "Esta cuota no está pagada.")
    return redirect("meta_detalle", pk=cuota.meta_id)


@login_required
def meta_eliminar(request, pk):
    meta = get_object_or_404(MetaAhorro, pk=pk, usuario=request.user)
    cuotas_pagadas = meta.cuotas_programadas.filter(estado="pagada")
    tiene_pagadas = cuotas_pagadas.exists()
    cuotas_pagadas_count = cuotas_pagadas.count()
    monto_pagado = cuotas_pagadas.aggregate(t=Sum("monto"))["t"] or 0

    if request.method == "POST":
        borrar_movimientos = request.POST.get("borrar_movimientos") == "1"
        with transaction.atomic():
            if borrar_movimientos:
                mov_ids = list(
                    cuotas_pagadas.filter(movimiento__isnull=False).values_list("movimiento_id", flat=True)
                )
                cuotas_pagadas.update(movimiento=None)
                Movimiento.objects.filter(id__in=mov_ids, usuario=request.user).delete()
            else:
                cuotas_pagadas.update(movimiento=None)
            meta.delete()
        messages.success(request, f"Meta «{meta.nombre}» eliminada.")
        return redirect("metas")

    return render(request, "finanzas/meta_eliminar.html", {
        "meta": meta,
        "tiene_pagadas": tiene_pagadas,
        "cuotas_pagadas_count": cuotas_pagadas_count,
        "monto_pagado": monto_pagado,
    })


# ==========================================
# PERFIL, TEMA E INGRESOS FIJOS
# ==========================================

@login_required
@require_POST
def cambiar_tema(request):
    tema_val = request.POST.get("tema", "auto")
    if tema_val not in ("auto", "light", "dark"):
        tema_val = "auto"
    perfil, _ = Perfil.objects.get_or_create(usuario=request.user)
    perfil.tema = tema_val
    perfil.save(update_fields=["tema"])
    next_url = request.POST.get("next") or request.META.get("HTTP_REFERER") or "dashboard"
    return redirect(next_url)


@login_required
def perfil(request):
    usuario = request.user
    perfil_obj, _ = Perfil.objects.get_or_create(usuario=usuario)
    form_email = CambiarEmailForm(user=usuario, initial={"email": usuario.email})
    form_pass = PasswordChangeForm(user=usuario)
    form_ingreso = IngresoFijoForm()

    if request.method == "POST":
        accion = request.POST.get("accion")
        if accion == "cambiar_email":
            form_email = CambiarEmailForm(request.POST, user=usuario)
            if form_email.is_valid():
                usuario.email = form_email.cleaned_data["email"]
                usuario.save(update_fields=["email"])
                messages.success(request, "Correo electrónico actualizado con éxito.")
                return redirect("perfil")
        elif accion == "cambiar_password":
            form_pass = PasswordChangeForm(user=usuario, data=request.POST)
            if form_pass.is_valid():
                user = form_pass.save()
                update_session_auth_hash(request, user)
                messages.success(request, "Contraseña actualizada con éxito.")
                return redirect("perfil")
        elif accion == "crear_ingreso":
            form_ingreso = IngresoFijoForm(request.POST)
            if form_ingreso.is_valid():
                ing = form_ingreso.save(commit=False)
                ing.usuario = usuario
                ing.save()
                messages.success(request, f"Ingreso fijo «{ing.nombre}» agregado.")
                return redirect("perfil")

    ingresos_fijos = usuario.ingresos_fijos.all()
    total_esperado = ingresos_fijos.aggregate(t=Sum("monto"))["t"] or 0
    tu_mes = servicios.calculo_tu_mes(usuario)

    return render(request, "finanzas/perfil.html", {
        "usuario": usuario,
        "perfil": perfil_obj,
        "form_email": form_email,
        "form_pass": form_pass,
        "form_ingreso": form_ingreso,
        "ingresos_fijos": ingresos_fijos,
        "total_esperado": total_esperado,
        "tu_mes": tu_mes,
    })


@login_required
def ingreso_fijo_editar(request, pk):
    instancia = get_object_or_404(IngresoFijo, pk=pk, usuario=request.user)
    form = IngresoFijoForm(request.POST or None, instance=instancia)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Ingreso fijo actualizado.")
        return redirect("perfil")
    return render(request, "finanzas/form.html", {
        "form": form,
        "titulo": "Editar ingreso fijo",
        "volver": "perfil",
    })


@login_required
@require_POST
def ingreso_fijo_borrar(request, pk):
    get_object_or_404(IngresoFijo, pk=pk, usuario=request.user).delete()
    messages.success(request, "Ingreso fijo eliminado.")
    return redirect("perfil")
