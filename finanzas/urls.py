from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("registro/", views.registro, name="registro"),
    path("recuperar-contrasena/", views.solicitar_recuperacion, name="password_reset_request"),
    path("recuperar-contrasena/codigo/", views.confirmar_recuperacion, name="password_reset_code"),
    path("movimientos/", views.movimientos, name="movimientos"),
    path("movimientos/nuevo/", views.movimiento_form, name="movimiento_nuevo"),
    path("movimientos/<int:pk>/editar/", views.movimiento_form, name="movimiento_editar"),
    path("movimientos/<int:pk>/borrar/", views.movimiento_borrar, name="movimiento_borrar"),
    path("categorias/", views.categorias, name="categorias"),
    path("categorias/<int:pk>/borrar/", views.categoria_borrar, name="categoria_borrar"),
    path("presupuestos/", views.presupuestos, name="presupuestos"),
    path("presupuestos/<int:pk>/editar/", views.presupuesto_editar, name="presupuesto_editar"),
    path("presupuestos/<int:pk>/borrar/", views.presupuesto_borrar, name="presupuesto_borrar"),
    path("metas/", views.metas, name="metas"),
    path("metas/<int:pk>/", views.meta_detalle, name="meta_detalle"),
    path("metas/<int:pk>/comprar/", views.meta_comprar, name="meta_comprar"),
    path("metas/<int:pk>/eliminar/", views.meta_eliminar, name="meta_eliminar"),
    path("metas/<int:pk>/cancelar/", views.meta_eliminar, name="meta_cancelar"),
    path("cuotas/<int:pk>/pagar/", views.cuota_pagar, name="cuota_pagar"),
    path("cuotas/<int:pk>/deshacer/", views.cuota_deshacer, name="cuota_deshacer"),
    path("perfil/", views.perfil, name="perfil"),
    path("perfil/tema/", views.cambiar_tema, name="cambiar_tema"),
    path("perfil/ingresos-fijos/<int:pk>/editar/", views.ingreso_fijo_editar, name="ingreso_fijo_editar"),
    path("perfil/ingresos-fijos/<int:pk>/borrar/", views.ingreso_fijo_borrar, name="ingreso_fijo_borrar"),
]
