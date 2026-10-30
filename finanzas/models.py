from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

CATEGORIAS_INICIALES = {
    "gasto": ["Comida", "Transporte", "Universidad", "Ocio", "Hogar", "Salud", "Otros"],
    "ingreso": ["Mesada", "Beca", "Trabajo", "Otros ingresos"],
}


class Categoria(models.Model):
    TIPOS = [("ingreso", "Ingreso"), ("gasto", "Gasto")]

    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="categorias")
    nombre = models.CharField(max_length=50)
    tipo = models.CharField(max_length=7, choices=TIPOS)

    class Meta:
        ordering = ["tipo", "nombre"]
        constraints = [
            models.UniqueConstraint(fields=["usuario", "nombre", "tipo"], name="categoria_unica_por_usuario")
        ]

    def __str__(self):
        return self.nombre


class Movimiento(models.Model):
    TIPOS = Categoria.TIPOS
    CUENTAS = [("efectivo", "Efectivo"), ("banco", "Banco")]

    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="movimientos")
    tipo = models.CharField(max_length=7, choices=TIPOS)
    cuenta = models.CharField("cuenta", max_length=10, choices=CUENTAS, default="efectivo")
    monto = models.PositiveIntegerField(validators=[MinValueValidator(1)], help_text="Monto en pesos chilenos")
    fecha = models.DateField()
    categoria = models.ForeignKey(Categoria, on_delete=models.PROTECT, related_name="movimientos", verbose_name="categoría")
    descripcion = models.CharField("descripción", max_length=120, blank=True)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha", "-creado"]
        indexes = [models.Index(fields=["usuario", "fecha"])]

    def __str__(self):
        return f"{self.get_tipo_display()} ${self.monto} - {self.categoria}"


class Presupuesto(models.Model):
    """Límite mensual de gasto para una categoría."""

    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="presupuestos")
    categoria = models.ForeignKey(Categoria, on_delete=models.CASCADE, related_name="presupuestos", verbose_name="categoría")
    monto_mensual = models.PositiveIntegerField(validators=[MinValueValidator(1)])

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["usuario", "categoria"], name="presupuesto_unico_por_categoria")
        ]

    def __str__(self):
        return f"{self.categoria}: ${self.monto_mensual}/mes"


class MetaAhorro(models.Model):
    ESTADOS = [
        ("simulacion", "Simulación"),
        ("comprada", "Comprada"),
        ("anulada", "Anulada"),
    ]

    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="metas")
    nombre = models.CharField(max_length=80)
    precio = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    estado = models.CharField(max_length=12, choices=ESTADOS, default="simulacion")
    cuotas = models.PositiveSmallIntegerField(null=True, blank=True)
    tasa_mensual = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    valor_cuota = models.PositiveIntegerField(null=True, blank=True)
    total_pagar = models.PositiveIntegerField(null=True, blank=True)
    fecha_compra = models.DateField(null=True, blank=True)
    fecha_primera_cuota = models.DateField(null=True, blank=True)
    creada = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-creada"]

    def __str__(self):
        return self.nombre


class CuotaMeta(models.Model):
    meta = models.ForeignKey(MetaAhorro, on_delete=models.CASCADE, related_name="cuotas_programadas")
    movimiento = models.OneToOneField(
        Movimiento, on_delete=models.CASCADE, related_name="cuota_meta"
    )
    numero = models.PositiveSmallIntegerField()
    fecha = models.DateField()
    monto = models.PositiveIntegerField(validators=[MinValueValidator(1)])

    class Meta:
        ordering = ["fecha", "numero"]
        constraints = [
            models.UniqueConstraint(fields=["meta", "numero"], name="cuota_unica_por_meta")
        ]


class CodigoRecuperacion(models.Model):
    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="codigo_recuperacion",
    )
    codigo_hash = models.CharField(max_length=128)
    creado = models.DateTimeField(auto_now=True)
    intentos = models.PositiveSmallIntegerField(default=0)


def crear_categorias_iniciales(usuario):
    for tipo, nombres in CATEGORIAS_INICIALES.items():
        for nombre in nombres:
            Categoria.objects.get_or_create(usuario=usuario, nombre=nombre, tipo=tipo)
