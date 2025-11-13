# /////////////////////////////////////////////////////////////////////////////////////////////
# ////---- Importovanie potrebných knižníc, cesty k súborom a nastavenia ----////
# /////////////////////////////////////////////////////////////////////////////////////////////
import sqlite3
import time
import configparser
import os
import json
import platform
from datetime import datetime

# ////---- Cesty k súborom ----////
module_root = os.path.dirname(os.path.dirname(__file__))
config_path = os.path.join(module_root, 'config', 'config.json')
data_path = os.path.join(module_root, 'data', 'quest.json')
log_path = os.path.join(module_root, 'data', 'log.txt')
path_ini_path = os.path.join(module_root, 'config', 'path.ini')
# ////-----------------------------------------------------------------------------------------

# ////---- Logovanie do log.txt ktorý si načíta GUI widget console ----////
def log_to_console(message, color=None):
    timestamp = datetime.now().strftime("%H:%M:%S")
    line = f"[{timestamp}] {message}\n"
    try:
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(line)
    except Exception as e:
        print(f"[LOGIC] Chyba pri zápise do log.txt: {e}")
# ////-----------------------------------------------------------------------------------------

# ////---- Automatická detekcia cesty k SCUM.db ----////
def detect_db_path():
    config = configparser.ConfigParser()
    if os.path.exists(path_ini_path):
        config.read(path_ini_path)
        if 'paths' in config and 'db_path' in config['paths']:
            db_path = config['paths']['db_path']
            if os.path.exists(db_path):
                return db_path

    # Pokus o automatickú detekciu podľa OS
    system = platform.system()
    if system == 'Windows':
        default_win = os.path.expandvars(r"%LOCALAPPDATA%\\SCUM\\Saved\\SaveFiles\\SCUM.db")
        if os.path.exists(default_win):
            return default_win
    elif system == 'Linux':
        candidates = [
            os.path.expanduser("~/Steam/steamapps/compatdata/513710/pfx/drive_c/users/steamuser/AppData/Local/SCUM/Saved/SaveFiles/SCUM.db"),
            os.path.expanduser("~/.var/app/com.valvesoftware.Steam/.steam/steam/steamapps/compatdata/513710/pfx/drive_c/users/steamuser/AppData/Local/SCUM/Saved/SaveFiles/SCUM.db")
        ]
        for path in candidates:
            if os.path.exists(path):
                return path

    log_to_console("[ActiveQuests] SCUM.db nebol nájdený. Prosím zadajte cestu ručne do config/path.ini [paths] db_path=...")
    return None
# ////-----------------------------------------------------------------------------------------

# ////---- Zabezpečenie indexov v databáze pre rýchlejšie vyhľadávanie ----////
def ensure_indexes(conn):
    try:
        cursor = conn.cursor()

        # entity – pre detekciu aktívneho hráča
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_entity_flags ON entity(flags);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_entity_system_id ON entity(entity_system_id);")

        # entity_system – pre prepojenie s user_profile
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_entity_system_id ON entity_system(id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_entity_system_user_profile_id ON entity_system(user_profile_id);")

        # active_quest – rýchly prístup k questom hráča
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_active_quest_user_profile_id ON active_quest(user_profile_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_active_quest_id ON active_quest(id);")

        # tracking_data – rýchly prístup podľa quest ID
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tracking_data_set_id ON tracking_data(tracking_data_set_id);")

        conn.commit()
    except sqlite3.Error as e:
        log_to_console(f"[ActiveQuests] Chyba pri vytváraní indexov: {e}")
# ////-----------------------------------------------------------------------------------------

# ////---- Otvorenie spojenia s databázou ----////
def open_db_connection(db_path):
    try:
        conn = sqlite3.connect(db_path, timeout=1)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA locking_mode=NORMAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA read_uncommitted = true;")
        conn.row_factory = sqlite3.Row
        ensure_indexes(conn)
        return conn
    except sqlite3.Error as e:
        log_to_console(f"[ActiveQuests] Chyba pri otváraní databázy: {e}")
        return None
# ////-----------------------------------------------------------------------------------------

# ////---- Zatvorenie spojenia s databázou ----////
def close_db_connection(conn):
    if conn:
        try:
            conn.close()
        except sqlite3.Error as e:
            log_to_console(f"[ActiveQuests] Chyba pri zatváraní databázy: {e}")
# ////-----------------------------------------------------------------------------------------

# ////---- Načítanie alebo vytvorenie config.json ----////
def load_or_create_config():
    default_config = {
        "scan_interval": 4
    }
    if not os.path.exists(config_path):
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(default_config, f, indent=4)
        return default_config

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            user_config = json.load(f)
        for key in default_config:
            if key not in user_config:
                user_config[key] = default_config[key]
        return user_config
    except Exception as e:
        log_to_console(f"[ActiveQuests] Chyba pri načítaní config.json: {e}")
        return default_config
# ////-----------------------------------------------------------------------------------------

# ////---- Detekcia aktívneho hráča cez flag=0 ----////
def get_active_user_profile_id(conn):
    cursor = conn.cursor()
    cursor.execute("""
        SELECT entity_system_id
        FROM entity
        WHERE class = 'FPrisonerEntity' AND flags = 0
    """)
    row = cursor.fetchone()
    if not row:
        return None
    entity_system_id = row['entity_system_id']

    cursor.execute("""
        SELECT user_profile_id
        FROM entity_system
        WHERE id = ?
    """, (entity_system_id,))
    result = cursor.fetchone()
    return result['user_profile_id'] if result else None
# ////-----------------------------------------------------------------------------------------

# ////---- Načítanie aktuálneho timestampu sveta pre aktívneho hráča ----////
def get_world_timestamp(conn, user_profile_id):
    """
    Načíta aktuálny časový údaj (timestamp) z tabuľky entity_system
    pre aktívneho hráča podľa jeho user_profile_id.
    Tento timestamp reprezentuje interný čas sveta.
    """
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT timestamp
            FROM entity_system
            WHERE user_profile_id = ?
        """, (user_profile_id,))
        row = cursor.fetchone()
        if row and "timestamp" in row.keys():
            return row["timestamp"]
        return None
    except sqlite3.Error as e:
        log_to_console(f"[ActiveQuests] Chyba pri načítaní timestampu z entity_system: {e}")
        return None

# ////---- Načítanie všetkých questov aktívneho hráča ----////
def get_active_quests(conn, user_profile_id):
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, sector, completion_deadline, quest_data_asset_path, auto_complete
        FROM active_quest
        WHERE user_profile_id = ?
    """, (user_profile_id,))
    rows = cursor.fetchall()
    return [dict(row) for row in rows]
# ////-----------------------------------------------------------------------------------------

# ////---- Doplenie questov o BLOB data z tracking_data ----////
def attach_tracking_data(conn, quests):
    cursor = conn.cursor()
    for quest in quests:
        quest_id = quest.get("id")
        cursor.execute("""
            SELECT data
            FROM tracking_data
            WHERE tracking_data_set_id = ?
        """, (quest_id,))
        row = cursor.fetchone()
        if row and "data" in row.keys():
            # Konverzia binárnych dát na hex string
            blob_data = row["data"]
            if blob_data is not None:
                quest["data"] = blob_data.hex()
            else:
                quest["data"] = None
        else:
            quest["data"] = None
    return quests
# ////-----------------------------------------------------------------------------------------

# ////---- Uloženie questov do quest.json ----////
def save_quests_to_json(user_profile_id, timestamp, quests):
    """
    Uloží všetky questy do data/quest.json ako slovník:
    {
        "user_profile_id": ...,
        "timestamp": ...,
        "quests": [
            {
                "id": ...,
                "sector": ...,
                "completion_deadline": ...,
                "quest_data_asset_path": ...,
                "auto_complete": ...,
                "data": "HEX"
            }
        ]
    }
    """
    try:
        data = {
            "user_profile_id": user_profile_id,
            "timestamp": timestamp,
            "quests": quests
        }

        with open(data_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    except Exception as e:
        log_to_console(f"[ActiveQuests] Chyba pri zápise do quest.json: {e}")
# ////-----------------------------------------------------------------------------------------

# ////---- Vyprázdnenie quest.json ak nie je aktívny hráč ----////
def clear_quest_json():
    try:
        with open(data_path, 'w', encoding='utf-8') as f:
            json.dump({
                "user_profile_id": None,
                "timestamp": None,
                "quests": []
            }, f, indent=4)
    except Exception as e:
        log_to_console(f"[ActiveQuests] Chyba pri čistení quest.json: {e}")
# ////-----------------------------------------------------------------------------------------

# /////////////////////////////////////////////////////////////////////////////////////////////
# ////---- Hlavná slučka ----////
# /////////////////////////////////////////////////////////////////////////////////////////////
def main_loop(conn=None, stop_event=None):
    config_json = load_or_create_config()
    SCAN_INTERVAL = config_json.get("scan_interval", 4)

    while not (stop_event and stop_event.is_set()):
        try:
            user_profile_id = get_active_user_profile_id(conn)

            if not user_profile_id:
                log_to_console("[ActiveQuests] Nebol nájdený aktívny hráč. Quest.json bude vyčistený.")
                clear_quest_json()
            else:
                quests = get_active_quests(conn, user_profile_id)
                quests = attach_tracking_data(conn, quests)
                timestamp = get_world_timestamp(conn, user_profile_id)
                save_quests_to_json(user_profile_id, timestamp, quests)
                log_to_console(f"[ActiveQuests] Načítaných {len(quests)} aktívnych questov pre hráča ID {user_profile_id}.")

        except Exception as e:
            log_to_console(f"[ActiveQuests] Chyba: {e}")

        if stop_event and stop_event.is_set():
            break
        time.sleep(SCAN_INTERVAL)
# ////-----------------------------------------------------------------------------------------

# ////---- Inicializácia modulu ----////
def logic_main_init(stop_event=None):
    try:
        with open(log_path, 'w', encoding='utf-8') as f:
            f.write("[ActiveQuests] Module Loaded...\n")
    except Exception as e:
        print(f"[LOGIC] Nepodarilo sa vytvoriť log.txt: {e}")

    db_path = detect_db_path()
    if not db_path or not os.path.exists(db_path):
        log_to_console("[ActiveQuests] SCUM.db file not found or disk disconnected. Please fix path.ini.")
        clear_quest_json()
        return

    conn = open_db_connection(db_path)
    if not conn:
        log_to_console("[ActiveQuests] Nepodarilo sa otvoriť databázu.")
        return

    main_loop(conn, stop_event)
    close_db_connection(conn)
# ////-----------------------------------------------------------------------------------------

# ////---- Spustenie priamo ----////
if __name__ == "__main__":
    logic_main_init()

