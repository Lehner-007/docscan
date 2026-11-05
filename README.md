# Docscan

Version 0.4.0 · Python / GTK4 / SANE · GPL-3.0-or-later.

Entwicklung: Start über `start.sh` oder den lokalen Starter.
Benutzer-ZIP: `python3 python/docscan.py`; DEB: Startbefehl `docscan`.
Versionsanzeige jeweils mit `--version`.
Voraussetzungen: Python 3, PyGObject/GTK4, Pillow und SANE `scanimage`.
Auf diesem Rechner vorhanden; beim Programmstart wird nichts installiert.

## Bedienung

Nach erfolgreicher Erkennung zeigt das leere Hauptfenster „Bereit zum Scannen“,
die Scanner-Auswahl und einen Button zum erneuten Suchen an. Das Zahnrad öffnet
die Scan-Einstellungen mit Scanart, Vorlage, Treibermodus, Papierquelle und DPI.

- Einzelne Seite: eine Seite aus der gewählten Quelle.
- Alle Seiten aus dem Papiereinzug: liest bis der Treiber den leeren Einzug meldet;
  mit Stopp vorzeitig beenden (Sicherheitszeitlimit: eine Stunde).
- Mehrere Seiten vom Flachbett: nach jedem Scan die Vorlage wechseln und im Dialog
  „Nächste Seite scannen“ oder „Dokument abschließen“ wählen. Jede Seite wird vorher
  als Wiederherstellung gesichert.

Nur vom Treiber angebotene Quellen werden verwendet; ohne Papiereinzug ist dessen
Scanart gesperrt. „Text“ wählt bevorzugt Graustufen/Schwarzweiß, „Bild“ Farbe, soweit
der Treiber diese Modi anbietet. Der Farbmodus bleibt manuell wählbar. Beide scannen
Seitenbilder; Texterkennung (OCR) ist nicht enthalten.
DPI-Stufen: 75, 150, 300, 600, 1200, 2400, auf die vom Scanner unterstützten Werte
begrenzt. Scannen startet über die Kopfleiste oder Strg+R. Bei fehlendem Scanner
bleibt der Bildimport nutzbar.

Große zentrierte Vorschau wie beim Dokument-Scanner. Die Kopfleiste bietet Scannen/Stopp, Scan-Einstellungen (Zahnrad) und PDF-Speichern. Unten stehen Neues Dokument, Drehen, Zuschneiden, Löschen und die Seitenauswahl. Die klassische Menüleiste mit allen Funktionen bleibt verfügbar. Menü Seite: Drehen, Zuschneiden nach Pixeln,
Umordnen und Löschen. Bild-/TIFF-Import ergänzt ein Dokument. PDF exportiert alle
Seiten, PNG/JPEG die Auswahl. Bestehende Exportdateien werden nicht überschrieben.
Die DPI-Einstellung bestimmt die PDF-Ausgabeauflösung. Scans mit unterschiedlichen
DPI sollten für gleiche physische Größen in separaten Dokumenten gespeichert werden.
F1 öffnet die lokale Hilfe; Datei → Einstellungen schaltet Deutsch/Englisch um.

Wiederherstellung nach Änderungen unter `.config/session`; beim Neustart wird das
Dokument wiederhergestellt. Datei → Neues Dokument verwirft es nach Bestätigung.
In der Entwicklung: Einstellungen und Logs unter `.config/`.
Installierte Version: `$XDG_CONFIG_HOME/docscan`, standardmäßig `~/.config/docscan`.
Die verwendeten Speicherorte werden für die Deinstallation vorgemerkt.
Schließen während laufender Vorgänge ist gesperrt; Scanner-Aufträge sind abbrechbar.
Import, Export und Wiederherstellung werden vor dem Schließen abgeschlossen.

Während des Scans baut sich die Seite zeilenweise auf. Eine rote Linie markiert den
aktuellen Lesestand; darunter bleibt die Vorschau weiß. Seite und Prozentwert stehen
unter dem Bild. Vor den ersten Bilddaten läuft eine Warteanzeige. Bei Treibern, die
das Bild erst am Ende liefern oder die Seitenhöhe nicht melden, kann der genaue
Fortschritt erst später erscheinen. Die rote Linie gehört nur zur Vorschau und wird
nicht exportiert. Zwischendateien von scanimage (.part) werden mit berücksichtigt.

## Analyse des gelieferten Simple-Scan-Quellcodes

Untersucht wurde `/home/josef/Labor/Austausch/simple-scan-master`:

| Originalbaustein | Aufgabe | Umsetzung in Docscan |
| --- | --- | --- |
| scanner.vala | SANE, Optionen, Einzel-/Einzugsscans, Abbruch | python/scanner.py über scanimage |
| book.vala, page.vala | Mehrseitiges Dokument und Bildbearbeitung | python/document.py und Seitenmenü |
| book-view.vala, page-view.vala | Seitenwahl und Vorschau | GTK4-ListBox / Picture |
| app-window.vala, preferences-dialog.vala | Oberfläche und Einstellungen | python/docscan.py und lokale bausteine.py |
| autosave-manager.vala | Wiederherstellung ungespeicherter Arbeit | atomar erneuertes Sitzungsmanifest und PNG-Seiten |

Es handelt sich um eine eigenständige Python-Neuumsetzung der Kernfunktionen,
keine vollständige Portierung des Vala-Programms. Nicht umgesetzt sind OCR,
Druck-/E-Mail-Integration, Farbprofile/colord, Scanner-Anmeldung, Treiberinstallation,
PDF-Import, automatische Seitenerkennung und erweiterte Duplex-Nachsortierung.
Kein Gerät oder Treiber wird als unterstützt behauptet, bevor SANE es meldet.

Die ältere Grundvorlage `.bausteien/vorlage` und ihre Dialogvorlagen sind auf diesem
Rechner nicht vorhanden. Die verfügbare `.bausteine.py` wurde unverändert als
eigenständige Projektkopie eingebunden. Keine Laufzeitabhängigkeit zu anderen Projekten.
Eine Veröffentlichungsquelle für Updates/weitere Sprachpakete ist noch nicht
konfiguriert; DE/EN und die jeweilige Hilfe funktionieren offline. Die Paketierung ist vorbereitet; Installation und Veröffentlichung werden getrennt geprüft.

## Bibliotheken und Herkunft

- PyGObject / GTK4: native Linux-Oberfläche, LGPL-2.1-or-later;
  <https://github.com/GNOME/pygobject>, <https://pygobject.gnome.org/>.
- Pillow: Bildimport, Drehen/Zuschneiden und PDF-/Bildexport, MIT-CMU;
  <https://github.com/python-pillow/Pillow>.
- SANE scanimage: vorhandene Treiberanbindung ohne zusätzliche Python-SANE-Bindung.
- Simple Scan: Analysevorlage und unverändertes Programmsymbol aus
  `data/icons/hicolor/scalable/org.gnome.SimpleScan.svg`, Copyright GNOME-Mitwirkende;
  <https://gitlab.gnome.org/GNOME/simple-scan>. Lizenztext liegt in LICENSE.
- `assets/report_watermark.png`: unverändertes, von Josef vorgegebenes Markenzeichen.

Quellenvergleich am 05.11.2026; die vorhandenen Systembibliotheken werden verwendet,
keine zusätzlichen GitHub-Bibliotheken heruntergeladen oder installiert.

## Prüfung

`PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 python/test_docscan.py`

Der Test nutzt einen separaten Ordner unter tests und einen lokalen SANE-Kontext
mit dem Testbackend. Er verändert keine Systemkonfiguration und keinen realen Scanner.
Geprüft: SANE-Erkennung, Optionen, Bildscan, ADF-Ende, Abbruch, fehlendes Backend,
Wiederherstellung, Mehrseiten-PDF, PNG und Schutz bestehender Dateien sowie GTK-Bedienung.
Ein echter Scanner wurde in dieser Umgebung nicht erkannt. Hardwarefreigabe ausstehend.

Vorgesehenes Gerät: Canon CanoScan LiDE 200, USB-ID 04a9:1905, SANE-Backend
genesys. SANE führt das Gerät als vollständig unterstützt mit Auflösungen von
75 bis 4800 dpi: <https://www.sane-project.org/sane-mfgs.html>.
Docscan übernimmt trotzdem ausschließlich die tatsächlich gemeldeten Optionen.
Ein erkannter LiDE 200 wird bei noch nicht gewähltem Gerät zuerst angeboten.
Der LiDE 200 ist ein Flachbettscanner: einzelne Vorlagen nacheinander scannen,
danach gemeinsam als PDF exportieren. Am Laborrechner war er am 05.11.2026
weder in lsusb noch in der SANE-Erkennung erreichbar. Bei einer VM muss das
USB-Gerät zuerst an die VM durchgereicht werden; es wurden keine USB- oder
Systemeinstellungen verändert.

## Pakete

`erstelledeb.sh` erstellt das DEB, `erstellezip.sh` das Laufzeit-ZIP und
`erstellegithub.sh` ein öffentliches Quell-ZIP. Alle Ausgaben liegen unter `dist/`,
jeweils mit SHA-256-Datei. Vorhandene Ausgaben werden nicht überschrieben.
Benutzerkonfigurationen, Scans, Logs und Caches sind ausgeschlossen.
Das Quell-ZIP enthält zusätzlich die Testquellen und Paketierung, keine lokalen Prüfprotokolle.
Die Skripte führen keinen Git-Push und keine Installation aus.

Installation: `sudo apt install ./docscan_0.4.0_all.deb`. Ein markierter
Desktop-Starter wird im konfigurierten Schreibtischordner angelegt, soweit vorhanden.
Bei normaler Entfernung werden programmspezifische Einstellungen, Wiederherstellung,
Logs und markierte Starter bereinigt. Eigene exportierte Dokumente bleiben erhalten.
Upgrades erhalten Einstellungen und Wiederherstellung.
Paketierungsbausteine basieren auf Josefs GPLv3-Projekt Showipmac.

## Zehn Sprachen und Hilfen

Deutsch und Englisch liegen im Basispaket. Acht vollständige Zusatzpakete mit
Oberflächentexten und eingebetteter Offline-Hilfe liegen getrennt unter
`publishing/languages/`: Arabisch, Spanisch, Französisch, Hindi, Portugiesisch,
Russisch, Türkisch und Chinesisch. Sie sind im GitHub-Quellpaket enthalten;
das DEB und das Laufzeit-ZIP enthalten weiterhin ausschließlich DE/EN.

Datei → Einstellungen → Sprachen installieren → Sprachpaket importieren:
eine `<code>.json` auswählen, danach Speichern. Der Sprachwechsel erfolgt ohne
Neustart; Arabisch verwendet RTL. Vorhandene Sprachen werden nicht überschrieben.
Eigene vollständige Pakete mit anderen Sprachcodes werden ebenfalls unterstützt.
Importierte Pakete und Hilfen liegen unter dem Benutzer-Konfigurationsordner in
`languages/<code>/`. Englisch ist die Rückfallsprache. Abbrechen ändert die aktive
Sprache nicht; ein bereits importiertes Paket bleibt installiert.

Nach Veröffentlichung kann die direkte GitHub-Basisadresse für `catalog.json` in
den Einstellungen eingetragen werden. Katalog und Pakete werden ausschließlich
auf Benutzeraktion geladen. Derzeit ist noch keine Quelle veröffentlicht;
der lokale Import funktioniert unabhängig davon.

Erneutes Erzeugen: `./erstellesprachen.sh` erstellt die acht JSON-Pakete und
ein getrenntes `dist/docscan-<Version>-languages.zip` samt Prüfsumme. Vollständigkeit,
Platzhalter, Paketidentität, sichere Pfade und aktive HTML-Inhalte werden geprüft.
Die Übersetzungen sind technisch geprüft; eine Prüfung durch Muttersprachler
steht aus. Vorhandene Sprachpakete mit älteren Schlüsselbeständen müssen separat
aktualisiert werden und werden niemals still überschrieben.
