# quest.py
# Widget: Active Quests
# Dynamické zobrazenie questov z data/quest.json podľa config/quest.json
# Autor: Jastronit (spolupráca s GPT-5)
# Verzia: 1.0 alpha

import os
import json
import html
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QScrollArea, QSizePolicy
from PySide6.QtCore import QMetaObject, Qt, QTimer
from PySide6.QtGui import QFont, QFontMetrics
from shortcut_manager import get_bridge
import time

# /////////////////////////////////////////////////////////////////////////////////////////////
# ////---- Default config ----////
# /////////////////////////////////////////////////////////////////////////////////////////////
DEFAULT_CONFIG = {
  "refresh_interval": 4,
  "time_simulation_duration": 120,
  "time_remaining_format": "%dd %hh %mm %ss",
  "font_family": "Consolas",
  "default_font_size": 8,

  # Token colors
  "token_colors": {
    "quest_count": "#ff8000",
    "id": "#ffff00",
    "sector": "#00ff00",
    "time_remaining": "dynamic",
    "filter_enabled": "#00ff00",
    "filter_active_sectors": "#00ff00",
    "sort_keys": "#ffff00",
    "sort_order": "#80ff80"
  },
  "time_remaining_colors": {
    "172800": "#00ff00",
    "86400": "#80ff80",
    "43200": "#ffff00",
    "21600": "#ffaa00",
    "14400": "#ff8000",
    "7200": "#ff4000",
    "3600": "#ff0000",
    "0": "#000000"
  },

  # Per-sector colors when sector is active (true) or inactive (false)
  # Example: "sector_token_colors": { "A0": {"true":"#00ff00","false":"#666666"}, ... }
  "sector_token_colors": {},

  # Header template
  "header": [
    {
      "font": "Comic Sans MS",
      "size": 16,
      "color": "#ffff00",
      "data": "🧭️ Active quests: %quest_count% "
    },
    {
      "font": "Consolas",
      "size": 8,
      "color": "#ffffff",
      "data": "Last sync: %timestamp%"
    },
    {
      "font": "Consolas",
      "size": 10,
      "color": "#ffffff",
      "data": "Sort: %sort_keys% (%sort_order%)"
    },
    {
      "font": "Consolas",
      "size": 10,
      "color": "#ffffff",
      "data": "Filter: %filter_enabled% Sectors: %filter_active_sectors%"
    }
  ],

  # Quest lines template
  "lines": [
    {
      "font": "Consolas",
      "size": 12,
      "color": "#ffffff",
      "data": "📜%id% 🗺️%sector% ⏱️ %time_remaining%"
    },
    {
      "font": "Consolas",
      "size": 8,
      "color": "#cccccc",
      "data": "Asset: %quest_data_asset_path%"
    },
    {
      "font": "Consolas",
      "size": 4,
      "color": "#ffffff",
      "data": "____________________________________________________________________________________________________________"
    }
  ],

  # Filter and Sort defaults
  "filter": {
    "enabled": True,
    "sectors": {
      "A0": True,
      "Z3": True,
      "B4": True,
      "C2": True
    }
  },
  "sort": {
    "keys": [
      "time_remaining"
    ],
    "order": "asc"
  },

  # Shortcuts (all fixed shortcuts moved here so user can remap)
  # NOTE: 'refresh' and 'sync' intentionally omitted — they previously caused issues.
  "shortcuts": {
    "toggle_filter": "ctrl+alt+f",
    "toggle_sector_A0": "ctrl+alt+a",
    "toggle_sector_Z3": "ctrl+alt+z",
    "toggle_sector_B4": "ctrl+alt+b",
    "toggle_sector_C2": "ctrl+alt+c",
    "sort_order_asc": "ctrl+alt+u",
    "sort_order_desc": "ctrl+alt+d",
    # three shortcuts for sort-key management
    "cycle_sort_key": "ctrl+alt+n",
    "add_sort_key": "ctrl+alt+m",
    "clear_sort_keys": "ctrl+alt+r"
  }
}

# Fixed list of possible sort keys (pevný slovník) used by shortcuts to cycle/add
SORT_KEY_OPTIONS = [
    "id",
    "sector",
    "time_remaining",
    "completion_deadline",
    "quest_data_asset_path",
    "auto_complete",
    "data"
]

# /////////////////////////////////////////////////////////////////////////////////////////////
# ////---- Pomocné funkcie ----////
# /////////////////////////////////////////////////////////////////////////////////////////////

# ////---- Zabezpečenie existencie adresára ----////
def ensure_dir(path):
    try:
        os.makedirs(path, exist_ok=True)
    except Exception:
        pass
# -----------------------------------------------------------------------------------------

# ////---- Normalizácia skratky ----////
def _normalize_combo(combo: str) -> str:
    """Normalize combo: remove spaces, lowercase and put modifiers in stable order."""
    if not combo:
        return ""
    s = combo.replace(" ", "").lower()
    parts = [p for p in s.split("+") if p]
    mods_order = ["ctrl", "alt", "shift"]
    mods = [p for p in parts if p in mods_order]
    others = [p for p in parts if p not in mods_order]
    ordered_mods = [m for m in mods_order if m in mods]
    return "+".join(ordered_mods + others)
# -----------------------------------------------------------------------------------------

# ////---- Získanie farby podľa zostávajúceho času ----////
def get_time_color(seconds_left, color_rules):
    """Vráti farbu podľa zostávajúceho času."""
    if not isinstance(color_rules, dict) or seconds_left is None:
        if isinstance(color_rules, dict) and "0" in color_rules:
            return color_rules.get("0", "#ffffff")
        return "#ffffff"
    try:
        keys = sorted([int(k) for k in color_rules.keys()])
        for k in keys:
            if seconds_left <= k:
                return color_rules[str(k)]
        return color_rules[str(keys[-1])] if keys else "#ffffff"
    except Exception:
        return "#ffffff"
# -----------------------------------------------------------------------------------------

# ////---- Formátovanie zostávajúceho času ----////
def format_time_remaining(seconds, fmt="%dd %hh %mm %ss"):
    """Prevedie sekundy na formátovaný reťazec s jednotkami."""
    if seconds is None:
        return "N/A"
    if seconds < 0:
        seconds = 0
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    return (
        fmt.replace("%dd", f"{days:02}d")
        .replace("%hh", f"{hours:02}h")
        .replace("%mm", f"{minutes:02}m")
        .replace("%ss", f"{secs:02}s")
        .replace("%d", f"{days:02}")
        .replace("%h", f"{hours:02}")
        .replace("%m", f"{minutes:02}")
        .replace("%s", f"{secs:02}")
    )
# -----------------------------------------------------------------------------------------

# ////---- Nahradenie tokenov v HTML riadku ----////
def replace_tokens_html(line_template, quest, globals_dict, cfg, remaining=None, line_color=None):
    token_colors = cfg.get("token_colors", {}) if isinstance(cfg, dict) else {}
    combined = {}
    if isinstance(quest, dict):
        combined.update(quest)
    if isinstance(globals_dict, dict):
        combined.update(globals_dict)

    out = html.escape(line_template)
    # Nahradzuje tokeny %token% farebne podľa konfigurácie
    for key, val in combined.items():
        raw_val = "" if val is None else str(val)
        safe_val = html.escape(raw_val).replace(" ", "&nbsp;")  # zachovanie medzier

        color = token_colors.get(key, None)
        # Dynamická farba pre time_remaining
        if color == "dynamic" and key == "time_remaining":
            color = get_time_color(remaining, cfg.get("time_remaining_colors", {}))

        # Speciálna logika pre sektor (farebné podľa aktivity)
        if key == "sector":
            sector_code = raw_val.upper() if raw_val else ""
            sector_colors = cfg.get("sector_token_colors", {}) or {}
            # Globálne aktívne sektory
            active_sectors = globals_dict.get("active_sectors") if isinstance(globals_dict, dict) else None
            if sector_code and sector_code in sector_colors:
                # Zvoľ farbu podľa aktivity sektora
                is_active = False
                try:
                    if isinstance(active_sectors, (set, list)):
                        is_active = sector_code in active_sectors
                    else:
                        # fallback: try to read from cfg.filter.sectors map
                        is_active = bool(cfg.get("filter", {}).get("sectors", {}).get(sector_code, False))
                except Exception:
                    is_active = False
                entry = sector_colors.get(sector_code, {}) or {}
                color = entry.get("true") if is_active else entry.get("false")
                # if not defined, fallback to token_colors['sector']
                if not color:
                    color = token_colors.get("sector")

        if color:
            colored_val = f'<span style="color:{color}">{safe_val}</span>'
        else:
            colored_val = safe_val
        out = out.replace(f"%{key}%", colored_val)

    if line_color:
        out = f'<span style="color:{line_color}">{out}</span>'
    return out

# ////---- Bezpečné čítanie JSON súboru ----////
def read_json_safe(path, default=None):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default
# -----------------------------------------------------------------------------------------

# /////////////////////////////////////////////////////////////////////////////////////////////
# ////---- Hlavná trieda widgetu ----////
# /////////////////////////////////////////////////////////////////////////////////////////////

def create_widget(BaseClass, module_name):
    class QuestWidget(BaseClass):
        def __init__(self):
            super().__init__(module_name)

            # Layout
            main_layout = QVBoxLayout()
            main_layout.setAlignment(Qt.AlignTop)

            # Scroll area
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

            self.scroll_area = scroll
            self.scroll_widget = QWidget()
            self.scroll_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            self.scroll_layout = QVBoxLayout(self.scroll_widget)
            self.scroll_layout.setAlignment(Qt.AlignTop)
            scroll.setWidget(self.scroll_widget)

            main_layout.addWidget(scroll)
            self.setLayout(main_layout)

            # Paths
            self._config_path = self.get_config_path("quest.json")
            self._data_path = self.get_data_path("quest.json")

            # State
            self._last_config_mtime = None
            self._last_data_mtime = None
            # load config with defaults merged
            self._config = DEFAULT_CONFIG.copy()
            user_cfg = read_json_safe(self._config_path, {}) or {}
            if isinstance(user_cfg, dict):
                # merge user cfg (user can override shortcuts etc.)
                self._config.update(user_cfg)
            # ensure filter/sort structure exists
            self._config.setdefault("filter", DEFAULT_CONFIG["filter"].copy())
            self._config.setdefault("sort", DEFAULT_CONFIG["sort"].copy())

            self._quests = []
            self._timestamp = None
            self._simulated_time = 0
            self._simulation_active = True

            # active sectors set (keeps current runtime state, initialised from config)
            self._active_sectors = set()
            self._load_active_sectors_from_config()

            self.timer = QTimer(self)
            self.timer.setInterval(1000)
            self.timer.timeout.connect(self._tick)
            QTimer.singleShot(0, self.timer.start)

            # Bridge support
            self.bridge = get_bridge()
            self._bridge_handlers = {}

            # Inicializácia
            self._ensure_config()
            # register shortcuts (including the fixed sector toggles)
            try:
                self._register_shortcuts()
            except Exception:
                pass
            self._load_data_json(force=True)
            self.schedule_render()

        # -------------------------------------------------------------------------------------
 
        # ////---- Zabezpečenie existencie config súboru ----////
        def _ensure_config(self):
            cfg_dir = os.path.dirname(self._config_path)
            ensure_dir(cfg_dir)
            if not os.path.exists(self._config_path):
                # write full default config if missing
                try:
                    with open(self._config_path, "w", encoding="utf-8") as f:
                        json.dump(self._config, f, indent=2, ensure_ascii=False)
                except Exception:
                    pass

        # -------------------------------------------------------------------------------------

        # ////---- Načítanie a aplikovanie config súboru ----////
        def _load_and_apply_config(self):
            try:
                mtime = os.path.getmtime(self._config_path)
            except Exception:
                mtime = None
            if mtime and mtime == self._last_config_mtime:
                return
            self._last_config_mtime = mtime

            # načítaj a aplikuj
            user_cfg = read_json_safe(self._config_path, {}) or {}
            if isinstance(user_cfg, dict):
                self._config.update(user_cfg)
            # ensure filter/sort structure exists
            self._config.setdefault("filter", DEFAULT_CONFIG["filter"].copy())
            self._config.setdefault("sort", DEFAULT_CONFIG["sort"].copy())
            # reload active sectors from config (in case external edit)
            self._load_active_sectors_from_config()
            # re-register shortcuts in case user changed them
            try:
                self._register_shortcuts()
            except Exception:
                pass
        # -------------------------------------------------------------------------------------

        # ////---- Načítanie aktívnych sektorov z configu ----////
        def _load_active_sectors_from_config(self):
            """Read filter.sectors map from config into runtime set _active_sectors."""
            try:
                filt = self._config.get("filter", {})
                sectors_map = filt.get("sectors", {})
                if isinstance(sectors_map, dict):
                    self._active_sectors = {k.upper() for k, v in sectors_map.items() if v}
                else:
                    self._active_sectors = set()
            except Exception:
                self._active_sectors = set()

        # -------------------------------------------------------------------------------------

        # ////---- Uloženie filtra do configu ----////
        def _save_filter_to_config(self):
            """Persist current filter.enabled and sectors map into config file."""
            try:
                current = read_json_safe(self._config_path, {}) or {}
                current.setdefault("filter", {})
                current["filter"].setdefault("sectors", {})
                # write enabled
                current["filter"]["enabled"] = bool(self._config.get("filter", {}).get("enabled", False))
                # write sectors map based on _active_sectors (we'll preserve other sector keys)
                sectors_map = current["filter"].get("sectors", {})
                if not isinstance(sectors_map, dict):
                    sectors_map = {}
                # update from existing keys and also any active ones
                for s in set(list(sectors_map.keys()) + list(self._active_sectors)):
                    sectors_map[s] = True if s in self._active_sectors else False
                current["filter"]["sectors"] = sectors_map
                # also save sort if present
                current.setdefault("sort", self._config.get("sort", DEFAULT_CONFIG["sort"]))
                ensure_dir(os.path.dirname(self._config_path))
                with open(self._config_path, "w", encoding="utf-8") as f:
                    json.dump(current, f, indent=2, ensure_ascii=False)
                # also update in-memory _config to reflect saved state
                self._config["filter"] = current["filter"]
                self._config["sort"] = current.get("sort", self._config.get("sort", DEFAULT_CONFIG["sort"]))
            except Exception as e:
                print("[QuestWidget] Error saving filter to config:", e)

        # -------------------------------------------------------------------------------------

        # ////---- Uloženie sortu do configu ----////
        def _save_sort_to_config(self):
            """Persist sort config into file."""
            try:
                current = read_json_safe(self._config_path, {}) or {}
                current.setdefault("filter", self._config.get("filter", {}))
                current["sort"] = self._config.get("sort", DEFAULT_CONFIG["sort"])
                ensure_dir(os.path.dirname(self._config_path))
                with open(self._config_path, "w", encoding="utf-8") as f:
                    json.dump(current, f, indent=2, ensure_ascii=False)
            except Exception as e:
                print("[QuestWidget] Error saving sort to config:", e)

        # -------------------------------------------------------------------------------------

        # ////---- Načítanie dát zo súboru config/quest.json ----////
        def _load_data_json(self, force=False):
            try:
                mtime = os.path.getmtime(self._data_path)
            except Exception:
                mtime = None

            if not force and mtime and mtime == self._last_data_mtime:
                return

            # update mtime
            self._last_data_mtime = mtime
            data = read_json_safe(self._data_path, {
                "user_profile_id": None,
                "timestamp": None,
                "quests": []
            })

            new_ts = data.get("timestamp", None)
            if new_ts != self._timestamp and new_ts is not None:
                self._timestamp = new_ts
                self._simulated_time = 0
                self._simulation_active = True

            self._quests = data.get("quests", []) or []

        # -------------------------------------------------------------------------------------

        # ////---- Tick handler ----////
        def _tick(self):
            """Každú sekundu simuluj čas a kontroluj zmeny."""
            self._simulated_time += 1
            duration = self._config.get("time_simulation_duration", 120)
            refresh_interval = self._config.get("refresh_interval", 2)

            # reload config ak sa zmenil on disk
            try:
                mtime = os.path.getmtime(self._config_path)
                if mtime != self._last_config_mtime:
                    self._load_and_apply_config()
            except Exception:
                pass

            if self._simulated_time >= duration:
                self._simulation_active = False

            if self._simulated_time % refresh_interval == 0:
                self._load_data_json()
            # Render only if widget is visible to avoid reparent/deletion race
            try:
                if self.isVisible():
                    self.schedule_render()
            except Exception as e:
                print("[QuestWidget] _tick render error:", e)

        # -------------------------------------------------------------------------------------

        # ////---- Naplánovanie renderu ----////
        def schedule_render(self):
            """Bezpečne naplánuje render v GUI thread-e, debounce."""
            if getattr(self, "_render_scheduled", False):
                return
            self._render_scheduled = True
            QTimer.singleShot(0, self._render_quests_safe)

        # ////---- Filter questov podľa konfigurácie a aktívnych sektorov ----////
        def _filter_quests(self, quests):
            """Filter questov podľa konfigurácie a aktívnych sektorov."""
            if not isinstance(quests, list):
                return []
            filt = self._config.get("filter", {})
            enabled = bool(filt.get("enabled", False))
            result = []
            for q in quests:
                include = True
                sec = str(q.get("sector", "")).upper()
                if enabled:
                    cfg_sectors = filt.get("sectors", {})
                    if isinstance(cfg_sectors, dict) and any(cfg_sectors.values()):
                        if sec not in self._active_sectors:
                            include = False
                    else:
                        pass
                if include:
                    result.append(q)
            return result
        # -------------------------------------------------------------------------------------

        # ////---- Sortovanie questov podľa konfigurácie ----////
        def _sort_quests(self, quests):
            """Sortovanie questov podľa multi-key konfigurácie."""
            sort_cfg = self._config.get("sort", {}) or {}
            keys = sort_cfg.get("keys", [])
            if isinstance(keys, str):
                keys = [keys]
            if not keys:
                return quests
            order_asc = sort_cfg.get("order", "asc").lower() == "asc"

            def sort_value(q, key):
                if key == "time_remaining":
                    completion = q.get("completion_deadline", 0) or 0
                    current_ts = (self._timestamp + self._simulated_time) if self._timestamp else 0
                    try:
                        return int(completion) - int(current_ts)
                    except Exception:
                        return 0
                val = q.get(key, "")
                try:
                    return float(val)
                except Exception:
                    return str(val).lower()
            try:
                return sorted(quests, key=lambda q: tuple(sort_value(q, k) for k in keys), reverse=not order_asc)
            except Exception as e:
                print("[QuestWidget] sort error:", e)
                return quests
        # -------------------------------------------------------------------------------------

        # ////---- Bezpečný render questov ----////
        def _render_quests_safe(self):
            """Bezpečný render questov so zachovaním headerov, času a farieb."""
            try:
                cfg = self._config
                quests = self._quests or []
                # apply filter and sort BEFORE calculating required labels
                quests = self._filter_quests(quests)
                quests = self._sort_quests(quests)

                quest_count = len(quests)

                if self._timestamp is not None and self._simulation_active:
                    current_ts = self._timestamp + self._simulated_time
                else:
                    current_ts = self._timestamp

                # prepare globals for tokens (include filter/sort tokens)
                globals_dict = {
                    "quest_count": quest_count,
                    "timestamp": current_ts,
                    "filter_enabled": str(bool(cfg.get("filter", {}).get("enabled", False))),
                    "filter_active_sectors": ", ".join(sorted(list(self._active_sectors))) if self._active_sectors else "ALL",
                    "sort_keys": ", ".join(cfg.get("sort", {}).get("keys", [])) if cfg.get("sort", {}).get("keys") else "",
                    "sort_order": cfg.get("sort", {}).get("order", "")
                }

                # pass active sectors to token replacer so it can choose sector colors dynamically
                globals_dict["active_sectors"] = self._active_sectors

                header_cfg = cfg.get("header", [])
                lines_cfg = cfg.get("lines", [])
                lines_per_quest = len(lines_cfg) if lines_cfg else 1
                required_labels = max(1, len(header_cfg) + len(quests) * lines_per_quest)

                if not hasattr(self, "_quest_labels"):
                    self._quest_labels = []

                # Vytvor labely, ak chýbajú
                while len(self._quest_labels) < required_labels:
                    lbl = QLabel(parent=self.scroll_widget)
                    lbl.setTextFormat(Qt.RichText)
                    lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
                    lbl.setWordWrap(True)
                    self.scroll_layout.addWidget(lbl)
                    self._quest_labels.append(lbl)

                # Schovaj prebytočné labely
                for i in range(required_labels, len(self._quest_labels)):
                    self._quest_labels[i].hide()

                idx = 0

                # HEADER render
                for line in header_cfg:
                    if idx >= len(self._quest_labels):
                        break
                    lbl = self._quest_labels[idx]
                    raw = line.get("data", "")
                    html_text = replace_tokens_html(raw, {}, globals_dict, cfg, remaining=None, line_color=line.get("color"))
                    font = QFont(line.get("font", cfg.get("font_family", "Consolas")), int(line.get("size", cfg.get("default_font_size", 10))))
                    lbl.setFont(font)
                    lbl.setText(html_text)
                    fm = QFontMetrics(font)
                    lbl.setMinimumHeight(fm.height() + 4)
                    lbl.show()
                    idx += 1

                # QUESTS render
                for quest in quests:
                    completion = quest.get("completion_deadline", 0) or 0
                    remaining = int(completion - current_ts) if current_ts else 0
                    quest["time_remaining"] = format_time_remaining(remaining, cfg.get("time_remaining_format", "%dd %hh %mm %ss"))
                    render_globals = dict(globals_dict)
                    render_globals.update(quest.get("globals", {}))

                    for line in lines_cfg:
                        if idx >= len(self._quest_labels):
                            break
                        lbl = self._quest_labels[idx]
                        raw = line.get("data", "")
                        html_text = replace_tokens_html(raw, quest, render_globals, cfg, remaining=remaining, line_color=line.get("color"))
                        font = QFont(line.get("font", cfg.get("font_family", "Consolas")), int(line.get("size", cfg.get("default_font_size", 10))))
                        lbl.setFont(font)
                        fm = QFontMetrics(font)
                        lbl.setMinimumHeight(fm.height() + 4)
                        lbl.setText(html_text)
                        lbl.show()
                        idx += 1

                # Placeholder pre žiadne questy
                if quest_count == 0:
                    lbl = self._quest_labels[1]  # after header
                    lbl.setText("<font color='#888888'><i>Žiadne aktívne questy</i></font>")
                    font = QFont(cfg.get("font_family", "Consolas"), int(cfg.get("default_font_size", 10)))
                    lbl.setFont(font)
                    fm = QFontMetrics(font)
                    lbl.setMinimumHeight(fm.height() + 4)
                    lbl.show()

                # Adjust scroll area podľa obsahu (zabráni deformácii)
                self.scroll_widget.adjustSize()

            except Exception as e:
                print(f"[QuestWidget] Render error: {e}")
            finally:
                self._render_scheduled = False
        # -------------------------------------------------------------------------------------

        # ////---- Registrácia skratiek do bridge ----////
        # Ide o registráciu všetkých skratiek z configu do bridge s bezpečnými lambda funkciami bez argumentov.
        def _register_shortcuts(self):
            try:
                # Odregistrovať staré (použije presný event-name s prefixom "shortcut.")
                for combo_norm, handler in list(self._bridge_handlers.items()):
                    try:
                        self.bridge.off(f"shortcut.{combo_norm}", handler)
                    except Exception:
                        pass
            except Exception:
                pass
            self._bridge_handlers.clear()

            # Registrovať nové
            shortcuts = self._config.get("shortcuts", {}) or {}
            for action, combo in shortcuts.items():
                combo_norm = _normalize_combo(combo)
                event_name = f"shortcut.{combo_norm}"

                def make_handler(act, combo_norm_local):
                    # zero-arg closure; bridge will call it from its thread — our handler must be safe
                    return lambda act=act, combo_norm=combo_norm_local: self._on_shortcut_triggered(act, combo_norm)

                # Vytvoriť handler s uzáverom pre action a combo_norm
                handler = make_handler(action, combo_norm)
                self.bridge.on(event_name, handler)
                self._bridge_handlers[combo_norm] = handler
                # print(f"[QuestWidget] Registered shortcut: {action} -> {event_name}")
        # -------------------------------------------------------------------------------------

        # ////---- Spracovanie spustenej skratky ----////
        def _on_shortcut_triggered(self, action_name: str, combo_norm: str):
            # -------------------------------------------------------------------------------------
            # Tento handler môže byť volaný z iného threadu (bridge worker thread),
            # preto musí byť thread-safe a nesmie priamo meniť GUI prvky.
            # Všetky zmeny stavu a render musia byť naplánované do GUI thread-u.
            # -------------------------------------------------------------------------------------
            try:
                cfg = self._config

                # --- Filter toggle ---
                if action_name == "toggle_filter":
                    cfg["filter"]["enabled"] = not cfg["filter"].get("enabled", False)

                # --- Sector toggle ---
                elif action_name.startswith("toggle_sector_"):
                    sector_code = action_name.replace("toggle_sector_", "").upper()
                    sectors = cfg.setdefault("filter", {}).setdefault("sectors", {})
                    sectors[sector_code] = not sectors.get(sector_code, False)

                # Prepínanie aktívnych sektorov v runtime stave
                elif action_name == "sort_order_asc":
                    cfg.setdefault("sort", {})["order"] = "asc"
                elif action_name == "sort_order_desc":
                    cfg.setdefault("sort", {})["order"] = "desc"

                # Cyklické prepínanie posledného sort kľúča
                elif action_name == "cycle_sort_key":
                    keys = cfg.setdefault("sort", {}).get("keys", [])
                    
                    if keys:  # Ak je v zozname nejaký kľúč
                        last_idx = len(keys) - 1  # Získaj index posledného kľúča
                        last_key = keys[last_idx]  # Získaj posledný kľúč
                        
                        # Zisti index posledného kľúča v SORT_KEY_OPTIONS
                        idx = SORT_KEY_OPTIONS.index(last_key) if last_key in SORT_KEY_OPTIONS else -1
                        
                        # Uprav posledný kľúč (cyklicky prepni)
                        keys[last_idx] = SORT_KEY_OPTIONS[(idx + 1) % len(SORT_KEY_OPTIONS)]
                    else:
                        # Ak nie sú žiadne kľúče, pridaj prvý kľúč
                        keys.append(SORT_KEY_OPTIONS[0])
                    
                    # Ulož kľúče do konfigurácie
                    cfg["sort"]["keys"] = keys

                # Pridanie sort kľúča
                elif action_name == "add_sort_key":
                    keys = cfg.setdefault("sort", {}).get("keys", [])
                    for k in SORT_KEY_OPTIONS:
                        if k not in keys:
                            keys.append(k)
                            break
                    cfg["sort"]["keys"] = keys

                # Vymazanie všetkých sort kľúčov okrem prvého
                elif action_name == "clear_sort_keys":
                    keys = cfg.setdefault("sort", {}).get("keys", [])
                    if len(keys) > 1:
                        cfg["sort"]["keys"] = [keys[0]]

                else:
                    # neznáma skratka
                    return

                # Uloženie zmien do configu
                #self._save_filter_to_config()
                #self._save_sort_to_config()
                self._save_config()

                # Bezpečne (queued) zaktualizujeme runtime stav a naplánujeme render v GUI vlákne.
                # Používame QMetaObject.invokeMethod s Qt.QueuedConnection, aby sa volanie
                # vykonalo v thread-e objektu (GUI thread) a nevyvolalo thread-related varovania.
                try:
                    QMetaObject.invokeMethod(self, "_load_active_sectors_from_config", Qt.QueuedConnection)
                except Exception:
                    # fallback: ignoruj
                    pass
                try:
                    QMetaObject.invokeMethod(self, "schedule_render", Qt.QueuedConnection)
                except Exception:
                    pass
                # (takto bude reload/render bezpečný aj keď bridge volá handler z worker threadu)
            except Exception as e:
                print(f"[QuestWidget] _on_shortcut_triggered error ({action_name}): {e}")
            # -------------------------------------------------------------------------------------

        def _save_config(self):
            """Uloží filter aj sort do config súboru naraz."""
            try:
                current = read_json_safe(self._config_path, {}) or {}
                current["filter"] = self._config.get("filter", DEFAULT_CONFIG["filter"])
                current["sort"] = self._config.get("sort", DEFAULT_CONFIG["sort"])
                ensure_dir(os.path.dirname(self._config_path))
                with open(self._config_path, "w", encoding="utf-8") as f:
                    json.dump(current, f, indent=2, ensure_ascii=False)
            except Exception as e:
                print("[QuestWidget] Error saving config:", e)

        # ////---- Uzavretie widgetu ----////
        def close_widget(self):
            try:
                self.timer.stop()
            except Exception:
                pass
            # Odregistrovať skratky z bridge
            try:
                # Prebehne každú registrovanú skratku
                for combo_norm, handler in list(self._bridge_handlers.items()):
                    try:
                        # IMPORTANT: use same event name format used in registration
                        self.bridge.off(f"shortcut.{combo_norm}", handler)
                    except Exception:
                        pass
            except Exception:
                pass
            self._bridge_handlers.clear()

    return QuestWidget()

# --------------------------------------------------------------------------------------------
def get_widget_dock_position():
    return Qt.LeftDockWidgetArea, 1
