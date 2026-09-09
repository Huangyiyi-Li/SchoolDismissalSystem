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
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS credential_aliases (
                school_id TEXT NOT NULL,
                credential_type TEXT NOT NULL,
                credential_value TEXT NOT NULL,
                api_card_id TEXT NOT NULL,
                class_id TEXT NOT NULL,
                class_type INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (school_id, credential_type, credential_value)
            )
        """)

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

        # One row per class returned by the server. This is deliberately separate
        # from mapping because a class can have multiple physical cards.
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS led_classes (
                school_id TEXT NOT NULL,
                class_type INTEGER NOT NULL,
                class_id TEXT NOT NULL,
                grade_name TEXT,
                class_name TEXT NOT NULL,
                class_show_name TEXT,
                class_voice_name TEXT,
                source_order INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (school_id, class_type, class_id)
            )
        ''')

        # Same-day LED dismissal status. This is separate from the class catalog
        # so restarting the desktop client does not erase the live dismissal board.
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS led_class_statuses (
                school_id TEXT NOT NULL,
                class_type INTEGER NOT NULL DEFAULT 1,
                class_id TEXT NOT NULL,
                status_date TEXT NOT NULL,
                status TEXT NOT NULL,
                dismiss_due_at TEXT,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (school_id, class_type, class_id, status_date)
            )
        ''')
        cursor.execute("PRAGMA table_info(led_class_statuses)")
        status_columns = cursor.fetchall()
        status_column_names = [item[1] for item in status_columns]
        status_pk_columns = [
            item[1] for item in sorted(status_columns, key=lambda item: item[5]) if item[5]
        ]
        expected_status_pk = ["school_id", "class_type", "class_id", "status_date"]
        if "class_type" not in status_column_names or status_pk_columns != expected_status_pk:
            cursor.execute("ALTER TABLE led_class_statuses RENAME TO led_class_statuses_legacy")
            cursor.execute('''
                CREATE TABLE led_class_statuses (
                    school_id TEXT NOT NULL,
                    class_type INTEGER NOT NULL DEFAULT 1,
                    class_id TEXT NOT NULL,
                    status_date TEXT NOT NULL,
                    status TEXT NOT NULL,
                    dismiss_due_at TEXT,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (school_id, class_type, class_id, status_date)
                )
            ''')
            cursor.execute('''
                INSERT OR REPLACE INTO led_class_statuses
                    (school_id, class_type, class_id, status_date, status,
                     dismiss_due_at, updated_at)
                SELECT school_id, 1, class_id, status_date, status,
                       dismiss_due_at, updated_at
                FROM led_class_statuses_legacy
            ''')
            cursor.execute("DROP TABLE led_class_statuses_legacy")

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
        cursor.execute("DELETE FROM led_classes")
        conn.commit()
        conn.close()

    def upsert_led_class(
        self,
        school_id,
        class_type,
        class_id,
        grade_name,
        class_name,
        class_show_name=None,
        class_voice_name=None,
        source_order=0,
    ):
        if not school_id or not class_id or not class_name:
            return False
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT OR REPLACE INTO led_classes
                    (school_id, class_type, class_id, grade_name, class_name,
                     class_show_name, class_voice_name, source_order)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(school_id),
                    int(class_type or 0),
                    str(class_id),
                    grade_name or "",
                    class_name,
                    class_show_name,
                    class_voice_name,
                    int(source_order),
                ),
            )
            conn.commit()
            return True
        except Exception as e:
            print(f"[DB] Error adding LED class: {e}")
            return False
        finally:
            conn.close()

    def get_led_classes(self, school_id=None, class_type=1):
        """Return actual server-provided classes, optionally filtered by type."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        conditions = []
        params = []
        if school_id:
            conditions.append("school_id = ?")
            params.append(str(school_id))
        if class_type is not None:
            conditions.append("class_type = ?")
            params.append(int(class_type))
        where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""
        cursor.execute(
            f"""
            SELECT school_id, class_type, class_id, grade_name, class_name,
                   class_show_name, class_voice_name, source_order
            FROM led_classes
            {where_clause}
            ORDER BY class_type, source_order, class_id
            """,
            tuple(params),
        )
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return rows

    def save_led_class_status(
        self,
        school_id,
        class_id,
        status_date,
        status,
        dismiss_due_at=None,
        class_type=1,
    ):
        if not school_id or not class_id or not status_date or not status:
            return False
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT OR REPLACE INTO led_class_statuses
                    (school_id, class_type, class_id, status_date, status,
                     dismiss_due_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (
                    str(school_id),
                    int(class_type or 1),
                    str(class_id),
                    str(status_date),
                    str(status),
                    dismiss_due_at,
                ),
            )
            conn.commit()
            return True
        finally:
            conn.close()

    def get_led_class_statuses(self, school_id, status_date, class_type=None):
        if not school_id or not status_date:
            return []
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        if class_type is None:
            cursor.execute(
                """
                SELECT class_type, class_id, status, dismiss_due_at
                FROM led_class_statuses
                WHERE school_id = ? AND status_date = ?
                ORDER BY updated_at, class_type, class_id
                """,
                (str(school_id), str(status_date)),
            )
        else:
            cursor.execute(
                """
                SELECT class_type, class_id, status, dismiss_due_at
                FROM led_class_statuses
                WHERE school_id = ? AND status_date = ? AND class_type = ?
                ORDER BY updated_at, class_id
                """,
                (str(school_id), str(status_date), int(class_type)),
            )
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return rows

    def clear_led_class_statuses(self, school_id, status_date=None, class_type=None):
        if not school_id:
            return
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        conditions = ["school_id = ?"]
        params = [str(school_id)]
        if status_date is not None:
            conditions.append("status_date = ?")
            params.append(str(status_date))
        if class_type is not None:
            conditions.append("class_type = ?")
            params.append(int(class_type))
        cursor.execute(
            "DELETE FROM led_class_statuses WHERE " + " AND ".join(conditions),
            tuple(params),
        )
        conn.commit()
        conn.close()

    def delete_led_class_status(self, school_id, class_id, status_date, class_type=1):
        if not school_id or not class_id or not status_date:
            return
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            DELETE FROM led_class_statuses
            WHERE school_id = ? AND class_type = ? AND class_id = ? AND status_date = ?
            """,
            (str(school_id), int(class_type or 1), str(class_id), str(status_date)),
        )
        conn.commit()
        conn.close()

    def get_all_mappings(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT card_id, class_type, class_id, class_name, school_id FROM mapping")
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

    def bind_credential(self, school_id, epc, api_card_id):
        from .services.readers.uhf_protocol import normalize_epc
        epc = normalize_epc(epc)
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT class_id, class_type FROM mapping WHERE card_id=? AND school_id=?",
                (api_card_id, str(school_id)),
            ).fetchone()
            if not row or not row[0] or row[1] is None:
                raise ValueError("请选择当前学校已同步的班级卡号")
            conn.execute(
                "INSERT INTO credential_aliases "
                "(school_id,credential_type,credential_value,api_card_id,class_id,class_type) "
                "VALUES (?, 'uhf_epc', ?, ?, ?, ?)",
                (str(school_id), epc, api_card_id, str(row[0]), int(row[1])),
            )

    def resolve_credential(self, school_id, epc):
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("""
                SELECT a.api_card_id FROM credential_aliases a JOIN mapping m
                ON m.card_id=a.api_card_id AND m.school_id=a.school_id
                AND m.class_id=a.class_id AND m.class_type=a.class_type
                WHERE a.school_id=? AND a.credential_type='uhf_epc' AND a.credential_value=?
            """, (str(school_id), epc)).fetchone()
        return row[0] if row else None

    def list_credentials(self, school_id):
        with sqlite3.connect(self.db_path) as conn:
            return conn.execute("""
                SELECT a.credential_value,a.api_card_id,COALESCE(m.class_name,'绑定已失效')
                FROM credential_aliases a LEFT JOIN mapping m
                ON m.card_id=a.api_card_id AND m.school_id=a.school_id
                AND m.class_id=a.class_id AND m.class_type=a.class_type
                WHERE a.school_id=? ORDER BY a.created_at,a.credential_value
            """, (str(school_id),)).fetchall()

    def delete_credential(self, school_id, epc):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM credential_aliases WHERE school_id=? AND "
                         "credential_type='uhf_epc' AND credential_value=?", (str(school_id), epc))
