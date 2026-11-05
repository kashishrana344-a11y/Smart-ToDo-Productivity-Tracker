"""SQLite persistence layer. Database is created on first launch."""
import sqlite3
import hashlib
import secrets
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime, date, timedelta
from .models import Task, TaskRepository

class SQLiteTaskRepository(TaskRepository):
    def __init__(self, database_path):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.user_id = None
        self._initialize()
    @contextmanager
    def _connect(self):
        con = sqlite3.connect(self.database_path, timeout=10)
        con.row_factory = sqlite3.Row
        try:
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()
    def _initialize(self):
        try:
            with self._connect() as db:
                db.executescript("""
                CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, full_name TEXT NOT NULL, username TEXT NOT NULL UNIQUE COLLATE NOCASE, password_hash TEXT NOT NULL, salt TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT NOT NULL,category TEXT NOT NULL DEFAULT 'General',deadline TEXT NOT NULL DEFAULT '',estimated_minutes INTEGER NOT NULL DEFAULT 30,notes TEXT NOT NULL DEFAULT '',completed INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL,priority_override TEXT NOT NULL DEFAULT 'Auto', user_id INTEGER REFERENCES users(id));
                CREATE TABLE IF NOT EXISTS study_sessions (id INTEGER PRIMARY KEY AUTOINCREMENT,subject TEXT NOT NULL,start_time TEXT NOT NULL,duration_minutes INTEGER NOT NULL,notes TEXT NOT NULL DEFAULT '',completed INTEGER NOT NULL DEFAULT 0, user_id INTEGER REFERENCES users(id));
                """)
                # Upgrade databases created by earlier versions without deleting existing data.
                task_cols={r['name'] for r in db.execute("PRAGMA table_info(tasks)")}
                if 'user_id' not in task_cols: db.execute("ALTER TABLE tasks ADD COLUMN user_id INTEGER REFERENCES users(id)")
                if 'completed_at' not in task_cols:
                    db.execute("ALTER TABLE tasks ADD COLUMN completed_at TEXT NOT NULL DEFAULT ''")
                    db.execute("UPDATE tasks SET completed_at=created_at WHERE completed=1")
                session_cols={r['name'] for r in db.execute("PRAGMA table_info(study_sessions)")}
                if 'user_id' not in session_cols: db.execute("ALTER TABLE study_sessions ADD COLUMN user_id INTEGER REFERENCES users(id)")
        except sqlite3.Error as exc: raise RuntimeError(f"Could not initialize database: {exc}") from exc
    def register_user(self, full_name, username, password):
        full_name=full_name.strip(); username=username.strip()
        if len(full_name)<2: raise ValueError("Enter your name.")
        if len(username)<3: raise ValueError("Username must have at least 3 characters.")
        if len(password)<6: raise ValueError("Password must have at least 6 characters.")
        salt=secrets.token_hex(16)
        digest=hashlib.pbkdf2_hmac("sha256",password.encode(),salt.encode(),200000).hex()
        try:
            with self._connect() as db:
                cur=db.execute("INSERT INTO users(full_name,username,password_hash,salt,created_at) VALUES(?,?,?,?,?)",(full_name,username,digest,salt,datetime.now().isoformat(timespec="seconds")))
                user_id=int(cur.lastrowid)
                # Keep any pre-login demo tasks with the first account created.
                if db.execute("SELECT COUNT(*) FROM users").fetchone()[0]==1:
                    db.execute("UPDATE tasks SET user_id=? WHERE user_id IS NULL",(user_id,))
                    db.execute("UPDATE study_sessions SET user_id=? WHERE user_id IS NULL",(user_id,))
                return {"id":user_id,"full_name":full_name,"username":username}
        except sqlite3.IntegrityError as exc: raise ValueError("That username is already taken. Choose another.") from exc

    def authenticate_user(self, username, password):
        with self._connect() as db:
            row=db.execute("SELECT * FROM users WHERE username=? COLLATE NOCASE",(username.strip(),)).fetchone()
        if not row: return None
        digest=hashlib.pbkdf2_hmac("sha256",password.encode(),row['salt'].encode(),200000).hex()
        if not secrets.compare_digest(digest,row['password_hash']): return None
        return {"id":row['id'],"full_name":row['full_name'],"username":row['username']}

    def set_user(self, user_id):
        self.user_id=int(user_id)

    @staticmethod
    def _to_task(r):
        return Task(id=r["id"],title=r["title"],category=r["category"],deadline=r["deadline"],estimated_minutes=r["estimated_minutes"],notes=r["notes"],completed=bool(r["completed"]),created_at=r["created_at"],priority_override=r["priority_override"],completed_at=r["completed_at"])
    def list_tasks(self, include_completed=True):
        try:
            with self._connect() as db:
                q="SELECT * FROM tasks WHERE user_id=?"+("" if include_completed else " AND completed=0")+" ORDER BY completed, deadline='', deadline, id DESC"
                return [self._to_task(r) for r in db.execute(q,(self.user_id,)).fetchall()]
        except sqlite3.Error as exc: raise RuntimeError(f"Could not load tasks: {exc}") from exc
    def save_task(self, task):
        try:
            with self._connect() as db:
                fields=(task.title.strip(),task.category.strip() or "General",task.deadline,task.estimated_minutes,task.notes.strip(),int(task.completed),task.created_at or datetime.now().isoformat(timespec="seconds"),task.priority_override,task.completed_at)
                if task.id is None:
                    cur=db.execute("INSERT INTO tasks(title,category,deadline,estimated_minutes,notes,completed,created_at,priority_override,completed_at,user_id) VALUES(?,?,?,?,?,?,?,?,?,?)",fields+(self.user_id,)); task.id=cur.lastrowid
                else: db.execute("UPDATE tasks SET title=?,category=?,deadline=?,estimated_minutes=?,notes=?,completed=?,created_at=?,priority_override=?,completed_at=? WHERE id=? AND user_id=?",fields+(task.id,self.user_id))
                return int(task.id)
        except sqlite3.Error as exc: raise RuntimeError(f"Could not save task: {exc}") from exc
    def delete_task(self, task_id):
        try:
            with self._connect() as db: db.execute("DELETE FROM tasks WHERE id=? AND user_id=?",(task_id,self.user_id))
        except sqlite3.Error as exc: raise RuntimeError(f"Could not delete task: {exc}") from exc
    def list_sessions(self, day=None):
        try:
            with self._connect() as db:
                if day: return db.execute("SELECT * FROM study_sessions WHERE user_id=? AND substr(start_time,1,10)=? ORDER BY start_time",(self.user_id,day)).fetchall()
                return db.execute("SELECT * FROM study_sessions WHERE user_id=? ORDER BY start_time DESC",(self.user_id,)).fetchall()
        except sqlite3.Error as exc: raise RuntimeError(f"Could not load study sessions: {exc}") from exc
    def save_session(self, subject, start_time, duration, notes=""):
        try:
            with self._connect() as db: cur=db.execute("INSERT INTO study_sessions(subject,start_time,duration_minutes,notes,user_id) VALUES(?,?,?,?,?)",(subject.strip(),start_time,duration,notes.strip(),self.user_id)); return int(cur.lastrowid)
        except sqlite3.Error as exc: raise RuntimeError(f"Could not save study session: {exc}") from exc
    def toggle_session(self, session_id):
        try:
            with self._connect() as db: db.execute("UPDATE study_sessions SET completed=1-completed WHERE id=? AND user_id=?",(session_id,self.user_id))
        except sqlite3.Error as exc: raise RuntimeError(f"Could not update study session: {exc}") from exc
    def delete_session(self, session_id):
        try:
            with self._connect() as db: db.execute("DELETE FROM study_sessions WHERE id=? AND user_id=?",(session_id,self.user_id))
        except sqlite3.Error as exc: raise RuntimeError(f"Could not delete study session: {exc}") from exc

    def seed_demo_data(self):
        """Add realistic sample tasks and study blocks for the current user (used for demos)."""
        today = date.today()
        day = lambda n: (today + timedelta(days=n)).isoformat()
        # (title, category, deadline, minutes, notes, priority, completed-days-ago or None)
        tasks = [
            ("Submit OOP lab report", "College", day(0), 90, "Attach screenshots", "Auto", None),
            ("Pay hostel fees", "Personal", day(-1), 10, "Overdue example", "Auto", None),
            ("Revise Data Structures - Trees", "Study", day(1), 60, "", "Auto", None),
            ("Prepare Flowday presentation", "Project", day(2), 120, "Slides + live demo", "Auto", None),
            ("Record YouTube video script", "Creative", day(4), 45, "", "Auto", None),
            ("Read ML chapter 5", "Study", day(7), 60, "", "Auto", None),
            ("Gym workout", "Health", day(0), 40, "", "Low", None),
            ("Finish Python exercises", "Study", "", 30, "", "Auto", 5),
            ("Watch ML lecture", "Study", "", 45, "", "Auto", 4),
            ("Update resume", "Personal", "", 30, "", "Auto", 3),
            ("Solve 10 DSA problems", "Study", "", 60, "", "Auto", 2),
            ("Clean up class notes", "College", "", 30, "", "Auto", 1),
            ("Email professor", "College", "", 15, "", "Auto", 0),
            ("Set up GitHub repo", "Project", "", 20, "", "Auto", 0),
        ]
        sessions = [
            ("Data Structures", "09:30", 50, "Trees & graphs", 1),
            ("Machine Learning", "11:00", 45, "Linear regression", 1),
            ("OOP revision", "16:00", 60, "Design patterns", 0),
            ("Project work", "19:30", 90, "Flowday polish", 0),
        ]
        try:
            with self._connect() as db:
                for title, cat, due, mins, notes, prio, ago in tasks:
                    done = ago is not None
                    db.execute("INSERT INTO tasks(title,category,deadline,estimated_minutes,notes,completed,created_at,priority_override,completed_at,user_id) VALUES(?,?,?,?,?,?,?,?,?,?)",
                               (title, cat, due, mins, notes, int(done), day(-6) + "T09:00:00", prio, (day(-ago) + "T20:00:00") if done else "", self.user_id))
                for subject, start, mins, notes, done in sessions:
                    db.execute("INSERT INTO study_sessions(subject,start_time,duration_minutes,notes,completed,user_id) VALUES(?,?,?,?,?,?)",
                               (subject, f"{today.isoformat()} {start}", mins, notes, done, self.user_id))
        except sqlite3.Error as exc: raise RuntimeError(f"Could not load sample data: {exc}") from exc
