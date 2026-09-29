# Acid Mod Loader (live site version)

No mantiene ninguna copia del sitio ni de los mods. La app abre
**https://acidorg.com/#mods** directamente dentro de una ventana pywebview y,
apenas termina de cargar, le inyecta un script por JavaScript (sin tocar tu
servidor para nada) que:

1. Agrega un botón flotante abajo a la izquierda para elegir/ver tu carpeta
   de Brawlhalla (se recuerda entre sesiones en `config.json`).
2. Convierte los botones "Download ↓" de la grilla de mods del juego (no
   toca la sección "Acid tools"/AzuModification) en botones "Install ⚡".
3. Al hacer click, Python descarga ese mismo archivo directo desde
   acidorg.com y aplica la misma lógica que tu `install_mods.ps1`: swf
   sueltos a la raíz, `bones*` a `bones/`, zips anidados emparejados por
   nombre contra `mapart/`.

Como consecuencia: **necesita internet siempre** — si el sitio se cae o no
hay conexión, simplemente no carga la página / falla la descarga con un
mensaje claro en el log. No hay nada que quede desactualizado: cuando subas
un mod nuevo al sitio, ya aparece acá también, sin tocar la app.

## Por qué es seguro que la página inyecte cosas en tu API

`api.install_mod` sólo acepta URLs de `acidorg.com` (o `www.acidorg.com`) —
si algún día agregas un enlace externo a la página y por error queda dentro
de la grilla de mods, la app lo rechaza en vez de descargarlo y ejecutarlo.

## Instalar y correr

```
pip install -r requirements.txt
python main.py
```

## Configurar `vendor/ffdec_lib.jar` (para el merge de sprites/sonidos)

`ffdec_lib.jar` **solo** no alcanza — FFDec necesita varios jars de
terceros (`tomlj`, `jsyntaxpane`, `commons-io`, etc.) que vienen junto con
él en la descarga oficial, normalmente en una carpeta `lib/` o `libs/` al
lado del jar principal. Si copiás nada más que `ffdec_lib.jar` sin esa
carpeta, vas a ver errores tipo `NoClassDefFoundError: org/tomlj/Toml` (o
cualquier otra clase) al instalar un `.bmod` con sección `swfs`.

Bajá el zip de una release de FFDec
(github.com/jindrapetrik/jpexs-decompiler/releases) y copiá **todo** su
contenido — `ffdec_lib.jar` y la carpeta de dependencias completa, tal
cual vienen — dentro de `vendor/`. La app arma el classpath solo buscando
cualquier `.jar` bajo la carpeta de `ffdec_lib.jar`, así que no importa
cómo se llame esa subcarpeta ni cuántos jars tenga.

## Empaquetar a .exe (con Java incluido, sin pedirlo como prerequisito)

```
pip install pyinstaller
python build_exe.py
```

`build_exe.py` descarga un JRE 17 portable de Adoptium a `vendor/jre/` (una
sola vez, se salta el paso si ya existe), confirma que pusiste
`vendor/ffdec_lib.jar` a mano, y corre PyInstaller en modo **`--onefile`**,
dejando un único `dist/AcidModLoader.exe` con el JRE y el jar empaquetados
adentro. La persona que lo reciba no necesita tener Java instalado —
`api.py` usa ese JRE empaquetado automáticamente (`DEFAULT_JAVA_HOME`), y
sólo cae al Java del sistema si por algún motivo ese contenido no está.

Tanto `config.json` como el JRE/`ffdec_lib.jar` viven en
`%LOCALAPPDATA%\AcidModLoader\` (no al lado del `.exe`, ni en la carpeta
temporal que PyInstaller vuelve a descomprimir en cada arranque), así que:
- La ruta de Brawlhalla que elijas se recuerda entre sesiones sin importar
  desde dónde corras el `.exe` (Descargas, un pendrive, etc.).
- El JRE + `ffdec_lib.jar` se copian a esa carpeta de AppData **una sola
  vez**, en el primer arranque (esa primera vez sí tarda un poco más — son
  ~45+ MB). Del segundo arranque en adelante, el `.exe` usa directamente
  esa copia persistente, así que sólo el primer inicio es lento.
- Si alguna vez querés forzar que se vuelva a copiar (por ejemplo después
  de actualizar `vendor/ffdec_lib.jar` y generar un `.exe` nuevo), borrá a
  mano la carpeta `%LOCALAPPDATA%\AcidModLoader\vendor` — se recrea sola
  en el próximo arranque.

Junto a `AcidModLoader.exe`, el build también deja en `dist/` un
**`Run AcidModLoader.bat`**. Repartir sólo el `.exe` funciona bien en la
mayoría de las PCs con Windows 10/11 actualizado, pero si querés cubrir
también máquinas que nunca instalaron nada relacionado con Python/WebView2,
zipeá ambos archivos (`AcidModLoader.exe` + el `.bat`) juntos y pedile a la
otra persona que corra el `.bat`: reviza si esa PC ya tiene instalados el
"Microsoft Visual C++ Runtime" y el "Microsoft Edge WebView2 Runtime" y, si
le falta alguno, lo baja e instala solo en silencio (descargas únicas, no
hace nada si ya estaban instalados). Sin el primero, el `.exe` falla al
abrir con un error tipo "Failed to load Python DLL ... LoadLibrary: The
specified module could not be found"; sin el segundo, pywebview cae a un
backend viejo que falla con "Failed to resolve
Python.Runtime.Loader.Initialize". Ambos son comunes en PCs que nunca
instalaron nada que los trajera consigo antes — y si mandás sólo el `.exe`
suelto a una de esas PCs, la persona se va a topar con uno de esos dos
errores en vez de la instalación automática.

Si preferís no depender del `.bat`, las soluciones manuales siguen siendo
las mismas: que la persona instale a mano el
[Visual C++ Redistributable x64](https://aka.ms/vs/17/release/vc_redist.x64.exe)
y el
[WebView2 Runtime](https://developer.microsoft.com/microsoft-edge/webview2/).

Si preferís armarlo a mano sin el script (por ejemplo para no bundlear el
JRE en una build de prueba), seguís pudiendo invocar PyInstaller directo:

```
pyinstaller --noconfirm --windowed --name "AcidModLoader" --add-data "modloader_inject.js;." main.py
```

pero en ese caso el usuario final SÍ va a necesitar Java 9+ instalado (o
vos vas a tener que copiar `vendor/` al lado del .exe manualmente).

## Si el merge de sprites/sonidos falla por versión de Java (corriendo desde código fuente)

Los `.bmod` que también traen una sección `swfs` (merge de sprites/sonidos/
scripts) necesitan un Java 9+ real en la máquina para levantar FFDec vía
JPype. Esto sólo importa si corrés `python main.py` directo — el .exe
empaquetado con `build_exe.py` ya trae su propio Java adentro (ver más
abajo) y no depende de nada instalado en la máquina. Corriendo desde
código fuente, si tu Java por defecto es más viejo, la app te avisa
claramente en el log en vez de tirar un stack trace, y podés arreglarlo
sin tocar tu Java del sistema: instalá un JDK moderno (por ejemplo
https://adoptium.net/temurin/releases/) y agregá su carpeta a
`config.json`:

```json
{
  "brawlhalla_path": "...",
  "java_home": "C:\\Program Files\\Eclipse Adoptium\\jdk-17.0.9+9"
}
```

## Instalar mods desde GameBanana

Además de acidorg.com, la app puede navegar a la sección de Brawlhalla en
GameBanana (`https://gamebanana.com/mods/games/5704`) dentro de la misma
ventana:

- En acidorg.com aparece un botón flotante **"🍌 Go to GameBanana"** (debajo
  del botón de la carpeta de Brawlhalla) que lleva ahí.
- Ya en GameBanana aparece un botón **"⚡ Go to Acid Mods"** para volver.
- Cualquier botón "Download" de GameBanana queda convertido en una
  instalación directa: al hacer click, la app descarga ese mismo archivo
  (siguiendo el link real de GameBanana, sea `/dl/<id>`, el viejo
  `/mmdl/<id>,...` o un link directo a un `.zip`) y lo instala con la misma
  lógica que ya usa para acidorg.com.
- Como GameBanana empaqueta los mods en un `.zip` (con el/los `.swf` sueltos
  adentro, o en subcarpetas si reemplazan un archivo puntual del juego), no
  hace falta nada especial de tu lado — `install_zip_mod` en `installer.py`
  ya sabe manejar esos casos. Lo único que cambia es cómo se detecta el tipo
  de archivo: como el link de descarga de GameBanana no trae la extensión en
  la URL (es un id numérico), la app la deduce del header
  `Content-Disposition` o de la URL final después de la redirección.
- El botón de "elegir carpeta de Brawlhalla" también está disponible en la
  página de GameBanana, por si es la primera pantalla que abrís.

Como en el resto de la app, sólo se descarga de `gamebanana.com` (o
`acidorg.com`) — cualquier otro link se rechaza.

## Mods instalados y desinstalación

En las dos páginas (acidorg.com y GameBanana) aparece un botón
**"📦 Installed mods"** que abre un panel con todos los mods que instalaste
desde la app (nombre, archivo, fecha y cantidad de archivos), cada uno con su
botón **Uninstall**, más **Uninstall all** cuando hay dos o más.

Cómo funciona: antes de escribir cualquier archivo en la carpeta de
Brawlhalla, `mod_registry.py` guarda una copia del archivo original en
`%LOCALAPPDATA%\AcidModLoader\backups\` y anota la instalación en
`%LOCALAPPDATA%\AcidModLoader\installed_mods.json`. Al desinstalar:

- Los archivos que el mod reemplazó vuelven a su versión anterior.
- Los archivos que el mod creó (y las carpetas nuevas que quedaron vacías)
  se borran.
- Si dos mods tocan el mismo archivo, desinstalar el más viejo deja el
  archivo como lo dejó el más nuevo; cuando desinstales el más nuevo se
  restaura el original.
- Si un archivo no se puede restaurar (por ejemplo, con Brawlhalla abierto),
  el mod se queda en la lista con esos archivos para reintentar.
- Volver a instalar el mismo mod reemplaza la instalación anterior en vez de
  duplicarla.
- Un mod que falló a la mitad aparece marcado como "Install didn't finish"
  y también se puede desinstalar.

Los mods instalados **antes** de esta versión no tienen respaldo, así que no
aparecen en la lista. Para volver al original en esos casos, usá "Verificar
integridad de los archivos del juego" en Steam.

## Si cambias de dominio o quieres apuntar a otra URL

Edita `ACID_URL`/`GAMEBANANA_URL` en `main.py` y las listas `ALLOWED_HOSTS` /
`NAV_ALLOWED_HOSTS` en `api.py`.

## Limitación conocida

Los `.bmod` de legends (como el que revisamos antes) son SWF crudo sin
metadata de a qué archivo del juego reemplazan, así que no están soportados
todavía por `install_mod` — solo lo que tu `.ps1` ya sabía instalar (swf
sueltos y zips con imágenes de mapart). Si quieres sumarlos, hace falta
definir esa convención primero (nombre exacto del swf destino, carpeta,
etc.).
