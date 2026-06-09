# MetadataViewer

Прод-готовая программа для просмотра **метаданных файлов** с графическим интерфейсом
(Python + Tkinter). Превью изображений, EXIF/GPS, теги аудио, метаданные PDF,
контрольные суммы, экспорт отчётов, тёмная тема — всё в одном окне.

![GUI](https://img.shields.io/badge/GUI-Tkinter-blue)
![Python](https://img.shields.io/badge/Python-3.8%2B-green)
![Tests](https://img.shields.io/badge/tests-pytest-success)

## Возможности

| Категория | Что показывает | Зависимость |
|-----------|----------------|-------------|
| **Файловая система** | размер, MIME-тип, тип по сигнатуре (magic bytes), даты, права, владелец, inode | — (всегда) |
| **Изображения** | превью, формат, размеры, мегапиксели, DPI, **EXIF**, **GPS-координаты** + ссылка на карту | `Pillow` |
| **Аудио** | длительность, битрейт, частота, каналы, теги (MP3/FLAC/OGG/M4A…) | `mutagen` |
| **Видео** | длительность и размеры MP4/MOV (парсинг `moov`) | — (всегда) |
| **PDF** | число страниц, шифрование, автор, заголовок, создатель | `pypdf` |
| **Документы Office** | автор, заголовок, даты, приложение, статистика (docx/xlsx/pptx) | — (всегда) |
| **Архивы ZIP** | число файлов, степень сжатия, содержимое | — (всегда) |
| **Текст** | кодировка, число строк/слов/символов | — (всегда) |
| **Hex-заголовок** | дамп первых байтов (hex + ASCII) | — (всегда) |
| **Контрольные суммы** | MD5, SHA-256 (считаются в фоне) | — (всегда) |

Интерфейс (GUI):
- 🖼 **превью** изображений в боковой панели;
- 🔍 **поиск/фильтр** по всем свойствам в реальном времени;
- 🧹 **очистка метаданных** одной кнопкой (удаление EXIF/GPS — приватность);
- 🗺 **открыть GPS-координаты на карте** в браузере;
- 📋 **копирование** значения/свойства/строки (двойной клик, `Ctrl+C`, контекстное меню);
- 🌓 **светлая и тёмная** темы (`Ctrl+T`);
- 💾 **экспорт** отчёта в **TXT** и **JSON**;
- 🕘 **недавние файлы**, **drag-and-drop**, горячие клавиши;
- ⚙️ хеши больших файлов считаются **асинхронно** — интерфейс не зависает.

### Режим командной строки (CLI)

Работает в пайплайнах и скриптах, без графики:

```bash
metadataviewer photo.jpg                 # метаданные в терминал
metadataviewer *.jpg --json -o out.json  # пакетно в JSON-файл
metadataviewer photo.jpg --strip         # удалить EXIF/GPS (копия *_clean)
metadataviewer file.bin --hex --hash     # с hex-заголовком и хешами
metadataviewer report.docx               # автор/даты документа Office
```

## Установка

Базовая версия не требует ничего, кроме Python (Tkinter входит в стандартную поставку).
Для всех возможностей:

```bash
pip install -r requirements.txt
# или как пакет:
pip install -e ".[full]"
```

> Ошибка `No module named 'tkinter'`? Установите системный пакет:
> `sudo apt install python3-tk` (Debian/Ubuntu).

## Запуск

```bash
python3 metadata_viewer.py                 # открыть окно
python3 metadata_viewer.py фото.jpg        # сразу открыть файл
python3 -m metadataviewer                  # как модуль
metadataviewer                             # после pip install -e .
```

## Использование

1. **«Открыть»** или перетащите файл в окно.
2. Метаданные появятся в дереве по категориям; слева — превью и краткая сводка.
3. **Поиск** фильтрует свойства на лету; двойной клик копирует значение.
4. **Файл → Экспорт** сохраняет отчёт в TXT или JSON.

Горячие клавиши: `Ctrl+O` — открыть, `Ctrl+T` — тема, `F5` — обновить, `Ctrl+C` — копировать.

## Структура проекта

```
metadataviewer/
    extractors.py   # извлечение/очистка метаданных (без GUI, покрыто тестами)
    app.py          # графический интерфейс Tkinter
    cli.py          # интерфейс командной строки
    __main__.py     # точка входа: python -m metadataviewer
metadata_viewer.py  # тонкая обёртка для запуска
tests/              # pytest-тесты (extractors + CLI)
```

## Скачать готовую сборку

Готовые **standalone-исполняемые файлы** (без установки Python) для Windows, Linux
и macOS, а также Python-пакет (wheel) публикуются на странице
[**Releases**](../../releases) при каждом теге `v*`.

| Платформа | Файл | Запуск |
|-----------|------|--------|
| Windows | `MetadataViewer-windows.exe` | двойной клик или `MetadataViewer-windows.exe файл.jpg` |
| Linux (.deb) | `metadataviewer_1.1.0_all.deb` | `sudo apt install ./metadataviewer_1.1.0_all.deb`, затем `metadataviewer` |
| Linux (бинарь) | `MetadataViewer-linux` | `chmod +x MetadataViewer-linux && ./MetadataViewer-linux` |
| macOS | `MetadataViewer-macos` | `chmod +x MetadataViewer-macos && ./MetadataViewer-macos` |

Собрать `.deb` локально (нужен `dpkg-deb`):

```bash
bash packaging/build_deb.sh          # -> dist/metadataviewer_<версия>_all.deb
```

Сборка релиза автоматизирована в `.github/workflows/release.yml`: пуш тега
запускает PyInstaller на трёх ОС и прикладывает артефакты к релизу.

```bash
# выпустить новую версию
git tag v1.1.0
git push origin v1.1.0
```

Собрать исполняемый файл локально:

```bash
pip install pyinstaller -r requirements.txt
pyinstaller --onefile --name MetadataViewer --collect-submodules metadataviewer metadata_viewer.py
# результат: dist/MetadataViewer
```

## Тесты

```bash
pip install pytest Pillow
pytest -q
```

Логика извлечения метаданных полностью тестируется без дисплея (headless),
поэтому работает в CI — см. `.github/workflows/ci.yml`.

## Лицензия

См. файл [LICENSE](LICENSE).
