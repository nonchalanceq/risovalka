from tkinter import *
from tkinter import colorchooser, messagebox, filedialog
from PIL import Image, ImageDraw
import os

BACKGROUND = '#eedde2'
BT_COLOR = '#fcfdfc'

class PaintWindow:
    def __init__(self, root):
        self.root = root
        self.root.title('Рисовалка')
        self.root.geometry('520x700')
        self.root.configure(bg='#efebec')

        #Cостояние кисти/холста
        self.color_background = 'white'
        self.default_color = 'black'
        self.prev_color = self.default_color
        self.paintbrush_color = self.default_color
        self.capstyle = 'round'
        self.smooth_change = False
        self.dash = None
        self.width = 3
        self.eraser_mode = False

        self.last_x, self.last_y = None, None

        #Векторная модель текущего рисунка
        self.model: list[dict] = []

        #История/будущее
        self.history: list[dict] = []
        self.future: list[dict] = []
        self._current_segments: list[tuple] = []

        #Холст
        self.canvas = Canvas(
            root, width=520, height=520, cursor="hand2",
            bg=self.color_background, highlightthickness=1, highlightbackground="#cccccc"
        )
        self.canvas.pack(pady=10)


        self.scale_factor = 4
        cw, ch = int(self.canvas['width']), int(self.canvas['height'])
        self._img = Image.new("RGB", (cw * self.scale_factor, ch * self.scale_factor), self.canvas["bg"])
        self._draw = ImageDraw.Draw(self._img)

        #Бинды
        self.canvas.bind("<Button-1>", self._start_stroke)
        self.canvas.bind("<B1-Motion>", self._draw_motion)
        self.canvas.bind("<ButtonRelease-1>", self._end_stroke)

        #Панель
        top = Frame(root, bg='#efebec')
        top.pack(pady=6)
        Button(top, text='Кисть', command=self._to_brush, bg=BACKGROUND).pack(side=LEFT, padx=4)
        Button(top, text='Выбрать цвет', command=self._choose_color, bg=BACKGROUND).pack(side=LEFT, padx=4)
        Button(top, text='Ластик', command=self._to_eraser, bg=BACKGROUND).pack(side=LEFT, padx=4)
        Button(top, text='Очистить', command=self._clear, bg=BACKGROUND).pack(side=LEFT, padx=4)
        Button(top, text='Отменить', command=self._undo, bg=BACKGROUND).pack(side=LEFT, padx=4)
        Button(top, text='Повторить', command=self._redo, bg=BACKGROUND).pack(side=LEFT, padx=4)
        Button(top, text='Сохранить PNG', command=self._save_png, bg=BACKGROUND).pack(side=LEFT, padx=4)

        #Толщина
        Label(root, text='Толщина кисти', font=('Arial', 11), bg='#efebec').pack()
        self.scale = Scale(root, from_=1, to=32, orient=HORIZONTAL, command=self._change_width, bg='#efebec')
        self.scale.set(self.width)
        self.scale.pack()

        #Настройки
        Button(root, text='Открыть меню кистей', command=self._open_settings,
               font=('Arial', 11), bg=BT_COLOR, width=22, height=2).pack(pady=10)
        Button(root, text='Выйти', command=self.root.destroy, font=('Arial', 11), bg=BT_COLOR).pack(pady=8)

    # -----------Настройки кисти------------
    def _to_brush(self):
        self.eraser_mode = False
        self.canvas.config(cursor="hand2")
        self.paintbrush_color = self.prev_color or self.default_color

    def _to_eraser(self):
        self.eraser_mode = True
        self.canvas.config(cursor="tcross")

    def _choose_color(self):
        c = colorchooser.askcolor(title="Выберите цвет")
        if c and c[1]:
            self.prev_color = c[1]
            if not self.eraser_mode:
                self.paintbrush_color = self.prev_color

    def _change_width(self, _val):
        self.width = int(self.scale.get())

    # -----------Рисование------------
    def _start_stroke(self, event):
        self.last_x, self.last_y = event.x, event.y
        self._current_segments = []

    def _draw_motion(self, event):
        if self.last_x is None or self.last_y is None:
            self.last_x, self.last_y = event.x, event.y
            return


        fill_display = self.canvas["bg"] if self.eraser_mode else self.paintbrush_color
        opts = dict(smooth=self.smooth_change, fill=fill_display, dash=self.dash,
                    capstyle=self.capstyle, width=self.width)
        self.canvas.create_line(self.last_x, self.last_y, event.x, event.y, tags='line', **opts)


        self._current_segments.append((self.last_x, self.last_y, event.x, event.y))

        sf = self.scale_factor
        x1, y1, x2, y2 = int(self.last_x * sf), int(self.last_y * sf), int(event.x * sf), int(event.y * sf)
        fill_hr = fill_display
        self._pillow_segment(self._draw, (x1, y1, x2, y2), fill_hr, int(self.width * sf), self.dash)
        if self.dash is None and self.capstyle == 'round':
            r = (self.width * sf) / 2
            self._draw.ellipse((x2 - r, y2 - r, x2 + r, y2 + r), fill=fill_hr, outline=fill_hr)

        self.last_x, self.last_y = event.x, event.y

    def _end_stroke(self, _event):
        if self._current_segments:
            stroke = dict(
                mode=('erase' if self.eraser_mode else 'paint'),
                color=self.paintbrush_color,
                width=self.width,
                dash=self.dash,
                capstyle=self.capstyle,
                smooth=self.smooth_change,
                segments=self._current_segments[:],
            )
            self.model.append(self._copy_stroke(stroke))
            self.history.append({'type': 'add', 'stroke': self._copy_stroke(stroke)})
            self.future.clear()
        self.last_x, self.last_y = None, None
        self._current_segments = []

    # -----------Отменить/вернуть/очистить------------
    def _undo(self):
        if not self.history:
            return
        action = self.history.pop()
        self.future.append(action)
        if action['type'] == 'add':
            if self.model:
                self.model.pop()
        elif action['type'] == 'clear':
            self.model = self._copy_model(action['prev'])
        self._rebuild_from_model()

    def _redo(self):
        if not self.future:
            return
        action = self.future.pop()
        self.history.append(action)
        if action['type'] == 'add':
            self.model.append(self._copy_stroke(action['stroke']))
        elif action['type'] == 'clear':
            self.model = []
        self._rebuild_from_model()

    def _clear(self):
        self.history.append({'type': 'clear', 'prev': self._copy_model(self.model)})
        self.future.clear()
        self.model = []
        self._rebuild_from_model()

    # -----------Вспомогательные копии------------
    @staticmethod
    def _copy_stroke(st):
        return dict(
            mode=st['mode'],
            color=st['color'],
            width=st['width'],
            dash=tuple(st['dash']) if st['dash'] else None,
            capstyle=st['capstyle'],
            smooth=st['smooth'],
            segments=[tuple(s) for s in st['segments']],
        )

    def _copy_model(self, mdl):
        return [self._copy_stroke(s) for s in mdl]


    def _rebuild_from_model(self):
        self.canvas.delete("all")
        for st in self.model:
            fill = (self.canvas['bg'] if st['mode'] == 'erase' else st['color'])
            opts = dict(smooth=st['smooth'], fill=fill, dash=st['dash'],
                        capstyle=st['capstyle'], width=st['width'])
            for (x1, y1, x2, y2) in st['segments']:
                self.canvas.create_line(x1, y1, x2, y2, **opts)

        self._rerender_pillow_from_model()

    def _rerender_pillow_from_model(self):
        W, H = self._img.size
        self._img = Image.new("RGB", (W, H), self.canvas["bg"])
        self._draw = ImageDraw.Draw(self._img)
        sf = self.scale_factor
        for st in self.model:
            fill = (self.canvas['bg'] if st['mode'] == 'erase' else st['color'])
            w = int(st['width'] * sf)
            d = st['dash']
            for (x1, y1, x2, y2) in st['segments']:
                X1, Y1, X2, Y2 = int(x1 * sf), int(y1 * sf), int(x2 * sf), int(y2 * sf)
                self._pillow_segment(self._draw, (X1, Y1, X2, Y2), fill, w, d)
            if d is None and st['capstyle'] == 'round' and st['segments']:
                r = w / 2
                sx, sy = st['segments'][0][0], st['segments'][0][1]
                ex, ey = st['segments'][-1][2], st['segments'][-1][3]
                SX, SY, EX, EY = int(sx * sf), int(sy * sf), int(ex * sf), int(ey * sf)
                self._draw.ellipse((SX - r, SY - r, SX + r, SY + r), fill=fill, outline=fill)
                self._draw.ellipse((EX - r, EY - r, EX + r, EY + r), fill=fill, outline=fill)


    def _pillow_segment(self, draw: ImageDraw.ImageDraw, seg, fill, width, dash):
        x1, y1, x2, y2 = seg
        if not dash:
            draw.line((x1, y1, x2, y2), fill=fill, width=width)
            return
        import math
        dx, dy = x2 - x1, y2 - y1
        dist = math.hypot(dx, dy)
        if dist == 0:
            return
        ux, uy = dx / dist, dy / dist
        pattern = [max(1, int(d * self.scale_factor)) for d in (dash if len(dash) >= 2 else (dash[0], dash[0]))]
        pos, draw_on = 0.0, True
        px, py = x1, y1
        i = 0
        while pos < dist:
            step = pattern[i % len(pattern)]
            nx = x1 + ux * min(dist, pos + step)
            ny = y1 + uy * min(dist, pos + step)
            if draw_on:
                draw.line((px, py, nx, ny), fill=fill, width=width)
            px, py = nx, ny
            pos += step
            draw_on = not draw_on
            i += 1

    # -----------Сохранение------------
    def _save_png(self):
        self._rerender_pillow_from_model()
        cw, ch = int(self.canvas['width']), int(self.canvas['height'])
        out = self._img.resize((cw, ch), Image.LANCZOS)
        path = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[("PNG", "*.png")],
            title="Сохранить рисунок как..."
        )
        if not path:
            return
        out.save(path, "PNG")
        messagebox.showinfo("Готово", os.path.basename(path))

    # -----------Настройки кисти------------
    def _open_settings(self):
        SettingsWindow(self)


class SettingsWindow:
    def __init__(self, parent: PaintWindow):
        self.parent = parent
        self.win = Toplevel(parent.root)
        self.win.geometry('260x360')
        self.win.configure(bg='#efebec')
        self.win.title("Настройки кисти")
        self.win.transient(parent.root)
        self.win.resizable(False, False)

        Label(self.win, text='Тип кисти', bg='#efebec', font=('Arial', 11)).pack(pady=(8, 2))
        self.cap_var = StringVar(value=self.parent.capstyle)
        for text, val in [("Круглая", "round"), ("Прямая", "butt"), ("Выступающая", "projecting")]:
            Radiobutton(self.win, text=text, variable=self.cap_var, value=val,
                        command=self._apply_cap, bg='#efebec').pack(anchor='w', padx=14)

        Label(self.win, text='Сглаживание', bg='#efebec', font=('Arial', 11)).pack(pady=(10, 2))
        self.smooth_var = BooleanVar(value=self.parent.smooth_change)
        for text, val in [("Вкл", True), ("Выкл", False)]:
            Radiobutton(self.win, text=text, variable=self.smooth_var, value=val,
                        command=self._apply_smooth, bg='#efebec').pack(anchor='w', padx=14)

        Label(self.win, text='Пунктир', bg='#efebec', font=('Arial', 11)).pack(pady=(10, 2))
        self.dash_map = {'off': None, 'd1': (4, 2), 'd2': (2, 2)}
        current_key = next((k for k, v in self.dash_map.items() if v == self.parent.dash), 'off')
        self.dash_var = StringVar(value=current_key)
        for text, key in [("Выкл", 'off'), ("Пунктир 1", 'd1'), ("Пунктир 2", 'd2')]:
            Radiobutton(self.win, text=text, variable=self.dash_var, value=key,
                        command=self._apply_dash, bg='#efebec').pack(anchor='w', padx=14)

        Button(self.win, text='Сменить фон', command=self._change_background, bg=BACKGROUND).pack(pady=12)
        Button(self.win, text='Закрыть', command=self.win.destroy, bg=BT_COLOR).pack(pady=6)

    def _apply_cap(self):
        self.parent.capstyle = self.cap_var.get()

    def _apply_smooth(self):
        self.parent.smooth_change = self.smooth_var.get()

    def _apply_dash(self):
        self.parent.dash = self.dash_map[self.dash_var.get()]

    def _change_background(self):
        c = colorchooser.askcolor(title="Выберите цвет фона")
        if c and c[1]:
            self.parent.color_background = c[1]
            self.parent.canvas['bg'] = c[1]

            self.parent._rebuild_from_model()


def main():
    root = Tk()
    app = PaintWindow(root)
    root.mainloop()

if __name__ == "__main__":
    main()
