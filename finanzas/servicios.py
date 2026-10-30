"""Cálculos financieros. Todas las funciones reciben el usuario y filtran por él.

Estas funciones son las que después usará el chatbot como herramientas (tool use),
así que nunca deben aceptar datos de otro usuario.
"""
import calendar
from datetime import date
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP

from django.db.models import Q, Sum

from .models import CuotaMeta, MetaAhorro, Movimiento, Presupuesto

CUOTAS_PERMITIDAS = (1, 3, 6, 12, 24)
AVISO_SIMULACION = (
    "Simulación referencial. El valor real depende de la tienda o banco; "
    "revisa siempre la CAE antes de comprar."
)


def _rango_mes(anio, mes):
    ultimo = calendar.monthrange(anio, mes)[1]
    return date(anio, mes, 1), date(anio, mes, ultimo)


def movimientos_del_mes(usuario, anio, mes):
    inicio, fin = _rango_mes(anio, mes)
    return Movimiento.objects.filter(usuario=usuario, fecha__range=(inicio, fin))


def gastos_por_categoria(usuario, anio, mes):
    filas = (
        movimientos_del_mes(usuario, anio, mes)
        .filter(tipo="gasto")
        .values("categoria__id", "categoria__nombre")
        .annotate(total=Sum("monto"))
        .order_by("-total")
    )
    return [{"categoria_id": f["categoria__id"], "categoria": f["categoria__nombre"], "total": f["total"]} for f in filas]


def estado_presupuestos(usuario, anio, mes):
    gastado = {g["categoria_id"]: g["total"] for g in gastos_por_categoria(usuario, anio, mes)}
    resultado = []
    for p in Presupuesto.objects.filter(usuario=usuario).select_related("categoria"):
        usado = gastado.get(p.categoria_id, 0)
        porcentaje = round(usado * 100 / p.monto_mensual) if p.monto_mensual else 0
        if porcentaje >= 100:
            estado = "excedido"
        elif porcentaje >= 80:
            estado = "cerca"
        else:
            estado = "ok"
        resultado.append({
            "categoria": p.categoria.nombre,
            "limite": p.monto_mensual,
            "gastado": usado,
            "disponible": p.monto_mensual - usado,
            "porcentaje": porcentaje,
            "estado": estado,
        })
    return sorted(resultado, key=lambda r: -r["porcentaje"])


def resumen_mes(usuario, anio, mes):
    qs = movimientos_del_mes(usuario, anio, mes)
    ingresos = qs.filter(tipo="ingreso").aggregate(t=Sum("monto"))["t"] or 0
    ingresos_efectivo = qs.filter(tipo="ingreso", cuenta="efectivo").aggregate(t=Sum("monto"))["t"] or 0
    ingresos_banco = qs.filter(tipo="ingreso", cuenta="banco").aggregate(t=Sum("monto"))["t"] or 0
    gastos = qs.filter(tipo="gasto").aggregate(t=Sum("monto"))["t"] or 0
    balance = ingresos - gastos
    tasa_ahorro = round(balance * 100 / ingresos) if ingresos else None
    presupuestos = estado_presupuestos(usuario, anio, mes)
    return {
        "anio": anio,
        "mes": mes,
        "ingresos": ingresos,
        "ingresos_efectivo": ingresos_efectivo,
        "ingresos_banco": ingresos_banco,
        "gastos": gastos,
        "balance": balance,
        "tasa_ahorro": tasa_ahorro,
        "por_categoria": gastos_por_categoria(usuario, anio, mes),
        "presupuestos": presupuestos,
        "alertas": [p for p in presupuestos if p["estado"] != "ok"],
    }


def saldos_por_cuenta(usuario):
    saldos = Movimiento.objects.filter(usuario=usuario).aggregate(
        efectivo_ingresos=Sum("monto", filter=Q(cuenta="efectivo", tipo="ingreso")),
        efectivo_gastos=Sum("monto", filter=Q(cuenta="efectivo", tipo="gasto")),
        banco_ingresos=Sum("monto", filter=Q(cuenta="banco", tipo="ingreso")),
        banco_gastos=Sum("monto", filter=Q(cuenta="banco", tipo="gasto")),
    )
    efectivo = (saldos["efectivo_ingresos"] or 0) - (saldos["efectivo_gastos"] or 0)
    banco = (saldos["banco_ingresos"] or 0) - (saldos["banco_gastos"] or 0)
    return {"efectivo": efectivo, "banco": banco, "total": efectivo + banco}


def calcular_plan(precio, cuotas, tasa_mensual):
    if precio <= 0 or cuotas not in CUOTAS_PERMITIDAS:
        raise ValueError("Precio o número de cuotas inválido.")
    tasa = Decimal(str(tasa_mensual))
    if tasa < 0 or tasa > 10:
        raise ValueError("La tasa mensual debe estar entre 0 y 10.")
    principal = Decimal(precio)
    periodos = Decimal(cuotas)
    tasa_decimal = tasa / Decimal(100)
    if tasa_decimal:
        pago_teorico = principal * tasa_decimal / (
            Decimal(1) - (Decimal(1) + tasa_decimal) ** (-cuotas)
        )
    else:
        pago_teorico = principal / periodos
    total = int((pago_teorico * periodos).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    pago_regular = int(pago_teorico.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    importes = [pago_regular] * (cuotas - 1)
    importes.append(total - sum(importes))
    return {
        "cuotas": cuotas,
        "valor_cuota": pago_regular,
        "importes": importes,
        "total_pagar": total,
        "intereses": total - precio,
        "tasa_mensual": tasa,
    }


def promedio_financiero(usuario, hoy=None):
    hoy = hoy or date.today()
    primer_mes = hoy.month - 2
    anio_inicio = hoy.year + (primer_mes - 1) // 12
    mes_inicio = (primer_mes - 1) % 12 + 1
    desde = date(anio_inicio, mes_inicio, 1)
    totales = Movimiento.objects.filter(
        usuario=usuario, fecha__range=(desde, hoy)
    ).aggregate(
        ingresos=Sum("monto", filter=Q(tipo="ingreso")),
        gastos=Sum("monto", filter=Q(tipo="gasto")),
    )
    ingresos = Decimal(totales["ingresos"] or 0) / 3
    gastos = Decimal(totales["gastos"] or 0) / 3
    return {"ingresos": ingresos, "balance": ingresos - gastos}


def simular_meta(usuario, precio, tasa_mensual, hoy=None):
    promedio = promedio_financiero(usuario, hoy)
    opciones = []
    for numero_cuotas in CUOTAS_PERMITIDAS:
        plan = calcular_plan(precio, numero_cuotas, tasa_mensual)
        cuota = plan["valor_cuota"]
        porcentaje = (
            Decimal(cuota) * 100 / promedio["ingresos"]
            if promedio["ingresos"] > 0 else None
        )
        balance_despues = promedio["balance"] - cuota
        plan.update({
            "porcentaje_ingreso": porcentaje,
            "balance_despues": balance_despues,
            "alerta_30": porcentaje is not None and porcentaje > 30,
            "alerta_balance": balance_despues < 0,
        })
        opciones.append(plan)
    balance = promedio["balance"]
    meses_ahorro = (
        int((Decimal(precio) / balance).to_integral_value(rounding=ROUND_CEILING))
        if balance > 0 else None
    )
    return {
        "opciones": opciones,
        "ingreso_promedio": promedio["ingresos"],
        "balance_promedio": balance,
        "meses_ahorro": meses_ahorro,
        "aviso": AVISO_SIMULACION,
    }


def fecha_cuota(fecha_inicial, numero):
    total = fecha_inicial.year * 12 + fecha_inicial.month - 1 + numero
    anio, mes = divmod(total, 12)
    mes += 1
    dia = min(fecha_inicial.day, calendar.monthrange(anio, mes)[1])
    return date(anio, mes, dia)


def resumen_cuotas(usuario, hoy=None):
    hoy = hoy or date.today()
    mes_inicio = date(hoy.year, hoy.month, 1)
    mes_fin = date(hoy.year, hoy.month, calendar.monthrange(hoy.year, hoy.month)[1])
    cuotas_activas = CuotaMeta.objects.filter(
        meta__usuario=usuario, meta__estado="comprada"
    )
    return {
        "este_mes": cuotas_activas.filter(fecha__range=(mes_inicio, mes_fin)).aggregate(
            total=Sum("monto")
        )["total"] or 0,
        "deuda_pendiente": cuotas_activas.filter(fecha__gt=hoy).aggregate(
            total=Sum("monto")
        )["total"] or 0,
    }


def progreso_meta(meta, hoy=None):
    hoy = hoy or date.today()
    cuotas = meta.cuotas_programadas.all()
    pagadas = cuotas.filter(fecha__lte=hoy).aggregate(total=Sum("monto"))["total"] or 0
    pendientes = cuotas.filter(fecha__gt=hoy).aggregate(total=Sum("monto"))["total"] or 0
    return {
        "cuotas": cuotas,
        "pagadas": cuotas.filter(fecha__lte=hoy).count(),
        "pendientes": cuotas.filter(fecha__gt=hoy).count(),
        "monto_pagado": pagadas,
        "deuda_restante": pendientes,
        "porcentaje": round(pagadas * 100 / meta.total_pagar) if meta.total_pagar else 0,
    }
