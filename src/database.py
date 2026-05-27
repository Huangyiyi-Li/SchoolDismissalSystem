import sqlite3
import os
import datetime

class DatabaseManager:
    def __init__(self, db_path=None):
        if db_path is None:
            from .utils.path_utils import get_app_root
            base_dir = get_app_root()
            self.db_path = os.path.join(base_dir, "data", "school.db")
        else:
            self.db_path = db_path
            
        self._init_db()

    def _init_db(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Mapping table: Card ID -> Class Name
        # Added class_id for API support
        # Added school_id for multi-school support (Request)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS mapping (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                card_id TEXT UNIQUE NOT NULL,
                class_name TEXT NOT NULL,
                class_id TEXT,
                school_id TEXT,
                class_type INTEGER,
                class_show_name TEXT,
                class_voice_name TEXT
            )
        ''')
        
        # Check if class_id/school_id columns exist (for migration)
        cursor.execute("PRAGMA table_info(mapping)")
        columns = [info[1] for info in cursor.fetchall()]
        
        if "class_id" not in columns:
            try:
                cursor.execute("ALTER TABLE mapping ADD COLUMN class_id TEXT")
            except Exception as e:
                print(f"[DB] Migration Error (class_id): {e}")

        if "school_id" not in columns:
            try:
                cursor.execute("ALTER TABLE mapping ADD COLUMN school_id TEXT")
            except Exception as e:
                print(f"[DB] Migration Error (school_id): {e}")

        if "class_type" not in columns:
            try:
                cursor.execute("ALTER TABLE mapping ADD COLUMN class_type INTEGER")
            except Exception as e:
                print(f"[DB] Migration Error (class_type): {e}")

        if "class_show_name" not in columns:
            try:
                cursor.execute("ALTER TABLE mapping ADD COLUMN class_show_name TEXT")
            except Exception as e:
                print(f"[DB] Migration Error (class_show_name): {e}")

        if "class_voice_name" not in columns:
            try:
                cursor.execute("ALTER TABLE mapping ADD COLUMN class_voice_name TEXT")
            except Exception as e:
                print(f"[DB] Migration Error (class_voice_name): {e}")

        # Devices table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS devices (
                ip TEXT PRIMARY KEY,
                name TEXT,
                last_seen DATETIME
            )
        ''')
        
        # Logs table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                swipe_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                card_id TEXT,
                class_name TEXT,
                status TEXT,
                source TEXT,
                source_detail TEXT,
                class_type INTEGER
            )
        ''')

        cursor.execute("PRAGMA table_info(logs)")
        log_columns = [info[1] for info in cursor.fetchall()]
        if "source" not in log_columns:
            cursor.execute("ALTER TABLE logs ADD COLUMN source TEXT")
        if "source_detail" not in log_columns:
            cursor.execute("ALTER TABLE logs ADD COLUMN source_detail TEXT")
        if "class_type" not in log_columns:
            cursor.execute("ALTER TABLE logs ADD COLUMN class_type INTEGER")
        
        conn.commit()
        conn.close()

    def upsert_device(self, ip, name=None, last_seen=None):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            # Check existing to preserve name if not provided
            cursor.execute("SELECT name FROM devices WHERE ip = ?", (ip,))
            row = cursor.fetchone()
            existing_name = row[0] if row else None
            
            new_name = name if name is not None else existing_name
            new_name = new_name if new_name else f"Device-{ip.split('.')[-1]}" # Default name
            
            # If last_seen is None, update it? Or keep? usually update.
            if last_seen is None:
                import datetime
                last_seen = datetime.datetime.now()
            
            cursor.execute("INSERT OR REPLACE INTO devices (ip, name, last_seen) VALUES (?, ?, ?)", 
                           (ip, new_name, last_seen))
            conn.commit()
            return True
        except Exception as e:
            print(f"[DB] Error upserting device: {e}")
            return False
        finally:
            conn.close()

    def get_devices(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT ip, name, last_seen FROM devices ORDER BY last_seen DESC")
        results = cursor.fetchall()
        conn.close()
        return results

    def get_device_name(self, ip):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM devices WHERE ip = ?", (ip,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else ip

    def get_class_info_by_card(self, card_id):
        """Returns tuple (class_name, class_id, school_id, class_type, class_show_name, class_voice_name)."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT class_name, class_id, school_id, class_type, class_show_name, class_voice_name
            FROM mapping
            WHERE card_id = ?
            """,
            (card_id,),
        )
        result = cursor.fetchone()
        conn.close()
        if result:
            return result # (name, class_id, school_id)
        return (None, None, None, None, None, None)

    def get_class_info_by_class(self, class_id, class_type=None):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        if class_type is None:
            cursor.execute(
                """
                SELECT class_name, class_id, school_id, class_type, class_show_name, class_voice_name
                FROM mapping
                WHERE class_id = ?
                LIMIT 1
                """,
                (class_id,),
            )
        else:
            cursor.execute(
                """
                SELECT class_name, class_id, school_id, class_type, class_show_name, class_voice_name
                FROM mapping
                WHERE class_id = ? AND class_type = ?
                LIMIT 1
                """,
                (class_id, class_type),
            )
        result = cursor.fetchone()
        conn.close()
        if result:
            return result
        return (None, class_id, None, class_type, None, None)

    def get_class_by_card(self, card_id):
        # Backward compatibility
        info = self.get_class_info_by_card(card_id)
        return info[0]

    def add_mapping(
        self,
        card_id,
        class_name,
        class_id=None,
        school_id=None,
        class_type=None,
        class_show_name=None,
        class_voice_name=None,
    ):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT OR REPLACE INTO mapping
                    (card_id, class_name, class_id, school_id, class_type, class_show_name, class_voice_name)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    card_id,
                    class_name,
                    class_id,
                    school_id,
                    class_type,
                    class_show_name,
                    class_voice_name,
                ),
            )
            conn.commit()
            return True
        except Exception as e:
            print(f"[DB] Error adding mapping: {e}")
            return False
        finally:
            conn.close()

    def delete_mapping(self, card_id):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM mapping WHERE card_id = ?", (card_id,))
        conn.commit()
        conn.close()

    def clear_mappings(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM mapping")
        conn.commit()
        conn.close()

    def get_all_mappings(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT card_id, class_type, class_name, school_id FROM mapping")
        rows = cursor.fetchall()
        conn.close()
        return rows

    def log_swipe(
        self,
        card_id,
        class_name,
        status,
        source=None,
        source_detail=None,
        class_type=None,
    ):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            """
            INSERT INTO logs
                (swipe_time, card_id, class_name, status, source, source_detail, class_type)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now,
                card_id,
                class_name,
                status,
                source,
                source_detail,
                class_type,
            ),
        )
        conn.commit()
        conn.close()

    def get_recent_logs(self, limit=500):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT swipe_time, card_id, class_name, status FROM logs ORDER BY id DESC LIMIT ?", (limit,))
        rows = cursor.fetchall()
        conn.close()
        return rows

    def get_recent_log_records(self, limit=500):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT swipe_time, card_id, class_name, status, source, source_detail, class_type
            FROM logs
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cursor.fetchall()
        conn.close()

        records = []
        for row in rows:
            timestamp, card_id, class_name, status, source, source_detail, class_type = row
            inferred_source = source or "刷卡"
            inferred_detail = source_detail
            if inferred_source == "刷卡" and not inferred_detail:
                inferred_detail = card_id or ""
            records.append(
                {
                    "timestamp": timestamp,
                    "card_id": card_id or "",
                    "class_name": class_name or "",
                    "status": status or "",
                    "source": inferred_source,
                    "source_detail": inferred_detail or "",
                    "class_type": class_type,
                }
            )
        return records
