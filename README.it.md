<div align="center">

# Maya UX Pro per Blender

**Il workflow autentico di Autodesk Maya dentro Blender 4.2 – 5.3+ — Barra Spaziatrice & Hotbox fluttuante, Smart Middle Mouse, Selezione Face Center-Only, Poly Count HUD, Hold-`D` Pivot & Snap, Retopo e CamTools Pro.**

[![Blender](https://img.shields.io/badge/Blender-4.2%20--%205.3%2B-orange?logo=blender)](https://www.blender.org/)
[![Version](https://img.shields.io/badge/Release-v2.5.9-blue)](https://github.com/GiorgioDeAngelis/maya-ux-pro-blender/releases/latest)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-green.svg)](./LICENSE)
[![Platforms](https://img.shields.io/badge/OS-macOS%20%7C%20Windows%20%7C%20Linux-lightgrey)](#profili-piattaforma-macos--windowslinux)
[![Tests](https://img.shields.io/badge/Test%20Headless-16%2F16%20Superati-brightgreen)](./CONTRIBUTING.md)

[English (README.md)](./README.md) | **Italiano** · [Tutte le Scorciatoie](./docs/HOTKEYS.md) · [Guida Funzionalità](./docs/FEATURES.md) · [Changelog](./CHANGELOG.md)

</div>

---

## Perché Maya UX Pro?

Passare da Autodesk Maya a Blender richiede molto più di qualche scorciatoia cambiata. La keymap *Industry Compatible* di Blender copre solo le basi: non implementa **Spacebar Tap/Hold + Hotbox**, lo **Smart Middle Mouse**, il **Pivot temporaneo con `D` + snap `V`/`C`/`X`**, la **selezione delle facce solo dal quadratino centrale**, il **Poly Count HUD**, lo **Smooth Preview (`1`/`2`/`3`)** o il supporto nativo per **macOS & Trackpad MacBook Pro** senza conflitti con Spotlight.

**Maya UX Pro** porta tutto questo in un'unica **Estensione Blender (`4.2 – 5.3+`)** modulare, gratuita, open-source e **reversibile al 100%**.

---

## Installazione Rapida (30 Secondi)

### Metodo A — Drag & Drop (Consigliato, Blender 4.2+)
1. Scarica **`maya_ux_pro-2.5.9.zip`** dall'[**Ultima Release GitHub**](https://github.com/GiorgioDeAngelis/maya-ux-pro-blender/releases/latest/download/maya_ux_pro-2.5.9.zip).
2. Apri Blender e **trascina il file `.zip`** direttamente dentro la finestra di Blender.
3. Premi **OK** nella finestra di conferma: l'estensione si attiva subito.

### Metodo B — Install from Disk
1. Scarica `maya_ux_pro-2.5.9.zip` dalle [Releases](https://github.com/GiorgioDeAngelis/maya-ux-pro-blender/releases/latest).
2. Apri **Edit → Preferences → Get Extensions** (menu `⌄` in alto a destra) → **Install from Disk...**.
3. Seleziona il file `.zip` e verifica che **Maya UX Pro** sia attivo.

### Configurazione Iniziale Consigliata (1-Click & Reversibile)
1. In **Preferences → Extensions / Add-ons → Maya UX Pro**, premi **Apply Maya Base Setup**:
   - Crea un backup JSON automatico (`maya_ux_pro_backup.json`) della tua configurazione originale di Blender (keymap, zoom, navigazione, snap, gizmo e tema).
   - Imposta *Industry Compatible* + navigazione Maya, zoom invertito (*indietro = avvicina*), *Rotate Around Selection*, *Zoom to Mouse* e interfaccia scura pulita a 3 pannelli.
   - Puoi tornare in qualsiasi momento al Blender originale con **Restore Previous Setup**.
2. *(Opzionale)* Premi **Save Clean Empty Startup File** per salvare una scena iniziale completamente vuota (`0` oggetti) e interfaccia pulita senza timeline inferiore.

---

## Tutte le Funzionalità Principali

| Funzionalità | Comportamento Maya in Blender |
|---|---|
| **Barra Spaziatrice & Hotbox** | **Tap `Space`**: alterna Quad View a 4 viste (riquadro in alto a destra sempre **Persp**) o massimizza/ripristina il pannello sotto il cursore (`Outliner`, `Properties`, `UV`, `Graph`, `Nodes`). **Hold `Space`** (`≥0.20s` o drag): apre la **Floating Maya Hotbox** a 5 zone. **`⌃+Space` / `Ctrl+Space`**: Expert Mode a tutto schermo (`⌘+Space` Spotlight protetto su macOS). |
| **Smart Middle Mouse (`MMB`)** | Su vuoto o con **`Q`** (Select): **MMB fa Pan**. Con **`W` / `E` / `R` / `T`** su **Oggetti o Vertici / Edge / Facce selezionati**: **MMB trasforma globalmente (o lungo l'ultimo asse)** — e con **`V+MMB`** / **`C+MMB`** fa snap al vertice o edge! |
| **Navigazione Maya & Trackpad** | Zoom invertito stile Maya (*trascini indietro = avvicini*), **`⌥+Click`** Orbit, **`MMB`** / **`⌥+⇧+Click`** Pan, **`⌥+RMB`** / **`⌥+⌃+Click`** Zoom, gesture Trackpad 2 dita + Pinch, **`[` / `]`** Undo/Redo camera. |
| **`Hold D` Edit Pivot & Snap** | Tieni premuto **`D`** per spostare il pivot (`D+V` snap a vertice, `D+C` a edge, `D+X` a griglia). Tieni **`X` / `C` / `V` / `J`** per snap temporaneo Griglia / Edge / Vertice / Step. **`⌥+D`** apre il Pivot Pie. |
| **Face Center-Only Selection** | Mostra il quadratino centrale (`show_face_center`, dimensione `5`) su tutte le facce in Face Mode e seleziona una faccia **solo cliccando sull'handle centrale** (`Click`, `⇧+Click` toggle, `⌃+Click` deseleziona). |
| **Poly Count & Subdiv HUD** | Contatore Maya in alto a sinistra nella viewport (**Scena \| Oggetti Selezionati \| Componenti Selezionati**) per `Verts`, `Edges`, `Faces`, `Tris`, `UVs` + livello e modalità Subdiv. Nasconde automaticamente le scritte sovrapposte di Blender (`User Perspective / Cube`). |
| **Top Shelf (4 Menu Set)** | Barra rapida nell'header della 3D Viewport con tab **`Display` \| `Poly` \| `Retopo` \| `LookDev`**, badge **`EDIT PIVOT`** e **`LIVE`**, e pulsante **`HUD`**. |
| **Retopo & Target Weld Pro** | **`Target Weld`** interattivo con anteprima GPU; **`Make Live`** + **`Quad Draw`** (Shrinkwrap + Mirror + Poly Build) + **`Relax`** + **`Bake`**. |
| **Smooth Mesh Preview (`1`/`2`/`3`)** | **`1`** gabbia grezza, **`2`** subdiv + gabbia, **`3`** smooth (`PgUp`/`PgDn` regola i livelli). |
| **CamTools Pro & LookDev** | **`Cam from View`**, Lock Camera, preset `24/35/50/85mm`, `Fix Clip`, DoF, Passepartout, Guide composizione, 4 Camera Bookmarks; materiali **`lambert1`**, **`blinn1`**, **`maya_clay`**, **`maya_chrome`**, **`maya_uv_checker`**, **`maya_glass`** + **`3-Point Studio Lights`**. |
| **Scena Vuota & UI Pulita** | Rimuove automaticamente `Cube`, `Camera` e `Light` su `File → New` e applica il layout pulito a 3 pannelli senza Timeline inferiore. |
| **Assi & I/O Maya Y-Up** | Mantiene la coerenza 1:1 Z-Up dentro Blender (`Transform`, Graph Editor, Modificatori) convertendo automaticamente in **Maya Y-Up** su Import/Export **FBX / OBJ / USD**. |

---

## Approfondimento sui Workflow Principali

### 1. Barra Spaziatrice Maya & Floating Hotbox
- **Tap `Space`** (`< 0.20s` senza trascinare):
  - Nella **3D Viewport**: entra in **Quad View** mantenendo il riquadro in alto a destra sempre in **Prospettiva (`PERSP`)**; da Quad View massimizza esattamente il quadrante sotto il cursore (ricordando la tua camera `Persp`).
  - Negli **altri editor** (`Outliner`, `Properties`, `UV/Image`, `Graph`, `Dopesheet`, `Node Editor`, `NLA`, `Sequencer`): massimizza o ripristina il pannello sotto il cursore.
  - Non interferisce mai quando scrivi in `Text Editor`, `Console` o campi di testo.
- **Hold `Space`** (`≥ 0.20s` o trascinando `≥ 14px`): apre la **Floating Maya Hotbox** a 5 zone (`File / Edit / Display`, `Modes & Retopo`, `Maya Views & Panes`, `Modeling & Pivot`, `Channel Box & Workspaces`).
- **`⌃ + Space` (`Ctrl + Space`)**: attiva/disattiva **Expert Mode** (tutto schermo senza pannelli), lasciando intatto **`⌘ + Space`** per Spotlight su macOS.

### 2. Middle Mouse (`MMB`) su Oggetti e Componenti
- **Nulla selezionato** o **`Q`** attivo: trascinare con **`MMB`** fa il **Pan**.
- **Oggetto selezionato o Vertici / Edge / Facce selezionati in Edit Mode** con **`W` / `E` / `R` / `T`**:
  - Trascinando con **`MMB`** ovunque nella viewport sposti / ruoti / scali globalmente o lungo l'ultimo asse toccato sul gizmo.
  - Con **`V + MMB`** agganci il pivot (o i componenti) ai vertici; con **`C + MMB`** agli edge.
  - Passando da Object Mode a Component Mode (`RMB` menu, Hotbox, `F8..F11`, `Tab`) lo strumento attivo (`W/E/R/T`) viene ereditato automaticamente finché non premi `Q`.

### 3. Selezione Face Center-Only & Poly Count HUD
- In **Face Mode** ogni faccia mostra il quadratino centrale (`facedot_size = 5`) e si seleziona **solo cliccando su quel quadratino** (`Click`, `⇧+Click`, `⌃+Click`), evitando selezioni accidentali di facce grandi o posteriori.
- Il **Poly Count HUD** in alto a sinistra mostra sempre i conteggi reali di scena, oggetti selezionati e componenti selezionati, nascondendo le scritte di Blender per una lettura pulita.
- Premendo **`?`** (o **`F1`**) apri in qualsiasi momento il pannello **Hotkey Reference** con ricerca istantanea di tutte le scorciatoie.

→ Vedi tutte le tabelle complete in **[docs/HOTKEYS.md](./docs/HOTKEYS.md)** e la guida dettagliata ai moduli in **[docs/FEATURES.md](./docs/FEATURES.md)**.

---

<a id="profili-piattaforma-macos--windowslinux"></a>

## Profili Piattaforma (`macOS` & `Windows/Linux`)

Maya UX Pro rileva automaticamente macOS o Windows/Linux (`AUTO`):
- **Profilo macOS**: etichette Apple (`⌥ Option`, `⌘ Cmd`, `⌃ Ctrl`, `⇧ Shift`, `⌫ Delete`), zero conflitti con le scorciatoie di sistema (`⌘+Space`, `⌘+Q`, `⌘+W`, `⌘+H`, `⌘+Tab`, `⌘+M`), alias ergonomici `⌥+1 / 2 / 3 / 4` per cambiare modalità senza tasti `Fn`, e navigazione completa anche da Trackpad MacBook Pro.
- **Profilo Windows / Linux**: scorciatoie classiche Maya `Alt` / `Ctrl` / `Shift`.

---

## FAQ & Risoluzione Problemi

<details>
<summary><strong>1. Come avvio il Play della timeline visto che Space apre Hotbox / Quad View?</strong></summary>

Come in Autodesk Maya, il Play/Stop della timeline è assegnato a **`⌥ + V`** (`Alt + V`), `⌥+⇧+V` per tornare al frame iniziale e `⌥+K` per AutoKey.
</details>

<details>
<summary><strong>2. Perché dentro Blender gli assi restano Z-Up in Item → Transform?</strong></summary>

Il kernel C++ di Blender è nativamente **Z-Up** (`Location Z` è sempre la quota verticale in Transform, Graph Editor e Modificatori). Come *Maya Config Pro* e *Industry Compatible*, mantenere Blender Z-Up internamente garantisce coerenza 1:1 senza errori, mentre importando ed esportando in **FBX / OBJ / USD** l'add-on converte automaticamente in **Maya Y-Up**.
</details>

<details>
<summary><strong>3. Come ripristino Blender alle impostazioni originali?</strong></summary>

Apri **Preferences → Extensions → Maya UX Pro** e clicca **Restore Previous Setup**, quindi disattiva o rimuovi l'estensione.
</details>

---

## Sviluppo, Build & Test

```bash
blender --command extension validate ./maya_ux_pro
blender --command extension build --source-dir ./maya_ux_pro --output-dir ./dist
blender --background --python-exit-code 1 --python ./tests/test_maya_ux_pro.py
```

Leggi [CONTRIBUTING.md](./CONTRIBUTING.md) per architettura e linee guida.

---

## Licenza

Distribuito con licenza open-source **[GNU General Public License v3.0 (GPL-3.0-or-later)](./LICENSE)**.
