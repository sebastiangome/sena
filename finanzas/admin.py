from django.contrib import admin

from .models import Categoria, CuotaMeta, IngresoFijo, MetaAhorro, Movimiento, Perfil, Presupuesto


@admin.register(Movimiento)
class MovimientoAdmin(admin.ModelAdmin):
    list_display = ("fecha", "usuario", "tipo", "cuenta", "monto", "categoria", "descripcion")
    list_filter = ("tipo", "cuenta", "fecha")


admin.site.register(Categoria)
admin.site.register(Presupuesto)
admin.site.register(MetaAhorro)
admin.site.register(CuotaMeta)
admin.site.register(Perfil)
admin.site.register(IngresoFijo)
