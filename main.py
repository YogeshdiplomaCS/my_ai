import threading
import requests
from datetime import datetime

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.animation import Animation
from kivy.uix.screenmanager import ScreenManager, Screen, FadeTransition
from kivy.uix.scrollview import ScrollView
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.widget import Widget
from kivy.uix.popup import Popup
from kivy.graphics import Color, RoundedRectangle, Rectangle, Line
from kivy.metrics import dp, sp

# ── API CONFIG ──────────────────────────────────────────────
OPENROUTER_API_KEY  = "xxxxxxxxxxxxxxxxxxxxxxxx"   # ← paste your key
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1/chat/completions"

MODELS = [
    {"name": "GPT-4o Mini",      "id": "openai/gpt-4o-mini"},
    {"name": "Claude 3 Haiku",   "id": "anthropic/claude-3-haiku"},
    {"name": "Gemini Flash 1.5", "id": "google/gemini-flash-1.5"},
    {"name": "Llama 3 8B",       "id": "meta-llama/llama-3-8b-instruct"},
    {"name": "Mistral 7B",       "id": "mistralai/mistral-7b-instruct"},
    {"name": "DeepSeek Chat",    "id": "deepseek/deepseek-chat"},
]
DEFAULT_MODEL = MODELS[0]

# ── COLOUR PALETTE (normalised RGBA tuples) ─────────────────
BG   = (0.051, 0.051, 0.102, 1)   # #0D0D1A — deep dark
CARD = (0.075, 0.075, 0.169, 1)   # #13132B — card bg
INPT = (0.102, 0.102, 0.208, 1)   # #1A1A35 — input bg
ACNT = (0.659, 0.333, 0.969, 1)   # #A855F7 — vivid purple
TEAL = (0.024, 0.714, 0.831, 1)   # #06B6D4 — cyan teal
UBUB = (0.310, 0.275, 0.898, 1)   # #4F46E5 — user bubble
ABUB = (0.118, 0.106, 0.294, 1)   # #1E1B4B — AI bubble
TEXT = (0.945, 0.961, 0.980, 1)   # #F1F5F9 — near-white
MUTD = (0.580, 0.639, 0.722, 1)   # #94A3B8 — muted grey
GRN  = (0.133, 0.773, 0.369, 1)   # #22C55E — success green
ERR  = (0.937, 0.267, 0.267, 1)   # #EF4444 — error red

def f(c, a):
    """Return colour c with alpha a."""
    return (c[0], c[1], c[2], a)


# ── SAFE BACKGROUND HELPER ──────────────────────────────────
# NEVER calls canvas.clear() — stores rect ref and updates via bind
def add_bg(w, rgba, r=0):
    with w.canvas.before:
        Color(rgba=rgba)
        rect = (RoundedRectangle(pos=w.pos, size=w.size, radius=[r])
                if r else Rectangle(pos=w.pos, size=w.size))
    w.bind(pos =lambda *_: setattr(rect, "pos",  w.pos),
           size=lambda *_: setattr(rect, "size", w.size))
    return rect


# ── HELPER: QUICK LABEL ─────────────────────────────────────
def _lbl(text, fsz=14, color=None, h=24, bold=False, halign="center"):
    color = color if color is not None else TEXT
    l = Label(text=text, color=color, font_size=sp(fsz), bold=bold,
              halign=halign, valign="middle",
              size_hint_y=None, height=dp(h))
    l.bind(size=l.setter("text_size"))
    return l


# ── TOAST NOTIFICATION ──────────────────────────────────────
def toast(msg, color=None):
    color = color if color is not None else GRN
    try:
        fl = App.get_running_app()._fl
    except Exception:
        return
    w = min(dp(280), Window.width * 0.86)
    box = BoxLayout(size_hint=(None, None), size=(w, dp(40)),
                    pos=((Window.width - w) / 2, dp(22)),
                    padding=[dp(14), dp(6)], opacity=0)
    add_bg(box, f(color, 0.95), r=dp(20))
    l = Label(text=msg, color=TEXT, font_size=sp(13),
              halign="center", valign="middle")
    l.bind(size=l.setter("text_size"))
    box.add_widget(l)
    fl.add_widget(box)
    anim = (Animation(opacity=1, duration=0.22) +
            Animation(opacity=1, duration=1.8) +
            Animation(opacity=0, duration=0.3))
    anim.bind(on_complete=lambda *_: fl.remove_widget(box))
    anim.start(box)


# ── ROTATING ARC SPINNER ────────────────────────────────────
class ArcSpinner(Widget):
    """Pure Kivy animated spinner — no KivyMD needed."""
    def __init__(self, color=None, **kw):
        super().__init__(**kw)
        c = color if color is not None else ACNT
        self._ang = 0
        with self.canvas:
            Color(rgba=f(c, 0.18))
            self._tr = Line(
                ellipse=(self.x, self.y, self.width, self.height, 0, 359),
                width=dp(2.5))
            Color(rgba=c)
            self._ar = Line(
                ellipse=(self.x, self.y, self.width, self.height, 0, 80),
                width=dp(2.5))
        self.bind(pos=self._upd, size=self._upd)
        self._ev = Clock.schedule_interval(self._tick, 1 / 30)

    def _upd(self, *_):
        self._tr.ellipse = (self.x, self.y, self.width, self.height, 0, 359)
        self._ar.ellipse = (self.x, self.y, self.width, self.height,
                            self._ang, self._ang + 80)

    def _tick(self, *_):
        self._ang = (self._ang + 7) % 360
        self._upd()

    def stop(self):
        if hasattr(self, "_ev") and self._ev:
            self._ev.cancel()


# ── TYPING DOTS INDICATOR ───────────────────────────────────
class TypingDots(BoxLayout):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.orientation = "horizontal"
        self.size_hint_y = None
        self.height      = dp(40)
        self.padding     = [dp(10), dp(6)]
        self.spacing     = dp(5)

        av = Label(text="AI", color=TEXT, font_size=sp(9), bold=True,
                   halign="center", valign="middle",
                   size_hint=(None, None), size=(dp(22), dp(22)))
        add_bg(av, TEAL, r=dp(11))
        self.add_widget(av)

        self.add_widget(Label(text=" thinking ", color=MUTD, font_size=sp(11),
                              size_hint=(None, None), size=(dp(72), dp(28)),
                              halign="left", valign="middle"))
        self.dots = []
        for _ in range(3):
            d = Label(text="●", color=f(ACNT, 0.18), font_size=sp(10),
                      size_hint=(None, None), size=(dp(12), dp(28)))
            self.dots.append(d)
            self.add_widget(d)
        self._i  = 0
        self._ev = Clock.schedule_interval(self._tick, 0.38)

    def _tick(self, *_):
        for j, d in enumerate(self.dots):
            d.color = f(ACNT, 1.0 if j == self._i else 0.18)
        self._i = (self._i + 1) % 3

    def stop(self):
        self._ev.cancel()


# ── CHAT BUBBLE ─────────────────────────────────────────────
class Bubble(BoxLayout):
    def __init__(self, text, is_user=True, model_name="", ts="", **kw):
        super().__init__(**kw)
        self.orientation = "vertical"
        self.size_hint_y = None
        self.height      = dp(80)
        self.padding     = [dp(8), dp(2)]
        self.spacing     = dp(2)

        bub_col = UBUB if is_user else ABUB
        av_col  = UBUB if is_user else TEAL
        name    = "You" if is_user else (model_name or "YogeshAI")

        # ── avatar + name row
        nrow = BoxLayout(orientation="horizontal",
                         size_hint_y=None, height=dp(28), spacing=dp(6))
        av = Label(text="Y" if is_user else "AI", color=TEXT,
                   font_size=sp(9), bold=True, halign="center", valign="middle",
                   size_hint=(None, None), size=(dp(22), dp(22)))
        add_bg(av, f(av_col, 1), r=dp(11))

        nl = Label(text=f"{name}  ·  {ts}", color=MUTD, font_size=sp(10),
                   halign="left", valign="middle",
                   size_hint=(None, None), size=(dp(200), dp(22)))
        if is_user:
            nrow.add_widget(BoxLayout(size_hint_x=1))
            nrow.add_widget(nl)
            nrow.add_widget(av)
        else:
            nrow.add_widget(av)
            nrow.add_widget(nl)
            nrow.add_widget(BoxLayout(size_hint_x=1))

        # ── text bubble
        max_w = min(Window.width * 0.70, dp(290))
        tl = Label(text=text, color=TEXT, font_size=sp(14),
                   text_size=(max_w - dp(26), None),
                   halign="left", valign="top",
                   size_hint=(None, None), size=(max_w, dp(30)))

        wrap = BoxLayout(size_hint=(None, None), size=(max_w, dp(30)),
                         padding=[dp(12), dp(9), dp(12), dp(9)])
        add_bg(wrap, f(bub_col, 1), r=dp(14))
        wrap.add_widget(tl)

        def _rs(*_):
            ts2 = tl.texture_size
            h   = (ts2[1] + dp(18)) if (tl.texture and ts2[1] > 0) else dp(30)
            h   = max(h, dp(38))
            wrap.size   = (max_w, h)
            brow.height = h + dp(8)
            self.height = nrow.height + brow.height + dp(12)

        tl.bind(texture=_rs, texture_size=_rs)

        brow = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(46))
        if is_user:
            brow.padding = [0, 0, dp(10), 0]
            brow.add_widget(BoxLayout(size_hint_x=1))
            brow.add_widget(wrap)
        else:
            brow.padding = [dp(10), 0, 0, 0]
            brow.add_widget(wrap)
            brow.add_widget(BoxLayout(size_hint_x=1))

        self.add_widget(nrow)
        self.add_widget(brow)


# ── SPLASH SCREEN ───────────────────────────────────────────
class SplashScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.name = "splash"
        add_bg(self, BG)

        root = BoxLayout(orientation="vertical", padding=dp(40), spacing=dp(12))
        root.add_widget(BoxLayout(size_hint_y=1))

        # Glowing logo tile
        logo = BoxLayout(size_hint=(None, None), size=(dp(90), dp(90)))
        add_bg(logo, CARD, r=dp(22))
        logo.add_widget(_lbl("✦", 42, ACNT, 90, bold=True))
        lrow = BoxLayout(size_hint_y=None, height=dp(98))
        lrow.add_widget(BoxLayout(size_hint_x=1))
        lrow.add_widget(logo)
        lrow.add_widget(BoxLayout(size_hint_x=1))
        root.add_widget(lrow)

        root.add_widget(_lbl("YogeshAI", 34, TEXT, 50, bold=True))
        root.add_widget(_lbl("Your Intelligent Companion", 15, MUTD, 30))
        root.add_widget(_lbl(
            "Powered by OpenRouter  ·  Built by Yogesh\n"
            "Diploma in Computer Science & Engineering",
            11, f(ACNT, 0.85), 48))

        root.add_widget(BoxLayout(size_hint_y=1))

        spin = ArcSpinner(size_hint=(None, None), size=(dp(32), dp(32)))
        srow = BoxLayout(size_hint_y=None, height=dp(46))
        srow.add_widget(BoxLayout(size_hint_x=1))
        srow.add_widget(spin)
        srow.add_widget(BoxLayout(size_hint_x=1))
        root.add_widget(srow)

        root.add_widget(_lbl("Initialising…", 11, MUTD, 22))
        root.add_widget(BoxLayout(size_hint_y=None, height=dp(20)))
        self.add_widget(root)
        Clock.schedule_once(self._go, 2.8)

    def _go(self, *_):
        Animation(opacity=0, duration=0.4).start(self)
        Clock.schedule_once(
            lambda *_: setattr(self.manager, "current", "chat"), 0.45)


# ── CHAT SCREEN ─────────────────────────────────────────────
class ChatScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.name   = "chat"
        self.hist   = []
        self.model  = DEFAULT_MODEL
        self.typing = None
        add_bg(self, BG)
        self._build()

    def _build(self):
        root = BoxLayout(orientation="vertical")

        # ── top bar
        bar = BoxLayout(orientation="horizontal",
                        size_hint_y=None, height=dp(58),
                        padding=[dp(12), dp(8)], spacing=dp(6))
        add_bg(bar, CARD)

        title = Label(
            text="✦ YogeshAI", color=ACNT, font_size=sp(20), bold=True,
            halign="left", valign="middle",
            size_hint_x=None, width=dp(158),
            size_hint_y=None, height=dp(42))
        title.bind(size=title.setter("text_size"))
        bar.add_widget(title)
        bar.add_widget(BoxLayout(size_hint_x=1))

        # Model selector — Button, NOT MDButton (no KivyMD)
        self.mdl_btn = Button(
            text=self.model["name"], color=TEAL, font_size=sp(12),
            halign="center", valign="middle",
            background_normal="", background_down="",   # ← correct Kivy props
            background_color=(0, 0, 0, 0),
            size_hint_x=None, width=dp(140),
            size_hint_y=None, height=dp(42))
        self.mdl_btn.bind(
            size=self.mdl_btn.setter("text_size"),
            on_release=self._open_menu)
        bar.add_widget(self.mdl_btn)

        cog = Button(
            text="⚙", color=MUTD, font_size=sp(18),
            halign="center", valign="middle",
            background_normal="", background_down="",
            background_color=(0, 0, 0, 0),
            size_hint=(None, None), size=(dp(42), dp(42)))
        cog.bind(size=cog.setter("text_size"),
                 on_release=lambda *_: setattr(self.manager, "current", "settings"))
        bar.add_widget(cog)
        root.add_widget(bar)

        # ── quick-prompt chips
        self.chips = BoxLayout(orientation="horizontal",
                               size_hint_y=None, height=dp(44),
                               padding=[dp(8), dp(4)], spacing=dp(6))
        add_bg(self.chips, BG)
        for t in ["Write a poem", "Explain AI", "Tell a joke", "Code help"]:
            b = Button(
                text=t, color=TEAL, font_size=sp(11),
                background_normal="", background_down="",
                background_color=f(TEAL, 0.1),
                size_hint=(None, None), size=(dp(106), dp(32)))
            b.bind(on_release=lambda btn, txt=t: self._quick(txt))
            self.chips.add_widget(b)
        root.add_widget(self.chips)

        # ── scrollable chat
        self.scroll = ScrollView(do_scroll_x=False,
                                 bar_width=dp(2), bar_color=f(ACNT, 0.4))
        self.col = BoxLayout(orientation="vertical", size_hint_y=None,
                             spacing=dp(4), padding=[0, dp(8)])
        self.col.bind(minimum_height=self.col.setter("height"))
        self.scroll.add_widget(self.col)
        root.add_widget(self.scroll)
        self._welcome()

        # ── input bar
        ibar = BoxLayout(orientation="horizontal",
                         size_hint_y=None, height=dp(64),
                         padding=[dp(8), dp(8)], spacing=dp(6))
        add_bg(ibar, CARD)

        clr = Button(
            text="✕", color=MUTD, font_size=sp(16),
            halign="center", valign="middle",
            background_normal="", background_down="",
            background_color=(0, 0, 0, 0),
            size_hint=(None, None), size=(dp(40), dp(40)))
        clr.bind(size=clr.setter("text_size"), on_release=self._clear)
        ibar.add_widget(clr)

        # Rounded input: wrapper carries the rounded bg, TextInput is transparent
        inp_wrap = BoxLayout(size_hint_y=None, height=dp(46),
                             padding=[dp(2), dp(1)])
        add_bg(inp_wrap, INPT, r=dp(23))
        self.inp = TextInput(
            hint_text="Ask me anything…",
            background_normal="", background_active="",   # valid TextInput props
            background_color=(0, 0, 0, 0),
            foreground_color=TEXT, hint_text_color=MUTD,
            cursor_color=ACNT, font_size=sp(15),
            multiline=False, padding=[dp(12), dp(11)])
        self.inp.bind(on_text_validate=self._send)
        inp_wrap.add_widget(self.inp)
        ibar.add_widget(inp_wrap)

        # Send button — plain Kivy Button, background_down NOT background_active
        send = Button(
            text="▶", color=TEXT, font_size=sp(16),
            halign="center", valign="middle",
            background_normal="", background_down="",
            background_color=(0, 0, 0, 0),
            size_hint=(None, None), size=(dp(46), dp(46)))
        send.bind(size=send.setter("text_size"), on_release=self._send)
        add_bg(send, ACNT, r=dp(23))
        ibar.add_widget(send)
        root.add_widget(ibar)
        self.add_widget(root)

    def _welcome(self):
        w = _lbl(
            "✦  Hello! I'm YogeshAI\n"
            "Ask me anything — I'm here to help!",
            14, MUTD, 80)
        self.col.add_widget(w)

    def _open_menu(self, *_):
        content = BoxLayout(orientation="vertical",
                            spacing=dp(3), padding=dp(6))
        pop = Popup(
            title="Choose Model", content=content,
            size_hint=(0.82, None), height=dp(len(MODELS) * 50 + 90),
            title_color=TEXT, title_size=sp(15),
            separator_color=ACNT)
        for m in MODELS:
            b = Button(
                text=m["name"], color=TEXT, font_size=sp(13),
                background_normal="", background_down="",
                background_color=f(INPT, 1),
                size_hint_y=None, height=dp(44))
            b.bind(on_release=lambda btn, model=m:
                   [self._set_model(model), pop.dismiss()])
            content.add_widget(b)
        pop.open()

    def _set_model(self, m):
        self.model        = m
        self.mdl_btn.text = m["name"]
        toast(f"Model: {m['name']}")

    def _quick(self, txt):
        self.inp.text = txt
        self._send()

    def _send(self, *_):
        txt = self.inp.text.strip()
        if not txt:
            return
        self.inp.text      = ""
        self.chips.height  = 0
        self.chips.opacity = 0
        now = datetime.now().strftime("%I:%M %p")
        self.col.add_widget(Bubble(text=txt, is_user=True, ts=now))
        Clock.schedule_once(lambda *_: setattr(self.scroll, "scroll_y", 0), 0.1)
        self.hist.append({"role": "user", "content": txt})
        self.typing = TypingDots()
        self.col.add_widget(self.typing)
        Clock.schedule_once(lambda *_: setattr(self.scroll, "scroll_y", 0), 0.15)
        threading.Thread(target=self._api, daemon=True).start()

    def _api(self):
        try:
            r = requests.post(
                OPENROUTER_BASE_URL,
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type":  "application/json",
                    "HTTP-Referer":  "https://yogeshai.app",
                    "X-Title":       "YogeshAI"},
                json={
                    "model": self.model["id"],
                    "messages": [
                        {"role": "system",
                         "content": "You are YogeshAI, a helpful and friendly AI"
                                    " created by Yogesh (Diploma in CSE). Be concise and warm."}
                    ] + self.hist,
                    "max_tokens": 1024, "temperature": 0.8},
                timeout=30)
            r.raise_for_status()
            reply = r.json()["choices"][0]["message"]["content"]
            self.hist.append({"role": "assistant", "content": reply})
            Clock.schedule_once(lambda *_: self._reply(reply))
        except requests.exceptions.Timeout:
            Clock.schedule_once(lambda *_: self._err("Timed out — try again."))
        except requests.exceptions.ConnectionError:
            Clock.schedule_once(lambda *_: self._err("No internet connection."))
        except Exception as e:
            Clock.schedule_once(lambda *_: self._err(f"Error: {str(e)[:80]}"))

    def _reply(self, text):
        if self.typing:
            self.typing.stop()
            self.col.remove_widget(self.typing)
            self.typing = None
        now = datetime.now().strftime("%I:%M %p")
        self.col.add_widget(
            Bubble(text=text, is_user=False,
                   model_name=self.model["name"], ts=now))
        Clock.schedule_once(lambda *_: setattr(self.scroll, "scroll_y", 0), 0.15)

    def _err(self, msg):
        if self.typing:
            self.typing.stop()
            self.col.remove_widget(self.typing)
            self.typing = None
        toast(msg, ERR)

    def _clear(self, *_):
        self.col.clear_widgets()
        self.hist.clear()
        self.chips.height  = dp(44)
        self.chips.opacity = 1
        self._welcome()
        toast("Chat cleared ✓")


# ── SETTINGS SCREEN ─────────────────────────────────────────
class SettingsScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.name = "settings"
        add_bg(self, BG)
        self._build()

    def _build(self):
        root = BoxLayout(orientation="vertical")

        bar = BoxLayout(orientation="horizontal",
                        size_hint_y=None, height=dp(58),
                        padding=[dp(6), dp(8)], spacing=dp(6))
        add_bg(bar, CARD)

        back = Button(
            text="←", color=TEXT, font_size=sp(20),
            halign="center", valign="middle",
            background_normal="", background_down="",
            background_color=(0, 0, 0, 0),
            size_hint=(None, None), size=(dp(42), dp(42)))
        back.bind(size=back.setter("text_size"),
                  on_release=lambda *_: setattr(self.manager, "current", "chat"))
        bar.add_widget(back)
        bar.add_widget(_lbl("Settings", 20, TEXT, 42, bold=True, halign="left"))
        root.add_widget(bar)

        sv  = ScrollView()
        col = BoxLayout(orientation="vertical", spacing=dp(8),
                        padding=[dp(14), dp(14)], size_hint_y=None)
        col.bind(minimum_height=col.setter("height"))

        def section(t):
            col.add_widget(
                _lbl(t, 10, f(ACNT, 1), 24, bold=True, halign="left"))

        def row(icon, title, sub=""):
            card = BoxLayout(orientation="horizontal",
                             size_hint_y=None, height=dp(56 if sub else 46),
                             padding=[dp(10), dp(6)], spacing=dp(10))
            add_bg(card, CARD, r=dp(13))
            il = Label(text=icon, color=ACNT, font_size=sp(20),
                       halign="center", valign="middle",
                       size_hint=(None, None), size=(dp(32), dp(32)))
            card.add_widget(il)
            tb = BoxLayout(orientation="vertical")
            tb.add_widget(_lbl(title, 13, TEXT, 22, halign="left"))
            if sub:
                tb.add_widget(_lbl(sub, 10, MUTD, 18, halign="left"))
            card.add_widget(tb)
            col.add_widget(card)

        section("MODEL")
        row("🧠", "Default Model",   "GPT-4o Mini (OpenRouter)")
        row("🌡",  "Temperature",     "0.8 — Balanced & creative")

        section("APPEARANCE")
        row("🎨", "Theme",           "Dark gradient (always on)")
        row("✨", "Animations",      "Smooth transitions enabled")

        section("CHAT")
        row("📜", "History",         "In-session only — no database")
        row("🤖", "AI Persona",      "YogeshAI assistant active")

        section("ABOUT")
        row("👤", "Developer",       "Yogesh — Diploma in CSE")
        row("🔗", "API Provider",    "OpenRouter — Multi-model access")
        row("ℹ",  "Version",         "v1.0.0")

        sv.add_widget(col)
        root.add_widget(sv)
        self.add_widget(root)


# ── APP ENTRY POINT ─────────────────────────────────────────
class YogeshAIApp(App):
    def build(self):
        Window.clearcolor = BG     # dark window background
        # FloatLayout as root so toasts float above everything
        self._fl = FloatLayout()
        sm = ScreenManager(transition=FadeTransition(duration=0.4))
        sm.size_hint = (1, 1)
        sm.add_widget(SplashScreen())
        sm.add_widget(ChatScreen())
        sm.add_widget(SettingsScreen())
        sm.current = "splash"
        self._fl.add_widget(sm)
        return self._fl


if __name__ == "__main__":
    YogeshAIApp().run()
