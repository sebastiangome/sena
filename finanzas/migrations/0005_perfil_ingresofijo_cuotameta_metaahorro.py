import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('finanzas', '0004_codigorecuperacion'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RenameField(
            model_name='cuotameta',
            old_name='fecha',
            new_name='fecha_vencimiento',
        ),
        migrations.AlterField(
            model_name='cuotameta',
            name='fecha_vencimiento',
            field=models.DateField(verbose_name='fecha de vencimiento'),
        ),
        migrations.AlterModelOptions(
            name='cuotameta',
            options={'ordering': ['fecha_vencimiento', 'numero']},
        ),
        migrations.AddField(
            model_name='cuotameta',
            name='estado',
            field=models.CharField(
                choices=[('pendiente', 'Pendiente'), ('pagada', 'Pagada')],
                default='pendiente',
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name='cuotameta',
            name='fecha_pago',
            field=models.DateField(blank=True, null=True, verbose_name='fecha de pago'),
        ),
        migrations.AlterField(
            model_name='cuotameta',
            name='movimiento',
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='cuota_meta',
                to='finanzas.movimiento',
            ),
        ),
        migrations.AlterField(
            model_name='metaahorro',
            name='estado',
            field=models.CharField(
                choices=[('simulacion', 'Simulación'), ('comprada', 'Comprada'), ('pagada', 'Pagada')],
                default='simulacion',
                max_length=12,
            ),
        ),
        migrations.CreateModel(
            name='Perfil',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tema', models.CharField(choices=[('auto', 'Automático'), ('light', 'Claro'), ('dark', 'Oscuro')], default='auto', max_length=10)),
                ('usuario', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='perfil', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='IngresoFijo',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(max_length=80)),
                ('monto', models.PositiveIntegerField(validators=[django.core.validators.MinValueValidator(1)])),
                ('dia_mes', models.PositiveSmallIntegerField(help_text='Día del mes (1 a 31)', validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(31)])),
                ('creado', models.DateTimeField(auto_now_add=True)),
                ('usuario', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='ingresos_fijos', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['dia_mes', 'nombre'],
            },
        ),
    ]
