from datetime import date

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .models import Categoria, IngresoFijo, MetaAhorro, Movimiento, Presupuesto
from .servicios import CUOTAS_PERMITIDAS


class RegistroForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ["username", "email"]


class SolicitarRecuperacionForm(forms.Form):
    email = forms.EmailField(label="Correo electrónico")


class CodigoRecuperacionForm(forms.Form):
    email = forms.EmailField(label="Correo electrónico")
    codigo = forms.CharField(
        label="Código de recuperación",
        min_length=6,
        max_length=6,
        widget=forms.TextInput(attrs={"autocomplete": "one-time-code", "inputmode": "numeric"}),
    )
    new_password1 = forms.CharField(
        label="Nueva contraseña",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    new_password2 = forms.CharField(
        label="Confirma la nueva contraseña",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    def clean_codigo(self):
        codigo = self.cleaned_data["codigo"]
        if not codigo.isdecimal():
            raise forms.ValidationError("El código debe contener solo números.")
        return codigo

    def clean(self):
        datos = super().clean()
        contrasena1 = datos.get("new_password1")
        contrasena2 = datos.get("new_password2")
        if contrasena1 and contrasena2 and contrasena1 != contrasena2:
            self.add_error("new_password2", "Las contraseñas no coinciden.")
        return datos


class CambiarEmailForm(forms.Form):
    email = forms.EmailField(label="Nuevo correo electrónico", required=True)
    password = forms.CharField(
        label="Contraseña actual",
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
        required=True,
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_email(self):
        email = self.cleaned_data.get("email", "").strip()
        if self.user and User.objects.filter(email__iexact=email).exclude(pk=self.user.pk).exists():
            raise forms.ValidationError("Este correo ya está en uso por otra cuenta.")
        return email

    def clean_password(self):
        password = self.cleaned_data.get("password")
        if self.user and not self.user.check_password(password):
            raise forms.ValidationError("La contraseña actual es incorrecta.")
        return password


class IngresoFijoForm(forms.ModelForm):
    nombre = forms.CharField(
        label="Nombre del ingreso",
        max_length=80,
        required=True,
        widget=forms.TextInput(attrs={"placeholder": "Ej: Quincena, Beca..."}),
    )
    monto = forms.IntegerField(
        label="Monto mensual",
        min_value=1,
        required=True,
        widget=forms.NumberInput(attrs={"placeholder": "Monto en pesos"}),
    )
    dia_mes = forms.IntegerField(
        label="Día del mes (1 a 31)",
        min_value=1,
        max_value=31,
        required=True,
        widget=forms.NumberInput(attrs={"min": 1, "max": 31, "placeholder": "Ej: 15"}),
    )

    class Meta:
        model = IngresoFijo
        fields = ["nombre", "monto", "dia_mes"]

    def clean_nombre(self):
        nombre = self.cleaned_data.get("nombre", "").strip()
        if not nombre:
            raise forms.ValidationError("El nombre no puede estar vacío ni contener solo espacios.")
        return nombre

    def clean_monto(self):
        monto = self.cleaned_data.get("monto")
        if monto is None or monto <= 0:
            raise forms.ValidationError("El monto debe ser mayor a 0.")
        return monto


class MetaAhorroForm(forms.ModelForm):
    nombre = forms.CharField(
        label="¿Qué quieres comprar?",
        max_length=80,
        required=True,
        widget=forms.TextInput(attrs={"placeholder": "Ej: Bicicleta, Notebook..."}),
    )
    precio = forms.IntegerField(
        label="Precio",
        min_value=1,
        required=True,
        widget=forms.NumberInput(attrs={"placeholder": "Precio en pesos"}),
    )

    class Meta:
        model = MetaAhorro
        fields = ["nombre", "precio"]

    def clean_nombre(self):
        nombre = self.cleaned_data.get("nombre", "").strip()
        if not nombre:
            raise forms.ValidationError("El nombre no puede estar vacío ni contener solo espacios.")
        return nombre

    def clean_precio(self):
        precio = self.cleaned_data.get("precio")
        if precio is None or precio <= 0:
            raise forms.ValidationError("El precio debe ser mayor a 0.")
        return precio


class SimulacionMetaForm(forms.Form):
    cuotas = forms.TypedChoiceField(
        choices=[(n, f"{n} cuotas") for n in CUOTAS_PERMITIDAS],
        coerce=int,
    )
    tasa_mensual = forms.DecimalField(
        label="Tasa de interés mensual (%)",
        min_value=0,
        max_value=10,
        max_digits=4,
        decimal_places=2,
        initial=0,
        required=True,
    )


class ConfirmarCompraMetaForm(SimulacionMetaForm):
    fecha_primera_cuota = forms.DateField(
        label="Fecha de la primera cuota",
        initial=date.today,
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
    )

    def clean_cuotas(self):
        cuotas = self.cleaned_data["cuotas"]
        if cuotas not in CUOTAS_PERMITIDAS:
            raise forms.ValidationError("Elige una cantidad de cuotas permitida.")
        return cuotas


class PagarCuotaForm(forms.Form):
    fecha_pago = forms.DateField(
        label="Fecha de pago",
        initial=date.today,
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
    )
    monto = forms.IntegerField(
        label="Monto de la cuota",
        min_value=1,
    )
    cuenta = forms.ChoiceField(
        label="Cuenta de pago",
        choices=[("banco", "Banco"), ("efectivo", "Efectivo")],
        initial="banco",
    )


class MovimientoForm(forms.ModelForm):
    class Meta:
        model = Movimiento
        fields = ["tipo", "cuenta", "monto", "fecha", "categoria", "descripcion"]
        widgets = {"fecha": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")}

    def __init__(self, *args, usuario, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["categoria"].queryset = Categoria.objects.filter(usuario=usuario)
        self.fields["categoria"].empty_label = "Elige una categoría"

    def clean(self):
        datos = super().clean()
        cat, tipo = datos.get("categoria"), datos.get("tipo")
        if cat and tipo and cat.tipo != tipo:
            self.add_error("categoria", f"La categoría «{cat}» es de tipo {cat.get_tipo_display().lower()}.")
        return datos


class CategoriaForm(forms.ModelForm):
    class Meta:
        model = Categoria
        fields = ["nombre", "tipo"]

    def __init__(self, *args, usuario, **kwargs):
        super().__init__(*args, **kwargs)
        self.usuario = usuario

    def clean(self):
        datos = super().clean()
        if Categoria.objects.filter(usuario=self.usuario, nombre__iexact=datos.get("nombre", ""), tipo=datos.get("tipo")).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Ya tienes una categoría con ese nombre.")
        return datos


class PresupuestoForm(forms.ModelForm):
    class Meta:
        model = Presupuesto
        fields = ["categoria", "monto_mensual"]

    def __init__(self, *args, usuario, **kwargs):
        super().__init__(*args, **kwargs)
        self.usuario = usuario
        self.fields["categoria"].queryset = Categoria.objects.filter(usuario=usuario, tipo="gasto")
        self.fields["categoria"].empty_label = "Elige una categoría"

    def clean_categoria(self):
        cat = self.cleaned_data["categoria"]
        if Presupuesto.objects.filter(usuario=self.usuario, categoria=cat).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Ya hay un presupuesto para esa categoría; edítalo.")
        return cat
