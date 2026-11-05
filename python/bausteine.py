#!/usr/bin/python3
"""Einheitliche GTK4-Darstellung · Version 1.0.0 · 03.11.2026.

Analyse von /home/josef/Labor/Python/fertig (nur lesend):
- checkweb: GTK4, klassische Menüs, Ergebnis-/Detailbereiche, native Dateiauswahl.
- pcmonitor: GTK4, gemeinsame Dialoge, ColumnView, Such-/Statuszeile, Wasserzeichen.
- showipmac: GTK4, josef_basis-Kopie, gemeinsame Menüs/Dateidialoge/Einstellungen.
- mintpdf: GTK4, Werkzeugdialoge, Stack/StackSwitcher, native Dateiauswahl.
- saveconfig: GTK3, TreeView, Profile, Fortschritts-/Einstellungsdialoge.
  GTK3-Widgets können nicht im selben Prozess mit diesen GTK4-Bausteinen laufen.
  Bestehende Programme werden durch diese Datei NICHT geändert oder migriert.

Gestaltungsstandard:
Klassisches Menü oben; große sachliche Überschrift; 16 Pixel Außenabstand,
12 Pixel Gruppierungsabstand; native GTK-Formulare; scrollbar bei Platzmangel;
Status unten; lange Texte umbrechen; Status nicht allein durch Farbe ausdrücken.
Systemtheme, Systemschrift, Icons und Hell/Dunkel folgen GTK. Kein globales CSS,
keine erzwungenen Schriftgrößen, keine Framework-Mischung. CSS nur für begrenzte
Menütrennlinien, Abschnittsrahmen und Zebrazeilen. Fachaktionen ins Menü,
Bestätigungs-/Abbruchschaltflächen nur in Dialogen. Slider + Zahlenfeld teilen
Werte, Schrittweiten und Sperren. Fachliche Grenzen liefert die Anwendung.

Einbindung:
Diese Datei als bausteine.py in ein Projekt KOPIEREN und dort importieren.
Keine Laufzeitabhängigkeit von diesem versteckten Ablagepfad oder von fertig/.
Alle Funktionen nehmen übersetzte Texte entgegen; keine eigene Sprachverwaltung.
Icon/Wasserzeichen als Projektressource mitgeben, keine fremden Projektpfade.

Technische Prüfung am 03.11.2026 mit GTK 4.14.5:
Import/Version, 600-Pixel-Formular in Hell/Dunkel, Slider/Zahlenfeld/Sperren und
Schrittweite, Suchfilter/Ergebnisanzahl, modaler scrollbar aufgebauter Dialog,
tatsächlich geöffnetes Eintragsmenü ohne Scrollleerraum, Fortschrittsanzeige mit
nicht abbrechbarem Zustand, nativer Dateidialog mit Abbruch und nicht anklickbares
Wasserzeichen geprüft. Benutzerkontrolle der Gestaltung steht noch aus.
Kein Funktionstest der fünf abgeschlossenen Fachprogramme und kein Auftrag zu
deren rückwirkender Vereinheitlichung. Analyse enthält keine privaten Einstellungen.
Die Anwendung bleibt zuständig für Fachlogik, Hintergrundarbeit, Konfiguration,
Sprachen/Hilfe, sichere Exporte, Fensterzustand und kooperativen Abbruch.
Die Dateiauswahl schreibt selbst keine Dateien und genehmigt kein Überschreiben.

Explizite Vorschau: /usr/bin/python3 /home/josef/Labor/Python/.bausteine.py --preview
Import öffnet keine Fenster und legt keine Dateien an. Keine Paketinstallation.
"""
from pathlib import Path
import math
import gi

gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gio, Gdk, GLib, GObject, Pango

VERSION = '1.0.0'
MARGIN, GAP = 16, 12


def box(margin=0, spacing=GAP):
    widget = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=spacing)
    for edge in ('top', 'bottom', 'start', 'end'):
        getattr(widget, 'set_margin_' + edge)(margin)
    return widget


def label(text='', *, heading=False):
    widget = Gtk.Label(label=str(text), xalign=0, wrap=True,
                       wrap_mode=Pango.WrapMode.WORD_CHAR, selectable=not heading)
    if heading:
        widget.add_css_class('title-1')
    return widget


def scroll(child):
    widget = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
    widget.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    widget.set_child(child)
    return widget


def descendants(widget):
    yield widget
    child = widget.get_first_child()
    while child is not None:
        yield from descendants(child)
        child = child.get_next_sibling()


def install_style(widget):
    """Nur modulbezogene Klassen; weder Theme noch Standardschrift ersetzen."""
    display = widget.get_display()
    if not getattr(display, '_bausteine_style', None):
        provider = Gtk.CssProvider()
        provider.load_from_data(b'''
            .bausteine-section { border: 1px solid alpha(@theme_fg_color, .22);
                border-radius: 8px; padding: 12px; }
            .bausteine-menu popover.menu separator { min-height: 1px;
                background-color: alpha(@theme_fg_color,.45);
                margin-top: 4px; margin-bottom: 4px; }
            .bausteine-results row:nth-child(even):not(:selected):not(:hover) {
                background-color: alpha(@theme_fg_color,.045); }
        ''')
        Gtk.StyleContext.add_provider_for_display(
            display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        display._bausteine_style = provider


def compact_menu(bar):
    """Kurze Menüs ohne reservierten Scrollleerraum, lange bleiben scrollbar."""
    def fit(area):
        child = area.get_child()
        if child is None:
            return
        natural = child.measure(Gtk.Orientation.VERTICAL, -1).natural
        minimum = area.get_vscrollbar().measure(Gtk.Orientation.VERTICAL, -1).minimum
        area.set_policy(Gtk.PolicyType.NEVER,
                        Gtk.PolicyType.NEVER if natural < minimum else Gtk.PolicyType.AUTOMATIC)
    for child in descendants(bar):
        if isinstance(child, Gtk.ScrolledWindow):
            fit(child)
            if not getattr(child, '_bausteine_compact', False):
                child.connect('map', fit)
                child._bausteine_compact = True


def menu_bar(owner, groups):
    """groups=[('Datei', [('Einstellungen','settings',callback), None, ...])].

    Registriert win.*-Aktionen. None trennt Gruppen sichtbar. Namen eindeutig
    vergeben. Rückgabe: (PopoverMenuBar, {name: SimpleAction}); action.set_enabled
    steuert den Zustand bei laufender Arbeit. Keine funktionslosen Vorgaben.
    """
    model, actions = Gio.Menu(), {}
    for title, entries in groups:
        submenu, section = Gio.Menu(), Gio.Menu()
        for entry in [*entries, None]:
            if entry is None:
                if section.get_n_items():
                    submenu.append_section(None, section)
                    section = Gio.Menu()
                continue
            text, name, callback = entry
            if name in actions or owner.lookup_action(name):
                raise ValueError('Doppelter Aktionsname: ' + name)
            action = Gio.SimpleAction.new(name, None)
            action.connect('activate', lambda *_, fn=callback: fn())
            owner.add_action(action)
            actions[name] = action
            section.append(text, 'win.' + name)
        if submenu.get_n_items():
            model.append_submenu(title, submenu)
    bar = Gtk.PopoverMenuBar.new_from_model(model)
    bar.add_css_class('bausteine-menu')
    install_style(bar)
    bar.connect('map', lambda *_: compact_menu(bar))
    compact_menu(bar)
    return bar, actions


class Window(Gtk.ApplicationWindow):
    """Native Hauptfensterhülle; body ist der scrollbar angeordnete Arbeitsbereich."""
    def __init__(self, app, name, version, *, icon_name=None, width=960, height=720):
        super().__init__(application=app, title=f'{name} {version}',
                         default_width=width, default_height=height)
        if icon_name:
            self.set_icon_name(icon_name)
        self.layout = box(spacing=0)
        self.set_child(self.layout)
        self.body = box(margin=MARGIN)
        self.body.append(label(f'{name} · {version}', heading=True))
        self.layout.append(scroll(self.body))
        self.status = label('')
        self.status.set_margin_start(MARGIN)
        self.status.set_margin_end(MARGIN)
        self.status.set_margin_top(8)
        self.status.set_margin_bottom(8)
        self.layout.append(self.status)

    def set_menus(self, groups):
        if hasattr(self, 'menubar'):
            raise RuntimeError('Menüs einmal anlegen; Modelle für Sprachwechsel gezielt ändern.')
        self.menubar, self.actions = menu_bar(self, groups)
        self.layout.prepend(self.menubar)
        return self.actions


def section(title, *, collapsible=False, expanded=False):
    """Rückgabe (Rahmen/Expander, Inhaltsbox); keine feste Inhaltshöhe."""
    body = box()
    title_label = label(title)
    title_label.add_css_class('heading')
    if collapsible:
        wrapper = Gtk.Expander(expanded=expanded)
        wrapper.set_label_widget(title_label)
        body.set_margin_top(GAP)
        wrapper.set_child(body)
    else:
        wrapper = box()
        wrapper.append(title_label)
        wrapper.append(body)
    wrapper.add_css_class('bausteine-section')
    install_style(wrapper)
    return wrapper, body


def form_row(container, title, control):
    """Native Eingabe; Zahlenwerte mit gekoppeltem Slider, Schalter/Menüs ohne."""
    row = Gtk.Box(spacing=GAP)
    title_widget = label(title)
    title_widget.set_selectable(False)
    if isinstance(control, Gtk.SpinButton):
        title_widget.set_width_chars(20)
        title_widget.set_max_width_chars(20)
        adjustment = control.get_adjustment()
        slider = Gtk.Scale.new(Gtk.Orientation.HORIZONTAL, adjustment)
        slider.set_draw_value(False)
        slider.set_hexpand(True)
        slider.set_size_request(60, -1)
        slider.set_round_digits(control.get_digits())
        slider.set_tooltip_text(title)
        control.set_width_chars(7)
        control.set_max_width_chars(9)
        control.bind_property('sensitive', slider, 'sensitive', GObject.BindingFlags.SYNC_CREATE)
        def snap(*_):
            lower, upper = adjustment.get_lower(), adjustment.get_upper()
            step = adjustment.get_step_increment()
            value = adjustment.get_value()
            target = min(upper, max(lower, lower + round((value-lower)/step)*step))
            if not math.isclose(value, target, abs_tol=1e-8):
                adjustment.set_value(target)
        slider.connect('value-changed', snap)
        row.append(title_widget)
        row.append(slider)
        row.slider = slider
    else:
        title_widget.set_hexpand(True)
        row.append(title_widget)
    control.set_tooltip_text(title)
    row.append(control)
    container.append(row)
    return row


def number(lower, upper, step=1, value=None, digits=0):
    if not all(math.isfinite(v) for v in (lower,upper,step)) or lower > upper or step <= 0:
        raise ValueError('Ungültiger Wertebereich')
    widget = Gtk.SpinButton.new_with_range(lower, upper, step)
    widget.set_digits(digits)
    widget.set_value(lower if value is None else value)
    return widget


class Dialog(Gtk.Window):
    """Einheitlicher modaler, scrollbar aufgebauter Dialog mit großer Überschrift."""
    def __init__(self, parent, title, *, width=640, height=480):
        super().__init__(title=title, transient_for=parent, modal=True,
                         default_width=width, default_height=height)
        root = box()
        self.body = box(margin=MARGIN)
        self.body.append(label(title, heading=True))
        root.append(scroll(self.body))
        self.footer = Gtk.Box(spacing=GAP, halign=Gtk.Align.END,
                              margin_start=MARGIN, margin_end=MARGIN,
                              margin_bottom=MARGIN)
        root.append(self.footer)
        self.set_child(root)

    def button(self, text, callback):
        button = Gtk.Button(label=text)
        button.connect('clicked', lambda *_: callback())
        self.footer.append(button)
        return button


def message(parent, title, text, close_text='Schließen'):
    dialog = Dialog(parent, title, height=300)
    dialog.body.append(label(text))
    dialog.button(close_text, dialog.destroy)
    dialog.present()
    return dialog


class Progress(Dialog):
    """Anzeige für Hintergrundarbeit; update/finish nur im GTK-Hauptthread aufrufen.

    Abbrechen signalisiert lediglich den Wunsch an die Fachlogik. Erst finish()
    schließt den Dialog. Ohne cancel-Callback ist die Aktion nicht abbrechbar.
    """
    def __init__(self, parent, title, *, cancel=None, cancel_text='Abbrechen'):
        super().__init__(parent, title, width=480, height=240)
        self.bar = Gtk.ProgressBar(show_text=True)
        self.detail = label('')
        self.body.append(self.detail)
        self.body.append(self.bar)
        self.running = True
        self.cancel_button = self.button(cancel_text, lambda: self.request_cancel(cancel))
        self.cancel_button.set_sensitive(cancel is not None)
        self.connect('close-request', self.on_close)

    def on_close(self, *_):
        return self.running

    def request_cancel(self, callback):
        if callback is not None and self.running and self.cancel_button.get_sensitive():
            self.cancel_button.set_sensitive(False)
            callback()

    def update(self, fraction=None, text=''):
        self.detail.set_text(text)
        if fraction is None:
            self.bar.pulse()
        else:
            self.bar.set_fraction(min(1., max(0., fraction)))

    def finish(self):
        self.running = False
        self.destroy()


class _Record(GObject.Object):
    def __init__(self, values):
        super().__init__()
        self.values = dict(values)


class Results(Gtk.Box):
    """Suchbare native ColumnView. columns=[('key','Überschrift'), ...]."""
    def __init__(self, columns, *, search_text='Ergebnisse suchen …'):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=GAP)
        self.columns = list(columns)
        self.search = Gtk.SearchEntry()
        self.search.set_property('placeholder-text', search_text)
        self.append(self.search)
        self.store = Gio.ListStore.new(_Record)
        self.filter = Gtk.CustomFilter.new(self.matches)
        self.filtered = Gtk.FilterListModel.new(self.store, self.filter)
        self.selection = Gtk.SingleSelection.new(self.filtered)
        self.selection.set_autoselect(False)
        self.view = Gtk.ColumnView.new(self.selection)
        self.view.add_css_class('bausteine-results')
        install_style(self.view)
        self.view.set_show_column_separators(True)
        for key, title in self.columns:
            factory = Gtk.SignalListItemFactory()
            def setup(_, item):
                widget = label('')
                widget.set_selectable(False)
                for edge in ('top','bottom','start','end'):
                    getattr(widget,'set_margin_'+edge)(8)
                item.set_child(widget)
            def bind(_, item, field=key):
                item.get_child().set_text(str(item.get_item().values.get(field,'')))
            factory.connect('setup', setup)
            factory.connect('bind', bind)
            column = Gtk.ColumnViewColumn.new(title, factory)
            column.set_expand(True)
            column.set_resizable(True)
            self.view.append_column(column)
        self.append(scroll(self.view))
        self.count = label('')
        self.append(self.count)
        self.search.connect('search-changed', self.refilter)
        self.filtered.connect('items-changed', lambda *_: self.update_count())
        self.update_count()

    def matches(self, record):
        query = self.search.get_text().strip().casefold()
        return not query or any(query in str(record.values.get(key,'')).casefold()
                                for key,_ in self.columns)

    def refilter(self, *_):
        self.filter.changed(Gtk.FilterChange.DIFFERENT)
        self.update_count()

    def update_count(self):
        self.count.set_text(f'{self.filtered.get_n_items()} / {self.store.get_n_items()}')

    def set_rows(self, rows):
        records = [_Record(row) for row in rows]
        self.store.splice(0, self.store.get_n_items(), records)
        self.update_count()

    def rows(self, visible=False):
        model = self.filtered if visible else self.store
        return [dict(model.get_item(i).values) for i in range(model.get_n_items())]


def watermark(content, filename, opacity=.1):
    """Nur Hintergrundbild transparent; es fängt keine Eingaben ab."""
    area = Gtk.Overlay()
    area.set_child(content)
    if filename and Path(filename).is_file():
        picture = Gtk.Picture.new_for_filename(str(filename))
        picture.set_content_fit(Gtk.ContentFit.CONTAIN)
        picture.set_can_shrink(True)
        picture.set_opacity(min(1., max(0., opacity)))
        picture.set_can_target(False)
        picture.set_can_focus(False)
        area.add_overlay(picture)
    return area


def choose_file(parent, title, callback, *, save=False, folder=False,
                initial_folder=None, name=None, patterns=(), accept='Auswählen', cancel='Abbrechen'):
    """Native, asynchrone lokale Dateiauswahl; callback(Path|None).

    Der Aufrufer hält die zurückgegebene Referenz bis zur Antwort, beendet sie
    beim Schließen des Elternfensters und prüft Schreibrechte/Überschreiben selbst.
    """
    if folder and save:
        raise ValueError('Ordnerauswahl und Datei speichern sind getrennte Vorgänge')
    action = Gtk.FileChooserAction.SELECT_FOLDER if folder else Gtk.FileChooserAction.SAVE if save else Gtk.FileChooserAction.OPEN
    chooser = Gtk.FileChooserNative.new(title, parent, action, accept, cancel)
    chooser.set_modal(True)
    if initial_folder and Path(initial_folder).is_dir():
        chooser.set_current_folder(Gio.File.new_for_path(str(initial_folder)))
    if save and name:
        chooser.set_current_name(name)
    for text, globs in patterns:
        file_filter = Gtk.FileFilter()
        file_filter.set_name(text)
        for pattern in globs:
            file_filter.add_pattern(pattern)
        chooser.add_filter(file_filter)
    def response(dialog, result):
        chosen = dialog.get_file() if result == Gtk.ResponseType.ACCEPT else None
        path = chosen.get_path() if chosen else None
        dialog.destroy()
        callback(Path(path) if path else None)
    chooser.connect('response', response)
    chooser.show()
    return chooser


def about(parent, name, version, *, comments='', authors=(), icon_name=None):
    dialog = Gtk.AboutDialog(transient_for=parent, modal=True, program_name=name,
                             version=version, comments=comments, authors=list(authors))
    if icon_name:
        dialog.set_logo_icon_name(icon_name)
    dialog.present()
    return dialog


def preview():
    """Explizite Ansicht ohne Dateizugriff, Fachfunktionen oder Speicherung."""
    app = Gtk.Application(application_id='eu.dogtruck.BausteineVorschau',
                          flags=Gio.ApplicationFlags.NON_UNIQUE)
    def activate(application):
        win = Window(application, 'GTK-Bausteine', VERSION)
        win.set_menus([
            ('Datei', [('Einstellungen', 'settings', lambda: message(win,'Einstellungen','Projektfelder werden hier eingesetzt.')),
                       None, ('Beenden','quit',win.close)]),
            ('Hilfe', [('Hilfe','help',lambda: message(win,'Hilfe','Vorschau gemeinsamer GTK-Elemente. F1 öffnet diese Hilfe.')),
                       ('Über','about',lambda: about(win,'GTK-Bausteine',VERSION))])])
        application.set_accels_for_action('win.help',['F1'])
        application.set_accels_for_action('win.quit',['<Primary>q'])
        frame, body = section('Einstellungen', collapsible=True, expanded=True)
        form_row(body,'Zahlenwert',number(0,100,1,50))
        form_row(body,'Aktiviert',Gtk.Switch(valign=Gtk.Align.CENTER))
        form_row(body,'Auswahl',Gtk.DropDown.new_from_strings(['Erste Option','Zweite Option']))
        win.body.append(frame)
        results = Results([('name','Name'),('status','Status')])
        results.set_rows([{'name':'GTK-Elemente','status':'Vorschau'},
                          {'name':'Systemtheme','status':'Übernommen'}])
        win.body.append(results)
        win.status.set_text('Vorschau · keine Daten gespeichert')
        win.present()
    app.connect('activate',activate)
    return app.run([])


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Gemeinsame native GTK4-Darstellungsbausteine')
    parser.add_argument('--version',action='version',version='GTK-Bausteine '+VERSION)
    parser.add_argument('--preview',action='store_true',help='Vorschaufenster ohne Speicherung öffnen')
    options = parser.parse_args()
    if options.preview:
        raise SystemExit(preview())
    parser.print_help()
