from datetime import date, timedelta
import re

from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from . import servicios
from .models import (
    Categoria,
    CodigoRecuperacion,
    CuotaMeta,
    MetaAhorro,
    Movimiento,
    Presupuesto,
    crear_categorias_iniciales,
)
from .templatetags.clp import clp


def cat(usuario, nombre, tipo="gasto"):
    return Categoria.objects.get(usuario=usuario, nombre=nombre, tipo=tipo)


class Base(TestCase):
    def setUp(self):
        self.ana = User.objects.create_user("ana", password="clave-segura-123")
        self.beto = User.objects.create_user("beto", password="clave-segura-123")
        crear_categorias_iniciales(self.ana)
        crear_categorias_iniciales(self.beto)
        self.hoy = date.today()

    def mov(self, usuario, tipo, monto, categoria, fecha=None):
        return Movimiento.objects.create(usuario=usuario, tipo=tipo, monto=monto,
                                         categoria=cat(usuario, categoria, tipo), fecha=fecha or self.hoy)


class CalculosTest(Base):
    def test_resumen_mes(self):
        ingreso_efectivo = self.mov(self.ana, "ingreso", 200000, "Mesada")
        ingreso_efectivo.cuenta = "efectivo"
        ingreso_efectivo.save()
        ingreso_banco = self.mov(self.ana, "ingreso", 100000, "Trabajo")
        ingreso_banco.cuenta = "banco"
        ingreso_banco.save()
        self.mov(self.ana, "gasto", 50000, "Comida")
        self.mov(self.ana, "gasto", 25000, "Comida")
        self.mov(self.ana, "gasto", 30000, "Transporte")
        r = servicios.resumen_mes(self.ana, self.hoy.year, self.hoy.month)
        self.assertEqual(r["ingresos"], 300000)
        self.assertEqual(r["ingresos_efectivo"], 200000)
        self.assertEqual(r["ingresos_banco"], 100000)
        self.assertEqual(r["gastos"], 105000)
        self.assertEqual(r["balance"], 195000)
        self.assertEqual(r["tasa_ahorro"], 65)
        self.assertEqual(r["por_categoria"][0], {"categoria_id": cat(self.ana, "Comida").id, "categoria": "Comida", "total": 75000})

    def test_saldos_por_cuenta_suman_ingresos_y_restan_gastos(self):
        efectivo = self.mov(self.ana, "ingreso", 50000, "Mesada")
        efectivo.cuenta = "efectivo"
        efectivo.save()
        gasto_efectivo = self.mov(self.ana, "gasto", 12000, "Comida")
        gasto_efectivo.cuenta = "efectivo"
        gasto_efectivo.save()
        banco = self.mov(self.ana, "ingreso", 100000, "Trabajo")
        banco.cuenta = "banco"
        banco.save()
        r = servicios.saldos_por_cuenta(self.ana)
        self.assertEqual(r, {"efectivo": 38000, "banco": 100000, "total": 138000})

    def test_no_mezcla_meses_ni_usuarios(self):
        self.mov(self.ana, "gasto", 10000, "Comida", date(2025, 1, 31))
        self.mov(self.ana, "gasto", 20000, "Comida", date(2025, 2, 1))
        self.mov(self.beto, "gasto", 99999, "Comida", date(2025, 2, 10))
        self.assertEqual(servicios.resumen_mes(self.ana, 2025, 2)["gastos"], 20000)

    def test_sin_ingresos_no_divide_por_cero(self):
        self.mov(self.ana, "gasto", 1000, "Ocio")
        self.assertIsNone(servicios.resumen_mes(self.ana, self.hoy.year, self.hoy.month)["tasa_ahorro"])

    def test_alertas_presupuesto(self):
        Presupuesto.objects.create(usuario=self.ana, categoria=cat(self.ana, "Comida"), monto_mensual=100000)
        Presupuesto.objects.create(usuario=self.ana, categoria=cat(self.ana, "Ocio"), monto_mensual=20000)
        Presupuesto.objects.create(usuario=self.ana, categoria=cat(self.ana, "Transporte"), monto_mensual=50000)
        self.mov(self.ana, "gasto", 85000, "Comida")   # 85% -> cerca
        self.mov(self.ana, "gasto", 25000, "Ocio")     # 125% -> excedido
        self.mov(self.ana, "gasto", 10000, "Transporte")  # 20% -> ok
        r = servicios.resumen_mes(self.ana, self.hoy.year, self.hoy.month)
        estados = {a["categoria"]: a["estado"] for a in r["alertas"]}
        self.assertEqual(estados, {"Ocio": "excedido", "Comida": "cerca"})


class AislamientoTest(Base):
    """Un usuario jamás debe ver ni modificar datos de otro."""

    def setUp(self):
        super().setUp()
        self.mov_ana = self.mov(self.ana, "gasto", 12345, "Comida")
        self.client.login(username="beto", password="clave-segura-123")

    def test_no_ve_movimientos_ajenos(self):
        r = self.client.get(reverse("movimientos"))
        self.assertNotContains(r, "12.345")
        r = self.client.get(reverse("dashboard"))
        self.assertNotContains(r, "12.345")

    def test_no_edita_ni_borra_ajenos(self):
        self.assertEqual(self.client.get(reverse("movimiento_editar", args=[self.mov_ana.pk])).status_code, 404)
        self.client.post(reverse("movimiento_editar", args=[self.mov_ana.pk]),
                         {"tipo": "gasto", "monto": 1, "fecha": self.hoy, "categoria": cat(self.beto, "Comida").pk})
        self.assertEqual(self.client.post(reverse("movimiento_borrar", args=[self.mov_ana.pk])).status_code, 404)
        self.mov_ana.refresh_from_db()
        self.assertEqual(self.mov_ana.monto, 12345)

    def test_no_usa_categoria_ajena(self):
        r = self.client.post(reverse("movimiento_nuevo"),
                             {"tipo": "gasto", "monto": 500, "fecha": self.hoy, "categoria": cat(self.ana, "Comida").pk})
        self.assertEqual(r.status_code, 200)  # formulario rechazado
        self.assertFalse(Movimiento.objects.filter(usuario=self.beto).exists())

    def test_no_borra_categoria_ni_presupuesto_ajeno(self):
        p = Presupuesto.objects.create(usuario=self.ana, categoria=cat(self.ana, "Ocio"), monto_mensual=1000)
        self.assertEqual(self.client.post(reverse("categoria_borrar", args=[cat(self.ana, "Salud").pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("presupuesto_borrar", args=[p.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("presupuesto_editar", args=[p.pk])).status_code, 404)

    def test_requiere_login(self):
        self.client.logout()
        for nombre in ["dashboard", "movimientos", "categorias", "presupuestos", "movimiento_nuevo"]:
            r = self.client.get(reverse(nombre))
            self.assertEqual(r.status_code, 302, nombre)
            self.assertIn(reverse("login"), r.url)


class FlujoTest(Base):
    def test_registro_crea_categorias_y_entra(self):
        r = self.client.post(reverse("registro"), {"username": "seb", "email": "seb@example.com",
                                                    "password1": "UnaClave-Larga-99", "password2": "UnaClave-Larga-99"})
        self.assertRedirects(r, reverse("dashboard"))
        seb = User.objects.get(username="seb")
        self.assertTrue(Categoria.objects.filter(usuario=seb, nombre="Comida").exists())
        self.assertNotEqual(seb.password, "UnaClave-Larga-99")  # guardada hasheada

    def test_crear_movimiento_y_ver_paginas(self):
        self.client.login(username="ana", password="clave-segura-123")
        r = self.client.post(reverse("movimiento_nuevo"),
                             {"tipo": "gasto", "cuenta": "banco", "monto": 4500, "fecha": self.hoy, "categoria": cat(self.ana, "Comida").pk, "descripcion": "Almuerzo"})
        self.assertRedirects(r, reverse("movimientos"))
        self.assertEqual(Movimiento.objects.get(usuario=self.ana).cuenta, "banco")
        for nombre in ["dashboard", "movimientos", "categorias", "presupuestos"]:
            r = self.client.get(reverse(nombre))
            self.assertEqual(r.status_code, 200, nombre)
        self.assertContains(self.client.get(reverse("dashboard")), "$4.500")

    def test_categoria_de_tipo_incorrecto(self):
        self.client.login(username="ana", password="clave-segura-123")
        r = self.client.post(reverse("movimiento_nuevo"),
                             {"tipo": "ingreso", "monto": 1000, "fecha": self.hoy, "categoria": cat(self.ana, "Comida").pk})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Movimiento.objects.exists())

    def test_nombre_categoria_no_rompe_script(self):
        self.client.login(username="ana", password="clave-segura-123")
        c = Categoria.objects.create(usuario=self.ana, nombre="</script><script>alert(1)</script>", tipo="gasto")
        Movimiento.objects.create(usuario=self.ana, tipo="gasto", monto=100, categoria=c, fecha=self.hoy)
        r = self.client.get(reverse("dashboard"))
        self.assertNotContains(r, "<script>alert(1)</script>")

    def test_mes_invalido_en_url(self):
        self.client.login(username="ana", password="clave-segura-123")
        self.assertEqual(self.client.get(reverse("dashboard") + "?anio=x&mes=13").status_code, 200)

    def test_formato_clp(self):
        self.assertEqual(clp(1234567), "$1.234.567")
        self.assertEqual(clp(-500), "-$500")


class MetasServiciosTest(Base):
    def test_formula_sin_interes_y_redondeo_exacto(self):
        plan = servicios.calcular_plan(100000, 3, 0)
        self.assertEqual(plan["valor_cuota"], 33333)
        self.assertEqual(plan["importes"], [33333, 33333, 33334])
        self.assertEqual(sum(plan["importes"]), 100000)
        self.assertEqual(plan["total_pagar"], 100000)
        self.assertEqual(plan["intereses"], 0)

    def test_formula_francesa_con_interes(self):
        plan = servicios.calcular_plan(100000, 6, 1)
        self.assertEqual(plan["valor_cuota"], 17255)
        self.assertEqual(plan["total_pagar"], 103529)
        self.assertEqual(plan["intereses"], 3529)
        self.assertEqual(sum(plan["importes"]), plan["total_pagar"])

    def test_simular_no_crea_movimientos_y_sin_ingresos_no_divide_por_cero(self):
        resultado = servicios.simular_meta(self.ana, 50000, 0, self.hoy)
        self.assertEqual(resultado["ingreso_promedio"], 0)
        self.assertIsNone(resultado["opciones"][0]["porcentaje_ingreso"])
        self.assertIsNone(resultado["meses_ahorro"])
        self.assertFalse(Movimiento.objects.filter(usuario=self.ana).exists())

    def test_promedio_ingresos_usa_tres_meses_incluyendo_meses_sin_ingresos(self):
        inicio = servicios.fecha_cuota(date(self.hoy.year, self.hoy.month, 1), -2)
        trabajo = cat(self.ana, "Trabajo", "ingreso")
        Movimiento.objects.create(
            usuario=self.ana, tipo="ingreso", monto=90000, categoria=trabajo,
            fecha=inicio,
        )
        self.assertEqual(
            servicios.promedio_financiero(self.ana, self.hoy)["ingresos"],
            30000,
        )


class MetasFlujoTest(Base):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.ana)
        self.meta = MetaAhorro.objects.create(
            usuario=self.ana, nombre="Mouse gamer", precio=100000
        )

    def datos_compra(self, **extra):
        datos = {
            "cuotas": "6",
            "tasa_mensual": "1",
            "fecha_primera_cuota": self.hoy.isoformat(),
        }
        datos.update(extra)
        return datos

    def test_rechaza_precio_cero_cuotas_no_permitidas_y_tasa_fuera_de_rango(self):
        respuesta = self.client.post(
            reverse("metas"), {"nombre": "Mouse", "precio": "0"}
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(MetaAhorro.objects.filter(usuario=self.ana, nombre="Mouse").exists())

        respuesta = self.client.post(
            reverse("meta_detalle", args=[self.meta.pk]),
            {"cuotas": "2", "tasa_mensual": "0"},
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertIsNone(respuesta.context["simulacion"])

        respuesta = self.client.post(
            reverse("meta_comprar", args=[self.meta.pk]),
            self.datos_compra(tasa_mensual="10.01"),
        )
        self.assertEqual(respuesta.status_code, 302)
        self.assertFalse(Movimiento.objects.filter(usuario=self.ana).exists())
        self.meta.refresh_from_db()
        self.assertEqual(self.meta.estado, "simulacion")

    def test_simular_desde_pantalla_no_crea_movimientos(self):
        respuesta = self.client.post(
            reverse("meta_detalle", args=[self.meta.pk]),
            {"cuotas": "6", "tasa_mensual": "1"},
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Simulación referencial.")
        self.assertFalse(Movimiento.objects.filter(usuario=self.ana).exists())
        self.meta.refresh_from_db()
        self.assertEqual(self.meta.estado, "simulacion")

    def test_compra_en_seis_meses_y_envio_duplicado_no_duplica(self):
        url = reverse("meta_comprar", args=[self.meta.pk])
        datos = self.datos_compra()
        respuesta = self.client.post(url, datos)
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Confirmar compra")
        datos["confirmar"] = "1"
        self.assertEqual(self.client.post(url, datos).status_code, 302)
        self.assertEqual(self.client.post(url, datos).status_code, 302)
        cuotas = CuotaMeta.objects.filter(meta=self.meta).order_by("numero")
        self.assertEqual(cuotas.count(), 6)
        self.assertEqual(
            len({(cuota.fecha.year, cuota.fecha.month) for cuota in cuotas}), 6
        )
        self.assertEqual(
            Movimiento.objects.filter(
                usuario=self.ana, categoria__nombre="Cuotas"
            ).count(),
            6,
        )
        self.meta.refresh_from_db()
        self.assertEqual(self.meta.estado, "comprada")
        self.assertEqual(sum(cuota.monto for cuota in cuotas), self.meta.total_pagar)

    def test_anular_compra_conserva_solo_cuotas_pagadas(self):
        inicio = servicios.fecha_cuota(date(self.hoy.year, self.hoy.month, 1), -2)
        datos = self.datos_compra(fecha_primera_cuota=inicio.isoformat(), confirmar="1")
        self.client.post(reverse("meta_comprar", args=[self.meta.pk]), datos)
        cuotas_pagadas = CuotaMeta.objects.filter(meta=self.meta, fecha__lte=self.hoy).count()
        self.assertGreater(cuotas_pagadas, 0)

        respuesta = self.client.post(reverse("meta_cancelar", args=[self.meta.pk]))

        self.assertEqual(respuesta.status_code, 302)
        self.meta.refresh_from_db()
        self.assertEqual(self.meta.estado, "anulada")
        self.assertEqual(CuotaMeta.objects.filter(meta=self.meta).count(), cuotas_pagadas)
        self.assertFalse(CuotaMeta.objects.filter(meta=self.meta, fecha__gt=self.hoy).exists())
        self.assertEqual(
            Movimiento.objects.filter(usuario=self.ana, categoria__nombre="Cuotas").count(),
            cuotas_pagadas,
        )

    def test_no_accede_a_meta_ajena_para_ver_simular_comprar_o_borrar(self):
        self.client.logout()
        self.client.force_login(self.beto)
        detalle = reverse("meta_detalle", args=[self.meta.pk])
        compra = reverse("meta_comprar", args=[self.meta.pk])
        cancelar = reverse("meta_cancelar", args=[self.meta.pk])
        self.assertEqual(self.client.get(detalle).status_code, 404)
        self.assertEqual(
            self.client.post(detalle, {"cuotas": "6", "tasa_mensual": "0"}).status_code,
            404,
        )
        self.assertEqual(self.client.post(compra, self.datos_compra()).status_code, 404)
        self.assertEqual(self.client.post(cancelar).status_code, 404)
        self.meta.refresh_from_db()
        self.assertEqual(self.meta.estado, "simulacion")

    def test_cuotas_en_dashboard_y_pantalla_de_meta(self):
        self.client.post(
            reverse("meta_comprar", args=[self.meta.pk]),
            self.datos_compra(confirmar="1"),
        )
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)
        self.assertEqual(
            self.client.get(reverse("meta_detalle", args=[self.meta.pk])).status_code,
            200,
        )


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class RecuperacionContrasenaTest(Base):
    def setUp(self):
        super().setUp()
        self.ana.email = "ana@example.com"
        self.ana.save(update_fields=["email"])
        self.solicitud_url = reverse("password_reset_request")
        self.codigo_url = reverse("password_reset_code")

    def test_envia_codigo_solo_al_correo_registrado_sin_revelar_cuentas(self):
        respuesta = self.client.post(self.solicitud_url, {"email": self.ana.email})
        self.assertContains(respuesta, "Si existe una cuenta asociada")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.ana.email])
        self.assertTrue(CodigoRecuperacion.objects.filter(usuario=self.ana).exists())

        respuesta = self.client.post(self.solicitud_url, {"email": "inexistente@example.com"})
        self.assertContains(respuesta, "Si existe una cuenta asociada")
        self.assertEqual(len(mail.outbox), 1)

    def test_codigo_valido_cambia_contrasena_y_se_invalida(self):
        self.client.post(self.solicitud_url, {"email": self.ana.email})
        codigo = re.search(r"\b(\d{6})\b", mail.outbox[-1].body).group(1)
        respuesta = self.client.post(self.codigo_url, {
            "email": self.ana.email,
            "codigo": codigo,
            "new_password1": "OtraClave-Larga-2099!",
            "new_password2": "OtraClave-Larga-2099!",
        })

        self.assertRedirects(respuesta, reverse("login"))
        self.ana.refresh_from_db()
        self.assertTrue(self.ana.check_password("OtraClave-Larga-2099!"))
        self.assertFalse(CodigoRecuperacion.objects.filter(usuario=self.ana).exists())

    def test_codigo_incorrecto_vence_y_limita_intentos(self):
        self.client.post(self.solicitud_url, {"email": self.ana.email})
        CodigoRecuperacion.objects.filter(usuario=self.ana).update(
            creado=timezone.now() - timedelta(minutes=11)
        )
        respuesta = self.client.post(self.codigo_url, {
            "email": self.ana.email, "codigo": "123456",
            "new_password1": "OtraClave-Larga-2099!",
            "new_password2": "OtraClave-Larga-2099!",
        })
        self.assertContains(respuesta, "no es válido o ya venció")

        CodigoRecuperacion.objects.filter(usuario=self.ana).update(
            creado=timezone.now(), intentos=0
        )
        for _ in range(5):
            self.client.post(self.codigo_url, {
                "email": self.ana.email, "codigo": "000000",
                "new_password1": "OtraClave-Larga-2099!",
                "new_password2": "OtraClave-Larga-2099!",
            })
        self.assertFalse(CodigoRecuperacion.objects.filter(usuario=self.ana).exists())
        self.assertEqual(len(mail.outbox), 1)
