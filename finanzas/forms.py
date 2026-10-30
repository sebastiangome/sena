from datetime import date

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .models import Categoria, MetaAhorro, Movimiento, Presupuesto
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


class MetaAhorroForm(forms.ModelForm):
    class Meta:
        model = MetaAhorro
        fields = ["nombre", "precio"]


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


class MovimientoForm(forms.ModelForm):
    class Meta:
        model = Movimiento
        fields = ["tipo", "cuenta", "monto", "fecha", "categoria", "descripcion"]
        widgets = {"fecha": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")}

    def __init__(self, *args, usuario, **kwargs):
        super().__init__(*args, **kwargs)
        # Solo las categorías del usuario: impide asignar categorías ajenas aunque manipulen el HTML
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
