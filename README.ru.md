# LyricsFAG

[![GitHub repo](https://img.shields.io/badge/GitHub-reality52%2FLyricsFAG-181717?logo=github)](https://github.com/reality52/LyricsFAG)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![RU](https://img.shields.io/badge/README-%D0%A0%D1%83%D1%81%D1%81%D0%BA%D0%B8%D0%B9-blue)](README.ru.md)
[![Latest release](https://img.shields.io/badge/release-v1.2.1-blue)](RELEASE_NOTES.md)

> **Проект создан с помощью ИИ.** Эта кодовая база написана при существенной
> помощи AI-кодинг-ассистента ([Codebuff](https://codebuff.com), модель
> `minimax/minimax-m3`) под руководством и ревью человека. Код прошёл
> тестирование, но не сертификацию -- запуск LyricsFAG на вашей фонотеке
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
**[Genius]** (огромная база, обычный текст) -- если в LRCLIB ничего нет
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


## Возможности на одной странице

- **Сначала синхронизированный, потом обычный текст.** LRCLIB для
  текста с таймкодами, Genius для обычного текста, локальный Whisper +
  Demucs как 3-й синтетический фолбэк, когда оба веб-источника дали
  промах.
- **Opt-in запись тегов** (`--embed-in-tags` в CLI / галочка "Embed
  lyrics in tags" в GUI). Помимо `.lrc` пишется plain-text тег
  текста песни прямо в аудиофайл -- `USLT` для MP3, Vorbis `LYRICS`
  для FLAC/OGG-Vorbis/Opus, атом `©lyr` для MP4/M4A, дескриптор
  `WM/Lyrics` для WMA, APEv2 `LYRICS` для WavPack / APE. `.lrc`
  сохраняет синхронизацию и расширенные заголовки; в тег попадает
  только сам текст песни. WAV, TAK и сырой AAC стандарта на тег
  не имеют и тихо пропускаются (в логе -- суффикс `[tags=skipped
  (no standard tag)]`, батч не падает). `--force` перезаписывает
  существующий тег, `--no-force` -- оставляет, ровно как для `.lrc`.
  Сбой записи тега НЕ даунгрейдит статус `.lrc` (sitecar уже на
  диске, в логе вы увидите `[tags=ERROR: …]`, не красный fail).
- **Расширенные `.lrc` заголовки.** Каждый поставляемый файл получает
  `[ti:]` / `[ar:]` / `[al:]` / `[length:]` и, если теги исходного файла
  их содержат, -- `[au:composer]`, `[lang:language]`, `[year:YYYY]`.
  Кредит `[tool:LyricsFAG X.Y.Z]` штампуется на каждой записи, так
  что файл всегда атрибутируется. *(Новое в v1.2.1.)*
- **Защитные фильтры Genius.** Wiki / list-страницы, которые раньше
  высыпали 2000+ строк name-registry в ваш `.lrc`, детектятся и
  чисто отбраковываются; wrong-song auto-corrects, которые шарили
  одно ключевое слово с вашим запросом, тоже отбраковываются.
  *(Новое в v1.2.0.)*
- **Две PyInstaller-сборки, по одному бинарю каждая.** Тонкий
  `~50 МБ` `lite` `.exe` (только LRCLIB + Genius) и `~4 ГБ` `portable`
  `.exe`, бандлящий `torch` + `demucs` + `faster-whisper` + веса моделей
  (дефолтный `whisper-small` ~500 МБ + `htdemucs_ft` ~84 МБ) для
  полностью офлайнового использования. Каждый бинарь dual-mode:
  двойной клик открывает Tk-GUI, аргумент с путём из терминала
  запускает CLI.
- **PyTorch 2.6 ready.** Общий `.th`-scoped `torch.load` monkey-patch
  чинит `Weights only load failed` `WeightsUnpickler`-падение demucs
  4.0.1 на первом запуске под PyTorch 2.6+. *(Новое в v1.1.4.)*
- **Оба UI делят один движок.** Tk-базированный GUI (`lyricsfag_gui.py`)
  и CLI (`lyricsfag.py`) консумируют тот же `process_one()`-
  воркер, так что `_format_summary_lines()` / строка `Done in N.--..`
  идентичны в обоих.


## Быстрый старт (Windows)

1. Установите Python 3.10+ и `git` (или скачайте папку проекта как ZIP).
2. Из корня проекта:

   ```bat
   REM Основная цепочка (LRCLIB + Genius).  Всегда устанавливается.
   pip install -r requirements.txt
   python lyricsfag.py "C:\Music\Library"
   ```

3. Сборка готового `.exe` (пользователю не нужен Python):

   ```bat
   build.bat                REM собирает ОБА варианта (lite и portable) в dist\  (по одному .exe на вариант)
   build.bat lite           REM только LyricsFAG-Lite.exe     (~50 МБ; модели скачиваются при первом аудиоанализе)
   build.bat portable       REM только LyricsFAG-Portable.exe (~4 ГБ; полностью офлайн; вшит whisper-small + htdemucs_ft)
   ```

   Итоговый `.exe` -- dual-mode: двойной клик в Проводнике открывает
   Tk-GUI; запуск с аргументом-путь из PowerShell / cmd запускает
   CLI-цикл. Один и тот же бинарь, та же диспетчеризация в
   `lyricsfag._wants_gui`. Подробности -- в
   [Сборка исполняемого файла](#сборка-исполняемого-файла) ниже: таблица
   вариантов и скрипты для пред-загрузки весов.

4. *(Опционально)* Перед первым запуском сохраните локальные веса
   аудиоанализа с помощью встроенных скриптов. Оба лежат в `scripts/`
   и требуют только `python` плюс соответствующую опциональную
   зависимость (`faster-whisper`, `demucs`) из `requirements-audio.txt`:

   ```bat
   REM Веса Whisper (~150 MB для базового размера 'base').
   python scripts\download_whisper_model.py --size base

   REM Веса Demucs для дефолтного 'htdemucs_ft' (~336 MB:
   REM BagOfModels из 4 sub-models x ~84 MB на demucs 4.0.1).
   REM --verify прогоняет сквозную проверку загрузки перед сборкой в exe.
   REM (Флаг --model не нужен -- scripts/download_demucs_model.py теперь
   REM  по умолчанию использует htdemucs_ft.)
   python scripts\download_demucs_model.py
   python scripts\download_demucs_model.py --verify
   ```

   *(Если вы явно включили старый 5-модельный бэг через
   ``--demucs-model htdemucs``, скачивайте именно его: на demucs 4.0.1
   это одна предобученная HTDemucs на ~84 MB -- старое 5-модельное
   описание pre-dates 4.0.1 и больше не применяется:*

   ```bat
   python scripts\download_demucs_model.py --model htdemucs --verify
   ```

   Оба скрипта поддерживают докачку через `Range:`-заголовок, поэтому
   при повторном запуске на нестабильном соединении скачиваются лишь
   недостающие байты. Полный справочник по флагам, зеркалам и способам
   восстановления -- в разделах
   [Локальный аудио-фолбэк (faster-whisper)](#локальный-аудио-фолбэк-faster-whisper)
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
* Выпадающий список **Source** (``auto`` / ``lrclib`` / ``genius`` / ``audio``)
* Поле **Genius token** (или задайте ``GENIUS_ACCESS_TOKEN`` один раз в окружении)
* Главный переключатель **Use audio analysis (local)** -- при включении
  Demucs жёстко включён (отдельного переключателя нет); при выборе
  ``Source = audio`` чекбокс принудительно включается и блокируется, чтобы
  цепочка оставалась согласованной
* Выпадающие списки **Whisper model** + **Device** + опциональное локальное
  **Model path**
* Кнопки **Start** / **Stop** с живым прогрессом и возможностью отмены
* **Бейдж GPU / CPU** в правом нижнем углу окна, отслеживающий выбор
  пользователя в Device
* **Цветной лог** (зелёный = записано/dry-run, жёлтый = пропущено/не найдено,
  красный = ошибка, **оранжевый = Whisper-транскрипция** -- синтетика, может
  содержать ASR-ошибки, видно с одного взгляда)
* **Попап завершения** -- Done / Stopped / worker-crashed, после каждого
  прогона, кроме пустых папок
* Кнопку **Open output folder** -- открыть обрабатываемую папку в Проводнике
* Кнопку **`?`  Help** (последняя в ряду тулбара) -- попап с цепочкой
  провайдеров, подсказкой про токен Genius, размерами загрузки при первом
  запуске и советом про `--dry-run`
* **Тултипы** при наведении на все основные интерактивные элементы
  (entries, чекбоксы, комбобоксы, кнопки) -- задержка hover 500 мс,
  автоскрытие 8 с


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
                             Источник текстов. По умолчанию: auto (LRCLIB -> Genius).
                             'audio' сразу переходит к локальной транскрипции.
  --genius-token TOKEN       Токен Genius API (или задайте GENIUS_ACCESS_TOKEN).
  --use-audio-analysis       Включить локальный faster-whisper как 3-й фолбэк.
  --audio-model {tiny|base|small|medium|large-v3}
                             Размер модели Whisper. По умолчанию: base (~150 MB).
  --audio-model-path PATH    Локальная папка с файлами модели.
  --device {auto|cuda|cpu}   Вычислительное устройство для faster-whisper (+ demucs).
                             По умолчанию: auto (CUDA если есть, иначе CPU).
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
2. Чтение тегов через `mutagen` (`title`, `artist`, `album`, `composer`,
   `language`, `year`, `duration`). Если теги отсутствуют -- разбор имени
   файла (поддерживаются формы `(01) [Artist] Title.ext` и
   `Artist - Title.ext`).
3. Запрос `LRCLIB.net/api/get?artist_name=…&track_name=…&duration=…`.
   Если приходят синхронизированные строки, они записываются в LRC
   как есть.
4. Если LRCLIB ничего не вернул, запрашивается [Genius] (нужен токен).
   Результат валидируется **защитными фильтрами Genius** (v1.2.0+):
   * Wiki / list-страницы, чьё тело -- alphabet-navigation header
     (`A | B | C | … | Z`) или превышает 1000 строк, отбраковываются с
     диагностикой `genius: page looks like a Genius list/index (...)` --
     они раньше высыпали 2000+ строк name-registry в пользовательский
     `.lrc`.
   * Wrong-song auto-corrects, чей title / artist не делят достаточно
     ключевых слов с пользовательскими тегами, отбраковываются с
     диагностикой `genius: song mismatch: query 'Yesterday' by 'Beatles' !=
     response 'Imagine' by 'John Lennon' (title=0.00, artist=1.00)` --
     чтобы пользователь мог поправить теги без re-run.
   Простой текст из легитимных совпадений пишется обычными строками
   под мета-заголовками -- основные плееры (`foobar2000`, `AIMP`,
   `PowerAmp`, `MusicBee`, `Vanilla`, `Musicolet`, `VLC`) отображают
   такой LRC как статический/несинхронизированный текст.
5. (С `--use-audio-analysis`) Если оба источника не дали результата,
   трек транскрибируется локально через `faster-whisper`. Галлюцинации
   и тишина отсеиваются по `no_speech_prob` и небольшому списку
   стоп-фраз. Вокальная изоляция Demucs 4.x прогоняется **обязательно
   перед** Whisper (обязательно с v1.1.0, отдельного переключателя
   нет -- пользователь может выйти из *всего* локального фолбэка,
   сняв главную галку `Use audio analysis`).


## Записываемый формат LRC

```lrc
[ti:Moi... Lolita]
[ar:Alizée]
[al:Gourmandises]
[au:Laurent Boutonnat]
[lang:fr]
[year:2000][tool:LyricsFAG 1.2.1] 
[length:04:26]

[00:12.34]Moi je m'appelle Lolita
[00:16.78]Lo lo lo lo lo lo Lolita
```

Несколько вещей, которые стоит знать про заголовки:

* `[ti:]` / `[ar:]` / `[al:]` эмитятся только когда теги исходного
  аудио (или распарсенное имя файла) их заполняют.
* `[au:composer]` эмитится только когда `TCOM` / `\xa9wrt` /
  `COMPOSER` не пусто. *(Новое в v1.2.1.)*
* `[lang:language]` эмитится только когда `TLAN` / `LAN` не пусто.
  Pass-through (без ISO-639-1 санитизации) -- тегированный `English`
  попадает как `[lang:English]`. *(Новое в v1.2.1.)*
* `[year:YYYY]` эмитится только когда извлечение года даёт
  4-цифровое значение. Reader берёт первый 4-цифровой run из
  `TDRC` / `TYER` / `\xa9day` / `DATE` / `YEAR`, так что
  тегированный `TDRC:"2024-08-01"` аккуратно ложится на `2024`.
  *(Новое в v1.2.1.)*
* `[tool:LyricsFAG X.Y.Z]` эмитится на **каждой** записи через
  `process_one()` безусловно, так что текущая версия библиотеки
  всегда штампуется в файл. Используйте как простейший
  upgrade-verifier: re-process'ните один файл и посмотрите на
  правильный номер версии. *(Новое в v1.2.1; бампается на каждом
  релизе.)*
* `[length:]` эмитится когда длительность исходного аудио известна.

В несинхронизированном фолбэке (из Genius) таймкоды опускаются --
остаются только мета-заголовки и сам текст, но новые liner-notes-поля
выше всё равно появляются без изменений.


## Настройка

- `--genius-token` *или* переменная окружения `GENIUS_ACCESS_TOKEN`.
  Бесплатный токен получается здесь: <https://genius.com/api-clients>.
- Без токена Genius инструмент всё равно пробует LRCLIB. Когда в
  LRCLIB нет синхронизированного текста, но есть обычный, используется
  он; иначе трек считается не найденным.
- Состояние GUI (folder, recursive / force / dry-run / source /
  genius_token / audio_model / audio_model_path / device) персистится
  в `settings.json` под OS-конфиг-папкой на **Start** и **Close**, так
  что виджеты при следующем запуске приходят уже заполненными. Токен
  Genius хранится в plaintext by design (он и так живёт в окружении
  процесса); см. SECURITY-заметку в `lyricsfag_lib/settings.py` с
  обоснованием.
- `settings.json` от pre-v1.1.0 со старым ключом `demucs` молча
  отбрасывается при загрузке (on/off demucs-комбобокс был удалён
  в lockstep с CLI-флагом `--no-demucs` в v1.1.0).


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
| `tiny`     | ~75 MB  | ~10-30x                    | Быстрая; склонна к галлюцинациям на длинных инструменталах. |
| `base`     | ~150 MB | ~3-10x                     | **По умолчанию**; сбалансированный выбор для большинства музыки. |
| `small`    | ~500 MB | ~1-3x                      | Чище таймкоды LRC; ощутимо медленнее.                  |
| `medium`   | ~1.5 GB | < realtime                 | Максимальная точность; серьёзная нагрузка на CPU+RAM.  |
| `large-v3` | ~3 GB   | < realtime                 | Лучшая точность; настоятельно рекомендуется GPU.      |

### Что оказывается на диске

`python scripts/download_whisper_model.py --size base` записывает
файлы в `models/whisper-base/` рядом с проектом (путь, который
анализатор находит автоматически):

```
models/whisper-base/
├── config.json          (~2 KB)
├── model.bin            (~138 MB -- тяжёлые веса)
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
3. Перезапустите скрипт -- он пропустит уже скачанные файлы, потому
   что локальный размер совпадёт с Content-Length.
4. Проверьте: `python lyricsfag.py ... --use-audio-analysis --audio-model base --dry-run`.

Если `model.bin` отсутствует целиком, анализатор возвращает чистый
`LyricsFailure("whisper", "model load failed: ...")` -- прогон
продолжается по цепочке LRCLIB+Genius без падения.

### Размеры загрузки Demucs (v1.1.4+)

WARNING при первом запуске теперь показывает **корректные** размеры
для раскладки demucs 4.0.1:

| Модель | Размер | Примечания |
|--------|--------|------------|
| `htdemucs_ft` *(дефолт)* | ~336 MB | `BagOfModels` из 4 sub-models (4 × ~84 MB) per `htdemucs_ft.yaml`. Music-only fine-tune от Meta. |
| `htdemucs` *(legacy)* | ~84 MB | Одна предобученная `HTDemucs` per `htdemucs.yaml`. Используйте для более лёгкой загрузки. |

Прежние значения README (~84 MB для `htdemucs_ft`, ~420 MB для
`htdemucs`) были инвертированы; WARNING теперь указывает на
правильные числа для реальности demucs 4.0.1.

### Воркэраунд PyTorch 2.6 (v1.1.4+)

Общий `.th`-scoped `torch.load` monkey-patch
(`lyricsfag_lib/_torch_compat.py`) чинит `Weights only load failed ...
GLOBAL fractions.Fraction`-падение demucs 4.0.1 на первом запуске
под PyTorch 2.6+. Патч пробрасывает `weights_only=False` только для
`*.th`-файлов (веса demucs, которые мы только что скачали с
`facebookresearch/demucs`) и сохраняет безопасный 2.6-дефолт для
всех остальных `torch.load`-вызывов в процессе (в частности,
Silero VAD в faster-whisper). Патч ленивый (только при первом
использовании demucs) и идемпотентный.

### Примечания

- После `pip install -r requirements-audio.txt` (который тянет
  `faster-whisper`) и появления модели на диске анализатор
  грузит её с `local_files_only=True` (интернет не нужен).
- **lite**-сборка PyInstaller **не** ставит
  `requirements-audio.txt`, поэтому её пользователи видят
  `LyricsFailure` с подсказкой про portable-сборку. Подробности --
  в [Сборка исполняемого файла](#сборка-исполняемого-файла).
- Можно указать собственную папку с моделью через `--audio-model-path`,
  чтобы вшить пред-скачанные веса в ваш `.exe`. Скрипт `build-portable.bat`
  автоматически подхватывает всё, что лежит в `models\whisper-base\` и
  `models\demucs\`, и добавляет в сборку -- никаких env-переменных для
  активации не нужно. Старая переменная `LYRICSFAG_AUDIO=1` по-прежнему
  понимается как синоним `build.bat portable` (для обратной
  совместимости), но новый код лучше передавать явным аргументом.
- Чекбокс в GUI "Use audio analysis (local)" включает ту же цепочку
  (LRCLIB -> Genius -> faster-whisper) без перезапуска CLI.


## Сборка исполняемого файла

`build.bat` -- тонкий оркестратор, который запускает **два** варианта
PyInstaller. Каждый вариант даёт **один dual-mode `.exe`** в папке
`dist\`. Один бинарь обслуживает обе поверхности:

* **Двойной клик в Проводнике (нет argv)** → `_wants_gui()` возвращает
  `True` → `lyricsfag_gui.main()` запускает Tk-окно. Консольный
  процесс pyinstaller'а остаётся жить под ним, Tk-окно оверлеит
  консоль (стандартный Windows-паттерн, как у `git.exe` / `python.exe`).
* **Запуск с аргументами из терминала** (позиционный путь или любой
  флаг) → `_wants_gui()` возвращает `False` → argparse-CLI-цикл,
  цветные строки лога, финальное summary. Тот же `.exe`, никакого
  второго бинаря.

| Вариант     | Выходной бинарь                  | Размер        | Аудио-анализ                          | Сеть при первом запуске |
|-------------|----------------------------------|---------------|---------------------------------------|-------------------------|
| **lite**    | `dist\LyricsFAG-Lite.exe`        | **~50 МБ**    | **Не поддерживается** (только LRCLIB + Genius) | Да  -- веса whisper+demucs скачиваются при первом аудиоанализе (lite-пользователи получают `LyricsFailure`-подсказку про portable) |
| **portable**| `dist\LyricsFAG-Portable.exe`    | **~4 ГБ**     | Полный Whisper (дефолт `small`) + Demucs (`htdemucs_ft`) + бандл весов | Нет -- после пред-загрузки `models\whisper-small\` и `models\demucs\` через скрипты ниже `.exe` работает полностью офлайн |

> **Почему lite ~50 МБ, а portable ~4 ГБ?**
> `demucs` 4.x тянет `torch` транзитивно (~3.8 ГБ на Windows).
> PyInstaller `--onefile` бандлит всю Python-среду в `.exe`, поэтому
> portable платит полную цену torch плюс вшитые веса `whisper-small`
> (~500 МБ) плюс `htdemucs_ft` (~84 МБ) = ~4 ГБ. Lite обходит эту
> цену тем, что просто не ставит `requirements-audio.txt`. **Единственная**
> разница между двумя вариантами -- ставится ли `requirements-audio.txt`
> перед запуском pyinstaller. См. `requirements.txt` и
> `requirements-audio.txt`.

> **Изменение поведения vs v1.1.2:** **lite** больше **не**
> поддерживает локальный аудио-анализ. Пользователи, которые
> включат "Use audio analysis" в lite GUI, получат чистый
> `LyricsFailure` с подсказкой про portable-сборку.

### Команды сборки

```bat
REM Оба варианта (по умолчанию; создаёт два dual-mode .exe в dist\).
build.bat

REM Только один вариант.
build.bat lite
build.bat portable
```

Итоговый `.exe` сразу dual-mode -- никаких sub-бинарников GUI/CLI
для отгрузки рядом. Диспетчеризация -- одна строка в
`lyricsfag._wants_gui`:

```python
if not args_list:                                  # 1. двойной клик
    return True
if re.search(r"^--?gui(=|$)", any_arg):           # 2. явный --gui
    return True
return False                                      # 3. иначе -> CLI
```

Старая переменная `LYRICSFAG_AUDIO=1` по-прежнему распознаётся --
она эквивалентна `build.bat portable`:

```bat
set LYRICSFAG_AUDIO=1 ^& build.bat       REM (legacy)
build.bat portable                        REM (предпочтительно)
```

### Полностью автономная portable-сборка

В portable-`.exe` попадают только те веса, которые вы **сами**
положили в `models\` *до* запуска `build.bat portable`. Запустите
оба вспомогательных скрипта по очереди:

```batREM 1.  Веса Whisper 'small' (~500 МБ; v1.2.1 дефолт, вшивается в
REM    portable-сборку).  --size base / --size medium тоже работают,
REM    если хочется вшить другую модель, но build-хелпер авто-детектит
REM    models\whisper-[small|base] независимо от того, что засеяно.
python scripts\download_whisper_model.py

REM 2. Веса Demucs для дефолтного 'htdemucs_ft' (~84 МБ, единичный
REM    pretrained run на demucs 4.0.1). Скрипт читает собственный
REM    YAML-дескриптор demucs, так что раскладка автоматически
REM    подходит под LocalRepo (Path B в models\demucs\README.md).
REM    (Флаг --model не нужен -- скрипт по умолчанию использует htdemucs_ft.)
python scripts\download_demucs_model.py

REM 3. Проверьте, что директория в рабочем состоянии, перед сборкой.
python scripts\download_demucs_model.py --verify

REM    (Если вы закрепили старый --demucs-model htdemucs, передайте здесь
REM    --model htdemucs вместо дефолтного -- на demucs 4.0.1 это одна
REM    предобученная HTDemucs на ~84 МБ; старое 5-модельное описание
REM    pre-dates 4.0.1 и больше не применяется.)

REM 4. Соберите готовый к офлайну .exe.
build.bat portable
```

Если пропустить шаг 2, `build-portable.bat` предупредит и соберёт
частично-portable-`.exe`, который всё равно скачает Demucs при первом
аудиоанализе -- сам Whisper вшивается всегда (он лёгкий).

### Как отличить `.exe` друг от друга

* `LyricsFAG-Lite.exe` -- для пользователей, которым иногда нужен
  аудиоанализ и у которых стабильный интернет (веса Whisper + Demucs
  скачиваются при первом `--use-audio-analysis`).
* `LyricsFAG-Portable.exe` -- для USB-носителей, изолированных
  машин и корпоративных сетей с DPI, где 500 МБ-загрузка при первом
  запуске была бы заблокирована. Вшит `models\whisper-small\` и
  `models\demucs\` для полностью офлайновой работы.

В конце сборки вы увидите summary вида::

```
=== Build complete ===
  dist\LyricsFAG-Lite.exe       (dual-mode, ~50 МБ; модели скачиваются при первом запуске)
    CLI:    dist\LyricsFAG-Lite.exe "C:\Music\Library"
    GUI:    Двойной клик в Проводнике.  Тот же .exe -- _wants_gui() авто-диспетчит.
  dist\LyricsFAG-Portable.exe   (dual-mode, ~4 ГБ; полностью офлайн; засеяны small whisper + htdemucs_ft)
    CLI:    dist\LyricsFAG-Portable.exe "C:\Music\Library"
    GUI:    Двойной клик в Проводнике.  Тот же .exe -- _wants_gui() авто-диспетчит.
```

Для *nix-сборки эквивалентная ручная команда:

```bash
# lite (один dual-mode .exe)
pyinstaller --noconfirm --onefile --console  --name LyricsFAG-Lite  --paths . lyricsfag.py

# portable (один dual-mode .exe; только после того, как оба download-скрипта
#  засеяли models/whisper-small + models/demucs)
pyinstaller --noconfirm --onefile --console  --name LyricsFAG-Portable --paths . \
  --add-data models/whisper-small;models/whisper-small --collect-all faster_whisper \
  --add-data models/demucs;models/demucs --collect-all demucs \
  lyricsfag.py
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
│   ├── _torch_compat.py     # PyTorch 2.6 / demucs 4.0.1 weights_only monkey-patch
│   ├── device.py            # пробы возможностей CUDA / demucs
│   ├── lyrics.py            # LRCLIB + Genius клиенты (+ защитные фильтры, v1.2.0+)
│   ├── lrc.py               # сериализатор LRC (+ liner-notes-поля, v1.2.1+)
│   ├── tags.py              # opt-in запись тегов (USLT / LYRICS / ©lyr / WM/Lyrics / APEv2)
│   └── settings.py          # персистентные настройки GUI (JSON в %APPDATA%)
├── requirements.txt         # основные зависимости (всегда ставятся)
├── requirements-audio.txt   # опционально: Whisper + Demucs + torch
├── build.bat                # оркестратор: lite / portable / all
├── build-lite.bat           # один ~50 МБ .exe (модели скачиваются при первом запуске)
├── build-portable.bat       # один ~4 ГБ .exe (веса вшиты)
├── scripts/
│   ├── download_whisper_model.py    # HF-mirror Range-resume загрузчик (Whisper)
│   └── download_demucs_model.py     # demucs YAML-дескриптор + LocalRepo seed
├── models/
│   ├── whisper-small/       # веса faster-whisper (v1.2.1 дефолт; вшиваются, когда есть)
│   └── demucs/              # веса demucs (вшиваются, когда заполнено)
└── test/                    # тестовый альбом Alizée
```


## Фоновый / tray-режим

GUI по умолчанию работает в форграунде. Если нужно подцепить его к
tray-иконке для тихих фоновых прогонов, посмотрите на ``pystray`` --
замените вызов ``LyricsFAGApp.mainloop()`` в ``lyricsfag_gui.py`` на
tray-колбэк, который периодически вызывает ``_on_start``
(вне рамок текущего релиза).


## Текущая версия: v1.2.1

Подробные заметки к релизам -- единый [`RELEASE_NOTES.md`](RELEASE_NOTES.md)
в корне репозитория (все поставленные версии в одном файле,
newest-first). Краткое summary каждого релиза -- ниже, чтобы
свежий читатель не скроллил весь `RELEASE_NOTES.md`:

### v1.2.1 -- LRC liner-notes + `--embed-in-tags` + dual-mode 2-EXE-сборка (patch-релиз)

* **Заголовки LRC liner-notes.** Чтение тегов исходного аудио
  для `TCOM` / `\xa9wrt` / `COMPOSER`, `TLAN` / `LAN` и
  `TDRC` / `TYER` / `\xa9day` / `DATE` / `YEAR`, затем проброс
  их в LRC как `[au:]` / `[lang:]` / `[year:YYYY]` заголовки
  (каждый условен на non-empty / non-zero -- молча скипается
  на ошибочных тегах).
* **Продюсерский кредит `[tool:LyricsFAG 1.2.1]`** штампуется
  на **каждой** записи `.lrc` -- файл всегда атрибутируется.
  Используйте как простейший upgrade-verifier: re-process'ните
  один файл и ищите `[tool:LyricsFAG 1.2.1]` в результирующем
  `.lrc`.
* **`--embed-in-tags` opt-in запись тегов.** При передаче нового
  CLI-флага (или галочки "Embed lyrics in tags" в GUI) LyricsFAG
  дополнительно пишет plain-text тег текста песни прямо в
  нативные метаданные аудиофайла -- ID3 `USLT` для MP3, Vorbis
  `LYRICS` для FLAC/OGG-Vorbis/Opus, атом MP4 `©lyr` для M4A,
  дескриптор ASF `WM/Lyrics` для WMA, APEv2 `LYRICS` для
  WavPack/APE. WAV, TAK и сырой AAC стандарта на тег не имеют и
  тихо пропускаются (с суффиксом `[tags=skipped (no standard tag)]`
  в логе; батч НЕ падает). `.lrc` сохраняет синхронизированный
  /расширенный-заголовками вид; в тег попадает только сам текст.
  `--force` перезаписывает существующий тег; `--no-force`, как и
  для `.lrc`, оставляет существующий тег в покое. Сбой записи тега
  **не** даунгрейдит статус `.lrc` (sitecar уже на диске, в логе
  вы увидите `[tags=ERROR: ...]`, а не красный fail).
* **Dual-mode 2-EXE-сборка.** Каждый вариант теперь даёт **один**
  dual-mode `.exe` (а не пару CLI + GUI). Какая поверхность активна
  определяется в runtime через `lyricsfag._wants_gui()`: пустой
  argv открывает Tk-GUI; `--gui` / `-g` делает то же явно; любой
  другой argv (позиционный путь или флаг) -- CLI-цикл. Один и тот
  же `.exe`, одна точка входа (`lyricsfag.py`), никакого второго
  бинаря.
* **Whisper-small бандлится по умолчанию.** Portable-сборка вшивает
  `models\whisper-small\` (~500 МБ, размер, на который дефолтает
  `download_whisper_model.py`) вместо меньшего
  `models\whisper-base/` (~150 МБ). Более чистые таймкоды транскрипции
  заметно сокращают ручную правку на плотных миксах. Build-хелпер
  по-прежнему авто-детектит `whisper-base` как backward-compat
  фолбэк -- v1.2.x dev-деревья не требуют re-seed.
* **`--collect-all faster_whisper`** в PyInstaller заменил старый
  `--hidden-import faster_whisper`, так что вшитый `.exe` несёт все
  runtime-данные и CTranslate2 .so-файлы faster-whisper, по паритету
  с уже-имеющимся для demucs.
* **Модуль `lyricsfag_lib.tags`** -- новый дом для mutagen-диспатча
  записи тегов. `embed_lyrics(path, plain_text, force=...)` возвращает
  dataclass `EmbedResult` (status, format, tag_name, error) так что
  CLI / GUI могут рендерить суффикс `[tags=...]` в логе без
  инспектирования исключений.
* Задетые файлы: `lyricsfag.py`, `lyricsfag_gui.py`,
  `lyricsfag_lib/` (новый `tags.py`, твики audio.py / lrc.py /
  settings.py), `scripts/download_whisper_model.py` (дефолтный
  размер `small`, дефолтная папка `models/whisper-small`),
  `build.bat`, `build-lite.bat`, `build-portable.bat`, `README.md`,
  `README.ru.md`.

### v1.2.0 -- Защитные фильтры Genius + чистка мёртвого кода (минорный релиз)

* `lyrics.LyricsFetcher` (бывший typo-and-spell-prone Genius-шаг)
  теперь отбраковывает два класса плохих результатов, которые раньше
  приземлялись в пользовательский `.lrc` без предупреждения:
  * **Wiki / list-страницы**, чьё тело -- alphabet-navigation header
    (`A | B | C | ... | Z`) или длиннее 1000 строк. Страницы вроде
    `List of Virtual YouTubers (VTubers)` раньше высыпали 2000+ строк
    name-registry в song's `.lrc` -- теперь мы отбраковываем с
    `LyricsFailure("genius", "page looks like a Genius list/index (...)")`
    и передаём управление на LRCLIB.
  * **Wrong-song auto-corrects** -- Genius'овский typo-tolerant
    поиск мог, например, заматчить `"Yesterday" by "Beatles"` на
    `"Imagine" by "John Lennon"` на частичном keyword-overlap.
    Token-set Overlap Coefficient `|A ∩ B| / min(|A|, |B|)` >= 0.5
    на ОБА title и artist независимо ловит их с диагностикой, которая
    называет обе стороны.
* Чистка: удалены мёртвые `_looks_instrumental` /
  `_INSTRUMENTAL_TITLE_RE` в `lyrics.py`, пустой `_VALID_DEMUCS`
  frozenset в `settings.py`, избыточные `getattr(args, ...)` дефолты
  в `lyricsfag.py`, и `SyntaxWarning: invalid escape sequence` от
  `\` в docstring'овых Windows-path-примерах в `settings.py`,
  триггерившийся под `python -W error::SyntaxWarning` -- `\` заменён
  на `\\` так что docstring рендерит реальные backslash'и и варнинг
  замолкает.
* Без поведенческих изменений для корректно-тегированных файлов;
  оба фильтра -- аддитивные отбраковки и только.

### v1.1.4 -- PyTorch 2.6 совместимость + фикс размеров загрузки Demucs (patch-релиз)

* **PyTorch 2.6 ready.** Общий `.th`-scoped `torch.load`
  monkey-patch (`lyricsfag_lib/_torch_compat.py`) чинит
  `Weights only load failed ... GLOBAL fractions.Fraction`
  `WeightsUnpickler`-падение demucs 4.0.1 на первом запуске под
  PyTorch 2.6+. Патч ленивый (только при первом использовании demucs)
  и идемпотентный; он пробрасывает `weights_only=False` только для
  `*.th`-файлов, так что безопасный PyTorch 2.6 дефолт сохраняется
  для всех остальных `torch.load`-вызывов в процессе.
* **Размеры загрузки Demucs исправлены.** `_DEMUCS_DOWNLOAD_HINTS_MB`
  в `audio_analysis.py` имел инвертированные значения для двух
  моделей; WARNING показывал `~84 MB` для 4-sub-model `htdemucs_ft`
  и `~420 MB` для одной предобученной `htdemucs`. Числа теперь
  соответствуют реальности demucs 4.0.1.
* `models/demucs/README.md` обновлён в 8 местах под 4.0.1
  YAML-дескрипторы.
* `build.bat` `TARGET=all` guard разбит на две однострочные
  compound-`if` строки для совместимости со старыми Windows
  batch-парсерами.
* Filename-based instrumental short-circuit пере-анкерован к явным
  `(?:^|[\s\-_.])` границам (v1.1.2 `\b`-форма была чрезмерно
  жадной на определённых формах имён файлов).

### v1.1.3 -- Lite-сборка теперь действительно lite (patch-релиз)

* `requirements.txt` разделён на основной `requirements.txt` и
  опциональный `requirements-audio.txt`. Последний ставится
  только `build-portable.bat` (и dev-установками, которым нужен
  полный аудио-стек в командной строке).
* `build-lite.bat` больше не ставит `requirements-audio.txt`,
  поэтому итоговые `LyricsFAG-Lite.exe` / `LyricsFAG-GUI-Lite.exe`
  больше не бандлят `torch` (~3.8 GB на Windows) и остаются
  в задокументированных ~50 МБ. Из вызова PyInstaller убран
  `--hidden-import faster_whisper`, так как пакет больше
  не установлен.
* `build.bat`-оркестратор больше не затирает portable-.exe при
  сборке обоих вариантов. Раньше каждый скрипт варианта начинал
  с собственного `rmdir /s /q dist`, так что `build.bat all`
  оставлял только lite-.exe в `dist\`, а пара portable на ~6.4 ГБ
  молча удалялась. В результате `build.bat all` теперь даёт
  **четыре** exe в `dist\` (по одному CLI + GUI на вариант).

### v1.1.2 -- Фикс границ instrumental regex (хотфикс)

* Boundary-класс в `INSTRUMENTAL_FILENAME_RE` расширен с узкого
  ASCII-набора на Unicode-aware `\b`, так что имена файлов с
  парными/квадратными/фигурными скобками, кавычками, двоеточиями
  или запятыми вокруг ключевого слова корректно шорткатят
  аудио-ветку. `Song (Off Vocal).flac`,
  `Song [Instrumental].flac`, кириллические варианты и т.п. --
  всё матчится.

### v1.1.1 -- GUI crash хотфикс

* GUI падал на старте с `AttributeError`, потому что `trace_add`
  колбэк был привязан до того, как наблюдаемый `StringVar`
  был сконструирован. `trace_add` теперь живёт ниже строки
  источника, после `self.source_var = tk.StringVar(value="auto")`,
  с breadcrumb на старом месте, чтобы регрессия класса "виджет
  привязан не в том порядке" было сложнее повторить.

### v1.1.0 -- Контракт аудио-анализа + источник `audio`

* **Demucs обязателен** при включённом аудио-фолбэке. On/off
  `Demucs`-комбобокс в аудио-панели убран -- вокальная изоляция
  Demucs всегда работает вместе с `--use-audio-analysis`.
  Чтобы полностью отключить локальный фолбэк -- снимите
  `Use audio analysis` (GUI) или уберите `--use-audio-analysis`
  (CLI). CLI-флаг `--no-demucs` удалён; раскладка весов Demucs
  и дефолтный `htdemucs_ft` не поменялись.
* **Новый источник `audio`** (GUI Source-комбобокс + CLI
  `--source audio`). Полностью пропускает LRCLIB / Genius и сразу
  идёт в локальный пайплайн Whisper + Demucs. Полезно для
  полностью офлайновых прогонов, больших караоке-батчей и случаев,
  когда сетевые вызовы нежелательны. В GUI при выборе
  `Source = audio` чекбокс `Use audio analysis` принудительно
  включается и блокируется, чтобы цепочка оставалась согласованной.
* **Шорткат по имени файла** для аудио-ветки. Треки, в имени файла
  содержащие `instrumental`, `karaoke`, `off vocal`, `no vocal`,
  `minus one`, `backing track` и т.п., никогда не отправляются
  в Whisper. Ветки LRCLIB / Genius по-прежнему пытаются первыми
  (оригинал караоке-файла часто реальная песня с реальным текстом) --
  только аудио-ветка шорткатится.
* `settings.json` от v1.0.x с ключом `demucs` молча игнорируется
  при загрузке.

### v1.0.2 -- Полировка перед релизом

* **GUI:** кнопка `?  Help` (последняя в ряду тулбара, правее
  `Open output folder`) открывает `messagebox.showinfo(...)` с
  цепочкой LRCLIB -> Genius -> локальное аудио, напоминанием про
  `GENIUS_ACCESS_TOKEN` / `--genius-token`, размерами загрузки
  Whisper / Demucs при первом запуске и советом про `--dry-run`.
* **GUI:** тултипы на всех основных интерактивных элементах --
  задержка hover 500 мс, автоскрытие 8 с (16 виджетов итого).
* **GUI:** финальный попап -- Done / Stopped / worker-crashed, со
  страховкой гонки `_on_close` через `winfo_exists()`. Пустые
  папки больше не открывают его.
* **Старт:** `audio_analysis.describe_models_layout()` логирует
  резолвящиеся пути `models/whisper-base/` + `models/demucs/`,
  чтобы пользователь без grep'а по исходникам видел, куда реально
  лягут веса.
* **Чистка:** убраны неиспользуемая константа `COLOUR_BG` и
  неиспользуемый импорт `_format_provider_breakdown`; аудио-лейбл
  Device переименован, чтобы не перекрывать бейдж статуса.

### v1.0.1 -- Первый отмеченный релиз

* Полировка и изменения LRC-форматирования с момента v1.0.0 initial
  commit. README badges + helper-script-каллауты в Quick start,
  AI-дисклеймер, двуязычная пара README (`README.md` +
  `README.ru.md`). LRC-формат: verbose Whisper-диагностическая строка
  снята, оставлена одна человеко-читаемая `[# Generated Lyrics with
  Whisper]` или `[# Generated Lyrics with Demucs + Whisper]`.

См. [`RELEASE_NOTES.md`](RELEASE_NOTES.md) для полного
per-commit-разбора каждого поставленного релиза (newest first,
consolidated changelog).


## Лицензия и благодарности

Проект распространяется по лицензии MIT -- см. [LICENSE](LICENSE).

Сервисы и библиотеки, благодаря которым LyricsFAG работает:

- [LRCLIB.net](https://lrclib.net/) -- бесплатный публичный API текстов.
- [Genius](https://genius.com/) -- база текстов (нужен ваш бесплатный токен).
- [lyricsgenius](https://github.com/johnwmillr/lyricsgenius) -- MIT, интеграция с Genius.
- [mutagen](https://github.com/quodlibet/mutagen) -- GPLv2, чтение тегов аудио.
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) -- MIT, опциональная локальная транскрипция.
- [Demucs](https://github.com/facebookresearch/demucs) -- MIT, опциональное отделение вокала перед Whisper.

Эта кодовая база написана с существенной помощью AI-кодинг-ассистента
([Codebuff](https://codebuff.com), модель `minimax/minimax-m3`) под
руководством и ревью человека; полный дисклеймер -- в шапке этого README.
