YJ-64 — PROTECTED-LINE-GUARD

ЕДИНЫЙ КОНТРОЛЬНЫЙ ФАЙЛ И УПРАВЛЕНИЕ ИЗМЕНЕНИЯМИ

============================================================
РАЗДЕЛ 1. ОБЯЗАТЕЛЬНЫЙ ПОРЯДОК РАБОТЫ

НАЗНАЧЕНИЕ:
Guard — единственный источник разрешённых изменений защищённых
рабочих участков и обязательная контрольная точка перед Android Build.

ПОРЯДОК:
1. Определить рабочие файлы и точные участки, которые требуется изменить.
2. Показать владельцу план и получить явное согласование.
3. Скопировать точный исходный фрагмент рабочего файла на операционный стол.
4. Изменять только копию на операционном столе.
5. Перед переносом подтвердить, что исходный фрагмент встречается ровно один раз.
6. Заменить только согласованный участок и проверить уникальность нового фрагмента.
7. Проверить отсутствие изменений за пределами согласованного участка.
8. Обновить контрольные Git blob SHA по фактическим рабочим файлам.
9. Запустить Guard Validation; Android Build разрешён только после PASS.
10. После завершения переноса удалить патч с операционного стола.

ОГРАНИЧЕНИЯ:
- Исходный код копируется из рабочего файла, не восстанавливается по памяти.
- Пробелы, отступы и переводы строк считаются частью фрагмента.
- Наличие задачи в очереди не является разрешением на её реализацию.
- Успешная компиляция не заменяет Guard Validation.
- При несовпадении исходного фрагмента перенос прекращается; автоматическая
  подмена или расширение области изменения запрещены.

ФОРМАТ ЗАЩИЩЁННОГО ФРАГМЕНТА: в разделе 2 используется запись
`FILE: путь/к/файлу BEGIN ALLOWED` с точным исходным кодом и завершающей
строкой `END ALLOWED`. Этот формат не применяется на операционном столе;
там используются поля TARGET FILE / ORIGINAL FRAGMENT / NEW FRAGMENT.

============================================================
РАЗДЕЛ 2. ЗАЩИЩЁННЫЕ ФРАГМЕНТЫ

Назначение:

В этом разделе находятся точные фрагменты рабочего кода,
которые проверяются на сохранность.

FILE: main.py BEGIN ALLOWED
        actions = [
            ("СОЗДАТЬ АРХИВ В ЗАГРУЗКАХ", self._auto_export_download_archive),
            ("СОЗДАТЬ АРХИВ ВЫБОРОМ ПАПКИ", self._create_memory_archive),
            ("ВОССТАНОВИТЬ ИЗ ZIP", self._choose_memory_archive),
            ("НАСТРОЙКИ ЧАТА: ШРИФТ И ИМЕНА", self._open_chat_appearance_settings),
            (self._t(5), self._open_tools_menu),
            (self._t(6), self._show_chats),
            (self._t(7), self._new_chat),
            (self._t(11), self._open_skills_editor),
        ]
END ALLOWED

FILE: main.py BEGIN ALLOWED
            self._append_report("memory_archive_batch_completed",
                                successful=len(results), failed=len(failures),
                                results=results, failures=failures,
                                all_archives_verified=bool(results) and not failures)
END ALLOWED

FILE: chat_workspace.py BEGIN ALLOWED
    def __init__(self, user_data_dir: str | Path):
        self.root = Path(user_data_dir) / "yj64-workspace"
        self.root.mkdir(parents=True, exist_ok=True)
        self.chats_dir = self.root / "chats"
        self.agents_dir = self.root / "agents"
        self.histories_dir = self.root / "histories"
        for folder in (self.chats_dir, self.agents_dir, self.histories_dir):
            folder.mkdir(parents=True, exist_ok=True)
        self.skills_path = self.root / "skills.md"
        if not self.skills_path.exists():
            self.skills_path.write_text("# YJ-64 local skills\n", encoding="utf-8")
        self.index_path = self.root / "chats.json"
        if not self.index_path.exists():
            self._write_json(self.index_path, {"chats": []})
        if not self.list_chats():
            self.create_chat("Общий чат")
        self.ensure_chat_files()

    def ensure_chat_files(self) -> None:
        """Create missing chat histories without overwriting existing files."""
        for chat in self.list_chats():
            chat_id = str(chat.get("id", "")).strip()
            if not chat_id:
                continue
            path = self._messages_path(chat_id)
            if not path.exists():
                self._write_json(path, [])
END ALLOWED

============================================================

============================================================
РАЗДЕЛ 3. НЕИЗМЕНЯЕМЫЕ УЧАСТКИ

Рабочие участки, не включённые в согласованный патч, не изменяются.
Если требуется затронуть новый участок, он сначала точно копируется
на операционный стол и получает отдельный PATCH-ID.
Прямое редактирование такого участка без этого порядка запрещено.

============================================================
РАЗДЕЛ 4. ОПЕРАЦИОННЫЙ СТОЛ

СТАТУС: 1 НЕЗАВЕРШЁННЫЙ PATCH — ОСТАЛИСЬ ТОЛЬКО НЕЗАВЕРШЁННЫЕ ТРЕБОВАНИЯ

PATCH-ID: YJ64-PRIVATE-CHAT-ARCHIVE-001

TARGET FILES:
- main.py
- yj64_persistent_core.py
- Android runtime / private archive publication

ОСТАВШИЕСЯ ТРЕБОВАНИЯ:

1. Объединить создание общего и личных архивов в один пользовательский
   запуск. Сейчас автоматическая кнопка публикует только общий ZIP;
   личный экспорт запускается отдельным действием.

2. Определить и реализовать конечный формат личных архивов:
   текущая реализация формирует отдельные ZIP по участникам, но UI
   собирает их в один зашифрованный bundle и сохраняет через SAF.
   Требуется согласовать, как обеспечить отдельность архивов,
   шифрование и общий целевой каталог Download/YJ-64 без plaintext
   публикации личных данных.

3. Проверить сопоставление runner / participant_id с именами файлов
   историй. Не считать группировку корректной для всех вариантов
   runner, пока не пройдена отдельная проверка.

4. Проверить реальную Android-реализацию PrivateArchiveCrypto:
   наличие и работу AES-256-GCM / PBKDF2, экспорт, импорт и обработку
   неверной парольной фразы. Python-код вызывает Java-класс, но его
   исходник и работа на устройстве здесь не подтверждены.

5. Проверить Android runtime: публикацию всех требуемых архивов,
   чтение сохранённых файлов обратно, целостность, видимость в
   файловом менеджере и раздельную отчётность при частичном сбое.

6. Проверить границы доступа. В запрос модели передаётся её собственная
   личная история, но отдельный requester-level API с явной проверкой
   read/write прав для owner / participant / monitor пока не подтверждён.

7. После завершения — добавить недостающие регрессионные проверки,
   обновить контрольные SHA и выполнить Guard Validation.
   Android Build не запускать до Guard PASS.

ПРИМЕЧАНИЕ:
Уже реализованные механизмы общего архива, исключения histories и
private_messages, отдельного ZIP-экспорта, проверки ZIP/manifest/hash,
отдельного private bundle import с проверкой схемы и participant identity,
а также нормализации метаданных сообщений повторно в этот список
не включать. Их реализация и ограничения зафиксированы в
IMPLEMENTATION RECORD ниже. Это не означает, что Android runtime
проверен или что весь PATCH завершён.

============================================================

РАЗДЕЛ 5. ПРОВЕРКА ПЕРЕНОСА

Для каждого активного патча:
1. Проверить единственность ORIGINAL FRAGMENT в рабочем файле.
2. Проверить NEW FRAGMENT и его отступы.
3. Выполнить только согласованную замену.
4. Проверить единственность нового фрагмента и отсутствие побочных изменений.
5. Обновить SHA изменённых рабочих файлов.
6. Запустить tools/verify_guard.py и добиться успешного результата.

Если любой шаг не пройден, перенос считается незавершённым.
Сборка до успешной проверки Guard запрещена.

============================================================
РАЗДЕЛ 6. ОЧЕРЕДЬ ЗАДАЧ

СТАТУС: EMPTY
ОТЛОЖЕННЫХ ЗАДАЧ НЕТ.

Задачи добавляются сюда только по отдельному указанию владельца.
Запись в очереди фиксирует намерение, но не даёт разрешения на изменение.

============================================================
РАЗДЕЛ 7. КОНТРОЛЬНЫЕ ДАННЫЕ РАБОЧИХ ФАЙЛОВ

Контрольные значения — Git blob SHA-1.

После каждого согласованного переноса изменения в рабочие файлы
контрольные SHA должны быть обновлены по фактическому содержимому.

============================================================

============================================================
КОНЕЦ PROTECTED-LINE-GUARD

============================================================
ЗАМЕТКА О ПЕРЕНОСЕ — YJ64-REMOTE-RENAME-RESTORED-CONTEXT-002
Все изменения PATCH 002-A—002-F обнаружены в текущем рабочем main.py:
- защищённая загрузка remote_participant;
- переименование участника и отображаемые имена;
- отдельный restored-model-context.json;
- восстановление ZIP без добавления архива в видимую историю;
- передача восстановленного контекста в общий и личный запросы.
Подробный implementation record и проверки сохранены ниже.
Повторно в операционном столе эти фрагменты не держать.
============================================================

============================================================
PATCH IMPLEMENTATION RECORD — YJ64-REMOTE-RENAME-RESTORED-CONTEXT-002
APPROVED BY OWNER: 2026-10-31
TARGET: main.py; buildozer.spec; .github/workflows/android-apk.yml
VERSION: 0.1.34

EXACT ORIGINAL FRAGMENTS VERIFIED AGAINST WORKING BRANCH BEFORE EDIT:
- _open_remote_participant(): exact import/client initialization block.
- _open_chat_appearance_settings(): complete method; remove legacy participant-name fields because rename moves to participant menu.
- _participant_label(): insert custom-name precedence before localized default labels.
- _open_participant_menu(): insert rename action after participant title.
- build(): workspace initialization and common-history load.
- _on_archive_activity_result(): complete existing import branch.
- private participant send_message(): common/private history construction.
- _send_llm_chat(): per-participant history_snapshot loop.

IMPLEMENTATION DETAILS:
1. REMOTE import is wrapped in try/except; failure is reported and shown in a popup without crashing the base app. remote_participant.py itself is absent from this branch and is NOT created by this patch.
2. Participant rename is moved from global appearance settings into each participant menu. _participant_label() now prioritizes saved display names, so participant buttons reflect the change. Font settings retain stored names.
3. Restored common archive messages are stored in yj64-workspace/restored-model-context.json, separately from common_history. Existing restored context is merged with messages from every archived common chat; stable message IDs (or legacy content hashes) deduplicate entries; timestamp ordering is retained.
4. Import creates a fresh visible chat and sets common_history to empty. Archived content is never copied into the visible transcript.
5. Restored common context is included in general participant model requests and private participant requests. Participant-specific private histories remain separate and are appended only to that participant's request.
6. Private agent records under agents/*.json are not flattened into common restored context. Their private_messages remain separate.
7. The context file is inside yj64-workspace and is therefore included by PersistentCore._collect_files() in subsequent archives.
8. buildozer.spec version is raised from 0.1.32 to 0.1.33. Android workflow names the APK YJ-64-Base-v0.1.33-arm64-v8a-debug.apk and artifact yj64-base-v0.1.33-apk.

ACCEPTANCE CHECKS REQUIRED:
- Python compile and Guard Validation PASS before Android build.
- Verify no restored messages appear in common_history or chat_output after import.
- Verify Participant 1/2 each answer from restored context.
- Verify context survives restart and a second archive/export/import cycle.
- Verify custom participant labels persist after restart and appear on participant buttons.
- Verify missing remote_participant import opens error popup and app remains usable.

STATUS: IMPLEMENTED IN WORKING FILES; VALIDATION PENDING.
============================================================

============================================================
PATCH IMPLEMENTATION TABLE — YJ64-PRIVATE-CHAT-ARCHIVE-001
STATUS: IMPLEMENTATION IN PROGRESS — OWNER APPROVAL RECEIVED 2026-10-31
TARGET: yj64_persistent_core.py; main.py; chat_workspace.py

ORIGINAL FRAGMENTS — EXACT COPIES FROM WORKING FILES

FILE: yj64_persistent_core.py — _collect_files()
```python
        if isinstance(value,dict):return {k:cls._sanitize(v) for k,v in value.items() if str(k).lower() not in cls.SECRET_KEYS}
        if isinstance(value,list):return [cls._sanitize(x) for x in value]
        return value
    @classmethod
    def _sanitize_json(cls,payload:bytes)->bytes:
        try:data=json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError,json.JSONDecodeError):return payload
        return json.dumps(cls._sanitize(data),ensure_ascii=False,indent=2).encode("utf-8")
    def _collect_files(self)->dict[str,bytes]:
        result={}
        for base in (self.workspace_path,self.report_path):
            if base.is_file() and not base.is_symlink():items=[base]
            elif base.is_dir() and not base.is_symlink():items=[p for p in base.rglob("*") if p.is_file() and not p.is_symlink()]
```

FILE: yj64_persistent_core.py — export_archive()
```python
    def export_archive(self,destination:str|Path)->Path:
        dest=Path(destination);dest.parent.mkdir(parents=True,exist_ok=True);tmp=dest.with_suffix(dest.suffix+".tmp");state_tmp=self.archive_state_path.with_suffix(".zip.tmp")
        previous,old_manifest=self._read_previous();merged=dict(previous);current=self._collect_files()
        for name,data in current.items():
            if name.startswith("yj64-workspace/chats/") and name.endswith(".json") and name in merged:data=self._merge_history(merged[name],data)
            merged[name]=data
        idx="yj64-workspace/chats.json"
        if idx not in merged:raise IOError("Archive cannot be created: chat index missing")
        try:index=json.loads(merged[idx].decode("utf-8"));chats=index.get("chats",[]) if isinstance(index,dict) else []
        except (UnicodeDecodeError,json.JSONDecodeError,AttributeError) as exc:raise IOError("Invalid archive chat index") from exc
        if not isinstance(chats,list) or not chats:raise IOError("Archive has no saved chats")
        for item in chats:
            cid=re.sub(r"[^A-Za-z0-9_-]","",str(item.get("id",""))) if isinstance(item,dict) else ""
            if not cid or f"yj64-workspace/chats/{cid}.json" not in merged:raise IOError("Saved chat history missing")
        try:
            with self._connect() as db:events=db.execute("SELECT timestamp_ms,event,data_json FROM events ORDER BY id").fetchall()
            merged["yj64-events-export.json"]=json.dumps(events,ensure_ascii=False).encode("utf-8")
        except sqlite3.Error:pass
        messages=[]
        for name,data in merged.items():
            if name.startswith("yj64-workspace/chats/") and name.endswith(".json"):
                rows=json.loads(data.decode("utf-8"))
                if isinstance(rows,list):messages.extend(x for x in rows if isinstance(x,dict))
        messages.sort(key=lambda x:x.get("timestamp",x.get("timestamp_ms",0)) or 0);now=int(time.time()*1000)
        manifest={"schema":self.ARCHIVE_SCHEMA,"archive_id":(old_manifest or {}).get("archive_id") or uuid.uuid4().hex,
          "created_at":(old_manifest or {}).get("created_at") or time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime(now/1000)),
          "updated_at":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime(now/1000)),
          "last_message_id":str(messages[-1].get("message_id","")) if messages else None,"message_count":len(messages),
          "included":["common_chat_history","workspace_metadata","local_skills","router_model_settings_without_secrets","technical_diagnostics"],
          "excluded":["participant_private_messages","api_keys_and_tokens","application_private_database"],
          "files":{n:{"sha256":self._sha(d),"size":len(d)} for n,d in sorted(merged.items())}}
        try:
            for target in (tmp,state_tmp):
                with zipfile.ZipFile(target,"w",compression=zipfile.ZIP_DEFLATED) as z:
                    for n,d in sorted(merged.items()):z.writestr(n,d)
                    z.writestr("manifest.json",json.dumps(manifest,ensure_ascii=False,indent=2))
                self._verify_archive(target)
            os.replace(state_tmp,self.archive_state_path);os.replace(tmp,dest)
        except Exception:tmp.unlink(missing_ok=True);state_tmp.unlink(missing_ok=True);raise
        return dest
```

FILE: main.py — _auto_export_download_archive()
```python
    def _auto_export_download_archive(self, *_: Any) -> None:
        """Create a verified archive in public Downloads/YJ-64 without opening a picker."""
        temp_path = Path(self.user_data_dir) / "YJ-64-backup-auto.zip"
        verify_path = Path(self.user_data_dir) / "YJ-64-backup-auto-verify.zip"
        uri = None
        try:
            self._save_common_history()
            self.persistent_core.export_archive(temp_path)
            from jnius import autoclass
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            ContentValues = autoclass("android.content.ContentValues")
            MediaStoreDownloads = autoclass("android.provider.MediaStore$Downloads")
            resolver = PythonActivity.mActivity.getContentResolver()
            stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime())
            values = ContentValues()
            values.put("display_name", "YJ-64-backup-" + stamp + ".zip")
            values.put("mime_type", "application/zip")
            values.put("relative_path", "Download/YJ-64/")
            values.put("is_pending", 1)
            uri = resolver.insert(MediaStoreDownloads.EXTERNAL_CONTENT_URI, values)
            if uri is None:
                raise IOError("Android MediaStore did not create a Downloads file")
            output = resolver.openOutputStream(uri)
            if output is None:
                raise IOError("Android could not open the Downloads archive for writing")
            source_digest = hashlib.sha256(temp_path.read_bytes()).hexdigest()
            copied = 0
            try:
                with temp_path.open("rb") as source:
                    while True:
                        chunk = source.read(65536)
                        if not chunk:
                            break
                        for value_byte in chunk:
                            output.write(value_byte)
                        copied += len(chunk)
                output.flush()
            finally:
                output.close()
            expected = temp_path.stat().st_size
            if copied != expected or copied <= 0:
                raise IOError(f"Downloads archive size mismatch: {copied} of {expected} bytes")
            readback = resolver.openInputStream(uri)
            if readback is None:
                raise IOError("Android could not reopen the Downloads archive")
            read_count = 0
            try:
                with verify_path.open("wb") as verify_file:
                    while True:
                        value_byte = int(readback.read())
                        if value_byte < 0:
                            break
                        verify_file.write(bytes((value_byte & 0xff,)))
                        read_count += 1
            finally:
                readback.close()
            import zipfile
            read_digest = hashlib.sha256(verify_path.read_bytes()).hexdigest() if verify_path.is_file() else ""
            if read_count != copied or read_digest != source_digest or not zipfile.is_zipfile(verify_path):
                raise IOError("Downloads archive read-back, SHA-256 or ZIP integrity check failed")
            with zipfile.ZipFile(verify_path, "r") as check_zip:
                bad_member = check_zip.testzip()
                if bad_member or "manifest.json" not in check_zip.namelist():
                    raise IOError("Downloads archive is incomplete or has a corrupt member")
            values_done = ContentValues()
            values_done.put("is_pending", 0)
            resolver.update(uri, values_done, None, None)
            self._append_report("memory_archive_auto_download_succeeded",
                                size_bytes=copied, readback_bytes=read_count,
                                location="Download/YJ-64", zip_integrity_verified=True)
            self._archive_auto_export_error = ""
        except Exception as exc:
            self._archive_auto_export_error = f"{type(exc).__name__}: {exc}"
            self.status.text = (
                "Автосохранение архива не удалось: "
                + self._archive_auto_export_error
            )
            self._append_report(
                "memory_archive_auto_download_failed",
                error_type=type(exc).__name__,
                error=str(exc),
                location="Download/YJ-64",
            )
            if uri is not None:
                try:
                    from jnius import autoclass
                    PythonActivity = autoclass("org.kivy.android.PythonActivity")
                    PythonActivity.mActivity.getContentResolver().delete(
                        uri, None, None
                    )
                except Exception:
                    pass
        finally:
            temp_path.unlink(missing_ok=True)
            verify_path.unlink(missing_ok=True)

```

FILE: main.py — private participant history load/save use
```python
        history = self.private_histories.setdefault(
            participant_name, self.workspace.load_named_history(participant_name)
        )
        output_lines = [
            f"{'You' if item.get('role') == 'user' else participant_name}:\n{item.get('content', '')}"
            for item in history
        ]
        content = BoxLayout(orientation="vertical", spacing=8, padding=12)
        output = TextInput(
            text="\n\n".join(output_lines) or f"{participant_name} private conversation.",
            readonly=True,
            multiline=True,
        )
        prompt = TextInput(
            hint_text=f"Private message to {participant_name}...",
            multiline=True,
            size_hint_y=None,
            height=110,
            write_tab=False,
        )
        send = FeedbackButton(text="SEND PRIVATELY", size_hint_y=None, height=54)
```

IMPLEMENTATION DESIGN TO APPLY ON THE OPERATING TABLE
1. Common archive collector must omit yj64-workspace/histories/** entirely and recursively strip private_messages from all JSON. It must not copy private history content into restored common context.
2. PersistentCore gains export_private_archives(directory): build one ZIP per participant from the existing histories/*.json plus matching private_messages extracted from agents/*.json using the agent runner/name metadata; never mutate source JSON. Include manifest, IDs/timestamps, SHA-256 and verify every member with testzip + manifest checks.
3. Existing export_archive(destination) remains common-only and is changed to enforce the exclusion before merging prior archive state; previously merged private-history paths must be removed from the common archive on export.
4. Main export action creates common ZIP plus all private ZIPs, then publishes every ZIP to Download/YJ-64 using Android MediaStore and verifies byte count + SHA-256 + ZIP integrity after read-back. Report success/failure separately for each file; never report aggregate PASS if any file failed.
5. Keep import compatibility: common ZIP import restores only common data; private ZIP import is a distinct explicit operation and must validate participant identity/schema before writing to histories/agents. Do not silently import private archives as common archives.
6. Access policy: owner app controls all local private archives; model participants receive only their own private history in request construction; other participants and monitor receive no private archive contents. Do not claim cryptographic protection. Encryption/key management is a separate unresolved requirement and plaintext ZIPs must be labelled as such.
7. Preserve message_id, timestamp/timestamp_ms, session_id, participant_id and legacy message fields. Do not invent or flatten timestamps.

VALIDATION REQUIRED BEFORE BUILD
- Unit test common ZIP has no histories/** paths and no private_messages keys or values.
- Unit test each private ZIP contains only the matching participant's history/agent private messages.
- Verify ZIP manifest hashes, testzip, nonzero size and no duplicate/unsafe paths.
- Verify legacy common archive import still works and private ZIP is rejected by common importer.
- Verify Android MediaStore read-back for every generated ZIP, including failure reporting.
- Verify no private history is included in restored-model-context.json.
- Guard Validation PASS; only then version bump and Android build.

NOTE: this is a new implementation patch. No working files have been changed yet.
============================================================

IMPLEMENTATION RECORD — YJ64-PRIVATE-CHAT-ARCHIVE-001
APPROVED BY OWNER: 2026-10-31
WORKING FILES UPDATED ON APPROVED BRANCH:
- yj64_persistent_core.py — blob bf7bfffb6e0063ce09690c32146280c368b3cac8
- main.py — blob b3651dc053ee29ed099483cde2624bf7c87b72a4
- chat_workspace.py — blob 41201f85eeb892be09dd22c8b838e0195ba0cc1b

IMPLEMENTED:
1. Common archive collection excludes yj64-workspace/histories/**.
2. Existing accumulated common archive state removes legacy histories/** entries before writing the next common archive.
3. PersistentCore.export_private_archives() creates separate ZIP files grouped by participant from named private histories and agent private_messages; source files are not mutated.
4. Private ZIPs include a schema/participant manifest and SHA-256/size metadata, and are checked with ZIP integrity and member-list validation before acceptance.
5. Main automatic export creates the common archive and all private archives, publishes each to Download/YJ-64 using MediaStore, reads each published file back and verifies byte count, SHA-256 and ZIP integrity.
6. Each archive publication reports success or failure independently; batch PASS is withheld if any archive failed.
7. New agent private messages receive message_id, timestamp, timestamp_ms, session_id, participant_id and message_type metadata.
8. Private archives are plaintext ZIPs. Cryptographic encryption/key management is NOT implemented.

KNOWN LIMITATIONS / REQUIRED FOLLOW-UP:
- Private ZIP restore is not yet wired into the archive picker; common importer must not be used for private ZIPs. A separate explicit, identity-checked restore flow remains required.
- Existing legacy private agent messages retain their original fields; exporter preserves them without fabricating historical IDs/timestamps.
- Validate grouping for agents whose runner values differ from canonical participant labels.
- Device-level MediaStore operation, file-manager visibility and failure paths require Android runtime testing.
- Private archive ZIPs group histories by filename and agent records by runner. This is not encryption or an access-control boundary after a user copies the ZIP.

STATUS: PRIVATE CHAT ARCHIVE IMPLEMENTED; PRIVACY DIAGNOSTICS PATCH ADDED; GUARD/CI VALIDATION PENDING.

============================================================
PATCH-ID: YJ64-PRIVACY-DIAGNOSTICS-001
STATUS: IMPLEMENTED — GUARD/CI VALIDATION REQUIRED

SCOPE:
- Replace raw diagnostic payloads with allowlisted operational metadata.
- Store only sanitized data in JSONL and SQLite.
- Migrate existing local SQLite event rows to remove legacy payload text.
- Exclude diagnostic JSONL and private history files from common archives.
- Replace the repository's real diagnostic sample with synthetic metadata.
- Add regression tests and make CI run them before Android build.

FILE: diagnostics.py BEGIN ALLOWED
"""Privacy-safe diagnostic event filtering for YJ-64.

Only bounded operational metadata is retained. Message bodies, model output,
exception text, tracebacks, credentials, and arbitrary fields are never stored.
"""
from __future__ import annotations

import re
from typing import Any, Mapping

_SAFE_STRING_FIELDS = {
    "process_name", "provider", "model", "route_id", "operation_id",
    "request_id", "error_type", "status", "archive_schema",
}
_SAFE_INTEGER_FIELDS = {
    "pid", "history_count", "common_history_count", "private_history_count",
    "prompt_length", "response_length", "input_length", "output_length",
    "file_count", "file_size", "size_bytes", "status_code", "http_status",
    "retry_count", "attempt", "elapsed_ms", "duration_ms", "line_number",
}
_SAFE_BOOLEAN_FIELDS = {
    "configured", "explicit_user_action", "focused", "success",
    "all_archives_verified", "private", "error_present",
}
_PROMPT_FIELDS = {"prompt", "message", "request", "request_message", "input", "content"}
_RESPONSE_FIELDS = {"response", "output", "result"}
_ERROR_FIELDS = {"error", "exception", "traceback", "message_error"}
_SAFE_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,95}$")
_PARTICIPANT = re.compile(r"^(Owner|Participant [1-9][0-9]*)$")


def _safe_string(field: str, value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value or len(value) > 96:
        return None
    if field == "participant":
        return value if _PARTICIPANT.fullmatch(value) else None
    if field == "mode":
        return value if value in {"text", "agent"} else None
    if field == "provider":
        return value if _SAFE_TOKEN.fullmatch(value) else None
    return value if _SAFE_TOKEN.fullmatch(value) else None


def sanitize_event_data(event: str, data: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return a strict metadata-only representation of an event payload."""
    if not isinstance(data, Mapping):
        return {}

    safe: dict[str, Any] = {}
    prompt_length = None
    response_length = None
    error_present = False

    for raw_key, value in data.items():
        key = str(raw_key).strip().lower()

        if key in _PROMPT_FIELDS and isinstance(value, (str, bytes, bytearray)):
            prompt_length = len(value)
            continue
        if key in _RESPONSE_FIELDS and isinstance(value, (str, bytes, bytearray)):
            response_length = len(value)
            continue
        if key in _ERROR_FIELDS:
            error_present = value is not None
            continue

        if key in _SAFE_STRING_FIELDS or key in {"participant", "mode"}:
            cleaned = _safe_string(key, value)
            if cleaned is not None:
                safe[key] = cleaned
            continue

        if key in _SAFE_INTEGER_FIELDS:
            if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 2**63 - 1:
                safe[key] = value
            continue

        if key in _SAFE_BOOLEAN_FIELDS and isinstance(value, bool):
            safe[key] = value

    if prompt_length is not None:
        safe["prompt_length"] = prompt_length
    if response_length is not None:
        safe["response_length"] = response_length
    if error_present:
        safe["error_present"] = True
    return safe
END ALLOWED

FILE: main.py BEGIN ALLOWED
    def _append_report(self, event: str, **data: Any) -> None:
        try:
            safe_data = sanitize_event_data(event, data)
            self.report_path.parent.mkdir(parents=True, exist_ok=True)
            record = {
                "schema": "yj64.diagnostic.v1",
                "agent": "yj64-base-application",
                "event": event,
                "timestamp_ms": int(time.time() * 1000),
                "monotonic_ns": time.monotonic_ns(),
                "message_id": f"APP-{uuid.uuid4().hex}",
                "data": safe_data,
            }
            with self.report_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, sort_keys=True) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            try:
                self.persistent_core.record_event(event, safe_data)
            except Exception:
                # SQLite is secondary to the primary diagnostic JSONL; never block UI.
                pass
        except OSError:
            pass
END ALLOWED

FILE: yj64_persistent_core.py BEGIN ALLOWED
    def record_event(self,event:str,data:dict[str,Any]|None=None)->None:
        safe_data = sanitize_event_data(event, data or {})
        try:
            with self._connect() as db:
                db.execute(
                    "INSERT INTO events(timestamp_ms,event,data_json) VALUES(?,?,?)",
                    (int(time.time()*1000), str(event), json.dumps(safe_data, ensure_ascii=False)),
                )
        except sqlite3.Error:
            return

    def _sanitize_existing_events(self) -> None:
        """Remove legacy raw message/error payloads from the local event ledger."""
        try:
            with self._connect() as db:
                rows = db.execute("SELECT id,event,data_json FROM events").fetchall()
                for row_id, event, raw_json in rows:
                    try:
                        raw_data = json.loads(raw_json)
                    except (TypeError, ValueError, json.JSONDecodeError):
                        raw_data = {}
                    safe_data = sanitize_event_data(str(event), raw_data if isinstance(raw_data, dict) else {})
                    safe_json = json.dumps(safe_data, ensure_ascii=False)
                    if safe_json != raw_json:
                        db.execute("UPDATE events SET data_json=? WHERE id=?", (safe_json, row_id))
        except sqlite3.Error:
            return
END ALLOWED

FILE: yj64_persistent_core.py BEGIN ALLOWED
    def _collect_files(self)->dict[str,bytes]:
        result={}
        # Diagnostic JSONL can contain legacy sensitive records; never place it
        # in a common archive, even if older versions wrote raw payloads there.
        for base in (self.workspace_path,):
            if base.is_file() and not base.is_symlink():items=[base]
            elif base.is_dir() and not base.is_symlink():items=[p for p in base.rglob("*") if p.is_file() and not p.is_symlink()]
            else:items=[]
            for p in items:
                name=p.relative_to(self.root).as_posix()
                if name.startswith("yj64-workspace/histories/"):
                    continue
                if p.suffix.lower() == ".jsonl":
                    continue
                data=p.read_bytes()
                result[name]=self._sanitize_json(data) if p.suffix.lower()==".json" else data
        for pattern in ("yj64-router-config.json","yj64-llm-config*.json"):
            for p in self.root.glob(pattern):
                if p.is_file() and not p.is_symlink():result[p.name]=self._sanitize_json(p.read_bytes())
        return result
END ALLOWED

FILE: tests/test_diagnostics_privacy.py BEGIN ALLOWED
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from diagnostics import sanitize_event_data
from yj64_persistent_core import PersistentCore


class DiagnosticPrivacyTests(unittest.TestCase):
    def test_message_and_model_payloads_are_replaced_with_lengths(self):
        safe = sanitize_event_data(
            "participant_request_started",
            {
                "participant": "Participant 1",
                "route_id": "route_1",
                "mode": "text",
                "provider": "gemini",
                "model": "gemini-2.5-flash",
                "prompt": "private user message",
                "response": "private model response",
                "error": "authorization: Bearer very-secret-token",
                "traceback": "private traceback content",
                "private_history_count": 2,
            },
        )
        self.assertEqual(safe["prompt_length"], len("private user message"))
        self.assertEqual(safe["response_length"], len("private model response"))
        self.assertTrue(safe["error_present"])
        self.assertEqual(safe["private_history_count"], 2)
        for forbidden in ("prompt", "response", "error", "traceback"):
            self.assertNotIn(forbidden, safe)
        self.assertNotIn("very-secret-token", json.dumps(safe))

    def test_unknown_fields_and_custom_participant_names_are_dropped(self):
        safe = sanitize_event_data(
            "event",
            {
                "participant": "Alice Smith",
                "endpoint": "https://example.invalid/private?token=secret",
                "custom_field": "private data",
                "pid": 123,
            },
        )
        self.assertEqual(safe, {"pid": 123})

    def test_event_ledger_stores_only_sanitized_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            core = PersistentCore(tmp)
            core.record_event(
                "participant_api_response_received",
                {"response": "private answer", "provider": "openai", "model": "gpt-test"},
            )
            with sqlite3.connect(core.db_path) as db:
                stored = json.loads(db.execute("SELECT data_json FROM events").fetchone()[0])
            self.assertEqual(stored["response_length"], len("private answer"))
            self.assertNotIn("response", stored)
            self.assertEqual(stored["provider"], "openai")

    def test_startup_migration_scrubs_legacy_event_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "yj64-persistent-core.sqlite3"
            with sqlite3.connect(db_path) as db:
                db.execute(
                    "CREATE TABLE events (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp_ms INTEGER NOT NULL, event TEXT NOT NULL, data_json TEXT NOT NULL)"
                )
                db.execute(
                    "INSERT INTO events(timestamp_ms,event,data_json) VALUES(1,?,?)",
                    ("participant_request_started", json.dumps({"prompt": "legacy private text"})),
                )
            core = PersistentCore(tmp)
            with sqlite3.connect(core.db_path) as db:
                stored = json.loads(db.execute("SELECT data_json FROM events").fetchone()[0])
            self.assertEqual(stored["prompt_length"], len("legacy private text"))
            self.assertNotIn("prompt", stored)

    def test_common_archive_excludes_report_jsonl_and_private_histories(self):
        with tempfile.TemporaryDirectory() as tmp:
            core = PersistentCore(tmp)
            private_dir = core.workspace_path / "histories"
            common_dir = core.workspace_path / "chats"
            private_dir.mkdir(parents=True)
            common_dir.mkdir(parents=True)
            (private_dir / "Participant 1.json").write_text(
                json.dumps([{"role": "user", "content": "private chat text"}]),
                encoding="utf-8",
            )
            (common_dir / "common.json").write_text(
                json.dumps([{"role": "user", "content": "common chat text"}]),
                encoding="utf-8",
            )
            core.report_path.parent.mkdir(parents=True, exist_ok=True)
            core.report_path.write_text(
                '{"event":"participant_request_started","data":{"prompt":"legacy private prompt"}}\n',
                encoding="utf-8",
            )
            collected = core._collect_files()
            self.assertIn("yj64-workspace/chats/common.json", collected)
            self.assertNotIn("yj64-workspace/histories/Participant 1.json", collected)
            self.assertFalse(any(name.endswith(".jsonl") for name in collected))


if __name__ == "__main__":
    unittest.main()
END ALLOWED

NOTE:
Private ZIP archives remain plaintext ZIP files in this patch. Encryption and
portable password-based key management are not implemented here. Rewriting
the latest diagnostic sample does not erase earlier Git history; inspect
history separately if any credential was ever committed and rotate it.
============================================================

EXPECTED-GIT-BLOB-SHA:main.py=7d55a6da4ae5f6d367e2d5366c0c279f9982531a
EXPECTED-GIT-BLOB-SHA:chat_workspace.py=41201f85eeb892be09dd22c8b838e0195ba0cc1b
EXPECTED-GIT-BLOB-SHA:yj64_persistent_core.py=d227def6ad89ee0a3ecea66e2bf34e485cc5bf64
EXPECTED-GIT-BLOB-SHA:buildozer.spec=9ae2a656d9b91c81e739a389a29c4d16c7c7c92f
EXPECTED-GIT-BLOB-SHA:diagnostics.py=e768f425255e72c9f9098d9f0816b558b7e81751
EXPECTED-GIT-BLOB-SHA:tests/test_diagnostics_privacy.py=422a19145921a08acd975faeea2b7d488ae6384f
EXPECTED-GIT-BLOB-SHA:reports/latest-report.jsonl=ca9f1540f21dfb93aac91ad791dc2840b2d3f233

FILE: tools/verify_guard.py BEGIN ALLOWED
SECTION_RE = re.compile(
    r"^FILE: (?P<path>[^\n]+?) BEGIN ALLOWED\n(?P<content>.*?)\nEND ALLOWED$",
    re.MULTILINE | re.DOTALL,
)
END ALLOWED
EXPECTED-GIT-BLOB-SHA:tools/verify_guard.py=05604885ec0babf25fa55ea6d5343b21c7f88a7d
