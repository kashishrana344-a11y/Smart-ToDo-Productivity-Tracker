"""Tkinter desktop interface for the Smart Productivity Tracker."""
from __future__ import annotations
import tkinter as tk
import csv
import json
from pathlib import Path
from tkinter import ttk, messagebox, filedialog
from datetime import date, datetime, timedelta
from .database import SQLiteTaskRepository
from .models import Task, DeadlinePriorityStrategy, completion_streak

# Soft pastel palettes. "accent" and the semantic colours are pastel fills (backgrounds, bars, rings);
# the *_ink variants are slightly deeper tones used for text and icons so everything stays readable.
BASE = {
    "light": {"bg":"#f8f4ff","panel":"#ffffff","panel2":"#f1ecff","text":"#2e2a4d","muted":"#7d7799","line":"#e8e0fa","on_accent":"#2e2a4d"},
    "dark":  {"bg":"#1e1a2e","panel":"#2a2540","panel2":"#352f52","text":"#f5f0ff","muted":"#b0a9cf","line":"#463f69","on_accent":"#241f38"},
}
SEMANTIC = {
    "light": {"cyan":"#a5e3f0","green":"#a8e6cf","orange":"#ffd3a8","red":"#ffb3c6","cyan_ink":"#1b93ad","green_ink":"#1f9d6e","orange_ink":"#d9782b","red_ink":"#d94871"},
    "dark":  {"cyan":"#a5e3f0","green":"#a8e6cf","orange":"#ffd3a8","red":"#ffb3c6","cyan_ink":"#a5e3f0","green_ink":"#a8e6cf","orange_ink":"#ffd3a8","red_ink":"#ffb3c6"},
}
ACCENTS = {
    "Lavender": {"accent":"#c4b5fd","ink":"#6d4fd8","grad":["#c4b5fd","#f9a8d4","#fed7aa"]},
    "Mint":     {"accent":"#9be8c8","ink":"#0f9f78","grad":["#a7f3d0","#bae6fd","#ddd6fe"]},
    "Peach":    {"accent":"#fdc3a1","ink":"#d9622b","grad":["#fed7aa","#fbcfe8","#e9d5ff"]},
    "Sky":      {"accent":"#9ccfff","ink":"#2f7fd6","grad":["#a5d8ff","#c4b5fd","#fbcfe8"]},
}

def _mix_hex(c1, c2, t):
    x = [int(c1[i:i+2], 16) for i in (1, 3, 5)]; y = [int(c2[i:i+2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(int(x[i] + (y[i] - x[i]) * t) for i in range(3))

def build_palette(mode, accent_name):
    c = dict(BASE[mode]); c.update(SEMANTIC[mode]); acc = ACCENTS[accent_name]
    c["accent"] = acc["accent"]; c["accent_ink"] = acc["ink"] if mode == "light" else acc["accent"]; c["grad"] = acc["grad"]
    if mode == "light":  # tint the page, cards and borders with the chosen pastel
        c["bg"] = _mix_hex(acc["accent"], "#ffffff", .82); c["panel2"] = _mix_hex(acc["accent"], "#ffffff", .74); c["line"] = _mix_hex(acc["accent"], "#ffffff", .55)
    return c

QUOTES = [
    "Small steps every day lead to big results.",
    "Focus on progress, not perfection.",
    "Done is better than perfect.",
    "You don't have to be great to start, but you have to start to be great.",
    "Discipline is choosing what you want most over what you want now.",
    "One focused hour beats five distracted ones.",
    "Your future self is watching. Make them proud.",
]

class ProductivityApp(tk.Tk):
    """Main application object; owns views, theme, reminders and app services."""
    def __init__(self, database_path=None):
        super().__init__()
        self.title("Flowday | Smart Productivity")
        self.minsize(920, 620); self.geometry(f"1180x760+{max((self.winfo_screenwidth()-1180)//2,0)}+{max((self.winfo_screenheight()-760)//3,0)}")
        self.repo=SQLiteTaskRepository(database_path or (__import__('pathlib').Path.home()/".flowday"/"flowday.db"))
        self.priority=DeadlinePriorityStrategy(); self.theme,self.accent_name=self._load_settings(); self.page="Dashboard"; self.filter_var=None
        self.reminded=set(); self.current_user=None; self._rem_job=None; self.pomo=None; self._reset_pomo()
        self.show_auth_screen()

    def show_auth_screen(self, register=False):
        for child in self.winfo_children(): child.destroy()
        self.configure(bg="#f4f0ff")
        wrap=tk.Frame(self,bg="#f4f0ff"); wrap.pack(fill="both",expand=True)
        card=tk.Frame(wrap,bg="white",highlightbackground="#e4dcfa",highlightthickness=1); card.place(relx=.5,rely=.5,anchor="center")
        side=tk.Canvas(card,width=330,height=480,highlightthickness=0,bd=0); side.pack(side="left")
        for y in range(0,480,3): side.create_rectangle(0,y,330,y+3,fill=self._grad_color(ACCENTS["Lavender"]["grad"],y/480),outline="")
        side.create_text(34,72,text="✦  flowday",anchor="w",fill="#2e2a4d",font=("Segoe UI",26,"bold"))
        side.create_text(34,110,text="Plan smarter. Focus deeper.",anchor="w",fill="#4a4470",font=("Segoe UI",11))
        for i,(ic,title,sub) in enumerate([("✓","Smart priorities","Deadlines sort themselves"),("◔","Focus timer","Pomodoro with auto-logging"),("▥","Progress insights","Streaks and weekly trends")]):
            y=205+i*70; side.create_oval(34,y-17,68,y+17,fill="white",outline=""); side.create_text(51,y,text=ic,fill="#6d4fd8",font=("Segoe UI",12,"bold"))
            side.create_text(84,y-9,text=title,anchor="w",fill="#2e2a4d",font=("Segoe UI",11,"bold")); side.create_text(84,y+11,text=sub,anchor="w",fill="#4a4470",font=("Segoe UI",9))
        side.create_text(34,445,text="Small steps, steady progress.",anchor="w",fill="#4a4470",font=("Segoe UI",9,"italic"))
        form=tk.Frame(card,bg="white",padx=44,pady=38); form.pack(side="left",fill="y")
        tk.Label(form,text="Create your account" if register else "Welcome back",bg="white",fg="#292642",font=("Segoe UI",19,"bold")).pack(anchor="w")
        tk.Label(form,text="Start organising your day in a minute." if register else "Log in to continue your streak.",bg="white",fg="#7b7890",font=("Segoe UI",10)).pack(anchor="w",pady=(2,14))
        fields={}
        def add_field(label,secret=False):
            tk.Label(form,text=label,bg="white",fg="#57536d",font=("Segoe UI",9,"bold")).pack(anchor="w",pady=(8,3))
            ent=tk.Entry(form,width=32,relief="flat",bg="#f4f1fb",fg="#292642",insertbackground="#292642",highlightthickness=1,highlightbackground="#f4f1fb",highlightcolor="#a78bfa",show="●" if secret else "")
            ent.pack(ipady=9,fill="x"); fields[label]=ent
        if register: add_field("Full name")
        add_field("Username"); add_field("Password",True)
        def submit():
            try:
                if register:
                    user=self.repo.register_user(fields["Full name"].get(),fields["Username"].get(),fields["Password"].get())
                else:
                    user=self.repo.authenticate_user(fields["Username"].get(),fields["Password"].get())
                    if not user: raise ValueError("Incorrect username or password.")
                self.current_user=user; self.repo.set_user(user["id"])
                for child in self.winfo_children(): child.destroy()
                self._build_shell(); self.apply_theme(); self.show_page("Dashboard"); self._rem_job=self.after(15000,self._check_reminders)
            except ValueError as exc: messagebox.showerror("Account",str(exc),parent=self)
            except Exception as exc: messagebox.showerror("Account error",str(exc),parent=self)
        main=tk.Button(form,text="Create account" if register else "Login",command=submit,bg="#c4b5fd",fg="#2e2a4d",activebackground="#b4a2fa",activeforeground="#2e2a4d",relief="flat",bd=0,font=("Segoe UI",10,"bold"),cursor="hand2")
        main.pack(fill="x",pady=(22,10),ipady=10); main.bind("<Enter>",lambda e:main.configure(bg="#b4a2fa")); main.bind("<Leave>",lambda e:main.configure(bg="#c4b5fd"))
        tk.Button(form,text="Already have an account? Login" if register else "New here? Create an account",command=lambda:self.show_auth_screen(not register),bg="white",fg="#7561c4",activebackground="white",activeforeground="#5b49a8",relief="flat",bd=0,font=("Segoe UI",9,"bold"),cursor="hand2").pack()
        tk.Label(form,text="Passwords are stored securely as salted hashes.",bg="white",fg="#9691a8",font=("Segoe UI",8)).pack(side="bottom",pady=(16,0))
        for ent in fields.values(): ent.bind("<Return>",lambda e:submit())
        fields.get("Username",tk.Entry()).focus_set()

    def _build_shell(self):
        self.shell=tk.Frame(self); self.shell.pack(fill="both",expand=True)
        self.sidebar=tk.Frame(self.shell,width=220); self.sidebar.pack(side="left",fill="y"); self.sidebar.pack_propagate(False)
        self.brand=tk.Label(self.sidebar,text="✦  flowday",font=("Segoe UI",21,"bold")); self.brand.pack(anchor="w",padx=22,pady=(25,3))
        self.tagline=tk.Label(self.sidebar,text="YOUR PERSONAL WORKSPACE",font=("Segoe UI",8,"bold")); self.tagline.pack(anchor="w",padx=24,pady=(0,28))
        self.nav={}
        for name,icon in [("Dashboard","⌂"),("Tasks","✓"),("Study planner","◷"),("Focus timer","◔"),("Insights","▥")]:
            b=tk.Button(self.sidebar,text=f"  {icon}   {name}",anchor="w",relief="flat",bd=0,font=("Segoe UI",11),padx=12,pady=12,command=lambda n=name:self.show_page(n)); b.pack(fill="x",padx=12,pady=3); self.nav[name]=b
            b.bind("<Enter>",lambda e,n=name,w=b:w.configure(bg=self.c['panel']) if n!=self.page else None); b.bind("<Leave>",lambda e,n=name,w=b:w.configure(bg=self.c['bg']) if n!=self.page else None)
        self.spacer=tk.Frame(self.sidebar); self.spacer.pack(fill="both",expand=True)
        self.swatch_row=tk.Frame(self.sidebar); self.swatch_row.pack(anchor="w",padx=24,pady=(0,8))
        self.swatch_lbl=tk.Label(self.swatch_row,text="PALETTE",font=("Segoe UI",8,"bold")); self.swatch_lbl.pack(anchor="w",pady=(0,5))
        self.swatch_dots=tk.Frame(self.swatch_row); self.swatch_dots.pack(anchor="w"); self.swatches={}
        for nm in ACCENTS:
            cv=tk.Canvas(self.swatch_dots,width=28,height=28,highlightthickness=0,bd=0,cursor="hand2"); cv.pack(side="left",padx=(0,6)); cv.bind("<Button-1>",lambda e,n=nm:self.set_accent(n)); self.swatches[nm]=cv
        self.theme_btn=tk.Button(self.sidebar,text="☼  Switch to light mode",anchor="w",relief="flat",bd=0,font=("Segoe UI",10),padx=15,pady=10,command=self.toggle_theme); self.theme_btn.pack(fill="x",padx=12,pady=(8,2))
        self.logout_btn=tk.Button(self.sidebar,text="⏻  Log out",anchor="w",relief="flat",bd=0,font=("Segoe UI",10),padx=15,pady=10,command=self.logout); self.logout_btn.pack(fill="x",padx=12,pady=(2,8))
        self.side_hint=tk.Label(self.sidebar,text="Small steps, steady progress.\nYou’ve got this ✨",justify="left",font=("Segoe UI",9)); self.side_hint.pack(anchor="w",padx=24,pady=(0,24))
        self.main=tk.Frame(self.shell); self.main.pack(side="left",fill="both",expand=True)
        self.top=tk.Frame(self.main,height=72); self.top.pack(fill="x"); self.top.pack_propagate(False)
        self.page_title=tk.Label(self.top,text="",font=("Segoe UI",20,"bold")); self.page_title.pack(side="left",padx=28,pady=19)
        self.date_label=tk.Label(self.top,text=f"{self.current_user['full_name']}  ·  {date.today().strftime('%A, %B %d')}",font=("Segoe UI",10)); self.date_label.pack(side="right",padx=28)
        self.content=tk.Frame(self.main); self.content.pack(fill="both",expand=True,padx=24,pady=(4,22))

    def apply_theme(self):
        c=build_palette(self.theme,self.accent_name); self.c=c; self.configure(bg=c['bg'])
        for w in (self.shell,self.sidebar,self.main,self.top,self.content): w.configure(bg=c['bg'])
        self.brand.configure(bg=c['bg'],fg=c['accent_ink']); self.side_hint.configure(bg=c['bg'],fg=c['muted'])
        self.top.configure(bg=c['bg']); self.page_title.configure(bg=c['bg'],fg=c['text']); self.date_label.configure(bg=c['bg'],fg=c['muted'])
        for name,b in self.nav.items(): b.configure(bg=c['accent'] if name==self.page else c['bg'],fg=c['on_accent'] if name==self.page else c['muted'],activebackground=c['accent'],activeforeground=c['on_accent'])
        self.theme_btn.configure(text="☾  Switch to dark mode" if self.theme=="light" else "☼  Switch to light mode",bg=c['bg'],fg=c['muted'],activebackground=c['panel'])
        self.swatch_row.configure(bg=c['bg']); self.swatch_lbl.configure(bg=c['bg'],fg=c['muted']); self.swatch_dots.configure(bg=c['bg'])
        for nm,cv in self.swatches.items():
            cv.configure(bg=c['bg']); cv.delete("all"); cv.create_oval(3,3,25,25,fill=ACCENTS[nm]["accent"],outline=c['text'] if nm==self.accent_name else c['bg'],width=2)
        self.spacer.configure(bg=c['bg']); self.tagline.configure(bg=c['bg'],fg=c['muted'])
        self.logout_btn.configure(bg=c['bg'],fg=c['muted'],activebackground=c['panel'],activeforeground=c['text'])
        style=ttk.Style(self); style.theme_use("clam")
        style.configure("Treeview",background=c['panel'],fieldbackground=c['panel'],foreground=c['text'],rowheight=34,borderwidth=0,font=("Segoe UI",10))
        style.configure("Treeview.Heading",background=c['panel2'],foreground=c['muted'],font=("Segoe UI",9,"bold"),relief="flat")
        style.map("Treeview",background=[("selected",c['accent'])],foreground=[("selected",c["on_accent"])])
        style.configure("TCombobox",fieldbackground=c['panel'],background=c['panel'],foreground=c['text'])
        style.map("TCombobox",fieldbackground=[("readonly",c['panel'])],background=[("readonly",c['panel2']),("active",c['line'])],foreground=[("readonly",c['text'])],arrowcolor=[("readonly",c['accent_ink'])],selectbackground=[("readonly",c['panel'])],selectforeground=[("readonly",c['text'])])
        style.configure("TCombobox",bordercolor=c['line'],lightcolor=c['panel'],darkcolor=c['panel'],arrowcolor=c['accent_ink'])
        self.option_add("*TCombobox*Listbox.background",c['panel']); self.option_add("*TCombobox*Listbox.foreground",c['text']); self.option_add("*TCombobox*Listbox.selectBackground",c['accent']); self.option_add("*TCombobox*Listbox.selectForeground",c['on_accent'])

    def toggle_theme(self): self.theme="light" if self.theme=="dark" else "dark"; self._save_settings(); self.apply_theme(); self.show_page(self.page)
    def set_accent(self,name): self.accent_name=name; self._save_settings(); self.apply_theme(); self.show_page(self.page)
    def _load_settings(self):
        try:
            d=json.loads((Path.home()/".flowday"/"settings.json").read_text(encoding="utf-8"))
            return (d.get("theme") if d.get("theme") in BASE else "light"), (d.get("accent") if d.get("accent") in ACCENTS else "Lavender")
        except Exception: return "light","Lavender"
    def _save_settings(self):
        try:
            p=Path.home()/".flowday"/"settings.json"; p.parent.mkdir(parents=True,exist_ok=True)
            p.write_text(json.dumps({"theme":self.theme,"accent":self.accent_name}),encoding="utf-8")
        except Exception: pass
    def ink(self,color):
        for k in ("cyan","green","orange","red","accent"):
            if self.c[k]==color: return self.c[k+"_ink"]
        return color
    def clear(self):
        for child in self.content.winfo_children(): child.destroy()
    def show_page(self,name):
        self.page=name; self.page_title.configure(text=name); self.apply_theme(); self.clear()
        {"Dashboard":self.dashboard,"Tasks":self.tasks_page,"Study planner":self.planner_page,"Focus timer":self.focus_page,"Insights":self.insights_page}[name]()

    @staticmethod
    def _mix(c1,c2,t):
        a_=[int(c1[i:i+2],16) for i in (1,3,5)]; b_=[int(c2[i:i+2],16) for i in (1,3,5)]
        return "#%02x%02x%02x"%tuple(int(a_[i]+(b_[i]-a_[i])*t) for i in range(3))
    def _grad_color(self,stops,t):
        n=len(stops)-1; t=min(max(t,0),1)*n; i=min(int(t),n-1); return self._mix(stops[i],stops[i+1],t-i)
    def _gradient(self,cv,w,h,stops,step=3):
        for x in range(0,w,step): cv.create_rectangle(x,0,x+step,h,fill=self._grad_color(stops,x/max(w-1,1)),outline="")
    @staticmethod
    def _round_rect(cv,x1,y1,x2,y2,r=12,**kw):
        r=max(min(r,(x2-x1)/2,(y2-y1)/2),0.5)
        pts=[x1+r,y1,x2-r,y1,x2,y1,x2,y1+r,x2,y2-r,x2,y2,x2-r,y2,x1+r,y2,x1,y2,x1,y2-r,x1,y1+r,x1,y1]
        return cv.create_polygon(pts,smooth=True,**kw)
    @staticmethod
    def _ring(cv,cx,cy,r,width,frac,track,color):
        cv.create_oval(cx-r,cy-r,cx+r,cy+r,outline=track,width=width)
        if frac>0: cv.create_arc(cx-r,cy-r,cx+r,cy+r,start=90,extent=-359.9*min(frac,1),style="arc",outline=color,width=width)
    def toast(self,msg,kind="ok"):
        try:
            if getattr(self,"_toast",None) and self._toast.winfo_exists(): self._toast.destroy()
            col=self.c['green'] if kind=="ok" else self.c['accent']
            self._toast=tk.Label(self,text=msg,bg=col,fg=self.c['on_accent'],font=("Segoe UI",10,"bold"),padx=18,pady=11)
            self._toast.place(relx=1,rely=1,anchor="se",x=-28,y=-28); self._toast.lift(); t=self._toast
            self.after(2400,lambda:t.destroy() if t.winfo_exists() else None)
        except tk.TclError: pass

    def card(self,parent,padx=0,pady=0):
        f=tk.Frame(parent,bg=self.c['panel'],highlightbackground=self.c['line'],highlightthickness=1); f.pack(fill="both",expand=True,padx=padx,pady=pady); return f
    def label(self,parent,text, size=10, color=None, weight="normal", **kw):
        return tk.Label(parent,text=text,bg=self.c['panel'],fg=color or self.c['text'],font=("Segoe UI",size,weight),**kw)
    def button(self,parent,text,command,primary=False):
        base=self.c['accent'] if primary else self.c['panel2']; hov=self._mix(base,self.c['text'],.10) if primary else self.c['line']
        b=tk.Button(parent,text=text,command=command,relief="flat",bd=0,bg=base,fg=self.c['on_accent'] if primary else self.c['text'],activebackground=self.c['accent'],activeforeground=self.c['on_accent'],font=("Segoe UI",9,"bold"),padx=14,pady=9,cursor="hand2")
        b.bind("<Enter>",lambda e:b.configure(bg=hov)); b.bind("<Leave>",lambda e:b.configure(bg=base)); return b

    def dashboard(self):
        tasks=self.repo.list_tasks(); open_tasks=[t for t in tasks if not t.completed]; today=date.today().isoformat()
        done_today=sum(1 for t in tasks if t.completed and t.completed_at[:10]==today)
        sessions=self.repo.list_sessions(today); study=sum(int(s['duration_minutes']) for s in sessions if s['completed'])
        hour=datetime.now().hour; greet="Good morning" if hour<12 else "Good afternoon" if hour<17 else "Good evening"
        first=self.current_user['full_name'].split()[0]; streak=completion_streak(tasks)
        total=len(tasks); done_all=total-len(open_tasks); pct=done_all/total if total else 0
        hero=tk.Canvas(self.content,height=150,highlightthickness=0,bd=0); hero.pack(fill="x",pady=(0,16)); anim={"f":0.0}
        def draw_hero(_e=None):
            try:
                c=self.c; w=max(hero.winfo_width(),700); hero.delete("all"); self._gradient(hero,w,150,c['grad'])
                hero.create_text(30,40,text=f"{greet}, {first}!",anchor="w",fill=c['on_accent'],font=("Segoe UI",22,"bold"))
                hero.create_text(30,74,text="A clear plan turns big goals into small wins.",anchor="w",fill=c['on_accent'],font=("Segoe UI",10))
                badge=f"★  {streak}-day streak" if streak else "Complete a task to start a streak"; bw=len(badge)*7+34
                self._round_rect(hero,30,100,30+bw,128,14,fill=c['panel'],outline=""); hero.create_text(30+bw/2,114,text=badge,fill=c['accent_ink'],font=("Segoe UI",9,"bold"))
                cx,cy,r=w-90,64,38; hero.create_oval(cx-r-14,cy-r-14,cx+r+14,cy+r+14,fill=c['panel'],outline="")
                self._ring(hero,cx,cy,r,9,anim["f"],c['panel2'],c['accent_ink'])
                hero.create_text(cx,cy,text=f"{round(anim['f']*100)}%",fill=c['text'],font=("Segoe UI",16,"bold")); hero.create_text(cx,cy+r+28,text=f"{done_all}/{total} tasks done",fill=c['on_accent'],font=("Segoe UI",9,"bold"))
            except tk.TclError: pass
        def step():
            try:
                if not hero.winfo_exists(): return
            except tk.TclError: return
            anim["f"]=min(pct,anim["f"]+0.035); draw_hero()
            if anim["f"]<pct: self.after(16,step)
        hero.bind("<Configure>",draw_hero); step()
        row=tk.Frame(self.content,bg=self.c['bg']); row.pack(fill="x",pady=(0,16))
        self.metric(row,"Open tasks",str(len(open_tasks)),"◉",self.c['cyan']); self.metric(row,"Completed today",str(done_today),"✓",self.c['green']); self.metric(row,"Study time",f"{study//60}h {study%60:02d}m","◷",self.c['orange']); self.metric(row,"Due soon",str(sum(1 for t in open_tasks if t.deadline and t.deadline<= (date.today()+timedelta(days=2)).isoformat())),"!",self.c['red'])
        lower=tk.Frame(self.content,bg=self.c['bg']); lower.pack(fill="both",expand=True)
        left=tk.Frame(lower,bg=self.c['bg']); left.pack(side="left",fill="both",expand=True,padx=(0,8)); right=tk.Frame(lower,bg=self.c['bg'],width=280); right.pack(side="left",fill="both",expand=True,padx=(8,0))
        box=self.card(left); self.label(box,"Priority focus",14,weight="bold").pack(anchor="w",padx=18,pady=(17,12))
        urgent=sorted(open_tasks,key=lambda t:(0 if self.priority.calculate(t)=="High" else 1 if self.priority.calculate(t)=="Medium" else 2,t.deadline or "9999"))[:5]
        if not urgent: self.label(box,"Nothing urgent. Add a task to get started ✨",10,self.c['muted']).pack(anchor="w",padx=18,pady=15)
        for t in urgent: self.task_line(box,t)
        box2=self.card(right); self.label(box2,"Quick actions",14,weight="bold").pack(anchor="w",padx=18,pady=(17,12)); self.button(box2,"＋  Add a task",lambda:self.task_dialog(),True).pack(fill="x",padx=16,pady=5); self.button(box2,"◷  Plan a study session",lambda:self.show_page("Study planner")).pack(fill="x",padx=16,pady=5); self.button(box2,"▥  View productivity",lambda:self.show_page("Insights")).pack(fill="x",padx=16,pady=5); self.button(box2,"◔  Start focus timer",lambda:self.show_page("Focus timer")).pack(fill="x",padx=16,pady=5); self.button(box2,"✦  Load sample data",self.load_demo).pack(fill="x",padx=16,pady=5)
        self.label(box2,"Thought for today",9,self.c['cyan_ink'],"bold").pack(anchor="w",padx=18,pady=(22,4)); self.label(box2,QUOTES[date.today().toordinal()%len(QUOTES)],10,self.c['muted'],wraplength=225,justify="left").pack(anchor="w",padx=18,pady=(0,18))

    def metric(self,parent,title,value,icon,color):
        tint=self._mix(color,self.c['panel'],.55 if self.theme=="light" else .72)
        f=tk.Frame(parent,bg=tint,highlightbackground=self.c['line'],highlightthickness=1); f.pack(side="left",fill="x",expand=True,padx=5)
        tk.Frame(f,bg=color,height=4).pack(fill="x")
        tk.Label(f,text=icon,font=("Segoe UI",17,"bold"),bg=tint,fg=self.ink(color)).pack(anchor="w",padx=14,pady=(8,0))
        tk.Label(f,text=value,font=("Segoe UI",20,"bold"),bg=tint,fg=self.c['text']).pack(anchor="w",padx=14)
        tk.Label(f,text=title,font=("Segoe UI",9),bg=tint,fg=self.c['muted']).pack(anchor="w",padx=14,pady=(0,12))
    def task_line(self,parent,t):
        row=tk.Frame(parent,bg=self.c['panel']); row.pack(fill="x",padx=18,pady=5)
        color={"High":self.c['red_ink'],"Medium":self.c['orange_ink'],"Low":self.c['green_ink']}[self.priority.calculate(t)]
        tk.Label(row,text="●",bg=self.c['panel'],fg=color).pack(side="left",padx=(0,9)); tk.Label(row,text=t.title,bg=self.c['panel'],fg=self.c['text'],font=("Segoe UI",10)).pack(side="left"); late=bool(t.deadline) and t.deadline<date.today().isoformat() and not t.completed; tk.Label(row,text=(f"Overdue · {t.deadline}" if late else (t.deadline or "No deadline")),bg=self.c['panel'],fg=self.c['red_ink'] if late else self.c['muted'],font=("Segoe UI",9,"bold" if late else "normal")).pack(side="right")

    def tasks_page(self):
        bar=tk.Frame(self.content,bg=self.c['bg']); bar.pack(fill="x",pady=(0,12)); self.filter_var=tk.StringVar(value="All tasks")
        cb=ttk.Combobox(bar,textvariable=self.filter_var,values=["All tasks","Active","Completed"],state="readonly",width=15); cb.pack(side="left"); cb.bind("<<ComboboxSelected>>",lambda e:self.refresh_tasks())
        self.button(bar,"＋  New task",self.task_dialog,True).pack(side="right"); self.button(bar,"⇩  Export CSV",self.export_csv).pack(side="right",padx=8)
        self.search_var=tk.StringVar(); tk.Label(bar,text="Search",bg=self.c['bg'],fg=self.c['muted'],font=("Segoe UI",9)).pack(side="left",padx=(16,6))
        tk.Entry(bar,textvariable=self.search_var,bg=self.c['panel'],fg=self.c['text'],insertbackground=self.c['text'],relief="flat",width=26,highlightthickness=1,highlightbackground=self.c['line'],highlightcolor=self.c['accent']).pack(side="left",ipady=6)
        self.search_var.trace_add("write",lambda *args:self.refresh_tasks())
        box=self.card(self.content); cols=("title","category","deadline","priority","time","status"); self.tree=ttk.Treeview(box,columns=cols,show="headings",selectmode="browse")
        for col,title,width in [("title","TASK",260),("category","CATEGORY",120),("deadline","DEADLINE",130),("priority","SMART PRIORITY",130),("time","ESTIMATE",100),("status","STATUS",100)]: self.tree.heading(col,text=title); self.tree.column(col,width=width,anchor="w")
        self.tree.pack(fill="both",expand=True,padx=12,pady=12); self.tree.bind("<Double-1>",lambda e:self.edit_selected())
        actions=tk.Frame(box,bg=self.c['panel']); actions.pack(fill="x",padx=12,pady=(0,12)); self.button(actions,"Edit",self.edit_selected).pack(side="left",padx=3); self.button(actions,"Mark complete / reopen",self.toggle_selected).pack(side="left",padx=3); self.button(actions,"Delete",self.delete_selected).pack(side="left",padx=3); self.refresh_tasks()
    def refresh_tasks(self):
        if not hasattr(self,"tree") or not self.tree.winfo_exists(): return
        self.tree.tag_configure("overdue",foreground=self.c['red_ink']); self.tree.tag_configure("done",foreground=self.c['muted']); self.tree.tag_configure("odd",background=self.c['panel2'])
        for x in self.tree.get_children(): self.tree.delete(x)
        flt=self.filter_var.get() if self.filter_var else "All tasks"; today=date.today().isoformat(); shown=0
        q=self.search_var.get().strip().lower() if getattr(self,"search_var",None) else ""
        sym={"High":"▲  High","Medium":"●  Medium","Low":"▼  Low"}
        for t in self.repo.list_tasks():
            if flt=="Active" and t.completed or flt=="Completed" and not t.completed: continue
            if q and q not in f"{t.title} {t.category} {t.notes}".lower(): continue
            late=bool(t.deadline) and t.deadline<today and not t.completed
            status="✓ Completed" if t.completed else "Overdue" if late else "In progress"
            tags=(("done",) if t.completed else ("overdue",) if late else ())+(("odd",) if shown%2 else ()); shown+=1
            pr=self.priority.calculate(t)
            self.tree.insert("","end",iid=str(t.id),tags=tags,values=(t.title,t.category,t.deadline or "—",sym.get(pr,pr),f"{t.estimated_minutes} min",status))
    def export_csv(self):
        path=filedialog.asksaveasfilename(parent=self,defaultextension=".csv",initialfile="flowday_tasks.csv",filetypes=[("CSV file","*.csv")])
        if not path: return
        try:
            with open(path,"w",newline="",encoding="utf-8-sig") as f:
                w=csv.writer(f); w.writerow(["Title","Category","Deadline","Priority","Estimate (min)","Status","Notes"])
                for t in self.repo.list_tasks(): w.writerow([t.title,t.category,t.deadline,self.priority.calculate(t),t.estimated_minutes,"Completed" if t.completed else "Open",t.notes])
            messagebox.showinfo("Export complete",f"Saved to:\n{path}",parent=self)
        except OSError as exc: messagebox.showerror("Export failed",str(exc),parent=self)
    def selected_task(self):
        sel=self.tree.selection() if hasattr(self,"tree") else ()
        if not sel: messagebox.showinfo("Select a task","Choose a task row first."); return None
        return next((t for t in self.repo.list_tasks() if str(t.id)==sel[0]),None)
    def task_dialog(self,task=None):
        win=tk.Toplevel(self); win.title("Edit task" if task else "New task"); win.transient(self); win.grab_set(); win.configure(bg=self.c['bg']); win.resizable(False,False)
        body=tk.Frame(win,bg=self.c['panel'],padx=22,pady=18); body.pack(fill="both",expand=True,padx=12,pady=12)
        tk.Label(body,text="Edit task" if task else "Create a task",bg=self.c['panel'],fg=self.c['text'],font=("Segoe UI",16,"bold")).grid(row=0,column=0,columnspan=2,sticky="w",pady=(0,12))
        fields={}
        def lbl(text,row): tk.Label(body,text=text,bg=self.c['panel'],fg=self.c['muted'],font=("Segoe UI",9,"bold")).grid(row=row,column=0,sticky="w",pady=5)
        def entry(label,row,default=""):
            lbl(label,row); v=tk.StringVar(value=default); e=tk.Entry(body,textvariable=v,bg=self.c['panel2'],fg=self.c['text'],insertbackground=self.c['text'],relief="flat",width=32); e.grid(row=row,column=1,sticky="ew",pady=5,ipady=7); fields[label]=v
        def combo(label,row,values,default,readonly=True):
            lbl(label,row); v=tk.StringVar(value=default); ttk.Combobox(body,textvariable=v,values=values,state="readonly" if readonly else "normal",width=30).grid(row=row,column=1,sticky="ew",pady=5,ipady=4); fields[label]=v
        entry("Title",1,task.title if task else "")
        combo("Category",2,["General","College","Study","Project","Personal","Health","Creative"],task.category if task else "General",False)
        lbl("Deadline (YYYY-MM-DD)",3); dv=tk.StringVar(value=task.deadline if task else ""); fields["Deadline (YYYY-MM-DD)"]=dv
        drow=tk.Frame(body,bg=self.c['panel']); drow.grid(row=3,column=1,sticky="ew",pady=5)
        tk.Entry(drow,textvariable=dv,bg=self.c['panel2'],fg=self.c['text'],insertbackground=self.c['text'],relief="flat",width=14).pack(side="left",fill="x",expand=True,ipady=7)
        for txt,days in (("Today",0),("Tomorrow",1),("+7 days",7)):
            tk.Button(drow,text=txt,command=lambda n=days:dv.set((date.today()+timedelta(days=n)).isoformat()),relief="flat",bd=0,bg=self.c['panel2'],fg=self.c['text'],activebackground=self.c['accent'],activeforeground=self.c['on_accent'],font=("Segoe UI",8,"bold"),padx=8,pady=6,cursor="hand2").pack(side="left",padx=(4,0))
        entry("Estimate (minutes)",4,str(task.estimated_minutes if task else 30))
        combo("Priority",5,["Auto","Low","Medium","High"],task.priority_override if task else "Auto")
        entry("Notes",6,task.notes if task else "")
        def save():
            title=fields['Title'].get().strip(); due=fields['Deadline (YYYY-MM-DD)'].get().strip()
            if not title: messagebox.showerror("Missing title","Please enter a task title.",parent=win); return
            try:
                mins=int(fields['Estimate (minutes)'].get());
                if mins<1 or mins>10080: raise ValueError
                if due: date.fromisoformat(due)
                t=Task(task.id if task else None,title,fields['Category'].get(),due,mins,fields['Notes'].get(),task.completed if task else False,task.created_at if task else "",fields['Priority'].get(),task.completed_at if task else "")
                if t.priority_override not in {"Auto","Low","Medium","High"}: raise ValueError
                self.repo.save_task(t); win.destroy(); self.show_page("Tasks"); self.toast("✓  Task saved")
            except ValueError: messagebox.showerror("Check task details","Use a valid date (YYYY-MM-DD), estimate from 1 to 10080, and priority Auto/Low/Medium/High.",parent=win)
            except Exception as exc: messagebox.showerror("Could not save task",str(exc),parent=win)
        self.button(body,"Save task",save,True).grid(row=7,column=1,sticky="e",pady=(12,0)); self.button(body,"Cancel",win.destroy).grid(row=7,column=0,sticky="w",pady=(12,0))
    def edit_selected(self):
        t=self.selected_task()
        if t: self.task_dialog(t)
    def toggle_selected(self):
        t=self.selected_task()
        if t:
            t.mark_incomplete() if t.completed else t.mark_complete(); self.repo.save_task(t); self.refresh_tasks(); self.toast("✓  Task completed. Great job!") if t.completed else self.toast("Task reopened","info")
    def delete_selected(self):
        t=self.selected_task()
        if t and messagebox.askyesno("Delete task",f"Delete ‘{t.title}’ permanently?"):
            self.repo.delete_task(t.id); self.refresh_tasks()

    def planner_page(self):
        head=tk.Frame(self.content,bg=self.c['bg']); head.pack(fill="x",pady=(0,14))
        tk.Label(head,text="Build a balanced day with focused study blocks.",bg=self.c['bg'],fg=self.c['muted'],font=("Segoe UI",10)).pack(side="left")
        self.button(head,"＋  Add study block",self.session_dialog,True).pack(side="right")
        row=tk.Frame(self.content,bg=self.c['bg']); row.pack(fill="x",pady=(0,14))
        sessions=self.repo.list_sessions(date.today().isoformat()); completed=sum(int(s['duration_minutes']) for s in sessions if s['completed']); planned=sum(int(s['duration_minutes']) for s in sessions)
        self.metric(row,"Planned today",f"{planned//60}h {planned%60:02d}m","◷",self.c['cyan']); self.metric(row,"Focused time",f"{completed//60}h {completed%60:02d}m","✓",self.c['green']); self.metric(row,"Study blocks",str(len(sessions)),"▤",self.c['orange'])
        box=self.card(self.content); self.label(box,"Today's study plan",14,weight="bold").pack(anchor="w",padx=18,pady=(16,10))
        if not sessions: self.label(box,"Your day is a blank page. Add your first study block to get started.",10,self.c['muted']).pack(anchor="w",padx=18,pady=18)
        for s in sessions:
            line=tk.Frame(box,bg=self.c['panel2']); line.pack(fill="x",padx=15,pady=5); tk.Frame(line,bg=self.c['green'] if s['completed'] else self.c['accent'],width=5).pack(side="left",fill="y")
            time=s['start_time'][11:16] if len(s['start_time'])>=16 else s['start_time']
            tk.Label(line,text=time,bg=self.c['panel2'],fg=self.c['accent_ink'],font=("Segoe UI",12,"bold"),width=8).pack(side="left",padx=12,pady=12)
            text=tk.Frame(line,bg=self.c['panel2']); text.pack(side="left",fill="x",expand=True,pady=8)
            tk.Label(text,text=s['subject'],bg=self.c['panel2'],fg=self.c['text'],font=("Segoe UI",11,"bold")).pack(anchor="w")
            tk.Label(text,text=f"{s['duration_minutes']} min  ·  {s['notes'] or 'Focus session'}",bg=self.c['panel2'],fg=self.c['muted'],font=("Segoe UI",9)).pack(anchor="w")
            self.button(line,"✓ Done" if not s['completed'] else "↺ Reopen",lambda sid=s['id']:self.toggle_session(sid)).pack(side="right",padx=6)
            self.button(line,"Delete",lambda sid=s['id']:self.delete_session(sid)).pack(side="right",padx=6)
    def session_dialog(self):
        win=tk.Toplevel(self); win.title("Plan a study block"); win.transient(self); win.grab_set(); win.configure(bg=self.c['bg']); win.resizable(False,False)
        body=tk.Frame(win,bg=self.c['panel'],padx=22,pady=18); body.pack(fill="both",expand=True,padx=12,pady=12)
        tk.Label(body,text="New study block",bg=self.c['panel'],fg=self.c['text'],font=("Segoe UI",16,"bold")).grid(row=0,column=0,columnspan=2,sticky="w",pady=(0,12))
        defaults={"Subject":"","Start time":datetime.now().strftime("%H:%M"),"Duration (minutes)":"25","Notes":""}; vars={}
        for i,(label,val) in enumerate(defaults.items(),1):
            tk.Label(body,text=label,bg=self.c['panel'],fg=self.c['muted'],font=("Segoe UI",9,"bold")).grid(row=i,column=0,sticky="w",pady=5)
            vars[label]=tk.StringVar(value=val); tk.Entry(body,textvariable=vars[label],bg=self.c['panel2'],fg=self.c['text'],insertbackground=self.c['text'],relief="flat",width=30).grid(row=i,column=1,sticky="ew",pady=5,ipady=7)
        def save():
            try:
                subject=vars['Subject'].get().strip(); tm=vars['Start time'].get().strip(); mins=int(vars['Duration (minutes)'].get())
                if not subject or not 1<=mins<=720: raise ValueError
                datetime.strptime(tm,"%H:%M")
                self.repo.save_session(subject,f"{date.today().isoformat()} {tm}",mins,vars['Notes'].get()); win.destroy(); self.show_page("Study planner"); self.toast("✓  Study block added")
            except ValueError: messagebox.showerror("Check study block","Enter a subject, valid 24-hour time (HH:MM), and duration from 1 to 720 minutes.",parent=win)
            except Exception as exc: messagebox.showerror("Could not save study block",str(exc),parent=win)
        self.button(body,"Save block",save,True).grid(row=5,column=1,sticky="e",pady=(12,0)); self.button(body,"Cancel",win.destroy).grid(row=5,column=0,sticky="w",pady=(12,0))
    def toggle_session(self,sid):
        try: self.repo.toggle_session(sid); self.show_page("Study planner")
        except Exception as exc: messagebox.showerror("Update failed",str(exc))
    def delete_session(self,sid):
        if messagebox.askyesno("Delete study block","Remove this block from your plan?"):
            try: self.repo.delete_session(sid); self.show_page("Study planner")
            except Exception as exc: messagebox.showerror("Delete failed",str(exc))

    def insights_page(self):
        tasks=self.repo.list_tasks(); week=[date.today()-timedelta(days=i) for i in reversed(range(7))]
        completed=[]
        for day in week: completed.append(sum(1 for t in tasks if t.completed and t.completed_at[:10]==day.isoformat()))
        row=tk.Frame(self.content,bg=self.c['bg']); row.pack(fill="x",pady=(0,14))
        done=sum(1 for t in tasks if t.completed); total=len(tasks); rate=round(100*done/total) if total else 0
        self.metric(row,"Tasks completed",str(done),"✓",self.c['green']); self.metric(row,"Completion rate",f"{rate}%","◌",self.c['accent']); self.metric(row,"Total tasks",str(total),"▤",self.c['cyan']); self.metric(row,"Current streak",f"{completion_streak(tasks)} days","★",self.c['orange'])
        box=self.card(self.content); self.label(box,"Weekly completion trend",14,weight="bold").pack(anchor="w",padx=18,pady=(16,2)); self.label(box,"Completed tasks by day · based on completion activity",9,self.c['muted']).pack(anchor="w",padx=18)
        chart=tk.Canvas(box,height=200,bg=self.c['panel'],highlightthickness=0); chart.pack(fill="both",expand=True,padx=16,pady=10)
        def draw(_event=None):
            if not chart.winfo_exists(): return
            chart.delete("all"); w=max(chart.winfo_width(),420); h=max(chart.winfo_height(),220); left=42; right=w-15; top=18; bottom=h-35; peak=max(completed+[1]); [chart.create_line(left,bottom-(bottom-top)*k/3,right,bottom-(bottom-top)*k/3,fill=self.c["line"],dash=(2,5)) for k in (1,2,3)]; chart.create_line(left,bottom,right,bottom,fill=self.c["line"])
            for i,val in enumerate(completed):
                x=left+20+i*(right-left-30)/6; barh=(bottom-top)*val/peak if val else 3
                self._round_rect(chart,x-16,bottom-barh,x+16,bottom,min(7,barh/2),fill=self.c["accent"] if i<6 else self.c["cyan"],outline="")
                chart.create_text(x,bottom-barh-12,text=str(val),fill=self.c["text"],font=("Segoe UI",9,"bold"))
                chart.create_text(x,bottom+17,text=week[i].strftime("%a"),fill=self.c["muted"],font=("Segoe UI",9))
            chart.create_text(left,top,text=f"Peak: {peak}",anchor="nw",fill=self.c["muted"],font=("Segoe UI",8))
        chart.bind("<Configure>",draw); self.after(60,draw)
        cats={}
        for t in tasks: cats[t.category]=cats.get(t.category,0)+1
        topc=sorted(cats.items(),key=lambda kv:-kv[1])[:4]; peakc=max([n for _,n in topc]+[1])
        cbox=tk.Frame(self.content,bg=self.c['panel'],highlightbackground=self.c['line'],highlightthickness=1); cbox.pack(fill="x",pady=(12,0))
        self.label(cbox,"Tasks by category",13,weight="bold").pack(anchor="w",padx=18,pady=(12,6))
        if not topc: self.label(cbox,"No tasks yet. Add some to see your breakdown.",9,self.c['muted']).pack(anchor="w",padx=18,pady=(0,12))
        for name,n in topc:
            r=tk.Frame(cbox,bg=self.c['panel']); r.pack(fill="x",padx=18,pady=3)
            tk.Label(r,text=name,width=12,anchor="w",bg=self.c['panel'],fg=self.c['muted'],font=("Segoe UI",9)).pack(side="left")
            tr=tk.Frame(r,bg=self.c['panel2'],height=10); tr.pack(side="left",fill="x",expand=True,padx=8); tr.pack_propagate(False)
            tk.Frame(tr,bg=self.c['cyan']).place(relx=0,rely=0,relheight=1,relwidth=n/peakc)
            tk.Label(r,text=str(n),bg=self.c['panel'],fg=self.c['text'],font=("Segoe UI",9,"bold")).pack(side="left")
        tk.Frame(cbox,height=8,bg=self.c['panel']).pack()
        footer=tk.Frame(self.content,bg=self.c['bg']); footer.pack(fill="x",pady=(12,0)); tk.Label(footer,text="Keep your streak going",font=("Segoe UI",13,"bold"),bg=self.c['bg'],fg=self.c['text']).pack(side="left"); self.button(footer,"＋ Add task",lambda:self.task_dialog(),True).pack(side="right")

    def _check_reminders(self):
        """Show each due or overdue task once per run; reschedules while app is open."""
        if not self.current_user: return
        try:
            today=date.today().isoformat()
            due=[t for t in self.repo.list_tasks(False) if t.deadline and t.deadline<=today and t.id not in self.reminded]
            if due:
                self.reminded.update(t.id for t in due)
                preview="\n".join(f"• {t.title} ({'overdue' if t.deadline<today else 'due today'})" for t in due[:6])
                if len(due)>6: preview+=f"\n…and {len(due)-6} more"
                messagebox.showwarning("Deadline reminder",preview,parent=self)
        except Exception as exc: print(f"Reminder check failed: {exc}")
        self._rem_job=self.after(60000,self._check_reminders)

    # ------------------------------------------------------------ account / demo
    def logout(self):
        if self.pomo["running"] and not messagebox.askyesno("Log out","Your focus timer is still running. Log out anyway?",parent=self): return
        if self._rem_job: self.after_cancel(self._rem_job); self._rem_job=None
        self._reset_pomo(); self.reminded=set(); self.current_user=None; self.repo.user_id=None; self.page="Dashboard"
        self.show_auth_screen()

    def load_demo(self):
        if not messagebox.askyesno("Load sample data","Add sample tasks and study blocks to your account?\nGreat for demos. You can delete them anytime.",parent=self): return
        try: self.repo.seed_demo_data(); self.show_page(self.page); self.toast("✦  Sample data loaded","info")
        except Exception as exc: messagebox.showerror("Could not load sample data",str(exc),parent=self)

    # ------------------------------------------------------------- focus timer
    def _reset_pomo(self):
        if self.pomo and self.pomo.get("job"):
            try: self.after_cancel(self.pomo["job"])
            except Exception: pass
        self.pomo={"mode":"Focus","total":1500,"remaining":1500,"running":False,"job":None,"subject":"Focus session","log":True,"done":0}

    def focus_page(self):
        p=self.pomo; c=self.c
        box=self.card(self.content); inner=tk.Frame(box,bg=c['panel']); inner.place(relx=.5,rely=.5,anchor="center")
        self.pomo_time=tk.Canvas(inner,width=340,height=340,bg=c['panel'],highlightthickness=0); self.pomo_time.pack()
        ctr=tk.Frame(inner,bg=c['panel']); ctr.pack()
        self.pomo_btn=self.button(ctr,"▶  Start",self.pomo_toggle,True); self.pomo_btn.pack(side="left",padx=5); self.button(ctr,"↺  Reset",self.pomo_reset).pack(side="left",padx=5)
        pre=tk.Frame(inner,bg=c['panel']); pre.pack(pady=(16,4))
        for txt,mode,secs,log in (("Focus 25","Focus",1500,True),("Focus 50","Focus",3000,True),("Break 5","Break",300,False),("Break 15","Break",900,False),("Demo 10s","Focus",10,False)):
            self.button(pre,txt,lambda m=mode,s=secs,l=log:self.pomo_set(m,s,l)).pack(side="left",padx=4)
        sub=tk.Frame(inner,bg=c['panel']); sub.pack(pady=(14,4))
        tk.Label(sub,text="Studying:",bg=c['panel'],fg=c['muted'],font=("Segoe UI",9,"bold")).pack(side="left",padx=(0,8))
        sv=tk.StringVar(value=p["subject"]); sv.trace_add("write",lambda *args:p.__setitem__("subject",sv.get()))
        tk.Entry(sub,textvariable=sv,bg=c['panel2'],fg=c['text'],insertbackground=c['text'],relief="flat",width=28).pack(side="left",ipady=6)
        self.pomo_count=tk.Label(inner,text="",bg=c['panel'],fg=c['muted'],font=("Segoe UI",9)); self.pomo_count.pack(pady=(14,0))
        tk.Label(inner,text="Finished focus sessions are saved automatically to your Study planner.",bg=c['panel'],fg=c['muted'],font=("Segoe UI",8)).pack(pady=(4,0))
        self._pomo_refresh()

    def _pomo_refresh(self):
        p=self.pomo
        try:
            cv=getattr(self,"pomo_time",None)
            if cv is None or not cv.winfo_exists(): return
            c=self.c; col=c['accent'] if p['mode']=="Focus" else c['green']; ink=c['accent_ink'] if p['mode']=="Focus" else c['green_ink']; frac=1-p["remaining"]/p["total"] if p["total"] else 0
            cv.delete("all"); self._ring(cv,170,170,140,16,frac,c['panel2'],col)
            m,s=divmod(max(p["remaining"],0),60); state="RUNNING" if p["running"] else "READY" if p["remaining"]==p["total"] else "PAUSED"
            cv.create_text(170,152,text=f"{m:02d}:{s:02d}",fill=c['text'],font=("Segoe UI",54,"bold")); cv.create_text(170,208,text=f"{p['mode'].upper()}  ·  {state}",fill=ink,font=("Segoe UI",11,"bold"))
            self.pomo_btn.configure(text="❚❚  Pause" if p["running"] else "▶  Start"); self.pomo_count.configure(text=f"Focus sessions completed this run: {p['done']}")
        except tk.TclError: pass

    def pomo_set(self,mode,seconds,log=True):
        p=self.pomo
        if p["job"]:
            self.after_cancel(p["job"])
        p.update(mode=mode,total=seconds,remaining=seconds,running=False,job=None,log=log); self._pomo_refresh()

    def pomo_reset(self): self.pomo_set(self.pomo["mode"],self.pomo["total"],self.pomo["log"])

    def pomo_toggle(self):
        p=self.pomo
        if p["running"]:
            p["running"]=False
            if p["job"]: self.after_cancel(p["job"]); p["job"]=None
        elif p["remaining"]>0:
            p["running"]=True; p["job"]=self.after(1000,self._pomo_tick)
        self._pomo_refresh()

    def _pomo_tick(self):
        p=self.pomo; p["job"]=None
        if not p["running"]: return
        p["remaining"]-=1
        if p["remaining"]<=0: self._pomo_finish(); return
        p["job"]=self.after(1000,self._pomo_tick); self._pomo_refresh()

    def _pomo_finish(self):
        p=self.pomo; p["running"]=False; p["remaining"]=0; self._pomo_refresh()
        try: self.bell()
        except tk.TclError: pass
        if p["mode"]=="Focus" and p["log"]:
            try:
                mins=max(1,round(p["total"]/60)); start=(datetime.now()-timedelta(minutes=mins)).strftime("%Y-%m-%d %H:%M")
                sid=self.repo.save_session(p["subject"].strip() or "Focus session",start,mins,"Logged by focus timer"); self.repo.toggle_session(sid); p["done"]+=1
            except Exception as exc: print(f"Could not log focus session: {exc}")
        msg="Focus session complete. Take a short break!" if p["mode"]=="Focus" else "Break over. Ready for the next focus round?"
        messagebox.showinfo("Time's up!",msg,parent=self)
        p["remaining"]=p["total"]; self._pomo_refresh()
