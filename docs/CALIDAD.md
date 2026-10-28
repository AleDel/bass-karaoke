# Calidad de código — stack local

Instalación sin Docker, en `C:\sonar`.

| Pieza | Versión | Licencia |
|---|---|---|
| SonarQube Community Build | 26.10.0.133078 (ZIP) | LGPL-3.0 |
| SonarScanner CLI (win-x64, JRE incluido) | 8.3.0.16463 | LGPL-3.0 |
| SonarQube MCP Server | 1.30.0.4763 (JAR) | SSAL v1 (source-available, uso interno libre) |
| Semgrep OSS | 1.182.1 (dev-dep) | LGPL-2.1 |
| ruff / pytest / pytest-cov / bandit / vulture / radon / pip-audit | ver `.venv` | MIT / Apache-2.0 |

## Uso diario

```powershell
# 1. Arrancar el servidor (una vez por sesión de trabajo)
.\scripts\sonar.ps1 start

# 2. Analizar: cobertura (pytest-cov) + envío a SonarQube
$env:SONAR_TOKEN = Get-Content C:\sonar\token.txt -Raw
.\scripts\sonar.ps1 scan

# 3. Ver resultados
.\scripts\sonar.ps1 open      # http://localhost:9000/dashboard?id=bass-karaoke

# 4. Parar
.\scripts\sonar.ps1 stop
```

El token está en `C:\sonar\token.txt` y también en la variable de usuario `SONAR_TOKEN`.
Para regenerarlo: <http://localhost:9000/account/security> (usuario `admin`).

## Semgrep (SAST rápido, sin servidor)

```powershell
.\.venv\Scripts\semgrep.exe --config p/python --config p/security-audit --metrics off bass_karaoke
```

También está expuesto como MCP (`semgrep`), configurado en `opencode.json`.

## Herramientas ligeras

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m bandit -r bass_karaoke -ll
.\.venv\Scripts\python.exe -m vulture bass_karaoke --min-confidence 80
.\.venv\Scripts\python.exe -m radon cc bass_karaoke -s -n D
.\.venv\Scripts\python.exe -m pytest -q --cov=bass_karaoke --cov-report=term-missing
```

## Estado (2026-10-28)

Puerta de calidad **OK**: 0 issues abiertos, 0 bugs, 0 vulnerabilidades, 0 code
smells, duplicación 0.6 %, cobertura global 37.3 % y **90.5 % en código nuevo**
(umbral 80 %). 316 tests en verde.

La puerta exige 80 % de cobertura *sólo en código nuevo*: al tocar lógica, añade
su test en `tests/unit/`. Para código de dibujo hay patrón sin ventana en
`tests/unit/test_header_draw.py` (Surface normal + `pygame.font.init()`, sin
`pygame.display`), y para eventos en `tests/unit/test_event_*.py` (se instancia
`BassKaraoke` sin `__init__` y se espían las acciones).

## Estructura de eventos

`app.handle_event` solo reparte por tipo de evento; la lógica está en mixins:

| Módulo | Contenido |
|---|---|
| `bass_karaoke/events/keyboard.py` | Un `_key_<panel>` por modal + tablas `_SIMPLE_KEYS` / `_MOD_KEYS` para las teclas globales |
| `bass_karaoke/events/mouse.py` | Clics, arrastres y rueda: paneles, onda, mástil y partitura |

Contrato de los handlers de modal: `True`/`False` si el panel estaba abierto y
consumió la tecla (`False` = salir), `None` si no aplica y sigue la cadena.
Ningún gesto de ratón cierra la aplicación.

## Avisos

- **Disco**: la unidad C: está al ~95 % de uso (44 GB libres). Por eso
  `conf/sonar.properties` lleva `sonar.search.javaAdditionalOpts=-Dcluster.routing.allocation.disk.threshold_enabled=false`,
  que evita que Elasticsearch marque los índices como *read-only*. Es un parche para
  desarrollo local: si liberas espacio (>10 % libre), quita esa línea.
- **ZIP deprecado**: SonarSource anunció que la instalación por ZIP desaparecerá;
  la alternativa oficial será el contenedor.
- **Cobertura**: `sonar.python.coverage.reportPaths=coverage.xml`, generado por
  `scripts\sonar.ps1 scan`. No lo edites a mano.
- **Índice de issues**: la API puede tardar unos segundos tras el análisis; si el
  MCP devuelve issues ya corregidos, consulta
  `api/issues/search?componentKeys=bass-karaoke&resolved=false`.
