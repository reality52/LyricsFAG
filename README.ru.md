# LyricsFAG

[![GitHub repo](https://img.shields.io/badge/GitHub-reality52%2FLyricsFAG-181717?logo=github)](https://github.com/reality52/LyricsFAG)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![RU](https://img.shields.io/badge/README-%D0%A0%D1%83%D1%81%D1%81%D0%BA%D0%B8%D0%B9-blue)](README.ru.md)

> **Проект создан с помощью ИИ.** Эта кодовая база написана при существенной
> помощи AI-кодинг-ассистента ([Codebuff](https://codebuff.com), модель
> `minimax/minimax-m3`) под руководством и ревью человека. Код прошёл
> тестирование, но не сертификацию — запуск LyricsFAG на вашей фонотеке
> (сетевые запросы к LRCLIB / Genius, скачивание весов Whisper / Demucs,
> запись `.lrc` рядом с вашими аудиофайлами) осуществляется **на ваш
> собственный риск**. Сначала опробуйте инструмент на копии фонотеки.
>
> English version: [README.md](README.md).

Небольшой CLI-инструмент с минимальным набором зависимостей: обходит
фонотеку, читает теги аудиофайлов и кладёт рядом с каждым треком
соответствующий `.lrc`.

Тексты песен берутся из **[LRCLIB.net]** (бесплатно, без авторизации,
возвращает синхронизированный текст, когда возможно), с фолбэком на
**[Genius]** (огромная база, обычный текст) — если в LRCLIB ничего нет
или вы передали токен Genius. Если ни один из источников не нашёл
текст, инструмент попытается сгенерировать `.lrc` локально с помощью
[Demucs] и [Whisper]. Поддерживается работа на CUDA-совместимом GPU
или на CPU (заметно медленнее).

Поддерживаемые аудиоформаты (всё, что читает `mutagen`):
`FLAC`, `MP3`, `M4A/MP4`, `AAC`, `OGG`, `OPUS`, `WMA`, `WAV`, `APE`, `WV`,
`TAK`.

[LRC]: https://en.wikipedia.org/wiki/LRC_(file_format)
[LRCLIB.net]: https://lrclib.net/
[Genius]: https://genius.com/
[Demucs]: https://github.com/facebookresearch/demucs
[Whisper]: https://github.com/SYSTRAN/faster-whisper


## Быстрый старт (Windows)

1. Установите Python 3.10+ и `git` (или скачайте папку проекта как ZIP).
2. Из корня проекта:

   ```bat
   pip install -r requirements.txt
   python lyricsfag.py "C:\Music\Library"
   ```

3. Сборка готовых `.exe` (пользователю не нужен Python):

   ```bat
   build.bat                REM собирает ОБА варианта (lite и portable) в dist\
   build.bat lite           REM только LyricsFAG-Lite*.exe (~50 MB, модели скачиваются при первом запуске)
   build.bat portable       REM только LyricsFAG-Portable*.exe (~600 MB, полностью офлайн)
   ```

   Подробности — в разделе [Сборка исполняемого файла](#сборка-исполняемого-файла)
   ниже: таблица вариантов и вспомогательные скрипты для пред-загрузки весов.

4. *(Опционально)* Перед первым запуском сохраните локальные веса
   аудиоанализа с помощью встроенных скриптов. Оба лежат в `scripts/`
   и требуют только `python` плюс соответствующую опциональную
   зависимость (`faster-whisper`, `demucs`) из `requirements.txt`:

   ```bat
   REM Веса Whisper (~150 MB для базового размера 'base').
   python scripts\download_whisper_model.py --size base

   REM Веса Demucs (~420 MB для 'htdemucs' = 5 подмоделей по ~84 MB).
   REM --verify прогоняет сквозную проверку загрузки перед сборкой в exe.
   python scripts\download_demucs_model.py --model htdemucs
   python scripts\download_demucs_model.py --model htdemucs --verify
   ```

   Оба скрипта поддерживают докачку через `Range:`-заголовок, поэтому
   при повторном запуске на нестабильном соединении скачиваются лишь
   недостающие байты. Полный справочник по флагам, зеркалам и способам
   восстановления — в разделах [Локальный аудио-фолбэк (faster-whisper)](#локальный-аудио-фолбэк-faster-whisper)
   и [Сборка исполняемого файла](#сборка-исполняемого-файла) ниже.


## Графический режим

Вместе с CLI поставляется десктопный UI на Tk. После ``pip install -r
requirements.txt``:

```bat
python lyricsfag_gui.py
```

Или, в CLI-бинарнике, открыть GUI этим же флагом:

```bat
dist\LyricsFAG.exe --gui
```

Окно предлагает:

* **Выбор папки** с кнопкой Browse
* Чекбоксы **Recursive** / **Force overwrite** / **Dry-run**
* Выпадающий список **Source** (``auto`` / ``lrclib`` / ``genius``)
* Поле **Genius token** (или задайте ``GENIUS_ACCESS_TOKEN`` один раз в окружении)
* Кнопки **Start** / **Stop** с живым прогрессом и возможностью отмены
* **Цветной лог** (зелёный = записано/dry-run, жёлтый = пропущено/не найдено,
  красный = ошибка)
* Кнопку **Open output folder** — открыть обрабатываемую папку в Проводнике


## CLI

```
python lyricsfag.py PATH [options]

positional:
  PATH                       Папка или отдельный аудиофайл. По умолчанию: текущая папка.

options:
  --recursive | --no-recursive
                             Рекурсивно обходить подпапки или только корень.
                             По умолчанию: --recursive.
  --force                    Перезаписывать существующие .lrc.
  --source {auto|lrclib|genius|audio}
                             Источник текстов. По умолчанию: auto (LRCLIB → Genius).
                             'audio' сразу переходит к локальной транскрипции.
  --genius-token TOKEN       Токен Genius API (или задайте GENIUS_ACCESS_TOKEN).
  --use-audio-analysis       Включить локальный faster-whisper как 3-й фолбэк.
  --audio-model {tiny|base|small|medium|large-v3}
                             Размер модели Whisper. По умолчанию: base (~150 MB).
  --audio-model-path PATH    Локальная папка с файлами модели.
  --dry-run                  Показать, что произойдёт, ничего не записывать.
  --quiet | --verbose        Уровень логирования.
  --color {auto|always|never} Цвета ANSI. По умолчанию: auto (только TTY).
  --limit N                  Остановиться после N файлов (0 = без лимита).
  -h, --help                 Показать справку.
```

Коды возврата:
- `0` все выбранные треки обработаны успешно
- `1` один или несколько треков провалились (сетевые ошибки, нет совпадений)
- `2` неверные аргументы (нет пути, указан Genius без токена, ...)


## Как это работает

```
path/Artist - Album/
  01 - Song A.flac  ───────►  01 - Song A.lrc   (синхр., из LRCLIB)
  02 - Song B.flac  ───────►  02 - Song B.lrc   (синхр., из LRCLIB)
  03 - Song C.flac  ───────►  03 - Song C.lrc   (простой текст, из Genius)
  04 - Song D.flac  ───────►  04 - Song D.lrc   (синхр., локальный Whisper)
```

1. Обход директории, сбор всех файлов, похожих на аудио.
2. Чтение тегов через `mutagen` (`title`, `artist`, `album`, `duration`).
   Если теги отсутствуют — разбор имени файла (поддерживаются формы
   `(01) [Artist] Title.ext` и `Artist - Title.ext`).
3. Запрос `LRCLIB.net/api/get?artist_name=…&track_name=…&duration=…`.
   Если приходят синхронизированные строки, они записываются в LRC
   как есть.
4. Если LRCLIB ничего не вернул, запрашивается [Genius] (нужен токен).
   Простой текст пишется обычными строками под мета-заголовками —
   основные плееры (`foobar2000`, `AIMP`, `PowerAmp`, `MusicBee`,
   `Vanilla`, `Musicolet`, `VLC`) отображают такой LRC как
   статический/несинхронизированный текст.
5. (С `--use-audio-analysis`) Если оба источника не дали результата,
   трек транскрибируется локально через `faster-whisper`, и в LRC
   выписываются **синхронизированные** строки по таймкодам сегментов.
   Галлюцинации и тишина отсеиваются по `no_speech_prob` и небольшому
   списку стоп-фраз.


## Формат LRC

```
[ti:Moi... Lolita]
[ar:Alizée]
[al:Gourmandises]
[length:04:26]

[00:12.34]Moi je m'appelle Lolita
[00:16.78]Lo lo lo lo lo lo Lolita
```

В несинхронизированном фолбэке (из Genius) таймкоды опускаются —
остаются только мета-заголовки и сам текст.


## Настройка

- `--genius-token` *или* переменная окружения `GENIUS_ACCESS_TOKEN`.
  Бесплатный токен получается здесь: <https://genius.com/api-clients>.
- Без токена Genius инструмент всё равно пробует LRCLIB. Когда в
  LRCLIB нет синхронизированного текста, но есть обычный, используется
  он; иначе трек считается не найденным.


## Локальный аудио-фолбэк (faster-whisper)

Для треков, по которым LRCLIB и Genius не дали результата, можно
прогнать аудио через локальную модель `faster-whisper`, которая
сразу выдаёт **синхронизированные** таймкоды из звука. Опция
включается флагом.

```bat
pip install faster-whisper

REM 1. Скачайте модель (используется зеркало, обходящее блокировку LFS-CDN,
REM    если канонический путь недоступен). Поддерживает докачку при
REM    TCP-RST посреди потока.
python scripts/download_whisper_model.py --size base

REM 2. Запуск с включённым аудио-фолбэком
python lyricsfag.py "C:\Music\Library" --use-audio-analysis --audio-model base
```

Размеры моделей (для ноутбука на CPU):

| Модель     | Размер  | Скорость vs realtime (CPU) | Замечание по качеству                                  |
|------------|---------|----------------------------|--------------------------------------------------------|
| `tiny`     | ~75 MB  | ~10-30×                    | Быстрая; склонна к галлюцинациям на длинных инструменталах. |
| `base`     | ~150 MB | ~3-10×                     | **По умолчанию**; сбалансированный выбор для большинства музыки. |
| `small`    | ~500 MB | ~1-3×                      | Чище таймкоды LRC; ощутимо медленнее.                  |
| `medium`   | ~1.5 GB | < realtime                 | Максимальная точность; серьёзная нагрузка на CPU+RAM.  |
| `large-v3` | ~3 GB   | < realtime                 | Лучшая точность; настоятельно рекомендуется GPU.      |

### Что оказывается на диске

`python scripts/download_whisper_model.py --size base` записывает файлы
в `models/whisper-base/` рядом с проектом (путь, который анализатор
находит автоматически):

```
models/whisper-base/
├── config.json          (~2 KB)
├── model.bin            (~138 MB — тяжёлые веса)
├── tokenizer.json       (~2 MB)
└── vocabulary.txt       (~450 KB)
```

### Если скрипт не смог скачать `model.bin`

По умолчанию скрипт ходит на `https://hf-mirror.com` с докачкой через
заголовок `Range:`. В сетях, где LFS-хранилище
(`cdn-lfs.huggingface.co`) недоступно для тяжёлого `model.bin`
(типичные Windows + корпоративный DPI), скрипт печатает строку
`FAILED` **с прямыми URL на зеркале и каноническом источнике**, чтобы
вы могли скачать файл из любого браузера:

1. Откройте `https://hf-mirror.com/Systran/faster-whisper-base/tree/main`
   (или канонически `https://huggingface.co/Systran/faster-whisper-base/tree/main`).
2. Скачайте **`model.bin`** (~138 MB) в `models/whisper-base/`.
3. Перезапустите скрипт — он пропустит уже скачанные файлы, потому
   что локальный размер совпадёт с Content-Length.
4. Проверьте: `python lyricsfag.py ... --use-audio-analysis --audio-model base --dry-run`.

Если `model.bin` отсутствует целиком, анализатор возвращает чистый
`LyricsFailure("whisper", "model load failed: ...")` — прогон
продолжается по цепочке LRCLIB+Genius без падения.

### Примечания

- После `pip install faster-whisper` и появления модели на диске
  анализатор грузит её с `local_files_only=True` (интернет не нужен).
- Можно указать собственную папку с моделью через `--audio-model-path`,
  чтобы вшить пред-скачанные веса в ваш `.exe`. Скрипт `build-portable.bat`
  автоматически подхватывает всё, что лежит в `models\whisper-base\` и
  `models\demucs\`, и добавляет в сборку — никаких env-переменных для
  активации не нужно. Старая переменная `LYRICSFAG_AUDIO=1` по-прежнему
  понимается как синоним `build.bat portable` (для обратной
  совместимости), но новый код лучше передавать явным аргументом.
- Чекбокс в GUI «Use audio analysis (local)» включает ту же цепочку
  (LRCLIB → Genius → faster-whisper) без перезапуска CLI.


## Сборка исполняемого файла

`build.bat` — тонкий оркестратор, который запускает **два** варианта
PyInstaller. Оба кладут CLI- и оконный GUI-`.exe` в одну и ту же папку
`dist\`. Файлы отличаются по имени и потому сосуществуют:

| Вариант     | Выходные бинарники                                          | Размер     | Сеть при первом запуске                                                                                          |
|-------------|-------------------------------------------------------------|------------|-----------------------------------------------------------------------------------------------------------------|
| **lite**    | `dist\LyricsFAG-Lite.exe`, `dist\LyricsFAG-GUI-Lite.exe`    | ~50 MB     | Да — при первом `--use-audio-analysis` скачивает Whisper (~150 MB) и Demucs (~420 MB)                            |
| **portable**| `dist\LyricsFAG-Portable.exe`, `dist\LyricsFAG-GUI-Portable.exe` | ~600 MB | Нет — после пред-загрузки весов вспомогательными скриптами `.exe` работает полностью офлайн                       |

### Команды сборки

```bat
REM Оба варианта (по умолчанию; создаёт четыре .exe в dist\).
build.bat

REM Только один вариант.
build.bat lite
build.bat portable
```

Старая переменная `LYRICSFAG_AUDIO=1` по-прежнему распознаётся — она
эквивалентна `build.bat portable`:

```bat
set LYRICSFAG_AUDIO=1 ^& build.bat       REM (legacy)
build.bat portable                        REM (предпочтительно)
```

### Полностью автономная portable-сборка

В portable-`.exe` попадают только те веса, которые вы **сами**
положили в `models\` *до* запуска `build.bat portable`. Запустите
оба вспомогательных скрипта по очереди:

```bat
REM 1. Веса Whisper (~150 MB; после скачивания ~150 MB).
python scripts\download_whisper_model.py --size base

REM 2. Веса Demucs (~420 MB; 5 подмоделей по ~84 MB).
REM    Скрипт читает собственный files.txt demucs, так что раскладка
REM    автоматически подходит под LocalRepo (Path B в models/demucs/README.md).
python scripts\download_demucs_model.py --model htdemucs

REM 3. Проверьте, что директория в рабочем состоянии, перед сборкой.
python scripts\download_demucs_model.py --model htdemucs --verify

REM 4. Соберите пару .exe, готовых работать офлайн.
build.bat portable
```

Если пропустить шаг 2, `build-portable.bat` предупредит и соберёт
частично-portable-`.exe`, который всё равно скачает Demucs при первом
аудиоанализе — сам Whisper вшивается всегда (он лёгкий).

### Как отличить `.exe` друг от друга

* `LyricsFAG-Lite.exe` / `LyricsFAG-GUI-Lite.exe` — для пользователей,
  которым иногда нужен аудиоанализ и у которых стабильный интернет.
* `LyricsFAG-Portable.exe` / `LyricsFAG-GUI-Portable.exe` — для
  USB-носителей, изолированных машин и корпоративных сетей с DPI,
  где 420 MB-загрузка при первом запуске была бы заблокирована.

Для *nix-сборки эквивалентная ручная команда:

```bash
# lite
pyinstaller --noconfirm --onefile --console  --name LyricsFAG-Lite  --paths . --hidden-import faster_whisper lyricsfag.py
pyinstaller --noconfirm --onefile --windowed --name LyricsFAG-GUI-Lite  --paths . --hidden-import faster_whisper lyricsfag_gui.py

# portable (только после того, как оба download-скрипта засеяли models/)
pyinstaller --noconfirm --onefile --console  --name LyricsFAG-Portable --paths . \
  --add-data models/whisper-base;models/whisper-base --hidden-import faster_whisper \
  --add-data models/demucs;models/demucs --collect-all demucs \
  lyricsfag.py
pyinstaller --noconfirm --onefile --windowed --name LyricsFAG-GUI-Portable --paths . \
  --add-data models/whisper-base;models/whisper-base --hidden-import faster_whisper \
  --add-data models/demucs;models/demucs --collect-all demucs \
  lyricsfag_gui.py
```


## Структура проекта

```
LyricsFAG/
├── lyricsfag.py             # точка входа CLI (также обрабатывает --gui)
├── lyricsfag_gui.py         # десктопный UI на Tkinter
├── lyricsfag_lib/
│   ├── __init__.py
│   ├── audio.py             # разбор тегов и имён файлов (mutagen)
│   ├── audio_analysis.py    # faster-whisper + demucs (локальный аудио-фолбэк)
│   ├── device.py            # пробы возможностей CUDA / demucs
│   ├── lyrics.py            # LRCLIB + Genius клиенты
│   ├── lrc.py               # сериализатор LRC
│   └── settings.py          # персистентные настройки GUI (JSON в %APPDATA%)
├── requirements.txt
├── build.bat                # оркестратор: lite / portable / both
├── build-lite.bat           # ~50 MB-пара .exe (модели скачиваются при первом запуске)
├── build-portable.bat       # ~600 MB-пара .exe (веса вшиты)
├── scripts/
│   ├── download_whisper_model.py    # HF-mirror Range-resume загрузчик (Whisper)
│   └── download_demucs_model.py     # demucs files.txt reader + LocalRepo seed
├── models/
│   ├── whisper-base/        # веса faster-whisper (вшиваются, когда есть)
│   └── demucs/              # веса demucs (вшиваются, когда заполнено)
└── test/                    # тестовый альбом Alizée
```


## Фоновый / tray-режим

GUI по умолчанию работает в форграунде. Если нужно подцепить его к
tray-иконке для тихих фоновых прогонов, посмотрите на ``pystray`` —
замените вызов ``LyricsFAGApp.mainloop()`` в ``lyricsfag_gui.py`` на
tray-колбэк, который периодически вызывает ``_on_start`` (вне рамок
этого релиза).


## Лицензия и благодарности

Проект распространяется по лицензии MIT — см. [LICENSE](LICENSE).

Сервисы и библиотеки, благодаря которым LyricsFAG работает:

- [LRCLIB.net](https://lrclib.net/) — бесплатный публичный API текстов.
- [Genius](https://genius.com/) — база текстов (нужен ваш бесплатный токен).
- [lyricsgenius](https://github.com/johnwmillr/lyricsgenius) — MIT, интеграция с Genius.
- [mutagen](https://github.com/quodlibet/mutagen) — GPLv2, чтение тегов аудио.
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) — MIT, опциональная локальная транскрипция.
- [Demucs](https://github.com/facebookresearch/demucs) — MIT, опциональное отделение вокала перед Whisper.

Эта кодовая база написана с существенной помощью AI-кодинг-ассистента
([Codebuff](https://codebuff.com), модель `minimax/minimax-m3`) под
руководством и ревью человека; полный дисклеймер — в шапке этого README.
