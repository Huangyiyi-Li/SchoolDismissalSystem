import requests
import datetime

class ApiService:
    BASE_URL = "https://rest.xxt.cn"  # Formal Environment

    def __init__(self, school_id, base_url=None, session=None):
        self.school_id = school_id
        self.base_url = (base_url or self.BASE_URL).rstrip("/")
        self.session = session or requests
        self.headers = {
            "Content-Type": "application/json"
        }

    def get_classes(self):
        """
        Fetch class list and card mappings.
        Path: /kq-http/school-dismissal-system/get-classes-v2
        """
        if not self.school_id:
            print("[API] Error: School ID not set.")
            return None

        url = f"{self.base_url}/kq-http/school-dismissal-system/get-classes-v2"
        payload = {
            "schoolId": self.school_id
        }
        try:
            response = self.session.post(url, json=payload, headers=self.headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            if data.get("code") == 200:
                return data.get("data", [])
            else:
                print(f"[API] Get Classes Error: {data.get('message')}")
                return None
        except Exception as e:
            print(f"[API] Connection Error (get-classes): {e}")
            return None

    def push_dismissal_notice(
        self,
        class_id,
        card_id,
        dismissal_status=1,
        class_type=None,
        trigger_type=1,
        trigger_teacher_id=None,
        trigger_teacher_name=None,
        post_time=None,
    ):
        """
        Push dismissal notice to remote API.
        Path: /kq-http/school-dismissal-system/push-dismissal-notice-v2
        """
        url = f"{self.base_url}/kq-http/school-dismissal-system/push-dismissal-notice-v2"
        
        if not self.school_id:
            print("[API] Push Skipped: School ID not set.")
            return False
            
        post_time = post_time or datetime.datetime.now()
        now_str = post_time.strftime("%Y-%m-%d %H:%M:%S")
        
        payload = {
            "schoolId": self.school_id,
            "classId": class_id,
            "classType": class_type,
            "triggerType": trigger_type,
            "cardId": card_id,
            "dismissalStatus": dismissal_status, # 1-Dismissal
            "triggerTeacherId": trigger_teacher_id,
            "trigger_teacher_name": trigger_teacher_name,
            "postTime": now_str
        }
        
        try:
            # Increased timeout to 15s to avoid read timeouts
            response = self.session.post(url, json=payload, headers=self.headers, verify=False, timeout=15)
            # response.raise_for_status() # Optional, verify return code manually
            
            data = response.json()
            if data.get("code") == 200:
                print(f"[API] Push Success for Card {card_id}")
                return True
            else:
                print(f"[API] Push Failed: {data.get('msg') or data.get('message')}")
                return False
        except Exception as e:
            print(f"[API] Connection Error (push-notice): {e}")
            return False

    def get_school_dismissal_schedule(self):
        """
        Fetch dismissal schedule.
        Path: /kq-http/school-dismissal-system/get-school-dismissal-schedule-v2
        """
        if not self.school_id:
            return None

        url = f"{self.base_url}/kq-http/school-dismissal-system/get-school-dismissal-schedule-v2"
        payload = {
            "schoolId": self.school_id
        }
        try:
            response = self.session.post(url, json=payload, headers=self.headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            if data.get("code") == 200:
                return data.get("data", [])
            else:
                print(f"[API] Get Schedule Error: {data.get('message')}")
                return None
        except Exception as e:
            print(f"[API] Connection Error (get-schedule): {e}")
            return None
