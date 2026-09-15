# AGENT.md — Bass Karaoke (C:\DEA\ALE\Ensayos)

> Repo git `master` (ahead 2 el 2026-09-15). App desktop Python 3.10 + pygame.
> Este archivo es la fuente de verdad para agentes: qué es el proyecto y cómo usar
> correctamente los MCP `codebase-memory` y `gitnexus`.

## 0. Al iniciar cada sesión de chat (ADR por secciones) — OBLIGATORIO

El ADR de `Codebase Memory MCP` está organizado por áreas de trabajo en encabezados
`##` (ej. `Estado actual`, `Comparar features Python y C++ streamdiffusion`, `testotros`).
Proyecto ADR: `C-DEA-ALE-Ensayos`.

- **Acción obligatoria al arrancar la sesión:** lee el ADR (`manage_adr mode=get` +
  `mode=sections`) y pregunta al usuario, con un mensaje corto, en qué sección `##`
  vamos a trabajar esta sesión, mostrando la lista de secciones existentes, O si vamos
  a crear una sección nueva.
- No asumas la sección: confirma antes de editar. Al terminar, actualiza SOLO la sección
  trabajada (no reescribas las demás).
- **ANTI-PÉRDIDA ADR (obligatorio, causa del borrado anterior):** `manage_adr mode=update`
  sobrescribe TODO si le pasas solo la sección nueva. Prohibido hacer eso. Protocolo:
  1) `get` y guarda el contenido íntegro, 2) fusiona en memoria: conserva todas las demás
  secciones byte-por-byte y edita/añade solo la acordada como `## <nombre> (YYYY-MM-DD)`,
  3) `update` con el documento completo fusionado, 4) verifica con `get` + `sections` que
  el nº de secciones no ha disminuido. Si disminuye, avisa y restaura. Si el ADR viene sin
  `##` (legado), convierte el bloque huérfano en una sección `##` preservándolo, nunca lo borres.

## 1. Resumen del proyecto

**Bass Karaoke** es un karaoke de bajo eléctrico: tablatura con scroll en tiempo real,
detección de pitch del bajo conectado al PC, partitura estándar y editor de alineación
con waveform. Ver `README.md` (265 líneas, documentación completa) y captura en `assets/`.

### 1.1 Stack

- Lenguaje: Python 3.10 en Windows. UI: `pygame==2.6.1` + `numpy==1.26.4`.
- Audio/pitch: `PyAudio`, `aubio` (YIN), `librosa` + `sounddevice` (varispeed/time-stretch),
  `verovio` + `CairoSVG` (partitura), `onnxruntime` / `torchcrepe` / `pesto` / `basic-pitch`
  (detectores IA opcionales), `soundfile` (decode MP3 para waveform).
- Build: PyInstaller single-file `dist/BassKaraoke.exe` (~50 MB) vía `build_basic.spec` + `build.ps1`.
- Ver `requirements.txt` (41 líneas). Nota conocida: `aubio==0.5.0a0` ya no está en PyPI;
  usar `aubio==0.4.9` o `--find-links https://github.com/aubio/aubio/releases`. La app
  funciona sin aubio (pierde pitch).

### 1.2 Estructura (raíz del proyecto)

```
bass_karaoke/        → paquete principal
  main.py            → DPI-aware (SetProcessDpiAwareness) + main(): BassKaraoke().run()
  app.py             → clase BassKaraoke (~1797 líneas, orquestadora: estado, loop, countdown,
                       pitch, tempo_map, menús). NO duplicar lógica aquí: importar de submódulos.
  config.py          → constantes: rutas (SONGS_DIR, CONFIG_PATH), audio (44100Hz, CHUNK 2048,
                       WIN 4096, MPM/AUBIO thresholds, LOWPASS 700Hz), cuerdas, BPM 113,
                       layout UI 1280x860, paleta colores.
  parser.py          → parse_musicxml() → notes/sections/bpm/tempo_map; parse_grace_notes() (.tg).
                       Lee <metronome> del MusicXML; default 113 BPM. Deriva fret/string si no hay tab.
  utils.py           → fret_to_hz, hz_to_note_name, notes_match
  features.py        → gestor de funcionalidades opcionales: FEATURES[] (aubio, torch-core, crepe,
                       pesto, pesto-onnx, basic-pitch, varispeed, scipy, music21),
                       features_dir(), ensure_on_path(), install()/uninstall() con pip embebido.
  audio/player.py    → VarispeedPlayer, VARSPEED_OK, load_mp3_samples, SOUNDFILE_OK
  audio/pitch_engine.py → PitchEngine, PITCH_AVAILABLE, enumerate_devices, PA_OK.
                       Métodos: mpm (defecto, CPU, bueno en graves), aubio yinfft,
                       crepe-tiny/full, pesto, pesto-onnx, basic-pitch.
  score/verovio_renderer.py, score/music21_renderer.py → init_score_surface*()
  ui/                → draw_tab, draw_score, draw_guitartab, draw_neck, draw_piano,
                       draw_panels, draw_overlays, widgets
bass_karaoke_v3.py   → entrada DESARROLLO (solo hace sys.path + from bass_karaoke.main import main)
launcher.py          → entrada EXE (frozen): BK_VERIFY=1 → _verify() escribe _verify_out.txt; si no → main()
build_basic.spec     → spec PyInstaller: empaqueta verovio+cairosvg+soundfile+pip+cairo DLLs (GTK2-Runtime);
                       EXCLUYE torch/aubio/librosa/scipy/music21 (se instalan vía menú I → ./features).
build.ps1            → .\build.ps1 [-SkipClean] [-Verify]
bass_karaoke_config.json → por canción: bpm, bpm_map, mp3_offset_map, tempo_maps, device_idx, pitch_method, song
songs/<nombre>/      → <nombre>.musicxml (obligatorio) + .tg (opcional) + .mp3 (opcional).
                       Actuales: feet_dont_fail_me_now, infant_eyes, infant_eyes_ 9_measure, maitreya
models/              → mir-1k_g7_44100_512.onnx (PESTO)
assets/ tests/test_*.py (aubio, crepe, pesto, verovio)  scripts/list_audio_devices.py
```

### 1.3 Comandos

```powershell
# dev
uv venv .venv --python 3.10
uv pip install --python .venv\Scripts\python.exe -r requirements.txt --find-links https://github.com/aubio/aubio/releases
.venv\Scripts\python.exe bass_karaoke_v3.py
# L = elegir canción, SPACE = play con countdown, W = editor alineación, F5 = guardar config

# build
.\build.ps1                # normal
.\build.ps1 -Verify        # + auto-check BK_VERIFY=1
.venv\Scripts\pyinstaller.exe build_basic.spec --clean --noconfirm

# deploy exe: copiar BassKaraoke.exe + songs/ + models/ juntos (no van empaquetadas).
# features opcionales se instalan desde menú I y quedan en ./features junto al exe → reiniciar app.
```

### 1.4 Convenciones para agentes

- No crear archivos nuevos salvo pedido; preferir editar `bass_karaoke/*`. No crear `*.md` salvo este.
- `app.py` es orquestadora: la lógica nueva va en `audio/`, `score/`, `ui/`, `parser.py`, `utils.py`.
- Rutas frozen/dev ya resueltas en `config._BASE_DIR` — no hardcodear rutas absolutas.
- Config por canción se guarda con F5 en `bass_karaoke_config.json` (hay cambios sin commitear: ese
  json + `songs/infant_eyes/*` + `songs/infant_eyes_ 9_measure/` untracked — revisar antes de commit).
- Controles clave: SPACE, L, W, R, C, ←/→, ↑/↓, ,/., Shift/Ctrl+ ,/., D, P, S, M, N, T, H, B, I, F5/F6, ESC.

---

## 2. MCP `codebase-memory` (codebase-memory-mcp_*) — uso correcto

Sistema de grafo de conocimiento con resolución LSP. Ideal para: arquitectura, búsqueda
estructural, callers/callees, data-flow, impacto previo al cambio.

### 2.1 Estado actual (2026-09-15) — INDEXADO

Proyecto `C-DEA-ALE-Ensayos` indexado en `codebase-memory` (mode `moderate`):
490 nodos, 2606 aristas. ADR vacío todavía (`sections: []`).
`list_projects` también muestra `C-DEA-ALE-Maitreya-AppMaitreya` y
`C-DEA-ALE-PluginTouchdesigner` (otros proyectos, no usar para este repo).
Usa `project="C-DEA-ALE-Ensayos"` **siempre** en las llamadas. Re-indexar tras cambios
grandes:

```
codebase-memory-mcp_index_repository(repo_path="C:/DEA/ALE/Ensayos", mode="moderate")
# mode: moderate (recomendado aquí, Python+assets pesados) | full (incluye similarity/semantic)
#       fast (rápido, sin similarity/semantic). persistence: true si se quiere .codebase-memory/graph.db.zst
codebase-memory-mcp_index_status(project="C-DEA-ALE-Ensayos")
```

El nombre `project` se deriva de la ruta; confirmarlo con `list_projects` tras indexar y
usarlo **siempre** en las llamadas siguientes.

### 2.2 Cuándo usar cada herramienta

| Objetivo | Herramienta | Ejemplo en este repo |
|---|---|---|
| Visión arquitectura/paquetes | `get_architecture(project, aspects=["overview","structure","packages","clusters"])` | `path="bass_karaoke/audio"` para acotar |
| Buscar definición/implementación | `search_graph(project, query="pitch detection", label="Function")` o `name_pattern="PitchEngine.*"` o `semantic_query=["pitch","detect","bass"]` | `query="varispeed mp3 tempo"` |
| Buscar texto + ranking estructural | `search_code(project, pattern="tempo_map", mode="compact", limit=10)` → `full` para fuente, `files` solo paths | `pattern="parse_musicxml"`, `file_pattern="*.py"` |
| Leer símbolo exacto | `get_code_snippet(project, qualified_name="<qualified_name de search_graph>")` | primero `search_graph`, luego snippet |
| Callers/callees, impacto, data-flow | `trace_path(project, function_name="PitchEngine", mode="calls", direction="both", depth=3)` ; `mode="data_flow"` con `parameter_name` | `function_name="parse_musicxml"`, `function_name="VarispeedPlayer"` |
| Consultas multi-hop/agregadas | `query_graph(project, query="MATCH (f:Function) WHERE f.transitive_loop_depth>=3 RETURN ...")` | hot-paths, complejidad ciclomática |
| Qué cambió y su impacto | `detect_changes(project, since="HEAD~5", scope="...")` | pre-commit / pre-PR |
| Esquema del grafo | `get_graph_schema(project)` | antes de escribir Cypher a mano |

### 2.3 Reglas

1. **Graph primero, grep después.** Para "¿dónde se define X?", "¿quién llama a Y?",
   "¿cómo fluye tempo/offset?" usa `search_graph`/`trace_path` en vez de `grep`/`glob`.
   `search_code` es el puente cuando necesitas texto literal con ranking por grafo.
2. **Paginar.** `search_graph` devuelve `total` + `has_more` → re-llamar con
   `offset=offset+limit`. `search_code` devuelve `total_grep_matches`/`total_results` →
   subir `limit` o acotar con `file_pattern`/`path_filter` (p. ej. `^bass_karaoke/audio/`).
3. **Dos pasos para leer código:** `search_graph` → `qualified_name` exacto →
   `get_code_snippet`. No adivinar qualified names.
4. **Re-indexar** tras cambios grandes (`index_repository` de nuevo) o los resultados
   quedan stale. Verificar con `index_status`.
5. No usar `ingest_traces`/`delete_project` salvo pedido explícito. `manage_adr` SÍ es de
   uso obligatorio según §0 (lectura al arrancar + actualización de la sección trabajada
   con protocolo anti-pérdida).

## 3. MCP `gitnexus` (gitnexus_*) — uso correcto

Grafo de ejecución (procesos/call-chains), impacto/blast-radius y refactor seguro.
Ideal para: "¿cómo funciona X de punta a punta?", "¿qué rompo si cambio Y?", renames multi-archivo.

### 3.1 Estado actual — INDEXADO (2026-09-15)

Repo `bass-karaoke` indexado y fresco (`analyze` 2026-09-15, rama `master`,
commit `8a37d6e`): 55 ficheros, 543 nodos, 1047 aristas, 30 comunidades, 44 procesos.
Usa `repo="bass-karaoke"` (u omite `repo` si es el único índice en uso) **siempre**.
`list_repos` también muestra `AppMaitreya` y `PluginTouchdesigner` (otros proyectos,
ambos stale — no usar para este repo). Refrescar tras cambios grandes desde la raíz:

```powershell
node .gitnexus/run.cjs analyze
# flags: --force (re-index total), --embeddings (búsqueda semántica, off por defecto),
#        --pdg (capas para explain/pdg_query: taint + CDG + REACHING_DEF)
node .gitnexus/run.cjs status   # frescura del índice
node .gitnexus/run.cjs list     # equivale a list_repos
```

Si `node .gitnexus/run.cjs` dice `Cannot find module`, regenerar con `npx gitnexus analyze`.
Tras re-indexar grande, reiniciar el servidor MCP si el índice parece stale.
Skills de referencia: `gitnexus-cli`, `gitnexus-exploring`, `gitnexus-debugging`,
`gitnexus-impact-analysis`, `gitnexus-refactoring`, `gitnexus-guide`, `gitnexus-pr-review`,
`gitnexus-taint-analysis`, `gitnexus-pdg-query`.

### 3.2 Cuándo usar cada herramienta (con ejemplos de este repo)

| Objetivo | Herramienta | Ejemplo |
|---|---|---|
| Flujos de ejecución de un concepto | `query(search_query="pitch detection realtime", goal="entender detección", task_context="...")` | `search_query="varispeed mp3 playback tempo"` ; `search_query="musicxml parsing tempo map"` |
| Vista 360º de un símbolo (callers, callees, procesos, fichero) | `context(name="BassKaraoke")` / `context(name="PitchEngine")` / `context(name="parse_musicxml")` | desambiguar con `file_path="bass_karaoke/audio/pitch_engine.py"`, `kind="Class"`; `uid` para cero ambigüedad; `include_content:true` para fuente |
| Blast-radius ANTES de editar | `impact(target="PitchEngine", direction="upstream")` ; `direction="downstream"` para dependencias | `impact(target="parse_musicxml", direction="upstream")`, `impact(target="VarispeedPlayer", direction="upstream", summaryOnly=true)` para hubs |
| Cadena A→B | `trace(from="BassKaraoke", to="PitchEngine")` | `trace(from="BassKaraoke", to="parse_musicxml")` |
| Revisión pre-commit | `detect_changes(scope="unstaged")` / `"staged"` / `"all"` / `"compare"`+`base_ref="main"` | devuelve símbolos cambiados + procesos afectados + riesgo |
| Cypher estructural | `cypher(statement="MATCH (a)-[:CodeRelation {type:'CALLS'}]->(b:Function {name:'parse_musicxml'}) RETURN a.name, a.filePath")` | leer schema primero (`gitnexus://repo/{name}/schema`); relaciones: CALLS/IMPORTS/EXTENDS/IMPLEMENTS/HAS_METHOD/HAS_PROPERTY/ACCESSES/METHOD_OVERRIDES/INJECTS |
| Rename coordinado | `rename(symbol_name="...", new_name="...", dry_run=true)` → revisar → `dry_run:false` | p. ej. renombrar `fret_to_hz`; luego `detect_changes()` |
| Ciclos de imports | `check(cycles=true)` | para CI / limpieza |
| Seguridad taint / dependencias PDG | `explain(target="bass_karaoke/audio/pitch_engine.py")` ; `pdg_query(mode="controls"\|"flows", target="PitchEngine")` | **requiere índice con `--pdg`**; sin él devuelven nota "no layer", no error |
| `route_map` / `shape_check` / `api_impact` / `tool_map` | N/A aquí (no hay rutas HTTP; es pygame desktop) | no usar salvo que aparezca servidor/API |

### 3.3 Reglas

1. **Flujo estándar:** `query` (flujos) → `context` (símbolo concreto) → `impact` (si vas a
   cambiarlo) → `trace` (si dudas cómo llega A a B) → editar → `detect_changes` (verificar).
2. **Siempre `direction` en `impact`:** `upstream` = "¿qué depende de esto?" (uso habitual
   pre-refactor); `downstream` = "¿de qué depende esto?". Para hubs (p. ej. `BassKaraoke`,
   `utils.fret_to_hz`) usa `summaryOnly:true` + `limit` pequeño y pagina con `offset`.
3. **Desambiguación:** si `context`/`impact` devuelven candidatos, reintentar con `file_path`/
   `kind`/`uid`, nunca asumir el primero.
4. **`impact` con `mode:"pdg"`** solo con índice `--pdg`; su riesgo siempre es `UNKNOWN` y no
   admite `crossDepth` ni `@grupo`. El `pdg` con `line` ancla el slice a una línea concreta.
5. Refrescar índice (`analyze`) tras cambios mayores o si `context` avisa de staleness.

## 4. ¿Cuál MCP uso?

- **codebase-memory:** arquitectura por paquetes/clusters, búsqueda exacta/semántica de
  definiciones, snippets, data-flow de parámetros, queries de complejidad (loop_depth, etc.).
- **gitnexus:** procesos end-to-end (p. ej. "nota MusicXML → scroll → pitch → score"),
  impacto por profundidad (d=1 ROMPE / d=2 probablemente afectado / d=3 testear), trace A→B,
  detect_changes→procesos afectados, rename seguro.
- Regla práctica: explorar con ambos (`get_architecture` + `query`), profundizar símbolo con
  `context`+`get_code_snippet`, y antes de editar ejecutar `impact` (gitnexus) y/o `trace_path`
  (codebase-memory). Tras editar, `detect_changes` en ambos.

## 5. Recursos MCP disponibles

- `list_mcp_resources` / `list_mcp_resource_templates` / `read_mcp_resource(server, uri)` —
  p. ej. `gitnexus://repo/{name}/context`, `gitnexus://repo/{name}/schema`,
  `gitnexus://repo/{name}/process/{processName}` para trazas completas.
