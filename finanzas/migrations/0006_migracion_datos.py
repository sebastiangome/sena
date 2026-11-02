from datetime import date
from django.db import migrations


def migrar_datos(apps, schema_editor):
    User = apps.get_model('auth', 'User')
    Perfil = apps.get_model('finanzas', 'Perfil')
    MetaAhorro = apps.get_model('finanzas', 'MetaAhorro')
    CuotaMeta = apps.get_model('finanzas', 'CuotaMeta')
    Movimiento = apps.get_model('finanzas', 'Movimiento')

    # 1. Crear Perfil para usuarios existentes
    for user in User.objects.all():
        Perfil.objects.get_or_create(usuario=user, defaults={'tema': 'auto'})

    hoy = date.today()

    # 2. Migrar metas compradas
    for meta in MetaAhorro.objects.filter(estado='comprada'):
        cuotas = CuotaMeta.objects.filter(meta=meta)
        todas_pagadas = True
        for cuota in cuotas:
            if cuota.fecha_vencimiento <= hoy:
                cuota.estado = 'pagada'
                cuota.fecha_pago = cuota.fecha_vencimiento
                cuota.save()
            else:
                todas_pagadas = False
                cuota.estado = 'pendiente'
                cuota.fecha_pago = None
                if cuota.movimiento_id:
                    mov_id = cuota.movimiento_id
                    cuota.movimiento = None
                    cuota.save()
                    Movimiento.objects.filter(id=mov_id).delete()
                else:
                    cuota.save()
        if cuotas.exists() and todas_pagadas:
            meta.estado = 'pagada'
            meta.save()

    # 3. Migrar metas anuladas: eliminarlas conservando sus Movimientos ya pagados
    metas_anuladas = MetaAhorro.objects.filter(estado='anulada')
    for meta in metas_anuladas:
        CuotaMeta.objects.filter(meta=meta).update(movimiento=None)
        meta.delete()


class Migration(migrations.Migration):

    dependencies = [
        ('finanzas', '0005_perfil_ingresofijo_cuotameta_metaahorro'),
    ]

    operations = [
        migrations.RunPython(migrar_datos, migrations.RunPython.noop),
    ]

