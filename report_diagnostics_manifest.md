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
            ("ЭКСПОРТ ЛИЧНЫХ АРХИВОВ (ШИФРОВАНИЕ)", self._open_private_archive_export),
            ("ВОССТАНОВИТЬ ЛИЧНЫЕ АРХИВЫ", self._open_private_archive_import),
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

СТАТУС: CLEAN — НЕТ АКТИВНЫХ ПАТЧЕЙ.

На операционном столе нет незавершённых изменений.
Новые изменения помещаются сюда только после отдельного согласования
и копирования точных исходных фрагментов из рабочих файлов.

Нерешённые задачи и порядок их выполнения находятся в очереди
в последнем разделе этого файла.

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

Очередь перенесена в последний раздел файла, после всех implementation
records и контрольных данных. См. «ФИНАЛЬНАЯ ОЧЕРЕДЬ РЕШЕНИЯ ЗАДАЧ».

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

    def test_private_bundle_round_trip_restores_private_histories_and_agent_messages(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = PersistentCore(Path(tmp) / "source")
            histories = source.workspace_path / "histories"
            agents = source.workspace_path / "agents"
            histories.mkdir(parents=True)
            agents.mkdir(parents=True)
            history = [{"role": "user", "content": "secret participant message"}]
            private_messages = [{"role": "assistant", "content": "private agent response"}]
            (histories / "participant_1.json").write_text(json.dumps(history), encoding="utf-8")
            (agents / "agent_1.json").write_text(json.dumps({
                "id": "agent_1", "name": "Agent One", "runner": "participant_1",
                "created_ms": 123, "private_messages": private_messages,
            }), encoding="utf-8")
            bundle = Path(tmp) / "private-bundle.zip"
            source.export_private_bundle(bundle)
            self.assertTrue(bundle.is_file())
            target = PersistentCore(Path(tmp) / "target")
            restored = target.import_private_bundle(bundle)
            self.assertEqual(restored, 2)
            self.assertEqual(
                json.loads((target.workspace_path / "histories" / "participant_1.json").read_text(encoding="utf-8")),
                history,
            )
            restored_agent = json.loads((target.workspace_path / "agents" / "agent_1.json").read_text(encoding="utf-8"))
            self.assertEqual(restored_agent["private_messages"], private_messages)

    def test_private_bundle_rejects_tampered_member_without_restoring(self):
        import zipfile
        with tempfile.TemporaryDirectory() as tmp:
            source = PersistentCore(Path(tmp) / "source")
            histories = source.workspace_path / "histories"
            histories.mkdir(parents=True)
            (histories / "participant_1.json").write_text(
                json.dumps([{"role": "user", "content": "private"}]), encoding="utf-8"
            )
            bundle = Path(tmp) / "private-bundle.zip"
            source.export_private_bundle(bundle)
            tampered = Path(tmp) / "tampered.zip"
            with zipfile.ZipFile(bundle, "r") as original, zipfile.ZipFile(tampered, "w") as changed:
                for name in original.namelist():
                    data = original.read(name)
                    if name.startswith("participants/"):
                        data += b"tampered"
                    changed.writestr(name, data)
            target = PersistentCore(Path(tmp) / "target")
            with self.assertRaises(ValueError):
                target.import_private_bundle(tampered)
            self.assertFalse((target.workspace_path / "histories" / "participant_1.json").exists())


if __name__ == "__main__":
    unittest.main()
END ALLOWED

NOTE:
Private ZIP archives remain plaintext ZIP files in this patch. Encryption and
portable password-based key management are not implemented here. Rewriting
the latest diagnostic sample does not erase earlier Git history; inspect
history separately if any credential was ever committed and rotate it.
============================================================

EXPECTED-GIT-BLOB-SHA:main.py=3f8ca98d315c9646fb099afa4e9f685f6769a018
EXPECTED-GIT-BLOB-SHA:chat_workspace.py=41201f85eeb892be09dd22c8b838e0195ba0cc1b
EXPECTED-GIT-BLOB-SHA:yj64_persistent_core.py=3921e8e553a13c99ed999d258ad66b8705bfd471
EXPECTED-GIT-BLOB-SHA:buildozer.spec=9ae2a656d9b91c81e739a389a29c4d16c7c7c92f
EXPECTED-GIT-BLOB-SHA:diagnostics.py=e768f425255e72c9f9098d9f0816b558b7e81751
EXPECTED-GIT-BLOB-SHA:tests/test_diagnostics_privacy.py=1b0aac12ab641c879ef4d93d6e9513409a604599
EXPECTED-GIT-BLOB-SHA:reports/latest-report.jsonl=ca9f1540f21dfb93aac91ad791dc2840b2d3f233

FILE: tools/verify_guard.py BEGIN ALLOWED
SECTION_RE = re.compile(
    r"^FILE: (?P<path>[^\n]+?) BEGIN ALLOWED\n(?P<content>.*?)\nEND ALLOWED$",
    re.MULTILINE | re.DOTALL,
)
END ALLOWED
EXPECTED-GIT-BLOB-SHA:tools/verify_guard.py=05604885ec0babf25fa55ea6d5343b21c7f88a7d

============================================================
ФИНАЛЬНАЯ ОЧЕРЕДЬ РЕШЕНИЯ ЗАДАЧ
============================================================

СТАТУС: 7 ПОСЛЕДОВАТЕЛЬНЫХ ЭТАПОВ. АКТИВНЫХ ПАТЧЕЙ НЕТ.

Очередь содержит только незавершённую работу. Реализованные механизмы
не дублируются здесь. Переход к следующему этапу — после проверки
результата предыдущего. Запись в очереди не является разрешением
на изменение рабочих файлов.

ЭТАП 1. ПРОВЕРИТЬ ИСПРАВНОСТЬ СВЯЗИ «УЧАСТНИК — ЛИЧНЫЕ ДАННЫЕ»
Зависимость: нет; выполнить первым, до любых изменений архива.
- Проверить, как export_private_archives() сопоставляет имена файлов
  histories/*.json и runner у agents/*.json.
- Проверить canonical participant IDs, пользовательские отображаемые
  имена, пробелы/символы и варианты runner, отличные от Participant 1/2/3.
- Убедиться, что личные истории и private_messages не попадают в архив
  другого участника.
- Добавить тесты на корректные совпадения, несовпадения и конфликт имён.
Результат этапа: однозначное и протестированное правило группировки.

ЭТАП 2. ПРОВЕРИТЬ РЕАЛЬНУЮ КРИПТОГРАФИЮ В ANDROID-ПРИЛОЖЕНИИ
Зависимость: этап 1.
- Найти исходник класса
  org.blackmirror.blackmirror.PrivateArchiveCrypto и подтвердить,
  что он входит в Android APK.
- Проверить реализацию AES-256-GCM и PBKDF2-HMAC-SHA256, параметры
  соли/nonce/итераций и формат зашифрованного файла.
- Проверить encrypt/decrypt, неверную парольную фразу, повреждённый файл,
  пустой файл и очистку временного plaintext после ошибок.
- Добавить проверяемые тесты; не считать вызов Java-класса из main.py
  доказательством корректной криптографии.
Результат этапа: подтверждённая реализация и тесты шифрования/расшифрования.

ЭТАП 3. ЗАФИКСИРОВАТЬ ФИНАЛЬНЫЙ ФОРМАТ И ПОЛИТИКУ СОХРАНЕНИЯ
Зависимость: этапы 1–2.
- Определить, остаются ли личные архивы отдельными ZIP внутри
  зашифрованного bundle или требуется иной формат.
- Определить конечное место сохранения: единый каталог Download/YJ-64
  либо единый SAF-процесс выбора папки; не смешивать эти два поведения.
- Сохранить запрет на публикацию личных данных в открытом ZIP.
- Уточнить, какие файлы создаёт единая операция и как показываются
  частичный успех и ошибка каждого файла.
Результат этапа: согласованная спецификация экспорта и восстановления.

ЭТАП 4. ОБЪЕДИНИТЬ ЭКСПОРТ В ОДНУ ПОЛЬЗОВАТЕЛЬСКУЮ ОПЕРАЦИЮ
Зависимость: этапы 1–3.
- Сейчас общий архив и зашифрованный личный bundle запускаются
  разными действиями. Объединить их в один согласованный сценарий.
- Создавать общий архив и личный зашифрованный bundle в рамках одного
  запуска, не помещая личные данные в общий архив.
- Сохранять выбранным на этапе 3 способом; проверять запись и чтение
  сохранённых файлов обратно, размер и SHA-256.
- Отдельно показывать результат каждого артефакта; общий успех запрещён,
  если хотя бы один обязательный файл не сохранён или не проверен.
Результат этапа: один экспортный запуск с проверяемыми результатами.

ЭТАП 5. ЗАВЕРШИТЬ И ПРОВЕРИТЬ ВОССТАНОВЛЕНИЕ ЛИЧНЫХ АРХИВОВ
Зависимость: этапы 1–4.
- Отдельный выбор зашифрованного личного архива и запрос парольной фразы
  уже присутствуют в main.py; не переписывать их без необходимости.
- Проверить полный round-trip на устройстве: экспорт → сохранение →
  выбор файла → расшифрование → проверка bundle → восстановление.
- Проверить конфликт уже существующих историй, повторный импорт,
  несовпадающий participant ID, повреждение архива и неверный пароль.
- Убедиться, что общий ZIP никогда не принимается как личный bundle,
  и наоборот.
Результат этапа: безопасное и предсказуемое восстановление без потери
или смешивания данных участников.

ЭТАП 6. ПРОВЕРИТЬ И ЗАКРЕПИТЬ ПРАВА ДОСТУПА
Зависимость: этапы 1 и 5.
- Проверить построение запросов моделей: участник получает собственную
  личную историю и общий контекст; чужие private histories и private
  agent messages не передаются другим участникам или monitor.
- Определить и при необходимости добавить явные проверки requester /
  owner / participant / monitor для чтения и записи личных данных.
- Добавить регрессионные тесты на изоляцию участников и отсутствие
  утечки через общий контекст, экспорт, импорт и диагностику.
Результат этапа: проверяемая политика доступа, а не только разделение
данных по файлам.

ЭТАП 7. ПОЛНАЯ ПРОВЕРКА, GUARD, CI И APK
Зависимость: этапы 1–6.
- Выполнить unit/regression tests для общего и личного архивов,
  криптографии, сопоставления участников, восстановления и доступа.
- Провести Android runtime проверку на реальном устройстве: сохранение,
  чтение обратно, видимость файла, отмена, частичный сбой и повторный запуск.
- Обновить защищённые фрагменты и Git blob SHA только по фактическому
  содержимому рабочих файлов.
- Запустить Guard Validation и добиться PASS.
- Затем запустить CI и только после Guard PASS — Android APK build.
Результат этапа: проверенное состояние проекта и актуальный Guard.

ПРАВИЛО ВЕДЕНИЯ ОЧЕРЕДИ:
- Не переносить задачи из очереди на операционный стол автоматически.
- Перед каждым этапом определить точные файлы и фрагменты, показать
  владельцу план и получить согласование.
- После реализации удалить завершённую задачу из очереди и оставить
  краткую запись в implementation record.
- Не считать Android runtime или криптографию проверенными только
  на основании статического Python-кода.
- Сборку не запускать до успешной Guard Validation.

============================================================
