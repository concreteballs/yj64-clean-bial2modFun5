#!/usr/bin/env bash
set -eu

adb wait-for-device
mkdir -p emulator-test-artifacts

adb install -r "monitor-app/app/build/outputs/apk/debug/app-debug.apk"
adb install -r "bin/blackmirror-0.1.32-x86_64-debug.apk"

adb shell am force-stop org.blackmirror.yj64monitor
adb shell am force-stop org.blackmirror.blackmirror

echo "=== Launch Monitor ==="
adb shell monkey -p org.blackmirror.yj64monitor 1
sleep 3

echo "=== Launch YJ-64 Base ==="
adb shell monkey -p org.blackmirror.blackmirror 1
sleep 8

BASE_PID="$(adb shell pidof org.blackmirror.blackmirror | tr -d '\r')"
if [ -z "$BASE_PID" ]; then
  echo "ERROR: YJ-64 Base process is not running after launch." >&2
  exit 1
fi

adb exec-out screencap -p > emulator-test-artifacts/yj64-launch-screen.png
adb shell dumpsys activity activities > emulator-test-artifacts/activity-state.txt
adb shell dumpsys window > emulator-test-artifacts/window-state.txt

RECEIVED=0
for attempt in $(seq 1 60); do
  if adb exec-out run-as org.blackmirror.yj64monitor cat "files/yj64-reports/yj64-report.jsonl" 2>/dev/null | grep -q '"event":"self_diagnostic"'; then
    RECEIVED=1
    break
  fi
  sleep 2
done

adb exec-out run-as org.blackmirror.yj64monitor cat "files/yj64-reports/yj64-report.jsonl" > emulator-test-artifacts/monitor-report.jsonl 2>/dev/null || true
adb shell pidof org.blackmirror.blackmirror || true
adb shell pidof org.blackmirror.yj64monitor || true
adb logcat -d -t 5000 | grep -E "AndroidRuntime|Python|python|blackmirror|yj64|FATAL EXCEPTION" | tail -n 250 > emulator-test-artifacts/relevant-logcat.txt || true
cat emulator-test-artifacts/relevant-logcat.txt

if [ "$RECEIVED" -ne 1 ]; then
  echo "ERROR: Base diagnostic report did not reach Monitor through Content Provider IPC." >&2
  exit 1
fi

REPORT="$(cat emulator-test-artifacts/monitor-report.jsonl)"
echo "$REPORT" | grep -q '"event":"internal_startup"'
echo "$REPORT" | grep -q '"event":"internal_service_ready"'
echo "PASS: YJ-64 Base process launched and Monitor received IPC diagnostics."
