# SENA — Sistema para Estudiantes: Navegación y Ahorro

App web para registrar ingresos y gastos, ver un resumen mensual, recibir alertas de presupuesto y simular compras por cuotas con metas. Multiusuario: cada persona ve solo sus datos.

## Iniciar el proyecto (doble clic)

**La forma más fácil:** doble clic en `iniciar.bat` y abre [http://127.0.0.1:8000](http://127.0.0.1:8000).

No se necesita ingresar ninguna contraseña en la terminal. Para entrar a la app, usa la cuenta que ya tienes registrada o crea una nueva en `/registro/`.

---

## Iniciar manualmente (terminal)

```bash
# Solo la primera vez, si no tienes el entorno virtual creado:
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

# Siempre que quieras encender el proyecto:
venv\Scripts\activate
python manage.py migrate
python manage.py runserver
```

Abre [http://127.0.0.1:8000](http://127.0.0.1:8000) e inicia sesión con tu cuenta existente o regístrate.

> **No ejecutes** `createsuperuser` a menos que quieras acceso al panel de administración `/admin/`.  
> Ese comando pide contraseña y **no es necesario** para usar la aplicación.

Para probar desde el celular en la misma red WiFi:
`python manage.py runserver 0.0.0.0:8000` y agrega la IP de tu PC en `DJANGO_ALLOWED_HOSTS`.

---

## Recuperación de contraseña por correo

En desarrollo, Django muestra el código de recuperación en la consola donde corre `runserver`. Para enviar correos reales, configura las variables de entorno `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL` y, si aplica, `EMAIL_USE_TLS` antes de iniciar el servidor; al definir `EMAIL_HOST` se usa automáticamente el backend SMTP. El código vence en 10 minutos y permite hasta cinco intentos.

## Tests

```bash
venv\Scripts\activate
python manage.py test finanzas
```

Cubren cálculos del resumen, alertas, formato de pesos, perfil, metas con cuotas y, sobre todo, que un usuario no pueda ver, editar ni borrar datos de otro.

## Estructura

- `finanzas/models.py` — Categoria, Movimiento, Presupuesto, MetaAhorro, CuotaMeta, Perfil, IngresoFijo (todo ligado a un usuario).
- `finanzas/servicios.py` — cálculos (resumen del mes, gastos por categoría, estado de presupuestos, simulaciones de cuotas, cálculo "Tu mes"). El futuro chatbot usará estas funciones como herramientas.
- `finanzas/views.py` — páginas; cada consulta filtra por `request.user`.
- `finanzas/templates/` — HTML, diseñado primero para celular, con modo oscuro/claro/automático.
- `iniciar.bat` — script de Windows para encender el proyecto sin escribir comandos.

## Antes de publicarla en internet

Define variables de entorno: `DJANGO_SECRET_KEY` (una clave larga y aleatoria), `DJANGO_DEBUG=0`, `DJANGO_ALLOWED_HOSTS=tudominio.cl` y `DJANGO_CSRF_TRUSTED_ORIGINS=https://tudominio.cl`. Para usar una base distinta a `db.sqlite3`, define `DJANGO_DATABASE_PATH` con la ruta al archivo SQLite. Cambia SQLite por PostgreSQL y sirve los archivos estáticos con `collectstatic` (o WhiteNoise). No expongas el servidor de desarrollo con `DEBUG` activado ni datos reales.
