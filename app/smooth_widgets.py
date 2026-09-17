"""Antialiased surfaces for the small controls and provider cards.

Keep CTk's layout, event handling and accessibility bindings. Only replace the
canvas decoration, which otherwise uses tiny font glyphs for curves/arrows.
Render at the actual widget scaling, not at a fixed Windows DPI.
"""
import customtkinter as ctk
import math
from PIL import Image, ImageDraw, ImageTk


def _raster_surface(width, height, radius, border_width, background, fill, border,
                  right_fill=None, split=None, arrow=None):
    scale = 4
    width, height = max(1, round(width)), max(1, round(height))
    radius = max(0, min(radius, width / 2, height / 2))
    image = Image.new("RGB", (width * scale, height * scale), background)
    draw = ImageDraw.Draw(image)
    bounds = (0, 0, width * scale - 1, height * scale - 1)
    draw.rounded_rectangle(bounds, radius=radius * scale, fill=border if border_width else fill)
    inset = border_width * scale
    if inset and width * scale > 2 * inset and height * scale > 2 * inset:
        draw.rounded_rectangle((inset, inset, bounds[2] - inset, bounds[3] - inset),
                               radius=max(0, radius * scale - inset), fill=fill)
    if right_fill is not None:
        mask = Image.new("L", image.size, 0)
        md = ImageDraw.Draw(mask)
        md.rounded_rectangle((inset, inset, bounds[2] - inset, bounds[3] - inset),
                             radius=max(0, radius * scale - inset), fill=255)
        md.rectangle((0, 0, max(0, round(split * scale)), bounds[3]), fill=0)
        image.paste(right_fill, (0, 0, *image.size), mask)
    if arrow:
        x, y, color = arrow
        # Open chevron, with round end caps; independent of the shapes font.
        arm = max(3, height * .13) * scale
        stroke = max(1, height / 20) * scale
        x, y = x * scale, y * scale
        points = [(x - arm, y - arm / 3), (x, y + arm / 3), (x + arm, y - arm / 3)]
        draw = ImageDraw.Draw(image)
        draw.line(points, fill=color, width=round(stroke), joint="curve")
        for px, py in points:
            r = stroke / 2
            draw.ellipse((px-r, py-r, px+r, py+r), fill=color)
    return image.resize((width, height), Image.Resampling.LANCZOS)


def surface_image(width, height, radius, border_width, background, fill, border,
                  right_fill=None, split=None, arrow=None):
    width, height = max(1, round(width)), max(1, round(height))
    edge = math.ceil(max(radius, border_width)) + 2
    if right_fill is not None or arrow or min(width, height) <= edge * 2:
        return _raster_surface(width, height, radius, border_width, background, fill,
                               border, right_fill, split, arrow)
    # Nine-slice: supersample only the small corners/edges, not a whole 4K panel.
    tile = _raster_surface(2*edge+1, 2*edge+1, radius, border_width, background, fill, border)
    result = Image.new("RGB", (width, height), fill)
    for sx, sw, dx, dw in ((0, edge, 0, edge), (edge, 1, edge, width-2*edge),
                           (edge+1, edge, width-edge, edge)):
        for sy, sh, dy, dh in ((0, edge, 0, edge), (edge, 1, edge, height-2*edge),
                               (edge+1, edge, height-edge, edge)):
            piece = tile.crop((sx, sy, sx+sw, sy+sh))
            result.paste(piece.resize((dw, dh), Image.Resampling.NEAREST), (dx, dy))
    return result


class _Surface:
    def _paint_surface(self, *, fill=None, right_fill=None, arrow=False):
        if not hasattr(self, "_canvas") or not self._canvas.winfo_exists():
            return
        def resolve(value):
            color = self._apply_appearance_mode(value)
            if color == "transparent":
                return color
            # Tk also accepts system colors and grayNN names, unlike Pillow.
            return tuple(component // 257 for component in self.winfo_rgb(color))
        background = resolve(self._bg_color)
        fill = resolve(self._fg_color if fill is None else fill)
        if fill == "transparent":
            fill = background
        width = max(1, round(self._apply_widget_scaling(self._current_width)))
        height = max(1, round(self._apply_widget_scaling(self._current_height)))
        radius = self._apply_widget_scaling(self._corner_radius)
        border_width = self._apply_widget_scaling(self._border_width)
        if not arrow and border_width == 0:
            # Retain the lightweight native fill for borderless layout frames.
            self._canvas.delete("smooth_surface")
            self._canvas.itemconfigure("inner_parts", state="normal")
            self._canvas.itemconfigure("border_parts", state="normal")
            self._surface_signature = None
            self._surface_photo = None
            return
        border = resolve(self._border_color)
        right = resolve(right_fill) if right_fill is not None else None
        arrow_spec = None
        if arrow:
            text = self._text_color_disabled if self._state == "disabled" else self._text_color
            arrow_spec = (width - height / 2, height / 2, resolve(text))
        signature = (width, height, radius, border_width, background, fill, border,
                     right, width-height, arrow_spec)
        if signature != getattr(self, "_surface_signature", None):
            raster = surface_image(*signature)
            self._surface_photo = ImageTk.PhotoImage(raster, master=self._canvas)
            if not self._canvas.find_withtag("smooth_surface"):
                self._canvas.create_image(0, 0, anchor="nw", tags="smooth_surface",
                                          image=self._surface_photo)
            else:
                self._canvas.itemconfigure("smooth_surface", image=self._surface_photo)
            self._surface_signature = signature
        for tag in ("inner_parts", "border_parts", "dropdown_arrow"):
            self._canvas.itemconfigure(tag, state="hidden")
        self._canvas.tag_raise("smooth_surface")


class SmoothFrame(_Surface, ctk.CTkFrame):
    def _draw(self, no_color_updates=False):
        super()._draw(no_color_updates)
        self._paint_surface()


class SmoothButton(_Surface, ctk.CTkButton):
    def _create_grid(self):
        super()._create_grid()
        if self._desired_width == self._desired_height and len(self._text or "") <= 1 and self._image is None:
            # CTk normally reserves a whole corner radius on both sides of the
            # label, stretching a 32px circle into an oval. Icon buttons do not
            # need the same horizontal inset as long text buttons.
            inset = self._apply_widget_scaling(max(4, self._border_width + 1))
            self.grid_columnconfigure((0, 4), minsize=inset)

    def _draw(self, no_color_updates=False):
        super()._draw(no_color_updates)
        self._paint_surface()

    def _on_enter(self, event=None):
        super()._on_enter(event)
        self._paint_surface(fill=self._hover_color if self._hover and self._state == "normal" else None)

    def _on_leave(self, event=None):
        super()._on_leave(event)
        self._paint_surface()


class SmoothComboBox(_Surface, ctk.CTkComboBox):
    def _create_bindings(self, sequence=None):
        super()._create_bindings(sequence)
        if sequence is None:
            # The decoration replaces the old canvas hit target. The editable
            # entry remains a separate child and keeps its normal text events.
            self._canvas.tag_bind("smooth_surface", "<Enter>", self._on_enter)
            self._canvas.tag_bind("smooth_surface", "<Leave>", self._on_leave)
            self._canvas.tag_bind("smooth_surface", "<Button-1>", self._clicked)

    def _draw(self, no_color_updates=False):
        super()._draw(no_color_updates)
        self._paint_surface(right_fill=self._button_color, arrow=True)

    def _on_enter(self, event=0):
        super()._on_enter(event)
        color = self._button_hover_color if self._hover and self._state == "normal" else self._button_color
        self._paint_surface(right_fill=color, arrow=True)

    def _on_leave(self, event=0):
        super()._on_leave(event)
        self._paint_surface(right_fill=self._button_color, arrow=True)
