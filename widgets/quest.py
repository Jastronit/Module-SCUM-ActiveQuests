# quest_widget_qtextbrowser.py
# PAGINATION VERSION: Fixed - proper pagination without dynamic sizing
# Author: Assistant

import os
import json
import html
import re
import copy
import time
from PySide6.QtWidgets import QWidget, QVBoxLayout, QTextBrowser, QSizePolicy, QApplication
from PySide6.QtCore import Qt, QTimer, QMutex, QMutexLocker, QThread, QMetaObject
from PySide6.QtGui import QFont
from shortcut_manager import get_bridge

# ---------- Helper functions ----------

def ensure_dir(path):
    try:
        os.makedirs(path, exist_ok=True)
    except Exception:
        pass


def read_json_safe(path, default=None):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def format_time_remaining(seconds, fmt="%dd %hh %mm %ss"):
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


def get_time_color(seconds_left, color_rules):
    try:
        keys = sorted([int(k) for k in color_rules.keys()], reverse=True)
        for k in keys:
            if seconds_left >= k:
                return color_rules[str(k)]
        return color_rules[str(keys[-1])] if keys else "#ffffff"
    except Exception:
        return "#ffffff"


def load_translations(widget):
    try:
        if hasattr(widget, 'get_cached_translations'):
            return widget.get_cached_translations()
        
        base_path = getattr(widget, "_data_path", None)
        if not base_path:
            return {}
        folder = os.path.dirname(base_path)
        translate_path = os.path.join(folder, "translate.json")

        if not os.path.exists(translate_path):
            return {}

        with open(translate_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("quests", {}) if isinstance(data, dict) else {}
    except Exception:
        return {}


def merge_quest_texts(widget, combined, language="en"):
    quest_id = combined.get("quest_data_asset_path")
    if not quest_id:
        return {}

    base = quest_id.replace("QuestSetup:", "")
    parts = base.split("_")

    tier = parts[0] if len(parts) > 0 else ""
    shop = parts[1] if len(parts) > 1 else ""
    raw_name = "_".join(parts[2:]) if len(parts) > 2 else ""
    fallback_name = raw_name.replace("_", " ").strip()

    result = {
        "tier": tier,
        "shop": shop,
        "name": fallback_name,
        "description": "",
        "requirements": "",
        "rewards": "",
        "req_data": {}
    }

    translations = load_translations(widget)
    entry = translations.get(quest_id, {}) if isinstance(translations, dict) else {}

    if entry:
        if isinstance(entry.get("name"), dict):
            result["name"] = entry["name"].get(language, fallback_name)
        else:
            if isinstance(entry.get("name"), str):
                result["name"] = entry.get("name")

        desc_val = entry.get("description")
        if isinstance(desc_val, dict):
            result["description"] = desc_val.get(language, "")
        elif isinstance(desc_val, str):
            result["description"] = desc_val

        if isinstance(entry.get("requirements"), dict):
            result["requirements"] = entry["requirements"].get(language, "")
        elif isinstance(entry.get("requirements"), str):
            result["requirements"] = entry.get("requirements")

        if isinstance(entry.get("rewards"), dict):
            result["rewards"] = entry["rewards"].get(language, "")
        elif isinstance(entry.get("rewards"), str):
            result["rewards"] = entry.get("rewards")

        if isinstance(entry.get("translate_data"), dict):
            result["req_data"] = entry.get("translate_data")

    return result


def apply_translation(quest, translations, language="en"):
    if not isinstance(quest, dict):
        return quest
    q_key = quest.get("quest_key") or quest.get("id")
    entry = translations.get(q_key, {}) if translations else {}

    for key in ["name", "description", "requirements", "rewards"]:
        if key in entry:
            val = entry[key].get(language) if isinstance(entry[key], dict) else entry[key]
            if val:
                quest[key] = val

    if "tier" in entry:
        quest.setdefault("tier", entry.get("tier"))
    if "rewards" in entry:
        quest.setdefault("rewards", entry.get("rewards"))
    if "req_data" in entry:
        quest.setdefault("req_data", entry.get("req_data"))

    return quest


def replace_tokens_html_simple(template: str, combined: dict, globals_dict: dict, cfg: dict, remaining=None, line_color=None):
    token_colors = cfg.get("token_colors", {}) if isinstance(cfg, dict) else {}
    out = html.escape(template)

    out = out.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br>")

    flat = {}
    if isinstance(globals_dict, dict):
        flat.update(globals_dict)
    if isinstance(combined, dict):
        flat.update(combined)

    widget_instance = cfg.get("widget_instance") if isinstance(cfg, dict) else None
    if widget_instance and "quest_data_asset_path" in flat:
        try:
            quest_texts = {}
            if hasattr(widget_instance, "get_quest_texts"):
                quest_texts = widget_instance.get_quest_texts(flat.get("quest_data_asset_path"), language=cfg.get("language", "en")) or {}
            else:
                quest_texts = merge_quest_texts(widget_instance, flat, language=cfg.get("language", "en"))
            if isinstance(quest_texts, dict):
                for k, v in quest_texts.items():
                    if k not in flat or not flat.get(k):
                        flat[k] = v
        except Exception:
            pass

    if "time_remaining" in flat and remaining is not None:
        flat["time_remaining_seconds"] = remaining

    for key, val in list(flat.items()):
        token = f"%{key}%"
        if token in out:
            if key == "req_data" and isinstance(val, dict):
                quest_data_key = flat.get("data", "")
                
                matched_value = None
                
                if quest_data_key in val:
                    matched_value = val[quest_data_key]
                
                if matched_value is None and quest_data_key:
                    best_match_key = None
                    best_match_length = 0
                    
                    for translate_key in val.keys():
                        if quest_data_key.startswith(translate_key):
                            if len(translate_key) > best_match_length:
                                best_match_key = translate_key
                                best_match_length = len(translate_key)
                    
                    if best_match_key:
                        matched_value = val[best_match_key]
                
                if matched_value:
                    val = matched_value
                    if isinstance(val, str):
                        for sub_key, sub_val in flat.items():
                            token2 = f"%{sub_key}%"
                            if token2 in val:
                                val = val.replace(token2, str(sub_val))
                else:
                    val = quest_data_key if quest_data_key else ""
            
            elif key in ["rewards", "requirements"] and isinstance(val, str):
                for sub_key, sub_val in flat.items():
                    token2 = f"%{sub_key}%"
                    if token2 in val:
                        val = val.replace(token2, str(sub_val))

            raw_val = "" if val is None else str(val)
            safe = html.escape(raw_val)
            safe = safe.replace("&lt;br&gt;", "<br>")

            color = token_colors.get(key)
            if color == "dynamic" and key == "time_remaining":
                color = get_time_color(int(remaining or 0), cfg.get("time_remaining_colors", {}))

            if color:
                safe = f"<span style=\"color:{color};\">{safe}</span>"

            out = out.replace(token, safe)

    if line_color:
        out = f'<span style="color:{line_color};">{out}</span>'

    out = out.replace('&amp;#37;', '%')

    return out

def _normalize_combo(combo: str) -> str:
    if not combo:
        return ""
    s = combo.replace(" ", "").lower()
    parts = [p for p in s.split("+") if p]
    return "+".join(parts)


# ---------- Default config ----------

DEFAULT_CONFIG = {
    "refresh_interval": 4,
    "time_simulation_duration": 120,
    "time_remaining_format": "%dd %hh %mm %ss",
    "font_family": "Consolas",
    "default_font_size": 8,
    "page_size": 10,
    "token_colors": {},
    "time_remaining_colors": {},
    "header": [],
    "lines": [],
    "filter": {"enabled": True, "sectors": {}},
    "sort": {"keys": ["time_remaining"], "order": "asc"},
    "display": {},
    "shortcuts": {}
}

SORT_KEY_OPTIONS = [
    "id",
    "tier",
    "sector",
    "shop",
    "time_remaining",
    "sort_name"
]

DISPLAY_TOGGLE_OPTIONS = [
    "show_name",
    "show_description",
    "show_requirements",
    "show_rewards",
    "show_data"
]


# ---------- Main widget ----------

def create_widget(BaseClass, module_name):
    class QuestWidget(BaseClass):
        def __init__(self):
            super().__init__(module_name)

            self._render_mutex = QMutex()
            self._is_closing = False

            main_layout = QVBoxLayout()
            main_layout.setAlignment(Qt.AlignTop)

            self.text_browser = QTextBrowser()
            self.text_browser.setReadOnly(True)
            self.text_browser.setOpenExternalLinks(False)
            self.text_browser.setStyleSheet("background: transparent; border: none; padding: 6px;")
            # Dynamic sizing - shrinks to content size (like original)
            self.text_browser.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
            self.text_browser.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            self.text_browser.setMinimumHeight(0)

            main_layout.addWidget(self.text_browser)
            self.setLayout(main_layout)

            # Paths
            self._config_path = self.get_config_path("quest.json")
            self._data_path = self.get_data_path("quest.json")

            # State
            self._last_config_mtime = None
            self._last_data_mtime = None
            self._config = DEFAULT_CONFIG.copy()

            # OPTIMIZATION: Cache translations at startup
            self._translations_cache = None
            self._translations_mtime = None

            # Load user config
            self._ensure_config()
            user_cfg = read_json_safe(self._config_path, {}) or {}
            if isinstance(user_cfg, dict):
                self._config.update(user_cfg)
            
            self._config.setdefault("filter", DEFAULT_CONFIG["filter"].copy())
            self._config.setdefault("sort", DEFAULT_CONFIG["sort"].copy())

            # Pagination state - load from config
            self._page_size = self._config.get("page_size", 10)
            self._current_page = 0

            self._quests = []
            self._timestamp = None
            self._simulated_time = 0
            self._simulation_active = True

            self._active_sectors = set()
            self._load_active_sectors_from_config()
            
            self._active_shops = set()
            self._load_active_shops_from_config()

            self._last_html = None
            self._last_render_time = 0.0
            self._render_debounce_interval = 0.5

            self._pending_actions = []
            self._actions_lock = QMutex()

            self.timer = QTimer(self)
            self.timer.setInterval(1000)
            self.timer.timeout.connect(self._tick)

            self.bridge = get_bridge()
            self._bridge_handlers = {}

            try:
                self._register_shortcuts()
            except Exception:
                pass

            self._load_data_json(force=True)
            self._preload_translations()

            QTimer.singleShot(0, self.timer.start)
            QTimer.singleShot(100, self.schedule_render)

        def set_background(self, rgba_str):
            """Set background color for QTextBrowser."""
            try:
                self.text_browser.setStyleSheet(f"""
                    QTextBrowser {{
                        background-color: {rgba_str};
                        border: none;
                        padding: 6px;
                    }}
                """)
                self.text_browser.viewport().setStyleSheet(f"background-color: {rgba_str};")
            except Exception as e:
                print(f"[QuestWidget] Error setting background: {e}")

        def _preload_translations(self):
            try:
                folder = os.path.dirname(self._data_path)
                translate_path = os.path.join(folder, "translate.json")
                
                if not os.path.exists(translate_path):
                    self._translations_cache = {}
                    return
                
                self._translations_mtime = os.path.getmtime(translate_path)
                with open(translate_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._translations_cache = data.get("quests", {}) if isinstance(data, dict) else {}
            except Exception:
                self._translations_cache = {}

        def get_cached_translations(self):
            try:
                folder = os.path.dirname(self._data_path)
                translate_path = os.path.join(folder, "translate.json")
                
                if not os.path.exists(translate_path):
                    return {}
                
                current_mtime = os.path.getmtime(translate_path)
                if current_mtime != self._translations_mtime:
                    self._preload_translations()
                
                return self._translations_cache
            except Exception:
                return self._translations_cache or {}

        def _ensure_config(self):
            cfg_dir = os.path.dirname(self._config_path)
            ensure_dir(cfg_dir)
            if not os.path.exists(self._config_path):
                try:
                    with open(self._config_path, "w", encoding="utf-8") as f:
                        json.dump(DEFAULT_CONFIG, f, indent=2, ensure_ascii=False)
                except Exception:
                    pass

        def _load_and_apply_config(self):
            try:
                mtime = os.path.getmtime(self._config_path)
            except Exception:
                mtime = None
            
            if mtime and mtime == self._last_config_mtime:
                return
            
            self._last_config_mtime = mtime

            user_cfg = read_json_safe(self._config_path, {}) or {}
            if isinstance(user_cfg, dict):
                self._config.update(user_cfg)
            
            self._config.setdefault("filter", DEFAULT_CONFIG["filter"].copy())
            self._config.setdefault("sort", DEFAULT_CONFIG["sort"].copy())
            
            # Update page size if changed in config
            self._page_size = self._config.get("page_size", 10)
            
            self._load_active_sectors_from_config()
            self._load_active_shops_from_config()
            
            try:
                self._register_shortcuts()
            except Exception:
                pass

        def _load_active_sectors_from_config(self):
            try:
                filt = self._config.get("filter", {})
                sectors_map = filt.get("sectors", {})
                if isinstance(sectors_map, dict):
                    self._active_sectors = {k.upper() for k, v in sectors_map.items() if v}
                else:
                    self._active_sectors = set()
            except Exception:
                self._active_sectors = set()

        def _load_active_shops_from_config(self):
            try:
                filt = self._config.get("filter", {})
                shops_map = filt.get("shops", {})
                if isinstance(shops_map, dict):
                    self._active_shops = {k.upper() for k, v in shops_map.items() if v}
                else:
                    self._active_shops = set()
            except Exception:
                self._active_shops = set()

        def _save_filter_to_config(self):
            try:
                current = read_json_safe(self._config_path, {}) or {}
                current.setdefault("filter", {})
                current["filter"].setdefault("sectors", {})
                current["filter"].setdefault("shops", {})
                current["filter"]["enabled"] = bool(self._config.get("filter", {}).get("enabled", False))
                
                sectors_map = current["filter"].get("sectors", {})
                if not isinstance(sectors_map, dict):
                    sectors_map = {}
                
                for s in set(list(sectors_map.keys()) + list(self._active_sectors)):
                    sectors_map[s] = True if s in self._active_sectors else False
                
                current["filter"]["sectors"] = sectors_map
                
                shops_map = current["filter"].get("shops", {})
                if not isinstance(shops_map, dict):
                    shops_map = {}
                
                for s in set(list(shops_map.keys()) + list(self._active_shops)):
                    shops_map[s] = True if s in self._active_shops else False
                
                current["filter"]["shops"] = shops_map
                current.setdefault("sort", self._config.get("sort", DEFAULT_CONFIG["sort"]))
                
                ensure_dir(os.path.dirname(self._config_path))
                with open(self._config_path, "w", encoding="utf-8") as f:
                    json.dump(current, f, indent=2, ensure_ascii=False)
                
                self._config["filter"] = current["filter"]
                self._config["sort"] = current.get("sort", self._config.get("sort", DEFAULT_CONFIG["sort"]))
            except Exception as e:
                print("[QuestWidget] Error saving filter to config:", e)

        def _save_sort_to_config(self):
            try:
                current = read_json_safe(self._config_path, {}) or {}
                current["sort"] = self._config.get("sort", DEFAULT_CONFIG["sort"])
                
                ensure_dir(os.path.dirname(self._config_path))
                with open(self._config_path, "w", encoding="utf-8") as f:
                    json.dump(current, f, indent=2, ensure_ascii=False)
                
                print(f"[QuestWidget] Saved sort to config: {current['sort']}")
            except Exception as e:
                print("[QuestWidget] Error saving sort to config:", e)

        def _save_display_to_config(self):
            try:
                current = read_json_safe(self._config_path, {}) or {}
                current["display"] = self._config.get("display", DEFAULT_CONFIG.get("display", {}))
                
                ensure_dir(os.path.dirname(self._config_path))
                with open(self._config_path, "w", encoding="utf-8") as f:
                    json.dump(current, f, indent=2, ensure_ascii=False)
                
                print(f"[QuestWidget] Saved display to config: {current['display']}")
            except Exception as e:
                print("[QuestWidget] Error saving display to config:", e)

        def _save_page_config(self):
            """Save page_size to config."""
            try:
                current = read_json_safe(self._config_path, {}) or {}
                current["page_size"] = self._page_size
                ensure_dir(os.path.dirname(self._config_path))
                with open(self._config_path, "w", encoding="utf-8") as f:
                    json.dump(current, f, indent=2, ensure_ascii=False)
                print(f"[QuestWidget] Saved page_size to config: {self._page_size}")
            except Exception as e:
                print(f"[QuestWidget] Error saving page config: {e}")

        def _load_data_json(self, force=False):
            try:
                mtime = os.path.getmtime(self._data_path)
            except Exception:
                mtime = None

            if not force and mtime and mtime == self._last_data_mtime:
                return

            self._last_data_mtime = mtime
            data = read_json_safe(self._data_path, {"user_profile_id": None, "timestamp": None, "quests": []})
            if not data:
                data = {"user_profile_id": None, "timestamp": None, "quests": []}

            new_ts = data.get("timestamp", None)
            if new_ts != self._timestamp and new_ts is not None:
                self._timestamp = new_ts
                self._simulated_time = 0
                self._simulation_active = True

            self._quests = data.get("quests", []) or []

            for q in self._quests:
                ap = q.get("quest_data_asset_path", "")
                if ap and ":" in ap:
                    try:
                        _, raw = ap.split(":", 1)
                        parts = raw.split("_")
                        if len(parts) >= 3:
                            q["tier"] = parts[0]
                            q["shop"] = parts[1]
                            q["sort_name"] = " ".join(parts[2:]).replace("_", " ")
                        else:
                            q.setdefault("tier", "")
                            q.setdefault("shop", "")
                            q.setdefault("sort_name", raw)
                    except Exception:
                        q.setdefault("tier", "")
                        q.setdefault("shop", "")
                        q.setdefault("sort_name", ap)

        def _tick(self):
            if self._is_closing:
                return

            self._simulated_time += 1
            duration = self._config.get("time_simulation_duration", 120)
            refresh_interval = self._config.get("refresh_interval", 2)

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

            try:
                if not self._is_closing and self.isVisible():
                    self.schedule_render()
            except Exception:
                pass

        def schedule_render(self):
            if self._is_closing:
                return
            try:
                current_thread = QThread.currentThread()
                gui_thread = QApplication.instance().thread()

                if current_thread != gui_thread:
                    QMetaObject.invokeMethod(self, "_schedule_render_internal", Qt.QueuedConnection)
                    return

                self._schedule_render_internal()
            except Exception:
                pass

        def _schedule_render_internal(self):
            if self._is_closing:
                return
            
            now = time.time()
            time_since_last = now - self._last_render_time
            
            if time_since_last < self._render_debounce_interval:
                remaining = self._render_debounce_interval - time_since_last
                QTimer.singleShot(int(remaining * 1000), self._render_quests_safe)
            else:
                QTimer.singleShot(0, self._render_quests_safe)

        def _filter_quests(self, quests):
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
                
                shop = str(q.get("shop", "")).upper()
                if enabled and include:
                    cfg_shops = filt.get("shops", {})
                    if isinstance(cfg_shops, dict) and any(cfg_shops.values()):
                        if shop not in self._active_shops:
                            include = False
                
                if include:
                    result.append(q)
            return result

        def _sort_quests(self, quests):
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
            except Exception:
                return quests

        def _generate_full_html(self, quests, current_ts):
            cfg = self._config
            header_cfg = cfg.get("header", [])
            lines_cfg = cfg.get("lines", [])
            display_cfg = cfg.get("display", {})
            if "auto_complete" not in display_cfg and "show_data" in display_cfg:
                display_cfg["auto_complete"] = display_cfg.get("show_data", True)

            parts = []
            base_font = cfg.get("font_family", "Consolas")
            base_size = cfg.get("default_font_size", 10)

            parts.append(f"<div style='font-family: {base_font}; font-size: {base_size}pt; color: #ffffff;'>")

            # Pagination info
            total_quests = len(quests)
            total_pages = max(1, (total_quests + self._page_size - 1) // self._page_size)
            current_page_display = min(self._current_page + 1, total_pages)

            globals_dict = {
                "quest_count": total_quests,
                "timestamp": current_ts,
                "filter_enabled": str(bool(cfg.get("filter", {}).get("enabled", False))),
                "filter_active_sectors": ", ".join(sorted(list(self._active_sectors))) if self._active_sectors else "ALL",
                "filter_active_shops": ", ".join(sorted(list(self._active_shops))) if self._active_shops else "ALL",
                "sort_keys": ", ".join(cfg.get("sort", {}).get("keys", [])) if cfg.get("sort", {}).get("keys") else "",
                "sort_order": cfg.get("sort", {}).get("order", ""),
                "page_size": self._page_size,
                "current_page": current_page_display,
                "total_pages": total_pages,
                "page_info": f"Page {current_page_display}/{total_pages} ({self._page_size}/page)",
                "display_name": "✓" if display_cfg.get("show_name", True) else "✗",
                "display_description": "✓" if display_cfg.get("show_description", True) else "✗",
                "display_requirements": "✓" if display_cfg.get("show_requirements", True) else "✗",
                "display_rewards": "✓" if display_cfg.get("show_rewards", True) else "✗",
                "display_data": "✓" if display_cfg.get("show_data", True) else "✗"
            }

            for h in header_cfg:
                raw = h.get("data", "")
                html_line = replace_tokens_html_simple(raw, {}, globals_dict, cfg, remaining=None, line_color=h.get("color"))
                style = f"font-family:{h.get('font', base_font)}; font-size:{h.get('size', base_size)}pt; color:{h.get('color','#ffffff')};"
                parts.append(f"<div style='{style} margin:2px 0;'>{html_line}</div>")

            parts.append("<hr style='border: none; border-top: 1px solid #333; margin:6px 0;'/>")

            # Paginate quests
            start_idx = self._current_page * self._page_size
            end_idx = start_idx + self._page_size
            quests_on_page = quests[start_idx:end_idx]

            for q in quests_on_page:
                completion = q.get("completion_deadline", 0) or 0
                if current_ts is not None:
                    remaining = int(completion - current_ts)
                else:
                    remaining = 0

                q_copy = dict(q)
                q_copy["time_remaining"] = format_time_remaining(remaining, cfg.get("time_remaining_format", "%dd %hh %mm %ss"))
                q_copy["time_remaining_seconds"] = remaining

                parts.append("<div style='padding:4px 0;'>")
                for line in lines_cfg:
                    raw = line.get("data", "")

                    if ("%name%" in raw and not display_cfg.get("show_name", True)) or \
                       ("%description%" in raw and not display_cfg.get("show_description", True)) or \
                       ("%requirements%" in raw and not display_cfg.get("show_requirements", True)) or \
                       ("%rewards%" in raw and not display_cfg.get("show_rewards", True)) or \
                       ("%data%" in raw and not display_cfg.get("show_data", True)):
                        continue

                    html_line = replace_tokens_html_simple(raw, q_copy, globals_dict, cfg, remaining=remaining, line_color=line.get("color"))
                    style = f"font-family:{line.get('font', base_font)}; font-size:{line.get('size', base_size)}pt; color:{line.get('color','#ffffff')};"
                    parts.append(f"<div style='{style} margin:1px 0;'>{html_line}</div>")

                parts.append("</div>")
                parts.append("<hr style='border: none; border-top: 1px solid rgba(255,255,255,0.03); margin:6px 0;'/>")

            parts.append("</div>")
            return "".join(parts)

        def _render_quests_safe(self):
            if self._is_closing:
                return
            locker = QMutexLocker(self._render_mutex)
            try:
                self._process_pending_actions()

                cfg = self._config
                quests = self._quests or []
                quests = self._filter_quests(quests)
                quests = self._sort_quests(quests)

                if self._timestamp is not None and self._simulation_active:
                    current_ts = self._timestamp + self._simulated_time
                else:
                    current_ts = self._timestamp

                try:
                    cfg["widget_instance"] = self
                except Exception:
                    pass
                html_out = self._generate_full_html(quests, current_ts)

                if html_out != self._last_html:
                    sb = self.text_browser.verticalScrollBar()
                    old_value = sb.value()
                    old_max = sb.maximum()

                    self.text_browser.setHtml(html_out)
                    self._last_html = html_out
                    
                    # Dynamic height adjustment - shrink to content
                    try:
                        QApplication.processEvents()
                        
                        doc = self.text_browser.document()
                        doc_height = int(doc.size().height())
                        
                        # Set height to content size (max = parent overlay height)
                        parent_height = self.parent().height() if self.parent() else 1000
                        optimal_height = min(doc_height + 20, parent_height)
                        
                        self.text_browser.setFixedHeight(optimal_height)
                    except Exception as e:
                        print(f"[QuestWidget] Error adjusting height: {e}")

                    sb = self.text_browser.verticalScrollBar()
                    if old_value < old_max - 4:
                        sb.setValue(min(old_value, sb.maximum()))
                
                self._last_render_time = time.time()

            except Exception as e:
                print(f"[QuestWidget] Render error: {e}")
            finally:
                pass

        def _process_pending_actions(self):
            locker = QMutexLocker(self._actions_lock)
            if not self._pending_actions:
                return
            actions_to_process = list(self._pending_actions)
            self._pending_actions.clear()
            locker.unlock()

            config_changed = False
            
            for action_name in actions_to_process:
                cfg = self._config
                
                if action_name == "toggle_filter":
                    cfg["filter"]["enabled"] = not cfg["filter"].get("enabled", False)
                    config_changed = True

                elif action_name.startswith("toggle_sector_"):
                    sector_code = action_name.replace("toggle_sector_", "").upper()
                    sectors = cfg.setdefault("filter", {}).setdefault("sectors", {})
                    sectors[sector_code] = not sectors.get(sector_code, False)
                    
                    if sectors[sector_code]:
                        self._active_sectors.add(sector_code)
                    else:
                        self._active_sectors.discard(sector_code)
                    
                    config_changed = True

                elif action_name.startswith("toggle_shop_"):
                    shop_code = action_name.replace("toggle_shop_", "").upper()
                    shops = cfg.setdefault("filter", {}).setdefault("shops", {})
                    shops[shop_code] = not shops.get(shop_code, False)
                    
                    if shops[shop_code]:
                        self._active_shops.add(shop_code)
                    else:
                        self._active_shops.discard(shop_code)
                    
                    config_changed = True

                elif action_name == "sort_order_asc":
                    cfg.setdefault("sort", {})["order"] = "asc"
                    config_changed = True
                    
                elif action_name == "sort_order_desc":
                    cfg.setdefault("sort", {})["order"] = "desc"
                    config_changed = True

                elif action_name == "cycle_sort_key":
                    keys = cfg.setdefault("sort", {}).setdefault("keys", [])
                    
                    if not keys:
                        keys.append("id")
                    else:
                        last_idx = len(keys) - 1
                        last_key = keys[last_idx]
                        
                        try:
                            current_idx = SORT_KEY_OPTIONS.index(last_key)
                            next_idx = (current_idx + 1) % len(SORT_KEY_OPTIONS)
                            keys[last_idx] = SORT_KEY_OPTIONS[next_idx]
                        except ValueError:
                            keys[last_idx] = "id"
                    
                    cfg["sort"]["keys"] = keys
                    config_changed = True

                elif action_name == "add_sort_key":
                    keys = cfg.setdefault("sort", {}).setdefault("keys", [])
                    
                    for k in SORT_KEY_OPTIONS:
                        if k not in keys:
                            keys.append(k)
                            break
                    
                    cfg["sort"]["keys"] = keys
                    config_changed = True

                elif action_name == "clear_sort_keys":
                    cfg.setdefault("sort", {})["keys"] = ["id"]
                    config_changed = True

                elif action_name.startswith("toggle_display_"):
                    display_key = action_name.replace("toggle_display_", "")
                    if display_key in DISPLAY_TOGGLE_OPTIONS:
                        cfg.setdefault("display", {})[display_key] = not cfg.get("display", {}).get(display_key, True)
                        config_changed = True

                # PAGINATION ACTIONS
                elif action_name == "next_page":
                    filtered = self._filter_quests(self._quests or [])
                    sorted_quests = self._sort_quests(filtered)
                    total_pages = max(1, (len(sorted_quests) + self._page_size - 1) // self._page_size)
                    self._current_page = min(self._current_page + 1, total_pages - 1)
                    print(f"[QuestWidget] Next page: {self._current_page + 1}/{total_pages}")

                elif action_name == "prev_page":
                    self._current_page = max(0, self._current_page - 1)
                    print(f"[QuestWidget] Prev page: {self._current_page + 1}")

                elif action_name == "increase_page_size":
                    self._page_size = min(50, self._page_size + 1)
                    self._current_page = 0
                    self._config["page_size"] = self._page_size
                    self._save_page_config()
                    print(f"[QuestWidget] Page size increased: {self._page_size}")

                elif action_name == "decrease_page_size":
                    self._page_size = max(1, self._page_size - 1)
                    self._current_page = 0
                    self._config["page_size"] = self._page_size
                    self._save_page_config()
                    print(f"[QuestWidget] Page size decreased: {self._page_size}")

            if config_changed:
                if any(a.startswith("toggle_") and not a.startswith("toggle_display_") for a in actions_to_process):
                    self._save_filter_to_config()
                
                if any(a in ["sort_order_asc", "sort_order_desc", "cycle_sort_key", "add_sort_key", "clear_sort_keys"] for a in actions_to_process):
                    self._save_sort_to_config()
                
                if any(a.startswith("toggle_display_") for a in actions_to_process):
                    self._save_display_to_config()

        def _register_shortcuts(self):
            try:
                for combo_norm, handler in list(self._bridge_handlers.items()):
                    try:
                        self.bridge.off(f"shortcut.{combo_norm}", handler)
                    except Exception:
                        pass
            except Exception:
                pass
            self._bridge_handlers.clear()

            shortcuts = self._config.get("shortcuts", {}) or {}
            
            for action, combo in shortcuts.items():
                combo_norm = _normalize_combo(combo)
                event_name = f"shortcut.{combo_norm}"

                def make_handler(act, combo_norm_local):
                    return lambda act=act, combo_norm=combo_norm_local: self._on_shortcut_triggered(act, combo_norm)

                handler = make_handler(action, combo_norm)
                try:
                    self.bridge.on(event_name, handler)
                    self._bridge_handlers[combo_norm] = handler
                except Exception as e:
                    print(f"[QuestWidget] Failed to register {action}: {e}")

        def _on_shortcut_triggered(self, action_name: str, combo_norm: str):
            try:
                locker = QMutexLocker(self._actions_lock)
                self._pending_actions.append(action_name)
                locker.unlock()
                self.schedule_render()
            except Exception as e:
                print(f"[QuestWidget] _on_shortcut_triggered error ({action_name}): {e}")

        def close_widget(self):
            self._is_closing = True
            
            try:
                if hasattr(self, 'timer'):
                    self.timer.stop()
            except Exception:
                pass
                
            try:
                for combo_norm, handler in list(self._bridge_handlers.items()):
                    try:
                        self.bridge.off(f"shortcut.{combo_norm}", handler)
                    except Exception:
                        pass
            except Exception:
                pass
            self._bridge_handlers.clear()

    return QuestWidget()


def get_widget_dock_position():
    return Qt.LeftDockWidgetArea, 1